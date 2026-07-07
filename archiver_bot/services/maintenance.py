from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

import discord
from discord.ext import commands
from discord.utils import snowflake_time

from archiver_bot.config.settings import BotSettings


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
        for channel in guild.channels:
            if not isinstance(channel, discord.ForumChannel):
                continue
            if channel.category_id in self.settings.categories.non_archive:
                continue
            async for thread in channel.archived_threads(limit=None):
                if thread.archived and not thread.flags.pinned:
                    result.changed += 1
                    if not dry_run:
                        await thread.edit(archived=False)
        return result

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
            if now - last_activity > timedelta(weeks=1):
                result.changed += 1
                if not dry_run:
                    await thread.edit(archived=True, applied_tags=[inactive_tag])
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
            result.changed += 1
            if not dry_run:
                await thread.edit(archived=False, locked=True)
                await thread.edit(archived=True)
        return result
