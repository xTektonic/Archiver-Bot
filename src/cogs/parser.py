from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from app import ArchiverBot
from services.audit import diff_block
from services.checks import has_higher_role
from services.parser_service import ParseDiagnostic
from services.safe_discord import defer


class PostEditAndParseModal(discord.ui.Modal, title="Edit Post"):
    def __init__(
        self,
        bot: ArchiverBot,
        thread: discord.Thread,
        message: discord.Message,
    ):
        super().__init__()
        self.bot = bot
        self.thread = thread
        self.message = message
        self.change_notes = discord.ui.TextInput(
            label="Change notes",
            style=discord.TextStyle.long,
            required=False,
        )
        self.message_input = discord.ui.TextInput(
            label="Edit raw post",
            style=discord.TextStyle.paragraph,
            default=message.content,
        )
        self.add_item(self.change_notes)
        self.add_item(self.message_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        old_content = self.message.content
        await self.message.edit(content=self.message_input.value)
        log_embed = discord.Embed(
            title="Archive post message edited",
            description=(
                f"Message: {self.message.jump_url}\n"
                f"By: {interaction.user.mention}\n"
                f"Notes: {self.change_notes.value or 'None'}"
            ),
            colour=discord.Color.yellow(),
        )
        content_diff = diff_block(old_content, self.message_input.value)
        if content_diff:
            log_embed.add_field(name="Content Change", value=f"```ansi\n{content_diff}\n```", inline=False)
        await self.bot.services.audit.log_embed(log_embed)

        result = await self.bot.services.parser.parse_thread(self.thread)
        if not result.errors:
            await interaction.followup.send("Edit saved and parse succeeded.", ephemeral=True)
            return
        await interaction.followup.send(
            f"Edit saved, but parsing still failed: {result.errors[0].error}",
            view=await ParserErrorView.create(self.bot, self.thread, result.errors[0]),
            ephemeral=True,
        )


class ParserErrorView(discord.ui.View):
    def __init__(
        self,
        bot: ArchiverBot,
        thread: discord.Thread,
        diagnostic: ParseDiagnostic,
        messages: list[discord.Message],
    ):
        super().__init__(timeout=3600)
        self.bot = bot
        self.thread = thread
        self.diagnostic = diagnostic
        for index, message in enumerate(messages, start=1):
            button = discord.ui.Button(label=f"Edit {index}", style=discord.ButtonStyle.blurple)
            button.callback = self._edit_callback(message)
            self.add_item(button)

    @classmethod
    async def create(
        cls,
        bot: ArchiverBot,
        thread: discord.Thread,
        diagnostic: ParseDiagnostic,
    ) -> ParserErrorView:
        first_messages = [
            message
            async for message in thread.history(limit=3, oldest_first=True)
            if message.content and message.type == discord.MessageType.default
        ]
        messages = list(first_messages)
        seen = {message.id for message in messages}
        async for message in thread.history(limit=5, oldest_first=False):
            if len(messages) >= 5:
                break
            if (
                message.id not in seen
                and message.content
                and message.type == discord.MessageType.default
            ):
                messages.append(message)
                seen.add(message.id)
        return cls(bot, thread, diagnostic, messages)

    def _edit_callback(self, message: discord.Message):
        async def edit(interaction: discord.Interaction) -> None:
            if not await has_higher_role(interaction):
                await interaction.response.send_message(
                    "You do not have permission to edit archive posts.",
                    ephemeral=True,
                )
                return
            await interaction.response.send_modal(
                PostEditAndParseModal(self.bot, self.thread, message)
            )

        return edit


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
        if result.errors:
            await interaction.followup.send(
                f"{thread.jump_url}: {result.errors[0].error}",
                view=await ParserErrorView.create(self.bot, thread, result.errors[0]),
                ephemeral=True,
            )

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
        await self._send_error_views(interaction.channel, result.errors)

    @app_commands.command(name="parse_archive", description="Parse all configured archive forums")
    @app_commands.check(has_higher_role)
    async def parse_archive(self, interaction: discord.Interaction) -> None:
        await defer(interaction, ephemeral=False)
        result = await self.bot.services.parser.parse_archive(interaction.guild)
        await interaction.followup.send(self._format_result(result.total, result.errors))
        await self._send_error_views(interaction.channel, result.errors)

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

    async def _send_error_views(
        self,
        destination: discord.abc.Messageable | None,
        errors: list[ParseDiagnostic],
    ) -> None:
        if not isinstance(destination, discord.abc.Messageable):
            return
        for diagnostic in errors[:10]:
            thread = await self._fetch_thread(diagnostic.thread_id)
            if thread is None:
                continue
            await destination.send(
                f"{thread.jump_url}: **{diagnostic.error}**",
                view=await ParserErrorView.create(self.bot, thread, diagnostic),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        if len(errors) > 10:
            await destination.send(
                f"{len(errors) - 10} more parse errors were omitted from repair controls.",
                allowed_mentions=discord.AllowedMentions.none(),
            )

    async def _fetch_thread(self, thread_id: int) -> discord.Thread | None:
        channel = self.bot.get_channel(thread_id)
        if isinstance(channel, discord.Thread):
            return channel
        try:
            fetched = await self.bot.fetch_channel(thread_id)
        except discord.HTTPException:
            return None
        return fetched if isinstance(fetched, discord.Thread) else None


async def setup(bot: ArchiverBot) -> None:
    await bot.add_cog(ParserCog(bot))
