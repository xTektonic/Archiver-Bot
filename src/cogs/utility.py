from __future__ import annotations

import os
import sys

import discord
from discord import app_commands
from discord.ext import commands

from app import ArchiverBot
from services.checks import has_higher_role, has_moderator_role, has_staff_role
from services.safe_discord import defer, respond

OTHER_ARCHIVES = """**Storage Tech** - Item sorting and storage
**Storage Catalog** - Development-oriented storage tech
**Slimestone Tech Archive** - Flying machines and movable contraptions
**Minecraft Tech Discord Recollector** - Index of TMC SMP and archive servers
**TNT Archive** - TNT cannon tech and projectile physics
**Tree Huggers** - Tree farm development
**Huge Fungi Huggers** - Nether tree and foliage farm development
**Cartchives** - Piston bolts and minecart based tech
**Wither Archive** - Wither tech archive and development
**Saints of Suppression** - Light and update suppression and skipping
**Autocrafting Archive** - Crafters and modded autocrafting table tech
**Computational Minecraft Archive** - TMC-oriented computational redstone
**TMC Resources Archive** - Compilation of TMC tricks, links, and resources
**Luke's Video Archive** - Chinese (BiliBili) tech recollector
**Open Redstone** - Computational redstone community
**Piston Door Catalogue** - Piston door index
**Structureless Superflat Archive** - Structureless superflat tech
**Russian Technical Minecraft Catalogue** - Russian TMC archive
**Technical Bedrock Archive** - Bedrock TMC archive"""

COMMANDS_LIST = """## Helper commands:
**/tag_selector**: Set the tags of the current submission, correction, or help forum post
**Pin** *(App command)*: Pin the selected message
## Archiver commands:
**/close_resolved**: Close posts marked solved, rejected, archived, inactive, or off-topic
**/open_archived**: Open archived archive posts and pending managed posts
**/delete_post**: Send a delete request to archiver chat for another archiver to approve
**/edit_post_title**: Send a title edit request to archiver chat for another archiver to approve
**/track**: Make a post in the submission tracker for the current submission post
**/tracker_list**: Rebuild the submission tracker summary
**/parse_post**: Parse one archive post
**/parse_channel**: Parse all posts in one archive forum
**/parse_archive**: Parse all configured archive forums
**Edit** *(App command)*: Edit a message sent by the bot
**Delete** *(App command)*: Send a delete request to archiver chat for another archiver to approve
**Publish post** *(App command)*: Create a new thread in the archives with the selected message as the starter
**Append post** *(App command)*: Append the selected message to an existing archive post
## Mod commands:
**/send**: Send a message or embed through the bot to the current channel
**/restart**: Restart the bot
**/servers**: Send the list of other archive servers to the current channel
**/guild_list**: List the first 10 servers the bot is in
**/leave**: Make the bot leave a server by ID"""


class UtilityCog(commands.Cog):
    def __init__(self, bot: ArchiverBot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print(f"Archiver Bot online as {self.bot.user}")
        await self.bot.services.audit.log(
            "Archiver Bot Online", colour=discord.Color.green()
        )

    @app_commands.command(name="guild_list", description="List the first 10 servers the bot is in")
    @app_commands.check(has_moderator_role)
    async def guild_list(self, interaction: discord.Interaction) -> None:
        lines = [
            f"- **{guild.name}** (`{guild.id}`) - {guild.member_count} members"
            for guild in self.bot.guilds[:10]
        ]
        await respond(
            interaction,
            embed=discord.Embed(
                title=f"Installed Servers ({len(self.bot.guilds)})",
                description="\n".join(lines) or "The bot is not in any servers.",
            ),
        )

    @app_commands.command(name="leave", description="Leave the server with the given ID")
    @app_commands.check(has_moderator_role)
    async def leave(self, interaction: discord.Interaction, server_id: str) -> None:
        try:
            guild = await self.bot.fetch_guild(int(server_id))
            name = guild.name
            await guild.leave()
            await respond(interaction, f"Successfully left **{name}** (`{server_id}`).")
            await self.bot.services.audit.log(
                "Bot left server", f"Server: {name}\nID: `{server_id}`\nBy: {interaction.user.mention}"
            )
        except Exception as exc:
            await respond(interaction, f"Error trying to leave server: {exc}")

    @app_commands.command(name="restart", description="Restart the bot process")
    @app_commands.describe(sync_commands="Sync commands before restarting")
    @app_commands.check(has_moderator_role)
    async def restart(self, interaction: discord.Interaction, sync_commands: bool = False) -> None:
        await defer(interaction)
        if sync_commands:
            await self.bot.tree.sync()
        message = "Commands synced. Restarting..." if sync_commands else "Restarting..."
        await interaction.followup.send(message, ephemeral=True)
        os.execv(sys.executable, [sys.executable, *sys.argv])

    @app_commands.command(name="fetch_links", description="Return attachment links from a message")
    @app_commands.check(has_higher_role)
    async def fetch_links(self, interaction: discord.Interaction, message_id: str) -> None:
        try:
            message = await interaction.channel.fetch_message(int(message_id))
            links = [f"- <{attachment.url.split('?')[0]}>" for attachment in message.attachments]
            await respond(
                interaction,
                "The selected message has no attachments."
                if not links
                else "Attachment links:\n" + "\n".join(links),
            )
        except Exception as exc:
            await respond(interaction, f"Error while running the command: {exc}")

    @app_commands.command(name="servers", description="Send the list of other archive servers")
    @app_commands.check(has_moderator_role)
    async def servers(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="Other Archive Servers",
            description=OTHER_ARCHIVES,
            color=discord.Color.light_embed(),
        )
        await interaction.channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        await respond(interaction, "Embed sent.")

    @app_commands.command(name="help", description="Send the Archiver Bot command list")
    @app_commands.check(has_staff_role)
    async def help(self, interaction: discord.Interaction) -> None:
        await respond(interaction, embed=discord.Embed(description=COMMANDS_LIST))


async def setup(bot: ArchiverBot) -> None:
    await bot.add_cog(UtilityCog(bot))
