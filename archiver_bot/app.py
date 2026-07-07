from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from archiver_bot.config.settings import BotSettings, load_settings
from archiver_bot.services.approvals import ApprovalService
from archiver_bot.services.archive import ArchivePublishingService
from archiver_bot.services.audit import AuditLogService
from archiver_bot.services.container import ServiceContainer
from archiver_bot.services.maintenance import MaintenanceJobService
from archiver_bot.services.moderation import ModerationService
from archiver_bot.services.parser_service import ParserService
from archiver_bot.services.safe_discord import respond
from archiver_bot.services.state import StateService
from archiver_bot.services.tracker import SubmissionTrackerService
from archiver_bot.storage.state_store import StateStore


class ArchiverBot(commands.Bot):
    settings: BotSettings
    services: ServiceContainer


def create_bot(settings: BotSettings | None = None) -> ArchiverBot:
    load_dotenv()
    settings = settings or load_settings()
    intents = discord.Intents.none()
    intents.guilds = True
    intents.members = True
    intents.messages = True
    intents.message_content = True
    bot = ArchiverBot(command_prefix="!", intents=intents)
    bot.settings = settings

    state_service = StateService(StateStore(settings.data_dir))
    audit = AuditLogService(bot, settings)
    services = ServiceContainer(audit=audit, state=state_service)
    services.approvals = ApprovalService(bot, settings, state_service, audit)
    services.tracker = SubmissionTrackerService(bot, settings, state_service, audit)
    services.archive = ArchivePublishingService(bot, settings, state_service, audit)
    services.moderation = ModerationService(bot, settings, state_service, audit)
    services.parser = ParserService(bot, settings)
    services.maintenance = MaintenanceJobService(bot, settings)
    bot.services = services

    async def setup_hook() -> None:
        await state_service.initialize()
        await bot.load_extension("archiver_bot.cogs.utility")
        await bot.load_extension("archiver_bot.cogs.message_actions")
        await bot.load_extension("archiver_bot.cogs.submissions")
        await bot.load_extension("archiver_bot.cogs.archive")
        await bot.load_extension("archiver_bot.cogs.management")
        await bot.load_extension("archiver_bot.cogs.parser")
        if isinstance(services.approvals, ApprovalService):
            await services.approvals.restore_pending_views()
        if settings.sync_commands:
            await bot.tree.sync()

    async def on_app_command_error(
        interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(
            error,
            app_commands.MissingRole | app_commands.MissingAnyRole | app_commands.CheckFailure,
        ):
            await respond(
                interaction,
                "Sorry, you do not have the required role to use this command.",
                ephemeral=True,
            )
            return
        await respond(interaction, f"An error occurred: {error}", ephemeral=True)
        await audit.log("Command error", f"{interaction.command}: {error}", colour=discord.Color.red())

    bot.setup_hook = setup_hook
    bot.tree.on_error = on_app_command_error
    return bot


async def run_bot() -> None:
    bot = create_bot()
    if not bot.settings.token:
        raise RuntimeError("DISCORD_BOT_TOKEN is required.")
    async with bot:
        await bot.start(bot.settings.token)
