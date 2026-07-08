from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

import discord
from discord.ext import commands
from discord.utils import snowflake_time

from config.settings import BotSettings


@dataclass
class JobResult:
    name: str
    dry_run: bool
    changed: int = 0
    messages: list[str] = field(default_factory=list)


class MaintenanceJobService:
    def __init__(self, bot: commands.Bot, settings: BotSettings):
        self.bot = bot
        self.settings = settings

    async def close_resolved(self, guild: discord.Guild, *, dry_run: bool) -> JobResult:
        result = JobResult("close_resolved", dry_run)
        resolved_names = {"solved", "rejected", "archived", "inactive", "off-topic"}
        for channel in guild.channels:
            if not isinstance(channel, discord.ForumChannel):
                continue
            for thread in channel.threads:
                if thread.archived or thread.flags.pinned:
                    continue
                if any(tag.name.lower() in resolved_names for tag in thread.applied_tags):
                    result.changed += 1
                    result.messages.append(f"{thread.name} in {channel.name}")
                    if not dry_run:
                        await thread.edit(archived=True)
        return result

    async def open_archived(self, guild: discord.Guild, *, dry_run: bool) -> JobResult:
        result = JobResult("open_archived", dry_run)
        seen: set[int] = set()
        for channel in guild.channels:
            if not isinstance(channel, discord.ForumChannel):
                continue
            if channel.category_id in self.settings.categories.non_archive:
                continue
            await self._open_archived_threads(channel, result, dry_run=dry_run, seen=seen)

        faq_channel = self.bot.get_channel(self.settings.channels.faq)
        if isinstance(faq_channel, discord.ForumChannel):
            await self._open_archived_threads(faq_channel, result, dry_run=dry_run, seen=seen)

        for channel_id in self.settings.channels.managed_forums:
            managed_channel = self.bot.get_channel(channel_id)
            if not isinstance(managed_channel, discord.ForumChannel):
                continue
            await self._open_archived_threads(
                managed_channel,
                result,
                dry_run=dry_run,
                seen=seen,
                required_tags=self.settings.tags.pending,
            )
        return result

    async def _open_archived_threads(
        self,
        channel: discord.ForumChannel,
        result: JobResult,
        *,
        dry_run: bool,
        seen: set[int],
        required_tags: set[int] | None = None,
    ) -> None:
        async for thread in channel.archived_threads(limit=None):
            if thread.id in seen:
                continue
            seen.add(thread.id)
            if not thread.archived or thread.flags.pinned:
                continue
            if required_tags is not None and not any(
                tag.id in required_tags for tag in thread.applied_tags
            ):
                continue
            result.changed += 1
            result.messages.append(f"{thread.name} in {channel.name}")
            if not dry_run:
                await thread.edit(archived=False)

    async def mark_inactive_help(self, *, dry_run: bool) -> JobResult:
        result = JobResult("mark_inactive_help", dry_run)
        channel = self.bot.get_channel(self.settings.channels.help_forum)
        if not isinstance(channel, discord.ForumChannel):
            return result
        inactive_tag = channel.get_tag(self.settings.tags.inactive)
        if inactive_tag is None:
            return result
        now = discord.utils.utcnow()
        for thread in channel.threads:
            if not any(tag.id == self.settings.tags.unsolved for tag in thread.applied_tags):
                continue
            last_activity = snowflake_time(thread.last_message_id) if thread.last_message_id else thread.created_at
            if last_activity is None:
                continue
            if now - last_activity > timedelta(weeks=1):
                result.changed += 1
                result.messages.append(f"Marked inactive: {thread.name}")
                if not dry_run:
                    await thread.edit(archived=True, applied_tags=[inactive_tag])
                continue
            if now - last_activity > timedelta(days=3):
                last_message = thread.last_message
                if last_message is None and thread.last_message_id is not None:
                    try:
                        last_message = await thread.fetch_message(thread.last_message_id)
                    except discord.HTTPException:
                        last_message = None
                if last_message is not None and last_message.author != self.bot.user:
                    result.changed += 1
                    result.messages.append(f"Reminder sent: {thread.name}")
                    if not dry_run:
                        owner = thread.owner.mention if thread.owner else "Was this help request solved?"
                        await thread.send(
                            f"{owner} was this help request solved?\n"
                            "If so please make sure to mark it as solved using `/tag_selector`",
                            allowed_mentions=discord.AllowedMentions(users=True),
                        )
        return result

    async def lock_resolved_submissions(self, *, dry_run: bool) -> JobResult:
        result = JobResult("lock_resolved_submissions", dry_run)
        channel = self.bot.get_channel(self.settings.channels.submissions)
        if not isinstance(channel, discord.ForumChannel):
            return result
        for thread in channel.threads:
            if not any(tag.id in self.settings.tags.resolved for tag in thread.applied_tags):
                continue
            if thread.locked:
                continue
            last_activity = snowflake_time(thread.last_message_id) if thread.last_message_id else thread.created_at
            if last_activity is None:
                continue
            if discord.utils.utcnow() - last_activity <= timedelta(days=1):
                continue
            result.changed += 1
            if not dry_run:
                await thread.edit(archived=False, locked=True)
                await thread.edit(archived=True)
        return result
