from __future__ import annotations

import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import discord
from discord.ext import commands

from config.settings import BotSettings
from models.state import SubmissionStatus, TrackedSubmission
from services.audit import AuditLogService
from services.state import StateService
from services.time import utc_now_iso


@dataclass
class TrackerSyncResult:
    dry_run: bool
    include_archived: bool
    scanned_submissions: int = 0
    scanned_tracker_messages: int = 0
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    finalized: list[str] = field(default_factory=list)
    pruned: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def has_changes(self) -> bool:
        return any(
            [
                self.created,
                self.updated,
                self.finalized,
                self.pruned,
                self.duplicates,
                self.missing,
                self.failures,
            ]
        )

    def summary(self) -> str:
        mode = "Dry run" if self.dry_run else "Applied"
        scope = "active and archived submissions" if self.include_archived else "active submissions"
        lines = [
            f"{mode} tracker sync complete ({scope}).",
            (
                f"Scanned {self.scanned_submissions} submission thread(s) and "
                f"{self.scanned_tracker_messages} tracker message(s)."
            ),
        ]
        counts = [
            ("would create" if self.dry_run else "created", len(self.created)),
            ("would update" if self.dry_run else "updated", len(self.updated)),
            ("would finalize" if self.dry_run else "finalized", len(self.finalized)),
            ("would prune" if self.dry_run else "pruned", len(self.pruned)),
            ("duplicates", len(self.duplicates)),
            ("missing/inaccessible", len(self.missing)),
            ("failures", len(self.failures)),
        ]
        lines.append(", ".join(f"{count} {label}" for label, count in counts if count))
        if not self.has_changes():
            lines.append("No tracker changes needed.")
        details = [
            *self.created,
            *self.updated,
            *self.finalized,
            *self.pruned,
            *self.duplicates,
            *self.missing,
            *self.failures,
        ][:10]
        if details:
            lines.extend(f"- {detail}" for detail in details)
        return "\n".join(line for line in lines if line)


