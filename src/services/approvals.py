from __future__ import annotations

import uuid
from pathlib import Path

import discord
from discord.ext import commands

from config.settings import BotSettings
from models.state import ApprovalType, PendingApproval
from services.audit import AuditLogService
from services.state import StateService
from services.time import is_expired, seconds_until, utc_after_iso, utc_now_iso


class ApprovalService:
    def __init__(
        self,
        bot: commands.Bot,
        settings: BotSettings,
        state: StateService,
        audit: AuditLogService,
    ):
        self.bot = bot
        self.settings = settings
        self.state = state
        self.audit = audit

    async def request(
        self,
        approval_type: ApprovalType,
        requester: discord.Member,
        *,
        target_channel_id: int | None = None,
        target_message_id: int | None = None,
        target_thread_id: int | None = None,
        proposed_title: str | None = None,
        description: str,
    ) -> PendingApproval:
        approval = PendingApproval(
            approval_id=uuid.uuid4().hex,
            type=approval_type,
            requester_id=requester.id,
            status="pending",
            created_at=utc_now_iso(),
            expires_at=utc_after_iso(self.settings.approval_timeout_seconds),
            target_channel_id=target_channel_id,
            target_message_id=target_message_id,
            target_thread_id=target_thread_id,
            proposed_title=proposed_title,
        )
        channel = self.bot.get_channel(self.settings.channels.archiver_chat)
        if channel is None:
            channel = await self.bot.fetch_channel(self.settings.channels.archiver_chat)
        if isinstance(channel, discord.abc.Messageable):
            view = ApprovalView(self, approval.approval_id)
            message = await channel.send(
                embed=discord.Embed(title="Approval request", description=description),
                view=view,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            approval.approval_message_id = message.id
            approval.approval_channel_id = getattr(message.channel, "id", None)
        else:
            raise RuntimeError("Approval channel is not messageable.")
        await self.state.put_approval(approval)
        return approval

    async def approve(self, interaction: discord.Interaction, approval_id: str) -> None:
        approval = await self._get_pending(interaction, approval_id)
        if approval is None:
            return
        if interaction.user.id == approval.requester_id:
            await interaction.response.send_message("You cannot approve your own request.", ephemeral=True)
            return
        if not self._has_approver_role(interaction.user):
            await interaction.response.send_message("You do not have approval permissions.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        result_details = ""
        try:
            if approval.type == "delete_message":
                result_details = await self._delete_message(approval)
            elif approval.type == "delete_thread":
                result_details = await self._delete_thread(approval)
            elif approval.type == "edit_thread_title":
                result_details = await self._edit_thread_title(approval)
        except Exception as exc:
            await self.audit.log("Approval failed", str(exc), colour=discord.Color.red())
            await self.state.update_approval(approval)
            await interaction.followup.send(f"Approval failed: {exc}", ephemeral=True)
            return

        approval.status = "approved"
        approval.approver_id = interaction.user.id
        log = await self.audit.log(
            "Approval completed",
            (
                f"Type: {approval.type}\n"
                f"Requester: <@{approval.requester_id}>\n"
                f"Approver: {interaction.user.mention}"
                f"{result_details}"
            ),
            colour=discord.Color.green(),
        )
        approval.result_log_url = log.jump_url if log else None
        await self.state.remove_approval(approval.approval_id)
        try:
            if interaction.message is None:
                await interaction.followup.send("Approved.", ephemeral=True)
                return
            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=discord.Embed(title="Approved", description="Request approved."),
                view=None,
            )
        except discord.HTTPException as exc:
            await self.audit.log("Approval message update failed", str(exc), colour=discord.Color.orange())
        await interaction.followup.send("Approved.", ephemeral=True)

    async def reject(self, interaction: discord.Interaction, approval_id: str) -> None:
        approval = await self._get_pending(interaction, approval_id)
        if approval is None:
            return
        if not self._has_approver_role(interaction.user):
            await interaction.response.send_message("You do not have approval permissions.", ephemeral=True)
            return
        approval.status = "rejected"
        approval.approver_id = interaction.user.id
        await self.state.remove_approval(approval.approval_id)
        await interaction.response.edit_message(
            embed=discord.Embed(title="Rejected", description="Request rejected."),
            view=None,
        )

    async def restore_pending_views(self) -> None:
        bot_state = await self.state.get()
        for approval in bot_state.pending_approvals.values():
            if approval.status != "pending" or approval.approval_channel_id is None:
                continue
            if is_expired(approval.expires_at):
                approval.status = "expired"
                await self.state.remove_approval(approval.approval_id)
                await self._mark_approval_message(
                    approval,
                    discord.Embed(title="Timed Out", description="Request expired."),
                )
                continue
            channel = self.bot.get_channel(approval.approval_channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(approval.approval_channel_id)
                except discord.HTTPException:
                    continue
            if not isinstance(channel, discord.TextChannel | discord.Thread):
                continue
            if approval.approval_message_id is None:
                continue
            try:
                message = await channel.fetch_message(approval.approval_message_id)
                await message.edit(view=ApprovalView(self, approval.approval_id, timeout=seconds_until(approval.expires_at)))
            except discord.HTTPException:
                continue

    async def _get_pending(
        self, interaction: discord.Interaction, approval_id: str
    ) -> PendingApproval | None:
        approval = (await self.state.get()).pending_approvals.get(approval_id)
        if approval is None or approval.status != "pending":
            await interaction.response.send_message("This approval is no longer pending.", ephemeral=True)
            return None
        if is_expired(approval.expires_at):
            approval.status = "expired"
            await self.state.remove_approval(approval.approval_id)
            await self._mark_approval_message(
                approval,
                discord.Embed(title="Timed Out", description="Request expired."),
            )
            await interaction.response.send_message("This approval has expired.", ephemeral=True)
            return None
        return approval

    async def expire(self, approval_id: str) -> None:
        approval = (await self.state.get()).pending_approvals.get(approval_id)
        if approval is None or approval.status != "pending":
            return
        approval.status = "expired"
        await self.state.remove_approval(approval.approval_id)
        await self._mark_approval_message(
            approval,
            discord.Embed(title="Timed Out", description="Request expired."),
        )

    async def _mark_approval_message(
        self,
        approval: PendingApproval,
        embed: discord.Embed,
    ) -> None:
        if approval.approval_channel_id is None or approval.approval_message_id is None:
            return
        channel = self.bot.get_channel(approval.approval_channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(approval.approval_channel_id)
            except discord.HTTPException:
                return
        if not isinstance(channel, discord.TextChannel | discord.Thread):
            return
        try:
            message = await channel.fetch_message(approval.approval_message_id)
            await message.edit(embed=embed, view=None)
        except discord.HTTPException:
            return

    def _has_approver_role(self, user: discord.abc.User) -> bool:
        roles = getattr(user, "roles", [])
        return any(role.id in self.settings.roles.higher for role in roles)

    async def _delete_message(self, approval: PendingApproval) -> str:
        if approval.target_channel_id is None or approval.target_message_id is None:
            raise ValueError("delete_message approval is missing target IDs")
        channel = await self.bot.fetch_channel(approval.target_channel_id)
        if not isinstance(channel, discord.TextChannel | discord.Thread):
            raise ValueError("delete_message approval target is not a message channel")
        message = await channel.fetch_message(approval.target_message_id)
        message_content = message.content
        if message.embeds:
            first_embed = message.embeds[0]
            if first_embed.title:
                message_content += f"\nTitle: {first_embed.title}"
            if first_embed.description:
                message_content += f"\nDescription: {first_embed.description}"
        await message.delete()
        return f"\nMessage: {message.jump_url}\nContent: {message_content[:1500]}"

    async def _delete_thread(self, approval: PendingApproval) -> str:
        if approval.target_thread_id is None:
            raise ValueError("delete_thread approval is missing target thread ID")
        thread = await self.bot.fetch_channel(approval.target_thread_id)
        if not isinstance(thread, discord.Thread):
            raise ValueError("delete_thread approval target is not a thread")
        details = f"\nThread: {thread.name}\nIn: {thread.parent.jump_url if thread.parent else ''}"
        for parsed_file in (
            self.settings.data_dir / "parsed" / f"{thread.id}.json",
            Path("parsed") / f"{thread.id}.json",
        ):
            try:
                parsed_file.unlink(missing_ok=True)
            except OSError:
                await self.audit.log(
                    "Parsed file cleanup failed",
                    f"Could not remove {parsed_file}.",
                    colour=discord.Color.orange(),
                )
        await thread.delete()
        return details

    async def _edit_thread_title(self, approval: PendingApproval) -> str:
        if approval.target_thread_id is None or approval.proposed_title is None:
            raise ValueError("edit_thread_title approval is missing target data")
        thread = await self.bot.fetch_channel(approval.target_thread_id)
        if not isinstance(thread, discord.Thread):
            raise ValueError("edit_thread_title approval target is not a thread")
        old_name = thread.name
        await thread.edit(name=approval.proposed_title, archived=False)
        return f"\nThread: {thread.jump_url}\nFrom: {old_name}\nTo: {approval.proposed_title}"


class ApprovalView(discord.ui.View):
    def __init__(self, service: ApprovalService, approval_id: str, timeout: float | None = None):
        super().__init__(timeout=timeout or service.settings.approval_timeout_seconds)
        self.service = service
        self.approval_id = approval_id

    async def on_timeout(self) -> None:
        await self.service.expire(self.approval_id)

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green)
    async def approve_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        await self.service.approve(interaction, self.approval_id)

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.red)
    async def reject_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        await self.service.reject(interaction, self.approval_id)
