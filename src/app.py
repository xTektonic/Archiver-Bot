from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from config.settings import BotSettings, load_settings
from services.approvals import ApprovalService
from services.archive import ArchivePublishingService
from services.audit import AuditLogService
from services.container import ServiceContainer
from services.maintenance import MaintenanceJobService
from services.moderation import ModerationService
from services.parser_service import ParserService
from services.safe_discord import respond
from services.state import StateService
from services.tracker import SubmissionTrackerService
from storage.state_store import StateStore


class ArchiverBot(commands.Bot):
    settings: BotSettings
    services: ServiceContainer
    _approvals_restored: bool


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
    services = ServiceContainer(
        audit=audit,
        state=state_service,
        approvals=ApprovalService(bot, settings, state_service, audit),
        tracker=SubmissionTrackerService(bot, settings, state_service, audit),
        archive=ArchivePublishingService(bot, settings, state_service, audit),
        moderation=ModerationService(bot, settings, state_service, audit),
        parser=ParserService(bot, settings),
        maintenance=MaintenanceJobService(bot, settings),
    )
    bot.services = services
    bot._approvals_restored = False

    async def setup_hook() -> None:
        await state_service.initialize()
        await bot.load_extension("cogs.utility")
        await bot.load_extension("cogs.message_actions")
        await bot.load_extension("cogs.submissions")
        await bot.load_extension("cogs.archive")
        await bot.load_extension("cogs.management")
        await bot.load_extension("cogs.parser")
        await bot.tree.sync()

    async def on_ready() -> None:
        if not bot._approvals_restored and isinstance(services.approvals, ApprovalService):
            bot._approvals_restored = True
            await services.approvals.restore_pending_views()

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

    bot.setup_hook = setup_hook  # type: ignore[method-assign]
    bot.on_ready = on_ready  # type: ignore[attr-defined]
    bot.tree.on_error = on_app_command_error  # type: ignore[method-assign]
    return bot


async def run_bot() -> None:
    bot = create_bot()
    if not bot.settings.token:
        raise RuntimeError("DISCORD_BOT_TOKEN is required.")
    async with bot:
        await bot.start(bot.settings.token)
