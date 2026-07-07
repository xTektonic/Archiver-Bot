from __future__ import annotations

import discord


async def respond(
    interaction: discord.Interaction,
    content: str | None = None,
    *,
    embed: discord.Embed | None = None,
    view: discord.ui.View | None = None,
    ephemeral: bool = True,
) -> None:
    kwargs = {"content": content, "embed": embed, "view": view, "ephemeral": ephemeral}
    kwargs = {key: value for key, value in kwargs.items() if value is not None}
    if interaction.response.is_done():
        await interaction.followup.send(**kwargs)
    else:
        await interaction.response.send_message(**kwargs)


async def defer(interaction: discord.Interaction, *, ephemeral: bool = True) -> None:
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=ephemeral)


def no_mentions() -> discord.AllowedMentions:
    return discord.AllowedMentions.none()


def ensure_content_safe(content: str, *, limit: int = 2000) -> None:
    if len(content) > limit:
        raise ValueError(f"Message content is {len(content)} characters; limit is {limit}.")
    lowered = content.lower()
    if "@everyone" in lowered or "@here" in lowered:
        raise ValueError("Message content may not contain @everyone or @here.")