class SubmissionTrackerService:
    VOTE_EMOJIS = ("\u274c", "\U0001f534", "\U0001f7e2", "\u2705")
    TESTING_EMOJI = "\U0001f9ea"

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
        await self._ensure_tracker_record(thread.id)
        existing = (await self.state.get()).tracked_submissions.get(str(thread.id))
        if existing is not None and existing.tracker_message_id is not None:
            return existing
        return await self._create_tracker_post(thread)

    async def _create_tracker_post(
        self,
        thread: discord.Thread,
        *,
        rebuild: bool = True,
    ) -> TrackedSubmission | None:
        tracker_channel = self.bot.get_channel(self.settings.channels.submissions_tracker)
        if not isinstance(tracker_channel, discord.TextChannel):
            await self.audit.log("Tracker unavailable", "Submission tracker channel was not found.")
            return None

        discussion = await self._create_tracker_discussion(thread)
        if discussion is None:
            return None
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
            submission_url=thread.jump_url,
            tracker_thread_url=discussion.jump_url,
        )
        await self.state.upsert_submission(record)
        if rebuild:
            await self.rebuild_summary()
        await self.audit.log("Submission tracked", f"{thread.name}\n{thread.jump_url}")
        return record

    async def sync_all(
        self,
        *,
        dry_run: bool = True,
        include_archived: bool = False,
    ) -> TrackerSyncResult:
        result = TrackerSyncResult(dry_run=dry_run, include_archived=include_archived)
        tracker_channel = self.bot.get_channel(self.settings.channels.submissions_tracker)
        submissions = self.bot.get_channel(self.settings.channels.submissions)
        if not isinstance(tracker_channel, discord.TextChannel):
            result.failures.append("Submission tracker channel was not found.")
            return result
        if not isinstance(submissions, discord.ForumChannel):
            result.failures.append("Submissions forum was not found.")
            return result

        bot_state = await self.state.get()
        state_records = {
            record.submission_thread_id: record
            for record in bot_state.tracked_submissions.values()
        }
        tracker_records, duplicate_message_ids = await self._scan_tracker_records(
            tracker_channel,
            persist=not dry_run,
        )
        result.scanned_tracker_messages = len(tracker_records) + sum(
            len(ids) for ids in duplicate_message_ids.values()
        )

        submission_threads: dict[int, discord.Thread] = {}
        async for thread in self._iter_submission_threads(submissions, include_archived):
            submission_threads[thread.id] = thread
        result.scanned_submissions = len(submission_threads)

        for submission_id, message_ids in duplicate_message_ids.items():
            result.duplicates.append(
                f"Duplicate tracker messages for submission {submission_id}: {', '.join(str(x) for x in message_ids)}"
            )

        for thread in submission_threads.values():
            status = self._status_from_submission(thread)
            record = tracker_records.get(thread.id) or state_records.get(thread.id)
            if status in {"archived", "rejected"}:
                if record is not None:
                    result.finalized.append(f"{status}: {thread.name}")
                    if not dry_run:
                        record.status = status
                        record.title = thread.name
                        record.submission_url = thread.jump_url
                        await self._finalize_tracker_message(record)
                        await self.state.remove_submission(thread.id)
                continue
            if status == "accepted":
                if record is not None:
                    result.finalized.append(f"accepted: {thread.name}")
                    if not dry_run:
                        record.status = "accepted"
                        record.title = thread.name
                        record.submission_url = thread.jump_url
                        await self._finalize_tracker_message(record)
                        await self.state.remove_submission(thread.id)
                continue
            if record is None or record.tracker_message_id is None:
                result.created.append(thread.name)
                if not dry_run:
                    await self._create_tracker_post(thread, rebuild=False)
                continue
            changed = self._record_needs_thread_sync(record, thread)
            if record.status not in {"pending", "awaiting_testing"}:
                record.status = "pending"
                changed = True
            if await self._tracker_discussion_missing(record):
                result.updated.append(f"Recreated missing tracker discussion for {thread.name}")
                if not dry_run:
                    await self._repair_tracker_discussion(record, thread)
            if changed:
                result.updated.append(thread.name)
                if not dry_run:
                    await self._sync_tracker_record(record, thread)

        known_submission_ids = set(submission_threads)
        bot_state = await self.state.get()
        missing_tracker_records = [
            record
            for record in bot_state.tracked_submissions.values()
            if (
                record.submission_thread_id not in tracker_records
                and record.submission_thread_id not in known_submission_ids
            )
        ]
        for record in missing_tracker_records:
            fetched_thread = await self._fetch_submission_thread(record.submission_thread_id)
            if fetched_thread is None:
                result.missing.append(
                    f"Submission thread {record.submission_thread_id} is missing or inaccessible."
                )
                if not dry_run:
                    await self.state.remove_submission(record.submission_thread_id)
                continue
            status = self._status_from_submission(fetched_thread)
            if status in {"accepted", "archived", "rejected"}:
                result.pruned.append(f"Removed stale {status} record: {fetched_thread.name}")
                if not dry_run:
                    await self.state.remove_submission(fetched_thread.id)
            else:
                result.created.append(fetched_thread.name)
                if not dry_run:
                    await self._create_tracker_post(fetched_thread, rebuild=False)

        for record in tracker_records.values():
            if record.submission_thread_id in known_submission_ids:
                continue
            fetched_thread = await self._fetch_submission_thread(record.submission_thread_id)
            if fetched_thread is None:
                result.missing.append(
                    f"Submission thread {record.submission_thread_id} is missing or inaccessible."
                )
                if not dry_run:
                    await self._delete_tracker_message(record, result)
                    await self.state.remove_submission(record.submission_thread_id)
                continue
            status = self._status_from_submission(fetched_thread)
            if status in {"accepted", "archived", "rejected"}:
                result.finalized.append(f"{status}: {fetched_thread.name}")
                if not dry_run:
                    record.status = status
                    record.title = fetched_thread.name
                    record.submission_url = fetched_thread.jump_url
                    await self._finalize_tracker_message(record)
                    await self.state.remove_submission(fetched_thread.id)
            elif self._record_needs_thread_sync(record, fetched_thread):
                result.updated.append(fetched_thread.name)
                if not dry_run:
                    await self._sync_tracker_record(record, fetched_thread)
            elif await self._tracker_discussion_missing(record):
                result.updated.append(
                    f"Recreated missing tracker discussion for {fetched_thread.name}"
                )
                if not dry_run:
                    await self._repair_tracker_discussion(record, fetched_thread)

        if not dry_run:
            await self.rebuild_summary()
        return result

    async def _create_tracker_discussion(self, thread: discord.Thread) -> discord.Thread | None:
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
        return discussion

    async def update_status(self, thread: discord.Thread, status: SubmissionStatus) -> None:
        await self._ensure_tracker_record(thread.id)
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
                submission_url=thread.jump_url,
            )
        else:
            previous_title = existing.title
            existing.title = thread.name
            existing.submission_url = thread.jump_url
            if status != "unknown":
                existing.status = status
            existing.updated_at = now
            if previous_title != thread.name:
                await self._sync_tracker_title(existing, thread)
        await self.state.upsert_submission(existing)
        if status in {"accepted", "archived", "rejected"}:
            await self._finalize_tracker_message(existing)
            await self.state.remove_submission(thread.id)
        await self.rebuild_summary()

    async def reconcile_submission(self, thread: discord.Thread) -> None:
        await self._ensure_tracker_record(thread.id)
        tag_ids = {tag.id for tag in thread.applied_tags}
        if self.settings.tags.archived in tag_ids:
            await self.update_status(thread, "archived")
            return
        if self.settings.tags.rejected in tag_ids:
            await self.update_status(thread, "rejected")
            return
        if self.settings.tags.accepted in tag_ids:
            await self.update_status(thread, "accepted")
            return

        existing = (await self.state.get()).tracked_submissions.get(str(thread.id))
        if existing is None:
            await self.rebuild_summary()
            return
        if existing.tracker_message_id is None:
            await self.state.remove_submission(thread.id)
            await self.rebuild_summary()
            return
        await self.update_status(thread, "pending")

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

    async def _sync_tracker_record(
        self, record: TrackedSubmission, thread: discord.Thread
    ) -> None:
        changed = self._record_needs_thread_sync(record, thread)
        record.title = thread.name
        record.submission_url = thread.jump_url
        record.updated_at = utc_now_iso()
        if record.status not in {"pending", "awaiting_testing"}:
            record.status = "pending"
        if changed:
            await self._sync_tracker_title(record, thread)
        await self.state.upsert_submission(record)

    async def rebuild_summary(self) -> None:
        tracker_channel = self.bot.get_channel(self.settings.channels.submissions_tracker)
        if not isinstance(tracker_channel, discord.TextChannel):
            return
        live_tracker_message_ids = await self._import_tracker_messages(tracker_channel)
        accepted_submission_ids = await self._refresh_accepted_submissions()
        await self._prune_stale_records(live_tracker_message_ids, accepted_submission_ids)
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
            legacy_lines=self._legacy_lines_not_tracked(
                bot_state.accepted_submission_entries,
                groups["accepted"],
            ),
        )
        await self.state.set_tracker_summary_messages(sent_ids)

    async def _import_tracker_messages(self, tracker_channel: discord.TextChannel) -> set[int]:
        bot_state = await self.state.get()
        pinned_ids = {message.id for message in await tracker_channel.pins()}
        summary_ids = set(bot_state.tracker_summary_message_ids)
        known_ids = {
            record.tracker_message_id
            for record in bot_state.tracked_submissions.values()
            if record.tracker_message_id is not None
        }
        live_tracker_message_ids: set[int] = set()
        async for message in tracker_channel.history(limit=None, oldest_first=True):
            if message.id in summary_ids or message.id in pinned_ids:
                continue
            if not message.content.startswith("## ["):
                continue
            live_tracker_message_ids.add(message.id)
            record = self._record_from_tracker_message(message)
            if record is not None:
                if message.id in known_ids:
                    existing = next(
                        (
                            item
                            for item in bot_state.tracked_submissions.values()
                            if item.tracker_message_id == message.id
                        ),
                        None,
                    )
                    if existing is not None:
                        record.created_at = existing.created_at
                        record.updated_at = utc_now_iso()
                await self.state.upsert_submission(record)
        return live_tracker_message_ids

    async def _scan_tracker_records(
        self,
        tracker_channel: discord.TextChannel,
        *,
        persist: bool = True,
    ) -> tuple[dict[int, TrackedSubmission], dict[int, list[int]]]:
        bot_state = await self.state.get()
        summary_ids = set(bot_state.tracker_summary_message_ids)
        pinned_ids = {message.id for message in await tracker_channel.pins()}
        records: dict[int, TrackedSubmission] = {}
        duplicates: dict[int, list[int]] = {}
        async for message in tracker_channel.history(limit=None, oldest_first=True):
            if message.id in summary_ids or message.id in pinned_ids:
                continue
            if not message.content.startswith("## ["):
                continue
            record = self._record_from_tracker_message(message)
            if record is None:
                continue
            if record.submission_thread_id in records:
                duplicates.setdefault(record.submission_thread_id, []).append(message.id)
                continue
            records[record.submission_thread_id] = record
            if persist:
                await self.state.upsert_submission(record)
        return records, duplicates

    async def _ensure_tracker_record(self, submission_thread_id: int) -> None:
        if str(submission_thread_id) in (await self.state.get()).tracked_submissions:
            return
        tracker_channel = self.bot.get_channel(self.settings.channels.submissions_tracker)
        if not isinstance(tracker_channel, discord.TextChannel):
            return
        async for message in tracker_channel.history(limit=None, oldest_first=True):
            if not message.content.startswith("## ["):
                continue
            record = self._record_from_tracker_message(message)
            if record is not None and record.submission_thread_id == submission_thread_id:
                await self.state.upsert_submission(record)
                return

    def _record_from_tracker_message(self, message: discord.Message) -> TrackedSubmission | None:
        title_match = re.match(r"## \[(?P<title>.+)\]\((?P<url>[^)]+)\)", message.content.splitlines()[0])
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
            submission_url=title_match.group("url"),
            tracker_thread_url=lines[1] if len(lines) > 1 else None,
        )

    def _last_snowflake(self, text: str) -> int | None:
        matches = re.findall(r"\d{15,25}", text)
        if not matches:
            return None
        return int(matches[-1])

    async def _iter_submission_threads(
        self,
        submissions: discord.ForumChannel,
        include_archived: bool,
    ) -> AsyncIterator[discord.Thread]:
        seen: set[int] = set()
        for thread in submissions.threads:
            seen.add(thread.id)
            yield thread
        if not include_archived:
            return
        async for thread in submissions.archived_threads(limit=None):
            if thread.id in seen:
                continue
            seen.add(thread.id)
            yield thread

    async def _fetch_submission_thread(self, thread_id: int) -> discord.Thread | None:
        channel = self.bot.get_channel(thread_id)
        if isinstance(channel, discord.Thread):
            return channel
        try:
            fetched = await self.bot.fetch_channel(thread_id)
        except discord.HTTPException:
            return None
        return fetched if isinstance(fetched, discord.Thread) else None

    def _status_from_submission(self, thread: discord.Thread) -> SubmissionStatus:
        tag_ids = {tag.id for tag in thread.applied_tags}
        if self.settings.tags.archived in tag_ids:
            return "archived"
        if self.settings.tags.rejected in tag_ids:
            return "rejected"
        if self.settings.tags.accepted in tag_ids:
            return "accepted"
        return "pending"

    def _record_needs_thread_sync(
        self,
        record: TrackedSubmission,
        thread: discord.Thread,
    ) -> bool:
        return record.title != thread.name or record.submission_url != thread.jump_url

    async def _tracker_discussion_missing(self, record: TrackedSubmission) -> bool:
        if record.tracker_thread_id is None:
            return True
        return await self._fetch_tracker_discussion(record.tracker_thread_id) is None

    async def _repair_tracker_discussion(
        self,
        record: TrackedSubmission,
        thread: discord.Thread,
    ) -> None:
        discussion = await self._create_tracker_discussion(thread)
        if discussion is None:
            return
        record.tracker_thread_id = discussion.id
        record.tracker_thread_url = discussion.jump_url
        tracker_channel = self.bot.get_channel(self.settings.channels.submissions_tracker)
        if isinstance(tracker_channel, discord.TextChannel) and record.tracker_message_id is not None:
            try:
                tracker_message = await tracker_channel.fetch_message(record.tracker_message_id)
                await tracker_message.edit(
                    content=f"## [{thread.name}]({thread.jump_url})\n{discussion.jump_url}",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException:
                await self.audit.log(
                    "Tracker message repair failed",
                    f"Could not repair tracker discussion link for {thread.jump_url}.",
                )
        await self.state.upsert_submission(record)

    async def _delete_tracker_message(
        self,
        record: TrackedSubmission,
        result: TrackerSyncResult,
    ) -> None:
        if record.tracker_message_id is None:
            return
        tracker_channel = self.bot.get_channel(self.settings.channels.submissions_tracker)
        if not isinstance(tracker_channel, discord.TextChannel):
            result.failures.append("Submission tracker channel was not found.")
            return
        try:
            await (await tracker_channel.fetch_message(record.tracker_message_id)).delete()
            result.pruned.append(f"Deleted orphan tracker message {record.tracker_message_id}.")
        except discord.HTTPException as exc:
            result.failures.append(
                f"Could not delete tracker message {record.tracker_message_id}: {exc}"
            )

    async def _refresh_accepted_submissions(self) -> set[int]:
        submissions = self.bot.get_channel(self.settings.channels.submissions)
        if not isinstance(submissions, discord.ForumChannel):
            return set()
        entries: list[str] = []
        accepted_ids: set[int] = set()
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
                accepted_ids.add(thread.id)
        await self.state.set_accepted_submission_entries(entries)
        return accepted_ids

    async def _prune_stale_records(
        self,
        live_tracker_message_ids: set[int],
        accepted_submission_ids: set[int],
    ) -> None:
        bot_state = await self.state.get()
        for record in list(bot_state.tracked_submissions.values()):
            if record.status in {"archived", "rejected"}:
                await self.state.remove_submission(record.submission_thread_id)
                continue
            if record.status == "accepted":
                if record.submission_thread_id not in accepted_submission_ids:
                    await self.state.remove_submission(record.submission_thread_id)
                continue
            if (
                record.status in {"pending", "awaiting_testing"}
                and record.tracker_message_id is not None
                and record.tracker_message_id not in live_tracker_message_ids
            ):
                await self.state.remove_submission(record.submission_thread_id)

    def _legacy_lines_not_tracked(
        self,
        legacy_lines: list[str],
        records: list[TrackedSubmission],
    ) -> list[str]:
        tracked_ids = {str(record.submission_thread_id) for record in records}
        return [line for line in legacy_lines if not any(thread_id in line for thread_id in tracked_ids)]

    async def _finalize_tracker_message(self, record: TrackedSubmission) -> None:
        try:
            await self._finalize_tracker_message_inner(record)
        except Exception as exc:
            await self.audit.log(
                "Tracker finalization failed",
                f"Could not finalize tracker state for {record.title}: {exc}",
                colour=discord.Color.red(),
            )

    async def _finalize_tracker_message_inner(self, record: TrackedSubmission) -> None:
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
        submission_url = record.submission_url or (
            f"https://discord.com/channels/{guild_id}/{record.submission_thread_id}"
        )
        line = f"- **[{record.title}]({submission_url})**"
        if record.tracker_thread_id is not None:
            discussion_url = record.tracker_thread_url or (
                f"https://discord.com/channels/{guild_id}/{record.tracker_thread_id}"
            )
            line += f" - {discussion_url}"
        return f"{line}\n"
