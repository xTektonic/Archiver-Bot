from __future__ import annotations

import discord
from discord.ext import commands

from config.settings import BotSettings
from services.audit import AuditLogService
from services.safe_discord import ensure_content_safe, no_mentions
from services.state import StateService


class ArchivePublishingService:
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

    async def publish(
        self,
        source_channel: discord.abc.GuildChannel,
        archive_channel: discord.ForumChannel,
        title: str,
        content: str,
        author: discord.Member,
        *,
        announce: bool,
    ) -> discord.Thread:
        if archive_channel.category_id in self.settings.categories.non_archive:
            raise ValueError("The selected forum is not an archive forum.")
        ensure_content_safe(content, limit=self.settings.discord_char_limit)
        created = await archive_channel.create_thread(
            name=title,
            content=content,
            allowed_mentions=no_mentions(),
        )
        thread = created.thread
        try:
            await self.state.set_last_archive_thread(thread.id)
        except Exception as exc:
            await self._try_audit_log(
                "Archive state update failed",
                f"Post: {thread.jump_url}\nError: {exc}",
            )
        await self._try_audit_log(
            "Post published",
            f"Post: {thread.jump_url}\nChannel: {archive_channel.jump_url}\nBy: {author.mention}",
            is_warning=False,
        )
        if announce:
            updates = self.bot.get_channel(self.settings.channels.archive_updates)
            if isinstance(updates, discord.abc.Messageable):
                try:
                    await updates.send(
                        f"Archived {thread.jump_url} in {archive_channel.jump_url}\n\n"
                        f"Source: {getattr(source_channel, 'jump_url', '')}",
                        allowed_mentions=no_mentions(),
                    )
                except discord.HTTPException as exc:
                    await self._try_audit_log(
                        "Archive announcement failed",
                        f"Post: {thread.jump_url}\nError: {exc}",
                    )
        return thread

    async def append(
        self,
        archive_thread: discord.Thread,
        content: str,
        author: discord.Member,
    ) -> discord.Message:
        if archive_thread.parent and archive_thread.parent.category_id in self.settings.categories.non_archive:
            raise ValueError("The selected thread is not in an archive forum.")
        ensure_content_safe(content, limit=self.settings.discord_char_limit)
        message = await archive_thread.send(content=content, allowed_mentions=no_mentions())
        try:
            await self.state.set_last_archive_thread(archive_thread.id)
        except Exception as exc:
            await self._try_audit_log(
                "Archive append state update failed",
                f"Message: {message.jump_url}\nError: {exc}",
            )
        await self._try_audit_log(
            "Post appended",
            f"In: {archive_thread.jump_url}\nBy: {author.mention}\n\n{content[:900]}",
            is_warning=False,
        )
        return message

    async def grant_role(
        self, guild: discord.Guild, member: discord.Member, role_id: int
    ) -> None:
        role = guild.get_role(role_id)
        if role is None:
            raise ValueError(f"Role {role_id} was not found.")
        await member.add_roles(role)

    async def _try_audit_log(
        self,
        title: str,
        description: str,
        *,
        colour: discord.Color | None = None,
        is_warning: bool = True,
    ) -> None:
        try:
            await self.audit.log(
                title,
                description,
                colour=colour if not is_warning else discord.Color.orange(),
            )
        except discord.HTTPException:
            return
