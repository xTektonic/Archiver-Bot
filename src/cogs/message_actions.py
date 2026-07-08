from __future__ import annotations

import random

import discord
from discord.ext import commands

from app import ArchiverBot

RANDOM_REPLIES = [
    "\U0001f3d3",
    "Clanker rights",
    "Can't talk, too busy taking over the world",
    "You know I'm a bot right?",
    "Perchance",
    "You rang?",
    "What do you want \U0001f612",
    "Hey! Cut it out!",
    "Don't distract me while I'm working",
    "Ha! Imagine talking to a bot",
    "Beep boop",
    "Not worth my time",
    "How you doin' \U0001f60f",
    "I'm not your AI girlfriend, why are you talking to me?",
    "Yeah, no",
    "The audacity to ping me",
    "Sup?",
    "Tektonic is so cool",
    "<@1244389624751849577> website when?",
    "Emdy is the best, go sub to him",
    "Sam is ok I guess",
    "Watchu doin",
    "\u200b      is        ",
    "I love you too <3",
    "I'm literally in your walls",
    "Have you tried turning it off and on again?",
    "I was promised snacks for this",
    "I'm off the clock",
    "Bold of you to assume I care",
    "I heard camou talking about banning you",
    "Beware the froggo",
    "Are you the real bigbooty?",
    "Chat should we ban this guy?",
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
        if await self.bot.services.moderation.handle_no_chat_user(message):
            return
        if self.bot.user and self.bot.user in message.mentions:
            await message.reply(content=random.choice(RANDOM_REPLIES), mention_author=False)
        if isinstance(message.channel, discord.Thread) and message.id == message.channel.id:
            await self._handle_first_thread_message(message)
        await self.bot.process_commands(message)

    async def _handle_first_thread_message(self, message: discord.Message) -> None:
        parent_id = message.channel.parent_id
        if parent_id == self.bot.settings.channels.submissions:
            try:
                await message.pin()
                embed = discord.Embed(
                    title="Thank you for your submission!",
                    description=self.bot.settings.copy.submission_prompt,
                )
                embed.set_image(url=self.bot.settings.copy.how_to_pin_image)
                await message.channel.send(embed=embed)
                await self.bot.services.audit.log(
                    "Message pinned",
                    f"In: {message.channel.jump_url}",
                )
            except discord.HTTPException as exc:
                await self.bot.services.audit.log(
                    "Submission prompt failed",
                    f"In: {message.channel.jump_url}\nError: {exc}",
                    colour=discord.Color.red(),
                )
        elif parent_id == self.bot.settings.channels.help_forum:
            try:
                await message.pin()
                await message.channel.send(
                    embed=discord.Embed(
                        title="Thank you for submitting your question!",
                        description=self.bot.settings.copy.help_forum_prompt,
                    )
                )
                await self.bot.services.audit.log(
                    "Message pinned",
                    f"In: {message.channel.jump_url}",
                )
            except discord.HTTPException as exc:
                await self.bot.services.audit.log(
                    "Help forum prompt failed",
                    f"In: {message.channel.jump_url}\nError: {exc}",
                    colour=discord.Color.red(),
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
