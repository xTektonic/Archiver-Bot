from __future__ import annotations

import discord
from discord.ext import commands

from config.settings import BotSettings
from models.state import SubmissionStatus, TrackedSubmission
from services.audit import AuditLogService
from services.state import StateService
from services.time import utc_now_iso


class SubmissionTrackerService:
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
        for emoji in ("❌", "🔴", "🟢", "✅"):
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
            existing.title = thread.name
            existing.status = status
            existing.updated_at = now
        await self.state.upsert_submission(existing)
        await self.rebuild_summary()

    async def rebuild_summary(self) -> None:
        tracker_channel = self.bot.get_channel(self.settings.channels.submissions_tracker)
        if not isinstance(tracker_channel, discord.TextChannel):
            return
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
        await self._send_group(tracker_channel, "## Pending Archival", groups["accepted"], sent_ids)
        await self.state.set_tracker_summary_messages(sent_ids)

    async def _send_group(
        self,
        channel: discord.TextChannel,
        header: str,
        records: list[TrackedSubmission],
        sent_ids: list[int],
    ) -> None:
        if not records:
            return
        content = f"{header} ({len(records)})\n"
        for record in sorted(records, key=lambda item: item.created_at):
            line = f"- **{record.title}**\n"
            if len(content) + len(line) > self.settings.discord_char_limit:
                sent = await channel.send(content, allowed_mentions=discord.AllowedMentions.none())
                sent_ids.append(sent.id)
                content = ""
            content += line
        if content.strip():
            sent = await channel.send(content, allowed_mentions=discord.AllowedMentions.none())
            sent_ids.append(sent.id)
