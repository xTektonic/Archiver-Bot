from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from app import ArchiverBot
from cogs.management import TagSelectView
from services.audit import diff_block
from services.checks import has_higher_role
from services.safe_discord import defer, respond


class SendModal(discord.ui.Modal, title="Send Message"):
    def __init__(self, bot: ArchiverBot, target_channel: discord.abc.Messageable, has_embed: bool):
        super().__init__()
        self.bot = bot
        self.target_channel = target_channel
        self.message_text = discord.ui.TextInput(
            label="Message content",
            style=discord.TextStyle.long,
            required=False,
        )
        self.add_item(self.message_text)
        self.has_embed = has_embed
        if has_embed:
            self.embed_title = discord.ui.TextInput(label="Embed title", required=False)
            self.embed_text = discord.ui.TextInput(
                label="Embed description",
                style=discord.TextStyle.long,
                required=False,
            )
            self.embed_colour = discord.ui.TextInput(
                label="Embed colour",
                default="#FFFFFF",
                required=False,
            )
            self.add_item(self.embed_title)
            self.add_item(self.embed_text)
            self.add_item(self.embed_colour)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        embed = None
        if self.has_embed:
            try:
                colour = discord.Colour.from_str(self.embed_colour.value or "#FFFFFF")
            except ValueError:
                await interaction.followup.send("Embed colour must look like #FFFFFF.", ephemeral=True)
                return
            embed = discord.Embed(
                title=self.embed_title.value,
                description=self.embed_text.value,
                colour=colour,
            )
        await self.target_channel.send(
            content=self.message_text.value,
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        details = [
            f"By: {interaction.user.mention}",
            f"In: {getattr(self.target_channel, 'jump_url', '')}",
            f"Content: {self.message_text.value[:900]}",
        ]
        if embed is not None:
            details.extend(
                [
                    f"Embed title: {embed.title or ''}",
                    f"Embed description: {(embed.description or '')[:900]}",
                ]
            )
        await self.bot.services.audit.log(
            "Message sent via bot",
            "\n".join(details),
        )
        await interaction.followup.send("Message successfully sent.", ephemeral=True)


class EditMessageModal(discord.ui.Modal, title="Edit Message"):
    def __init__(self, bot: ArchiverBot, message: discord.Message):
        super().__init__()
        self.bot = bot
        self.message = message
        self.original_content = message.content
        self.message_text = discord.ui.TextInput(
            label="Message content",
            default=message.content,
            style=discord.TextStyle.long,
            required=False,
        )
        self.add_item(self.message_text)
        self.rich_embeds = [embed for embed in message.embeds if embed.type == "rich"]
        if self.rich_embeds:
            first = self.rich_embeds[0]
            self.embed_title = discord.ui.TextInput(
                label="Embed title",
                default=first.title or "",
                required=False,
            )
            self.embed_text = discord.ui.TextInput(
                label="Embed description",
                default=first.description or "",
                style=discord.TextStyle.long,
                required=False,
            )
            self.add_item(self.embed_title)
            self.add_item(self.embed_text)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await defer(interaction)
        original_embeds = [discord.Embed.from_dict(embed.to_dict()) for embed in self.rich_embeds]
        embeds: list[discord.Embed] = []
        if self.rich_embeds:
            for index, embed in enumerate(self.rich_embeds):
                cloned = discord.Embed.from_dict(embed.to_dict())
                if index == 0:
                    cloned.title = self.embed_title.value
                    cloned.description = self.embed_text.value
                embeds.append(cloned)
        await self.message.edit(
            content=self.message_text.value,
            embeds=embeds,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        log_embed = discord.Embed(
            title="Bot message edited",
            description=f"Message: {self.message.jump_url}\nBy: {interaction.user.mention}",
            colour=discord.Color.yellow(),
        )
        content_diff = diff_block(self.original_content, self.message_text.value)
        if content_diff:
            log_embed.add_field(name="Content Change", value=f"```ansi\n{content_diff}\n```", inline=False)
        if original_embeds and embeds:
            title_diff = diff_block(original_embeds[0].title, embeds[0].title)
            description_diff = diff_block(original_embeds[0].description, embeds[0].description)
            if title_diff:
                log_embed.add_field(
                    name="Embed Title Change",
                    value=f"```ansi\n{title_diff}\n```",
                    inline=False,
                )
            if description_diff:
                log_embed.add_field(
                    name="Embed Description Change",
                    value=f"```ansi\n{description_diff}\n```",
                    inline=False,
                )
        await self.bot.services.audit.log_embed(log_embed)
        await interaction.followup.send("Message successfully edited.", ephemeral=True)


class PublishModal(discord.ui.Modal, title="Publish Post"):
    def __init__(self, bot: ArchiverBot, draft: discord.Message):
        super().__init__()
        self.bot = bot
        self.draft = draft
        self.channel_select = discord.ui.ChannelSelect(
            placeholder="Choose the forum to publish to",
            min_values=1,
            max_values=1,
            channel_types=[discord.ChannelType.forum],
        )
        self.add_item(discord.ui.Label(text="Archive forum", component=self.channel_select))
        self.post_title = discord.ui.TextInput(
            label="Post title",
            default=draft.channel.name if isinstance(draft.channel, discord.Thread) else "",
        )
        self.post_content = discord.ui.TextInput(
            label="Post content",
            default=draft.content,
            style=discord.TextStyle.long,
        )
        self.announce = discord.ui.Select(
            placeholder="Announce update?",
            options=[
                discord.SelectOption(label="No", value="false", default=True),
                discord.SelectOption(label="Yes", value="true"),
            ],
        )
        self.add_item(self.post_title)
        self.add_item(self.post_content)
        self.add_item(discord.ui.Label(text="Announce update", component=self.announce))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        channel = self.channel_select.values[0]
        archive_channel = await interaction.client.fetch_channel(channel.id)
        if not isinstance(archive_channel, discord.ForumChannel):
            await interaction.followup.send("The selected channel is not a forum.", ephemeral=True)
            return
        try:
            thread = await self.bot.services.archive.publish(
                interaction.channel,
                archive_channel,
                self.post_title.value,
                self.post_content.value,
                interaction.user,
                announce=self.announce.values[0] == "true",
            )
        except Exception as exc:
            await interaction.followup.send(f"Error publishing post: {exc}", ephemeral=True)
            await self.bot.services.audit.log(
                "Error publishing post",
                f"{exc}\nBy: {interaction.user.mention}",
                colour=discord.Color.red(),
            )
            return
        if (
            isinstance(interaction.channel, discord.Thread)
            and interaction.channel.parent_id == self.bot.settings.channels.submissions
        ):
            archived_tag = interaction.channel.parent.get_tag(self.bot.settings.tags.archived)
            if archived_tag is not None:
                await interaction.channel.edit(applied_tags=[archived_tag])
            link = await interaction.channel.send(
                f"Submission archived as {thread.jump_url}",
                allowed_mentions=discord.AllowedMentions.none(),
            )
            await link.pin()
        await interaction.followup.send(
            f"Post published: {thread.jump_url}\nSet post tags:",
            view=TagSelectView(thread),
            ephemeral=True,
        )


class AppendModal(discord.ui.Modal, title="Append to Post"):
    def __init__(self, bot: ArchiverBot, draft: discord.Message):
        super().__init__()
        self.bot = bot
        self.draft = draft
        self.thread_select = discord.ui.ChannelSelect(
            placeholder="Choose the archive thread",
            min_values=1,
            max_values=1,
            channel_types=[discord.ChannelType.public_thread],
        )
        self.add_item(discord.ui.Label(text="Archive thread", component=self.thread_select))
        self.post_content = discord.ui.TextInput(
            label="Post content",
            default=draft.content,
            style=discord.TextStyle.long,
        )
        self.add_item(self.post_content)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        thread = interaction.client.get_channel(self.thread_select.values[0].id)
        if not isinstance(thread, discord.Thread):
            thread = await interaction.client.fetch_channel(self.thread_select.values[0].id)
        if not isinstance(thread, discord.Thread):
            await interaction.followup.send("The selected channel is not a thread.", ephemeral=True)
            return
        try:
            message = await self.bot.services.archive.append(thread, self.post_content.value, interaction.user)
        except Exception as exc:
            await interaction.followup.send(f"Error appending post: {exc}", ephemeral=True)
            await self.bot.services.audit.log(
                "Error appending post",
                f"{exc}\nBy: {interaction.user.mention}",
                colour=discord.Color.red(),
            )
            return
        await interaction.followup.send(f"Post appended: {message.jump_url}", ephemeral=True)


class AppendPrompt(discord.ui.View):
    def __init__(self, bot: ArchiverBot, draft: discord.Message, thread: discord.Thread):
        super().__init__(timeout=300)
        self.bot = bot
        self.draft = draft
        self.thread = thread

    @discord.ui.button(label="Same thread", style=discord.ButtonStyle.green)
    async def same_thread(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            message = await self.bot.services.archive.append(
                self.thread,
                self.draft.content,
                interaction.user,
            )
        except Exception as exc:
            await interaction.followup.send(f"Error appending post: {exc}", ephemeral=True)
            await self.bot.services.audit.log(
                "Error appending post",
                f"{exc}\nBy: {interaction.user.mention}",
                colour=discord.Color.red(),
            )
            return
        await interaction.followup.send(f"Post appended: {message.jump_url}", ephemeral=True)

    @discord.ui.button(label="Different thread", style=discord.ButtonStyle.gray)
    async def different_thread(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(AppendModal(self.bot, self.draft))


class EditTitleModal(discord.ui.Modal, title="Edit Post Title"):
    def __init__(self, bot: ArchiverBot, thread: discord.Thread):
        super().__init__()
        self.bot = bot
        self.thread = thread
        self.title_input = discord.ui.TextInput(label="Title", default=thread.name)
        self.add_item(self.title_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await defer(interaction)
        await self.bot.services.approvals.request(
            "edit_thread_title",
            interaction.user,
            target_thread_id=self.thread.id,
            proposed_title=self.title_input.value,
            description=(
                f"{interaction.user.mention} wants to rename {self.thread.jump_url}\n"
                f"From: {self.thread.name}\nTo: {self.title_input.value}"
            ),
        )
        await interaction.followup.send("Thread title change request sent.", ephemeral=True)


class ArchiveCog(commands.Cog):
    def __init__(self, bot: ArchiverBot):
        self.bot = bot
        self.edit_ctx = app_commands.ContextMenu(name="Edit", callback=self.edit_message)
        self.delete_ctx = app_commands.ContextMenu(name="Delete", callback=self.delete_message)
        self.publish_ctx = app_commands.ContextMenu(name="Publish post", callback=self.publish_post)
        self.append_ctx = app_commands.ContextMenu(name="Append post", callback=self.append_post)
        bot.tree.add_command(self.edit_ctx)
        bot.tree.add_command(self.delete_ctx)
        bot.tree.add_command(self.publish_ctx)
        bot.tree.add_command(self.append_ctx)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.edit_ctx.name, type=self.edit_ctx.type)
        self.bot.tree.remove_command(self.delete_ctx.name, type=self.delete_ctx.type)
        self.bot.tree.remove_command(self.publish_ctx.name, type=self.publish_ctx.type)
        self.bot.tree.remove_command(self.append_ctx.name, type=self.append_ctx.type)

    @app_commands.command(name="send", description="Send a message via the bot to the current channel")
    @app_commands.describe(has_embed="Enable embed fields")
    @app_commands.check(has_higher_role)
    async def send(self, interaction: discord.Interaction, has_embed: bool = False) -> None:
        await interaction.response.send_modal(SendModal(self.bot, interaction.channel, has_embed))

    @app_commands.check(has_higher_role)
    async def edit_message(self, interaction: discord.Interaction, message: discord.Message) -> None:
        if message.author != interaction.client.user:
            await respond(interaction, "Only bot messages can be edited through this command.")
            return
        await interaction.response.send_modal(EditMessageModal(self.bot, message))

    @app_commands.check(has_higher_role)
    async def delete_message(self, interaction: discord.Interaction, message: discord.Message) -> None:
        if message.author != interaction.client.user:
            await respond(interaction, "Only bot messages can be deleted through this command.")
            return
        await defer(interaction)
        await self.bot.services.approvals.request(
            "delete_message",
            interaction.user,
            target_channel_id=interaction.channel_id,
            target_message_id=message.id,
            description=f"{interaction.user.mention} wants to delete {message.jump_url}",
        )
        await interaction.followup.send("Message deletion request sent.", ephemeral=True)

    @app_commands.check(has_higher_role)
    async def publish_post(self, interaction: discord.Interaction, message: discord.Message) -> None:
        await interaction.response.send_modal(PublishModal(self.bot, message))

    @app_commands.check(has_higher_role)
    async def append_post(self, interaction: discord.Interaction, message: discord.Message) -> None:
        last_thread_id = (await self.bot.services.state.get()).last_archive_thread_id
        if last_thread_id is None:
            await interaction.response.send_modal(AppendModal(self.bot, message))
            return
        last_thread = interaction.client.get_channel(last_thread_id)
        if not isinstance(last_thread, discord.Thread):
            await interaction.response.send_modal(AppendModal(self.bot, message))
            return
        await interaction.response.send_message(
            f"Append to **{last_thread.name}** or choose a different thread?",
            view=AppendPrompt(self.bot, message, last_thread),
            ephemeral=True,
        )

    @app_commands.command(name="delete_post", description="Request deletion of an archive post")
    @app_commands.check(has_higher_role)
    async def delete_post(self, interaction: discord.Interaction, thread: discord.Thread) -> None:
        if not self._is_archive_thread(thread):
            await respond(interaction, "That is not an archive thread.")
            return
        await defer(interaction)
        await self.bot.services.approvals.request(
            "delete_thread",
            interaction.user,
            target_thread_id=thread.id,
            description=f"{interaction.user.mention} wants to delete {thread.jump_url}",
        )
        await interaction.followup.send("Thread deletion request sent.", ephemeral=True)

    @app_commands.command(name="edit_post_title", description="Request an archive post title edit")
    @app_commands.check(has_higher_role)
    async def edit_post_title(self, interaction: discord.Interaction, thread: discord.Thread) -> None:
        if not self._is_archive_thread(thread):
            await respond(interaction, "That is not an archive thread.")
            return
        await interaction.response.send_modal(EditTitleModal(self.bot, thread))

    @app_commands.command(name="grant_role", description="Grant archived designer or submitter role")
    @app_commands.choices(
        role=[
            app_commands.Choice(name="Archived Designer", value=1),
            app_commands.Choice(name="Submitter", value=2),
        ]
    )
    @app_commands.check(has_higher_role)
    async def grant_role(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        role: app_commands.Choice[int],
    ) -> None:
        role_id = (
            self.bot.settings.roles.archived_designer
            if role.value == 1
            else self.bot.settings.roles.submitter
        )
        await defer(interaction)
        await self.bot.services.archive.grant_role(interaction.guild, member, role_id)
        await interaction.followup.send("Role granted.", ephemeral=True)

    def _is_archive_thread(self, thread: discord.Thread) -> bool:
        parent = thread.parent
        return bool(
            isinstance(parent, discord.ForumChannel)
            and parent.category_id not in self.bot.settings.categories.non_archive
        )


async def setup(bot: ArchiverBot) -> None:
    await bot.add_cog(ArchiveCog(bot))
