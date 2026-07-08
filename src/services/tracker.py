from __future__ import annotations

import re

import discord
from discord.ext import commands

from config.settings import BotSettings
from models.state import SubmissionStatus, TrackedSubmission
from services.audit import AuditLogService
from services.state import StateService
from services.time import utc_now_iso


class SubmissionTrackerService:
    VOTE_EMOJIS = ("❌", "🔴", "🟢", "✅")
    TESTING_EMOJI = "🧪"

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

    async def track_thread(self, thread: discord.Thread) -> TrackedSubmission | None:
        tracker_channel = self.bot.get_channel(self.settings.channels.submissions_tracker)
        if not isinstance(tracker_channel, discord.TextChannel):
            await self.audit.log("Tracker unavailable", "Submission tracker channel was not found.")
            return None

        discussion = await tracker_channel.create_thread(
            name=thread.name,
            type=discord.ChannelType.public_thread,
        )
        system_message = tracker_channel.get_partial_message(discussion.id)
        try:
            await system_message.delete()
        except discord.HTTPException:
            pass
        await discussion.send(
            f"For discussion and debate regarding the archival status of {thread.jump_url}",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        ping = await discussion.send(f"<@&{self.settings.roles.archiver}> chat away!")
        await ping.pin()
        tracker_message = await tracker_channel.send(
            f"## [{thread.name}]({thread.jump_url})\n{discussion.jump_url}",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        for emoji in self.VOTE_EMOJIS:
            try:
                await tracker_message.add_reaction(emoji)
            except discord.HTTPException:
                await self.audit.log("Tracker reaction failed", f"Could not add {emoji}.")

        now = utc_now_iso()
        record = TrackedSubmission(
            submission_thread_id=thread.id,
            title=thread.name,
            status="pending",
            tracker_message_id=tracker_message.id,
            tracker_thread_id=discussion.id,
            created_at=now,
            updated_at=now,
        )
        await self.state.upsert_submission(record)
        await self.rebuild_summary()
        await self.audit.log("Submission tracked", f"{thread.name}\n{thread.jump_url}")
        return record

    async def update_status(self, thread: discord.Thread, status: SubmissionStatus) -> None:
        bot_state = await self.state.get()
        existing = bot_state.tracked_submissions.get(str(thread.id))
        now = utc_now_iso()
        if existing is None:
            existing = TrackedSubmission(
                submission_thread_id=thread.id,
                title=thread.name,
                status=status,
                tracker_message_id=None,
                tracker_thread_id=None,
                created_at=now,
                updated_at=now,
            )
        else:
            previous_title = existing.title
            existing.title = thread.name
            if status != "unknown":
                existing.status = status
            existing.updated_at = now
            if previous_title != thread.name:
                await self._sync_tracker_title(existing, thread)
        await self.state.upsert_submission(existing)
        if status in {"accepted", "archived", "rejected"}:
            await self._finalize_tracker_message(existing)
        await self.rebuild_summary()

    async def _sync_tracker_title(
        self, record: TrackedSubmission, thread: discord.Thread
    ) -> None:
        if record.tracker_message_id is None:
            return
        tracker_channel = self.bot.get_channel(self.settings.channels.submissions_tracker)
        if not isinstance(tracker_channel, discord.TextChannel):
            return
        try:
            tracker_message = await tracker_channel.fetch_message(record.tracker_message_id)
        except discord.HTTPException:
            return

        discussion_url = ""
        discussion = await self._fetch_tracker_discussion(record.tracker_thread_id)
        if discussion is not None:
            discussion_url = discussion.jump_url
            try:
                await discussion.edit(name=thread.name)
            except discord.HTTPException:
                await self.audit.log(
                    "Tracker discussion rename failed",
                    f"Could not rename discussion thread for {thread.jump_url}.",
                )
        content = f"## [{thread.name}]({thread.jump_url})"
        if discussion_url:
            content += f"\n{discussion_url}"
        try:
            await tracker_message.edit(
                content=content,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            await self.audit.log(
                "Tracker message rename failed",
                f"Could not rename tracker message for {thread.jump_url}.",
            )

    async def rebuild_summary(self) -> None:
        tracker_channel = self.bot.get_channel(self.settings.channels.submissions_tracker)
        if not isinstance(tracker_channel, discord.TextChannel):
            return
        await self._import_tracker_messages(tracker_channel)
        await self._refresh_accepted_submissions()
        bot_state = await self.state.get()
        for message_id in bot_state.tracker_summary_message_ids:
            try:
                await (await tracker_channel.fetch_message(message_id)).delete()
            except discord.HTTPException:
                continue

        groups: dict[str, list[TrackedSubmission]] = {
            "pending": [],
            "awaiting_testing": [],
            "accepted": [],
        }
        for record in bot_state.tracked_submissions.values():
            if record.status in groups:
                groups[record.status].append(record)

        sent_ids: list[int] = []
        await self._send_group(tracker_channel, "## Pending Decision", groups["pending"], sent_ids)
        await self._send_group(
            tracker_channel, "## Awaiting Testing", groups["awaiting_testing"], sent_ids
        )
        await self._send_group(
            tracker_channel,
            "## Pending Archival",
            groups["accepted"],
            sent_ids,
            legacy_lines=bot_state.accepted_submission_entries,
        )
        await self.state.set_tracker_summary_messages(sent_ids)

    async def _import_tracker_messages(self, tracker_channel: discord.TextChannel) -> None:
        bot_state = await self.state.get()
        summary_ids = set(bot_state.tracker_summary_message_ids)
        known_ids = {
            record.tracker_message_id
            for record in bot_state.tracked_submissions.values()
            if record.tracker_message_id is not None
        }
        async for message in tracker_channel.history(limit=None, oldest_first=True):
            if message.id in summary_ids or message.id in known_ids:
                continue
            if not message.content.startswith("## ["):
                continue
            record = self._record_from_tracker_message(message)
            if record is not None:
                await self.state.upsert_submission(record)

    def _record_from_tracker_message(self, message: discord.Message) -> TrackedSubmission | None:
        title_match = re.match(r"## \[(?P<title>[^\]]+)\]\((?P<url>[^)]+)\)", message.content)
        if title_match is None:
            return None
        thread_id = self._last_snowflake(title_match.group("url"))
        if thread_id is None:
            return None
        discussion_id = None
        lines = message.content.splitlines()
        if len(lines) > 1:
            discussion_id = self._last_snowflake(lines[1])
        status: SubmissionStatus = (
            "awaiting_testing"
            if any(str(reaction.emoji) == self.TESTING_EMOJI for reaction in message.reactions)
            else "pending"
        )
        created_at = message.created_at.isoformat()
        return TrackedSubmission(
            submission_thread_id=thread_id,
            title=title_match.group("title"),
            status=status,
            tracker_message_id=message.id,
            tracker_thread_id=discussion_id,
            created_at=created_at,
            updated_at=created_at,
        )

    def _last_snowflake(self, text: str) -> int | None:
        matches = re.findall(r"\d{15,25}", text)
        if not matches:
            return None
        return int(matches[-1])

    async def _refresh_accepted_submissions(self) -> None:
        submissions = self.bot.get_channel(self.settings.channels.submissions)
        if not isinstance(submissions, discord.ForumChannel):
            return
        entries: list[str] = []
        for thread in submissions.threads:
            tag_ids = {tag.id for tag in thread.applied_tags}
            has_other_resolved_tag = any(
                tag_id in self.settings.tags.resolved and tag_id != self.settings.tags.accepted
                for tag_id in tag_ids
            )
            if (
                self.settings.tags.accepted in tag_ids
                and self.settings.tags.archived not in tag_ids
                and not has_other_resolved_tag
            ):
                entries.append(f"- **[{thread.name}]({thread.jump_url})**")
        await self.state.set_accepted_submission_entries(entries)

    async def _finalize_tracker_message(self, record: TrackedSubmission) -> None:
        if record.tracker_message_id is None:
            return
        tracker_channel = self.bot.get_channel(self.settings.channels.submissions_tracker)
        if not isinstance(tracker_channel, discord.TextChannel):
            return

        try:
            tracker_message = await tracker_channel.fetch_message(record.tracker_message_id)
        except discord.HTTPException:
            return

        discussion = await self._fetch_tracker_discussion(record.tracker_thread_id)
        if discussion is not None and tracker_message.reactions:
            lines = ["**Votes as of submission resolution:**"]
            for reaction in tracker_message.reactions:
                users = [
                    user.mention
                    async for user in reaction.users()
                    if self.bot.user is None or user.id != self.bot.user.id
                ]
                lines.append(f"{reaction.emoji} - {', '.join(users)}")
            try:
                await discussion.send(
                    "\n".join(lines),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException:
                await self.audit.log(
                    "Tracker vote capture failed",
                    f"Could not post vote results for {record.title}.",
                )

        try:
            await tracker_message.delete()
        except discord.HTTPException:
            await self.audit.log(
                "Tracker cleanup failed",
                f"Could not delete tracker message for {record.title}.",
            )

    async def _fetch_tracker_discussion(self, thread_id: int | None) -> discord.Thread | None:
        if thread_id is None:
            return None
        channel = self.bot.get_channel(thread_id)
        if isinstance(channel, discord.Thread):
            return channel
        try:
            fetched = await self.bot.fetch_channel(thread_id)
        except discord.HTTPException:
            return None
        return fetched if isinstance(fetched, discord.Thread) else None

    async def _send_group(
        self,
        channel: discord.TextChannel,
        header: str,
        records: list[TrackedSubmission],
        sent_ids: list[int],
        *,
        legacy_lines: list[str] | None = None,
    ) -> None:
        legacy_lines = legacy_lines or []
        if not records and not legacy_lines:
            return
        lines = [
            self._summary_line(record)
            for record in sorted(records, key=lambda item: item.created_at)
        ]
        lines.extend(line if line.endswith("\n") else f"{line}\n" for line in legacy_lines)
        content = f"{header} ({len(lines)})\n"
        for line in lines:
            if len(content) + len(line) > self.settings.discord_char_limit:
                sent = await channel.send(content, allowed_mentions=discord.AllowedMentions.none())
                sent_ids.append(sent.id)
                content = ""
            content += line
        if content.strip():
            sent = await channel.send(content, allowed_mentions=discord.AllowedMentions.none())
            sent_ids.append(sent.id)

    def _summary_line(self, record: TrackedSubmission) -> str:
        guild_id = self.bot.guilds[0].id if self.bot.guilds else "@me"
        submission_url = f"https://discord.com/channels/{guild_id}/{record.submission_thread_id}"
        line = f"- **[{record.title}]({submission_url})**"
        if record.tracker_thread_id is not None:
            discussion_url = f"https://discord.com/channels/{guild_id}/{record.tracker_thread_id}"
            line += f" - {discussion_url}"
        return f"{line}\n"
