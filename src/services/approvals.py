from __future__ import annotations

import uuid
from pathlib import Path

import discord
from discord.ext import commands

from config.settings import BotSettings
from models.state import ApprovalType, PendingApproval
from services.audit import AuditLogService
from services.state import StateService
from services.time import is_expired, utc_after_iso, utc_now_iso


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
        try:
            if approval.type == "delete_message":
                await self._delete_message(approval)
            elif approval.type == "delete_thread":
                await self._delete_thread(approval)
            elif approval.type == "edit_thread_title":
                await self._edit_thread_title(approval)
            approval.status = "approved"
            approval.approver_id = interaction.user.id
            log = await self.audit.log(
                "Approval completed",
                f"Type: {approval.type}\nRequester: <@{approval.requester_id}>\nApprover: {interaction.user.mention}",
                colour=discord.Color.green(),
            )
            approval.result_log_url = log.jump_url if log else None
            await self.state.update_approval(approval)
            if interaction.message is None:
                raise RuntimeError("Approval interaction is missing its message.")
            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=discord.Embed(title="Approved", description="Request approved."),
                view=None,
            )
            await interaction.followup.send("Approved.", ephemeral=True)
        except Exception as exc:
            approval.status = "failed"
            await self.state.update_approval(approval)
            await self.audit.log("Approval failed", str(exc), colour=discord.Color.red())
            await interaction.followup.send(f"Approval failed: {exc}", ephemeral=True)

    async def reject(self, interaction: discord.Interaction, approval_id: str) -> None:
        approval = await self._get_pending(interaction, approval_id)
        if approval is None:
            return
        if not self._has_approver_role(interaction.user):
            await interaction.response.send_message("You do not have approval permissions.", ephemeral=True)
            return
        approval.status = "rejected"
        approval.approver_id = interaction.user.id
        await self.state.update_approval(approval)
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
                await self.state.update_approval(approval)
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
                await message.edit(view=ApprovalView(self, approval.approval_id))
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
            await self.state.update_approval(approval)
            await interaction.response.send_message("This approval has expired.", ephemeral=True)
            return None
        return approval

    def _has_approver_role(self, user: discord.abc.User) -> bool:
        roles = getattr(user, "roles", [])
        return any(role.id in self.settings.roles.higher for role in roles)

    async def _delete_message(self, approval: PendingApproval) -> None:
        if approval.target_channel_id is None or approval.target_message_id is None:
            raise ValueError("delete_message approval is missing target IDs")
        channel = await self.bot.fetch_channel(approval.target_channel_id)
        if not isinstance(channel, discord.TextChannel | discord.Thread):
            raise ValueError("delete_message approval target is not a message channel")
        message = await channel.fetch_message(approval.target_message_id)
        await message.delete()

    async def _delete_thread(self, approval: PendingApproval) -> None:
        if approval.target_thread_id is None:
            raise ValueError("delete_thread approval is missing target thread ID")
        thread = await self.bot.fetch_channel(approval.target_thread_id)
        if not isinstance(thread, discord.Thread):
            raise ValueError("delete_thread approval target is not a thread")
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

    async def _edit_thread_title(self, approval: PendingApproval) -> None:
        if approval.target_thread_id is None or approval.proposed_title is None:
            raise ValueError("edit_thread_title approval is missing target data")
        thread = await self.bot.fetch_channel(approval.target_thread_id)
        if not isinstance(thread, discord.Thread):
            raise ValueError("edit_thread_title approval target is not a thread")
        await thread.edit(name=approval.proposed_title, archived=False)


class ApprovalView(discord.ui.View):
    def __init__(self, service: ApprovalService, approval_id: str):
        super().__init__(timeout=None)
        self.service = service
        self.approval_id = approval_id

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
