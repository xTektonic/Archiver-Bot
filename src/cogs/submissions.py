from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from app import ArchiverBot
from services.checks import has_higher_role
from services.safe_discord import defer


class SubmissionsCog(commands.Cog):
    def __init__(self, bot: ArchiverBot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread) -> None:
        if thread.parent_id == self.bot.settings.channels.submissions and thread.name != "Test":
            await self.bot.services.tracker.track_thread(thread)

    @commands.Cog.listener()
    async def on_thread_update(self, before: discord.Thread, after: discord.Thread) -> None:
        before_tags = {tag.id for tag in before.applied_tags}
        after_tags = {tag.id for tag in after.applied_tags}
        added = after_tags - before_tags
        if before.parent_id == self.bot.settings.channels.submissions:
            if before_tags != after_tags:
                await self.bot.services.tracker.reconcile_submission(after)
            elif before.name != after.name:
                await self.bot.services.tracker.update_status(after, "unknown")
        if before.parent_id in self.bot.settings.channels.managed_forums and added:
            await self._announce_added_tags(after, added)

    @app_commands.command(name="tracker_list", description="Rebuild the submission tracker summary")
    @app_commands.check(has_higher_role)
    async def tracker_list(self, interaction: discord.Interaction) -> None:
        await defer(interaction)
        await self.bot.services.tracker.rebuild_summary()
        await interaction.followup.send("Tracker list rebuilt.", ephemeral=True)

    @app_commands.command(name="track", description="Add the current submission post to the tracker")
    @app_commands.check(has_higher_role)
    async def track(self, interaction: discord.Interaction) -> None:
        await defer(interaction)
        if (
            isinstance(interaction.channel, discord.Thread)
            and interaction.channel.parent_id == self.bot.settings.channels.submissions
        ):
            await self.bot.services.tracker.track_thread(interaction.channel)
            await interaction.followup.send("Post tracked.", ephemeral=True)
        else:
            await interaction.followup.send("The current thread is not a submission post.", ephemeral=True)

    async def _announce_added_tags(self, thread: discord.Thread, tag_ids: set[int]) -> None:
        tags = [tag for tag in thread.applied_tags if tag.id in tag_ids]
        if not tags:
            return
        tag_names = [f"{tag.emoji or ''} {tag.name}".strip() for tag in tags]
        colour = self._tag_colour(tags[-1])
        try:
            await thread.send(
                embed=discord.Embed(
                    title=f"Marked as {',  '.join(tag_names)}",
                    color=colour,
                ),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            await self.bot.services.audit.log(
                "Tag announcement failed",
                f"Could not announce tag update in {thread.jump_url}.",
                colour=discord.Color.red(),
            )

    def _tag_colour(self, tag: discord.ForumTag) -> discord.Color:
        name = tag.name.lower()
        if name in {"accepted", "solved"}:
            return discord.Color.green()
        if name == "rejected":
            return discord.Color.red()
        if name == "archived":
            return discord.Color.dark_blue()
        return discord.Color.light_gray()


async def setup(bot: ArchiverBot) -> None:
    await bot.add_cog(SubmissionsCog(bot))
