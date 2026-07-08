from __future__ import annotations

from datetime import timedelta

import discord
from discord.ext import commands

from config.settings import BotSettings
from services.audit import AuditLogService
from services.state import StateService


class ModerationService:
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

    async def forward_dm(self, message: discord.Message) -> None:
        if await self.state.is_dm_blocked(message.author.id):
            return
        try:
            target = await self.bot.fetch_channel(self.settings.channels.bot_dm_thread)
            if not isinstance(target, discord.abc.Messageable):
                await self.audit.log("Error forwarding DM", "DM relay target is not messageable.")
                return
            embed = discord.Embed(
                title="DM received",
                description=f"From: {message.author} {message.author.mention}\n\n{message.content}",
                color=discord.Color.dark_gold(),
            )
            embed.set_thumbnail(url=message.author.display_avatar.url)
            files = [await attachment.to_file() for attachment in message.attachments]
            await target.send(
                embed=embed,
                files=files,
                view=DMRelayView(self, message),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except Exception as exc:
            await self.audit.log(
                "Error forwarding DM",
                f"From: {message.author} {message.author.mention}\nError: {exc}",
                colour=discord.Color.red(),
            )

    async def block_dm_user(self, user_id: int) -> bool:
        return await self.state.block_dm_user(user_id)

    async def reply_to_dm(self, original: discord.Message, content: str) -> None:
        await original.channel.send(content)
        await self.audit.log(
            "DM sent",
            f"To: {original.author} {original.author.mention}\n\n{content}",
        )

    async def handle_no_chat_user(self, message: discord.Message) -> bool:
        if not isinstance(message.author, discord.Member):
            return False
        if not message.author.get_role(self.settings.roles.no_chat):
            return False
        if any(role.id in self.settings.roles.staff for role in message.author.roles):
            return False
        try:
            attachments = [await attachment.to_file() for attachment in message.attachments]
            content = message.content
            await message.delete()
            try:
                until = discord.utils.utcnow() + timedelta(seconds=20)
                await message.author.timeout(until, reason="No-chat user caught")
            except discord.Forbidden:
                await self.audit.log("Timeout failed", f"Could not timeout {message.author.mention}.")
            warn = discord.Embed(
                title="Message blocked",
                description=self.settings.copy.no_chat_timeout_message,
                color=discord.Color.red(),
            )
            warn.set_image(url=self.settings.copy.no_chat_image)
            try:
                await message.author.send(embed=warn)
            except discord.Forbidden:
                pass
            await message.channel.send(
                content=message.author.mention,
                embed=warn,
                delete_after=20,
                allowed_mentions=discord.AllowedMentions(users=True),
            )
            logs = self.bot.get_channel(self.settings.channels.log)
            if isinstance(logs, discord.abc.Messageable):
                await logs.send(
                    embed=discord.Embed(
                        title="No-chat user caught",
                        description=(
                            f"User: {message.author.mention}\n"
                            f"Channel: {message.channel.jump_url}\n"
                            f"Content: {content}"
                        ),
                        colour=discord.Color.red(),
                    ),
                    files=attachments,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            else:
                await self.audit.log(
                    "No-chat user caught",
                    f"User: {message.author.mention}\nChannel: {message.channel.jump_url}\nContent: {content}",
                    colour=discord.Color.red(),
                )
        except Exception as exc:
            await self.audit.log(
                "Error in no-chat filter",
                f"User: {message.author.mention}\nChannel: {message.channel.jump_url}\nError: {exc}",
                colour=discord.Color.red(),
            )
        return True


class DMReplyModal(discord.ui.Modal, title="Reply to DM"):
    def __init__(self, service: ModerationService, original: discord.Message):
        super().__init__()
        self.service = service
        self.original = original
        self.message: discord.ui.TextInput[DMReplyModal] = discord.ui.TextInput(
            label="Message content",
            style=discord.TextStyle.long,
            required=True,
        )
        self.add_item(self.message)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.service.reply_to_dm(self.original, self.message.value)
        await interaction.response.send_message("DM sent.", ephemeral=True)


class DMRelayView(discord.ui.View):
    def __init__(self, service: ModerationService, original: discord.Message):
        super().__init__(timeout=86400)
        self.service = service
        self.original = original

    @discord.ui.button(label="Reply", style=discord.ButtonStyle.blurple)
    async def reply_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(DMReplyModal(self.service, self.original))

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.red)
    async def delete_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        if interaction.message is not None:
            await interaction.message.delete()

    @discord.ui.button(label="Block", style=discord.ButtonStyle.red)
    async def block_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        added = await self.service.block_dm_user(self.original.author.id)
        message = "User blocked." if added else "User was already blocked."
        await interaction.response.send_message(message, ephemeral=True)
