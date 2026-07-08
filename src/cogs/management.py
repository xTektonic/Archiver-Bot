from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands, tasks

from app import ArchiverBot
from services.checks import has_higher_role
from services.maintenance import JobResult
from services.safe_discord import respond


class TagSelectView(discord.ui.View):
    def __init__(self, thread: discord.Thread):
        super().__init__(timeout=300)
        self.thread = thread
        options = [
            discord.SelectOption(label=tag.name, emoji=tag.emoji, value=str(tag.id))
            for tag in thread.parent.available_tags[:25]
        ]
        self.select = discord.ui.Select(
            placeholder="Choose tags",
            min_values=1,
            max_values=min(5, len(options)),
            options=options,
        )
        self.select.callback = self.on_select
        self.add_item(self.select)

    async def on_select(self, interaction: discord.Interaction) -> None:
        selected = {int(value) for value in self.select.values}
        tags = [tag for tag in self.thread.parent.available_tags if tag.id in selected]
        await self.thread.edit(applied_tags=tags)
        client = interaction.client
        if isinstance(client, ArchiverBot):
            await client.services.audit.log(
                f"Tags {format_tag_names(tags)} added",
                f"To post: {self.thread.jump_url}\nBy: {interaction.user.mention}",
            )
        await interaction.response.edit_message(content="Tags set.", view=None)


class ManagementCog(commands.Cog):
    def __init__(self, bot: ArchiverBot):
        self.bot = bot
        self.pin_ctx = app_commands.ContextMenu(name="Pin", callback=self.pin_message)
        bot.tree.add_command(self.pin_ctx)
        self.periodic_maintenance.start()

    def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.pin_ctx.name, type=self.pin_ctx.type)
        self.periodic_maintenance.cancel()

    @tasks.loop(hours=12)
    async def periodic_maintenance(self) -> None:
        await self.bot.wait_until_ready()
        logs = self.bot.get_channel(self.bot.settings.channels.log)
        guild = logs.guild if isinstance(logs, discord.TextChannel | discord.Thread) else None
        if guild is None:
            return
        await self.bot.services.audit.log("Maintenance", "Running periodic maintenance.")
        for result in [
            await self.bot.services.maintenance.mark_inactive_help(dry_run=False),
            await self.bot.services.maintenance.lock_resolved_submissions(dry_run=False),
            await self.bot.services.maintenance.open_archived(guild, dry_run=False),
            await self.bot.services.maintenance.close_resolved(guild, dry_run=False),
        ]:
            await self._log_job(result)

    @app_commands.command(name="close_resolved", description="Close solved/rejected/archived posts")
    @app_commands.check(has_higher_role)
    async def close_resolved(self, interaction: discord.Interaction, dry_run: bool = False) -> None:
        result = await self.bot.services.maintenance.close_resolved(interaction.guild, dry_run=dry_run)
        await respond(interaction, self._format_job(result))

    @app_commands.command(name="open_archived", description="Open archived archive posts")
    @app_commands.check(has_higher_role)
    async def open_archived(self, interaction: discord.Interaction, dry_run: bool = False) -> None:
        result = await self.bot.services.maintenance.open_archived(interaction.guild, dry_run=dry_run)
        await respond(interaction, self._format_job(result))

    @app_commands.command(name="tag_selector", description="Set forum post tags")
    async def tag_selector(self, interaction: discord.Interaction, given_tag: str = "") -> None:
        if not isinstance(interaction.channel, discord.Thread) or not isinstance(
            interaction.channel.parent, discord.ForumChannel
        ):
            await respond(interaction, "This command can only be used in a forum post.")
            return
        has_staff = any(role.id in self.bot.settings.roles.staff for role in interaction.user.roles)
        owns_help_post = (
            interaction.channel.parent_id == self.bot.settings.channels.help_forum
            and interaction.user.id == interaction.channel.owner_id
        )
        if not has_staff and not owns_help_post:
            await respond(interaction, "You do not have permission to set tags here.")
            return
        if not given_tag:
            await interaction.response.send_message(
                "Select tags:", view=TagSelectView(interaction.channel), ephemeral=True
            )
            return
        tag = next(
            (
                tag
                for tag in interaction.channel.parent.available_tags
                if tag.name.lower() == given_tag.lower()
            ),
            None,
        )
        if tag is None:
            await respond(interaction, "Invalid tag name.")
            return
        await interaction.channel.edit(applied_tags=[tag])
        await self.bot.services.audit.log(
            f"Tag {format_tag_names([tag])} added",
            f"To post: {interaction.channel.jump_url}\nBy: {interaction.user.mention}",
        )
        await respond(interaction, f"Set tag to {tag.name}.")

    async def pin_message(self, interaction: discord.Interaction, message: discord.Message) -> None:
        if not isinstance(message.channel, discord.Thread):
            await respond(interaction, "This command can only be run in a thread.")
            return
        if message.channel.parent_id not in self.bot.settings.channels.allowed_pin_forums:
            await respond(interaction, "This command can only be used in allowed forums.")
            return
        if interaction.user.id != message.channel.owner_id:
            await respond(interaction, "You can only pin messages in your own post.")
            return
        await message.pin()
        await respond(interaction, "Message pinned.")

    async def _log_job(self, result: JobResult) -> None:
        await self.bot.services.audit.log(result.name, self._format_job(result))

    def _format_job(self, result: JobResult) -> str:
        mode = "dry run" if result.dry_run else "applied"
        content = f"{result.name}: {result.changed} change(s), {mode}."
        if not result.messages:
            return content
        details = "\n".join(f"- {message}" for message in result.messages)
        if len(content) + len(details) + 2 > self.bot.settings.discord_char_limit:
            details = details[: self.bot.settings.discord_char_limit - len(content) - 8] + "\n..."
        return f"{content}\n{details}"


async def setup(bot: ArchiverBot) -> None:
    await bot.add_cog(ManagementCog(bot))


def format_tag_names(tags: list[discord.ForumTag]) -> str:
    return ",  ".join(f"{tag.emoji or ''} {tag.name}".strip() for tag in tags)
