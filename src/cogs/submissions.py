from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from app import ArchiverBot
from services.checks import has_higher_role
from services.safe_discord import defer, respond


class SubmissionsCog(commands.Cog):
    def __init__(self, bot: ArchiverBot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread) -> None:
        if thread.parent_id == self.bot.settings.channels.submissions and thread.name != "Test":
            await self.bot.services.tracker.track_thread(thread)

    @commands.Cog.listener()
    async def on_thread_update(self, before: discord.Thread, after: discord.Thread) -> None:
        if before.parent_id != self.bot.settings.channels.submissions:
            return
        before_tags = {tag.id for tag in before.applied_tags}
        after_tags = {tag.id for tag in after.applied_tags}
        added = after_tags - before_tags
        if self.bot.settings.tags.accepted in added:
            await self.bot.services.tracker.update_status(after, "accepted")
        elif self.bot.settings.tags.archived in added:
            await self.bot.services.tracker.update_status(after, "archived")
        elif self.bot.settings.tags.rejected in added:
            await self.bot.services.tracker.update_status(after, "rejected")
        elif before.name != after.name:
            await self.bot.services.tracker.update_status(after, "unknown")

    @app_commands.command(name="tracker_list", description="Rebuild the submission tracker summary")
    @app_commands.check(has_higher_role)
    async def tracker_list(self, interaction: discord.Interaction) -> None:
        await defer(interaction)
        await self.bot.services.tracker.rebuild_summary()
        await interaction.followup.send("Tracker list rebuilt.", ephemeral=True)

    @app_commands.command(name="track", description="Add the current submission post to the tracker")
    @app_commands.check(has_higher_role)
    async def track(self, interaction: discord.Interaction) -> None:
        if (
            isinstance(interaction.channel, discord.Thread)
            and interaction.channel.parent_id == self.bot.settings.channels.submissions
        ):
            await self.bot.services.tracker.track_thread(interaction.channel)
            await respond(interaction, "Post tracked.")
        else:
            await respond(interaction, "The current thread is not a submission post.")


async def setup(bot: ArchiverBot) -> None:
    await bot.add_cog(SubmissionsCog(bot))
