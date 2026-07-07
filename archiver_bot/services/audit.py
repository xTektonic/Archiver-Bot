from __future__ import annotations

import discord
from discord.ext import commands

from archiver_bot.config.settings import BotSettings


class AuditLogService:
    def __init__(self, bot: commands.Bot, settings: BotSettings):
        self.bot = bot
        self.settings = settings

    async def log(
        self,
        title: str,
        message: str = "",
        *,
        colour: discord.Color | None = None,
    ) -> discord.Message | None:
        channel = self.bot.get_channel(self.settings.channels.log)
        if not isinstance(channel, discord.abc.Messageable):
            return None
        embed = discord.Embed(title=title, description=message, color=colour or discord.Color.default())
        return await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    async def log_embed(self, embed: discord.Embed) -> discord.Message | None:
        channel = self.bot.get_channel(self.settings.channels.log)
        if not isinstance(channel, discord.abc.Messageable):
            return None
        return await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
