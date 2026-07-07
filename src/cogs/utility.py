from __future__ import annotations

import os
import sys

import discord
from discord import app_commands
from discord.ext import commands

from app import ArchiverBot
from services.checks import has_higher_role, has_moderator_role
from services.safe_discord import defer, respond


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
    @app_commands.check(has_moderator_role)
    async def restart(self, interaction: discord.Interaction) -> None:
        await defer(interaction)
        await interaction.followup.send("Restarting...", ephemeral=True)
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


async def setup(bot: ArchiverBot) -> None:
    await bot.add_cog(UtilityCog(bot))
