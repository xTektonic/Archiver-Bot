from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from app import ArchiverBot
from services.checks import has_higher_role
from services.safe_discord import defer


class ParserCog(commands.Cog):
    def __init__(self, bot: ArchiverBot):
        self.bot = bot

    @app_commands.command(name="parse_post", description="Parse one archive post")
    @app_commands.check(has_higher_role)
    async def parse_post(self, interaction: discord.Interaction, thread: discord.Thread) -> None:
        if not self._is_archive_thread(thread):
            await interaction.response.send_message(
                "That is not an archive thread, it cannot be parsed.",
                ephemeral=True,
            )
            return
        await defer(interaction)
        result = await self.bot.services.parser.parse_thread(thread)
        await interaction.followup.send(self._format_result(result.total, result.errors), ephemeral=True)

    @app_commands.command(name="parse_channel", description="Parse all posts in one archive forum")
    @app_commands.check(has_higher_role)
    async def parse_channel(
        self, interaction: discord.Interaction, channel: discord.ForumChannel
    ) -> None:
        if not self._is_archive_forum(channel):
            await interaction.response.send_message(
                "That is not an archive channel, it cannot be parsed.",
                ephemeral=True,
            )
            return
        await defer(interaction, ephemeral=False)
        result = await self.bot.services.parser.parse_channel(channel)
        await interaction.followup.send(self._format_result(result.total, result.errors))

    @app_commands.command(name="parse_archive", description="Parse all configured archive forums")
    @app_commands.check(has_higher_role)
    async def parse_archive(self, interaction: discord.Interaction) -> None:
        await defer(interaction, ephemeral=False)
        result = await self.bot.services.parser.parse_archive(interaction.guild)
        await interaction.followup.send(self._format_result(result.total, result.errors))

    def _format_result(self, total: int, errors: list) -> str:
        if not errors:
            return f"Parsed {total} post(s) successfully."
        sample = "\n".join(f"- {error.thread_name}: {error.error}" for error in errors[:5])
        return f"Parsed {total} post(s). Errors: {len(errors)}.\n{sample}"

    def _is_archive_thread(self, thread: discord.Thread) -> bool:
        return bool(
            isinstance(thread.parent, discord.ForumChannel)
            and self._is_archive_forum(thread.parent)
        )

    def _is_archive_forum(self, channel: discord.ForumChannel) -> bool:
        return channel.category_id not in self.bot.settings.categories.non_archive


async def setup(bot: ArchiverBot) -> None:
    await bot.add_cog(ParserCog(bot))
