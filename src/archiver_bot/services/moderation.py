from __future__ import annotations

from datetime import timedelta

import discord
from discord.ext import commands

from archiver_bot.config.settings import BotSettings
from archiver_bot.services.audit import AuditLogService
from archiver_bot.services.state import StateService


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
        target = await self.bot.fetch_channel(self.settings.channels.bot_dm_thread)
        if not isinstance(target, discord.abc.Messageable):
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
            view=DMRelayView(self, message.author.id),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def block_dm_user(self, user_id: int) -> bool:
        return await self.state.block_dm_user(user_id)

    async def handle_no_chat_user(self, message: discord.Message) -> None:
        if not isinstance(message.author, discord.Member):
            return
        if not message.author.get_role(self.settings.roles.no_chat):
            return
        if any(role.id in self.settings.roles.staff for role in message.author.roles):
            return
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
        await self.audit.log(
            "No-chat user caught",
            f"User: {message.author.mention}\nChannel: {message.channel.jump_url}\nContent: {content}",
            colour=discord.Color.red(),
        )
        logs = self.bot.get_channel(self.settings.channels.log)
        if isinstance(logs, discord.abc.Messageable) and attachments:
            await logs.send(files=attachments)


class DMRelayView(discord.ui.View):
    def __init__(self, service: ModerationService, user_id: int):
        super().__init__(timeout=86400)
        self.service = service
        self.user_id = user_id

    @discord.ui.button(label="Block", style=discord.ButtonStyle.red)
    async def block_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        added = await self.service.block_dm_user(self.user_id)
        message = "User blocked." if added else "User was already blocked."
        await interaction.response.send_message(message, ephemeral=True)
