from __future__ import annotations

import random

import discord
from discord.ext import commands

from app import ArchiverBot

RANDOM_REPLIES = [
    "You rang?",
    "Beep boop",
    "Don't distract me while I'm working",
    "Sup?",
    "Perchance",
]


class MessageActionsCog(commands.Cog):
    def __init__(self, bot: ArchiverBot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author == self.bot.user:
            return
        if isinstance(message.channel, discord.DMChannel):
            await self.bot.services.moderation.forward_dm(message)
            return
        if message.flags.is_crossposted and message.channel.id == self.bot.settings.channels.snapshot:
            await self._pin_snapshot_message(message)
        await self.bot.services.moderation.handle_no_chat_user(message)
        if self.bot.user and self.bot.user in message.mentions:
            await message.reply(content=random.choice(RANDOM_REPLIES), mention_author=False)
        if isinstance(message.channel, discord.Thread) and message.id == message.channel.id:
            await self._handle_first_thread_message(message)
        await self.bot.process_commands(message)

    async def _handle_first_thread_message(self, message: discord.Message) -> None:
        parent_id = message.channel.parent_id
        if parent_id == self.bot.settings.channels.submissions:
            await message.pin()
            embed = discord.Embed(
                title="Thank you for your submission!",
                description=self.bot.settings.copy.submission_prompt,
            )
            embed.set_image(url=self.bot.settings.copy.how_to_pin_image)
            await message.channel.send(embed=embed)
        elif parent_id == self.bot.settings.channels.help_forum:
            await message.pin()
            await message.channel.send(
                embed=discord.Embed(
                    title="Thank you for submitting your question!",
                    description=self.bot.settings.copy.help_forum_prompt,
                )
            )

    async def _pin_snapshot_message(self, message: discord.Message) -> None:
        try:
            pinned_messages = await message.channel.pins()
            if pinned_messages:
                await pinned_messages[-1].unpin()
            await message.pin()
            await self.bot.services.audit.log(
                "Snapshot update message pinned",
                f"In: {message.channel.jump_url}",
            )
        except discord.HTTPException as exc:
            await self.bot.services.audit.log(
                "Snapshot pin failed",
                f"In: {message.channel.jump_url}\nError: {exc}",
                colour=discord.Color.red(),
            )


async def setup(bot: ArchiverBot) -> None:
    await bot.add_cog(MessageActionsCog(bot))
