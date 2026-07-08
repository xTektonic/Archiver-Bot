from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class RoleIds:
    moderator: int = 1161821342514036776
    archiver: int = 1162049503503863808
    helper: int = 1378983578251300934
    archived_designer: int = 1172971681527111700
    submitter: int = 1172971622240620594
    no_chat: int = 1390906563505684591

    @property
    def higher(self) -> set[int]:
        return {self.moderator, self.archiver}

    @property
    def staff(self) -> set[int]:
        return {self.moderator, self.archiver, self.helper}


@dataclass(frozen=True)
class ChannelIds:
    log: int = 1343664979831820368
    archiver_chat: int = 1163451952827478056
    bot_dm_thread: int = 1473708689461477641
    submissions: int = 1161814713496256643
    submissions_tracker: int = 1394308822926889060
    development_forum: int = 1420135695800074260
    snapshot: int = 1353055573935132703
    archive_corrections: int = 1284851559947305052
    archive_updates: int = 1235473478371643412
    help_forum: int = 1378037810975473846
    faq: int = 1365424262810177546

    @property
    def allowed_pin_forums(self) -> set[int]:
        return {self.development_forum, self.submissions}

    @property
    def managed_forums(self) -> set[int]:
        return {self.submissions, self.archive_corrections, self.help_forum}


@dataclass(frozen=True)
class TagIds:
    rejected: int = 1183092798908534804
    accepted: int = 1183092754834788414
    archived: int = 1197302327065972776
    inactive: int = 1430378085332815872
    unsolved: int = 1378041211150929990
    pending_submission: int = 1257162647040819250
    pending_correction: int = 1284913422487654612

    @property
    def resolved(self) -> set[int]:
        return {self.rejected, self.accepted}

    @property
    def pending(self) -> set[int]:
        return {self.pending_submission, self.pending_correction, self.unsolved, self.accepted}


@dataclass(frozen=True)
class CategoryIds:
    non_archive: set[int] = field(
        default_factory=lambda: {
            1355756508394160229,
            1184256131141484724,
            1163087048173965402,
            1378966923152195655,
            1182932696662560798,
            1374225342948053032,
            1161803873317568583,
        }
    )
    main_archive: set[int] = field(
        default_factory=lambda: {
            1162047368917692460,
            1162048271393505440,
            1162047650355482777,
            1162355688014622800,
            1162094819875762236,
            1173052495346552892,
        }
    )


@dataclass(frozen=True)
class CopyText:
    no_chat_image: str = (
        "https://cdn.discordapp.com/attachments/1315522702492172300/"
        "1466707151472033954/image.png"
    )
    how_to_pin_image: str = (
        "https://cdn.discordapp.com/attachments/1331670749471047700/"
        "1428615699378733108/how_to_pin.png"
    )
    no_chat_timeout_message: str = (
        "Your message on TMCC has been blocked as you didn't select the right onboarding "
        "option when joining the server and your account is suspected to be a bot.\n\n"
        'If you wish to partake in the server fully, select the correct option in "Channels '
        'and Roles" and follow the server rules.'
    )
    submission_prompt: str = (
        "- The submitter of the post can pin messages in the thread using the message command.\n"
        "- This thread is for archival-related discussion only. No development or help questions are allowed.\n"
        "- Please be patient. The archival team will review this post as soon as possible."
    )
    help_forum_prompt: str = (
        "- The submitter can mark posts as solved by using `/tag_selector`.\n"
        "- Refer to the guide for faster and better answers.\n"
        "- Please be patient and polite. Helpers are volunteers."
    )


@dataclass(frozen=True)
class BotSettings:
    token: str
    data_dir: Path
    roles: RoleIds = field(default_factory=RoleIds)
    channels: ChannelIds = field(default_factory=ChannelIds)
    tags: TagIds = field(default_factory=TagIds)
    categories: CategoryIds = field(default_factory=CategoryIds)
    copy: CopyText = field(default_factory=CopyText)
    discord_char_limit: int = 2000
    approval_timeout_seconds: int = 3600

def load_settings() -> BotSettings:
    token = os.getenv("DISCORD_BOT_TOKEN", "")
    data_dir = Path("data")
    return BotSettings(
        token=token,
        data_dir=data_dir,
    )
