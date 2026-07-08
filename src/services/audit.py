from __future__ import annotations

import difflib

import discord
from discord.ext import commands

from config.settings import BotSettings


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


def diff_block(old_text: str | None, new_text: str | None, *, limit: int = 950) -> str | None:
    old = str(old_text or "")
    new = str(new_text or "")
    if old == new:
        return None

    lines = list(
        difflib.unified_diff(
            old.splitlines(),
            new.splitlines(),
            n=1,
            lineterm="",
        )
    )[2:]
    formatted_lines: list[str] = []
    current_len = 0
    for line in lines:
        if line.startswith("+"):
            formatted = f"\u001b[0;32m{line}\u001b[0m"
        elif line.startswith("-"):
            formatted = f"\u001b[0;31m{line}\u001b[0m"
        elif line.startswith("@@"):
            formatted = f"\u001b[0;34m{line}\u001b[0m"
        else:
            formatted = line

        if current_len + len(formatted) > limit:
            formatted_lines.append("\u001b[0;33m... [Truncated for length]\u001b[0m")
            break
        formatted_lines.append(formatted)
        current_len += len(formatted) + 1
    return "\n".join(formatted_lines)
