from __future__ import annotations

import asyncio
import os
import sys

import discord
from discord import app_commands
from discord.ext import commands

from app import ArchiverBot
from services.checks import has_higher_role, has_moderator_role, has_staff_role
from services.safe_discord import defer, respond

OTHER_ARCHIVES = (
    "<:std:1399677131004580051> [**Storage Tech**](https://discord.gg/JufJ6uf) Item sorting and storage\n"
    "<:std2:1469724306446614650> [**Storage Catalog**](https://discord.gg/hztJMTsx2m) Development-oriented storage tech\n"
    "<:slime:1399677082472153098> [**Slimestone Tech Archive**](https://discord.gg/QQX5RBaHzK) Flying machines and movable contraptions\n"
    "<:mtdr:1399677041946923061> [**Minecraft Tech Discord Recollector**](https://discord.gg/UT8ns46As9) Index of TMC SMP and archive servers\n"
    "<:tnt:1399677165104009226> [**TNT Archive**](https://discord.gg/vPyUBcdmZV) TNT cannon tech and projectile physics\n"
    "<:tree:1399677175803805696> [**Tree Huggers**](https://discord.gg/8bUbuuS) Tree farm development\n"
    "<:hfh:1399677019767312404> [**Huge Fungi Huggers**](https://discord.gg/EKKkyfcPPV) Nether tree and foliage farm development\n"
    "<:cart:1399676987928219739> [**Cartchives**](https://discord.gg/8nGNTewveC) Piston bolts and minecart based tech\n"
    "<:wither:1399677185870008330> [**Wither Archive**](https://discord.gg/Ea28MyKB3J) Wither tech archive and development \n"
    "<:sos:1399677094169940139> [**Saints of Suppression**](https://discord.gg/xa7QWAeAng) Light and update suppression and skipping\n"
    "<:aca:1399676962464600155> [**Autocrafting Archive**](https://discord.gg/guZdbQ9KQe) Crafters and modded autocrafting table tech\n"
    "<:comp:1399677007406698516> [**Computational Minecraft Archive**](https://discord.gg/jSe4jR5Kx7) TMC-oriented computational redstone\n"
    "<:tmcra:1399677154702135328> [**TMC Resources Archive**](https://discord.gg/E4q8WDUc7k) Compilation of TMC tricks, links, and resources\n"
    "<:luke:1399677029707808768> [**Luke's Video Archive**](https://discord.gg/KTDacw6JYk) Chinese (BiliBili) tech recollector\n"
    "<:ore:1399677056584781946> [**Open Redstone**](https://discord.gg/zjWRarN) (DiscOREd) Computational redstone community\n"
    "<:squid:1399677105033183232> [**Piston Door Catalogue**](https://discord.gg/Khj8MyA) (Redstone Squid's Records Catalogue) Piston door index\n"
    "<:ssf:1399677117884534875> [**Structureless Superflat Archive**](https://discord.gg/96Qm6e2AVH) (SSf Archive) Structureless superflat tech\n"
    "<:rta:1399677071919288342> [**Russian Technical Minecraft Catalogue**](https://discord.com/invite/bMZYHnXnCA) (RTMC \u041a\u0430\u0442\u0430\u043b\u043e\u0433) Russian TMC archive\n"
    "<:tba:1399677142660546620> [**Technical Bedrock Archive**](https://discord.com/invite/technical-bedrock-archive-715182000440475648) Bedrock TMC archive"
)

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
**/restart**: Optionally update from a branch, sync commands, then restart
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
    @app_commands.describe(
        update="Pull updates before restarting",
        branch="Branch to pull from when updating",
    )
    @app_commands.check(has_moderator_role)
    async def restart(
        self,
        interaction: discord.Interaction,
        update: bool = True,
        branch: str = "main",
    ) -> None:
        await defer(interaction)
        if update:
            await interaction.followup.send(f"Updating from `{branch}`...", ephemeral=True)
            process = await asyncio.create_subprocess_exec(
                "git",
                "pull",
                "origin",
                branch,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                await interaction.followup.send(
                    "Update failed:\n"
                    f"```{stderr.decode(errors='replace').strip()[:1800]}```",
                    ephemeral=True,
                )
                return
            await self.bot.tree.sync()
            await interaction.followup.send(
                "Update complete and commands synced:\n"
                f"```{stdout.decode(errors='replace').strip()[:1700]}```\nRestarting...",
                ephemeral=True,
            )
        else:
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
