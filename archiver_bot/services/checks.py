from __future__ import annotations

import discord


def _role_ids(interaction: discord.Interaction) -> set[int]:
    return {role.id for role in getattr(interaction.user, "roles", [])}


async def has_moderator_role(interaction: discord.Interaction) -> bool:
    return interaction.client.settings.roles.moderator in _role_ids(interaction)


async def has_higher_role(interaction: discord.Interaction) -> bool:
    return bool(interaction.client.settings.roles.higher & _role_ids(interaction))


async def has_staff_role(interaction: discord.Interaction) -> bool:
    return bool(interaction.client.settings.roles.staff & _role_ids(interaction))
