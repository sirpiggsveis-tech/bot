"""Slash-command reference for the control panel (mirrors scriptt.AI_COMMAND_MAP)."""

from __future__ import annotations

COMMAND_MAP: list[dict[str, object]] = [
    {
        "category": "Voice & messages",
        "commands": [
            {
                "name": "order",
                "usage": "/order",
                "summary": "Join voice channel(s) and speak via TTS.",
                "access": "Everyone",
                "panel": "/messaging",
            },
            {
                "name": "say",
                "usage": "/say",
                "summary": "Send a red embed message to a text channel.",
                "access": "Everyone",
                "panel": "/messaging",
            },
            {
                "name": "purge",
                "usage": "/purge amount:<1-50>",
                "summary": "Delete recent messages in a text channel.",
                "access": "Manage Messages",
                "panel": "/messaging",
            },
        ],
    },
    {
        "category": "PD mode",
        "commands": [
            {
                "name": "pdconfig",
                "usage": "/pdconfig",
                "summary": "Configure lock role and channels for PD mode.",
                "access": "Manage Channels",
                "panel": "/pd-mode",
            },
            {
                "name": "pdconfigclear",
                "usage": "/pdconfigclear",
                "summary": "Clear PD config; unlock if active.",
                "access": "Manage Channels",
                "panel": "/pd-mode",
            },
            {
                "name": "pdon",
                "usage": "/pdon",
                "summary": "Lock channels and announce PD.",
                "access": "Manage Channels",
                "panel": "/pd-mode",
            },
            {
                "name": "pdoff",
                "usage": "/pdoff",
                "summary": "Unlock PD channels.",
                "access": "Manage Channels",
                "panel": "/pd-mode",
            },
        ],
    },
    {
        "category": "Auto-role",
        "commands": [
            {
                "name": "autoroleconfig view",
                "usage": "/autoroleconfig view",
                "summary": "Show join roles, reaction triggers, nickname.",
                "access": "Administrator",
                "panel": "/auto-roles",
            },
            {
                "name": "autoroleconfig join",
                "usage": "/autoroleconfig join",
                "summary": "Roles granted on member join.",
                "access": "Administrator",
                "panel": "/auto-roles",
            },
            {
                "name": "autoroleconfig reaction",
                "usage": "/autoroleconfig reaction",
                "summary": "Staff reaction → roles for message author.",
                "access": "Administrator",
                "panel": "/auto-roles",
            },
            {
                "name": "autoroleconfig nickname",
                "usage": "/autoroleconfig nickname",
                "summary": "Auto-nickname for new members.",
                "access": "Administrator",
                "panel": "/auto-roles",
            },
            {
                "name": "autoroleconfig clear",
                "usage": "/autoroleconfig clear",
                "summary": "Wipe all auto-role settings.",
                "access": "Administrator",
                "panel": "/auto-roles",
            },
        ],
    },
    {
        "category": "Squads",
        "commands": [
            {
                "name": "squadconfig",
                "usage": "/squadconfig",
                "summary": "Squad VC category and staff roles.",
                "access": "Administrator",
                "panel": "/squads",
            },
            {
                "name": "squadcreate",
                "usage": "/squadcreate",
                "summary": "Create a private squad voice channel.",
                "access": "Manage Channels",
                "panel": "/squads",
            },
            {
                "name": "squaddelete",
                "usage": "/squaddelete",
                "summary": "Delete a squad voice channel.",
                "access": "Manage Channels",
                "panel": "/squads",
            },
        ],
    },
    {
        "category": "ORBAT",
        "commands": [
            {
                "name": "orbatview",
                "usage": "/orbatview",
                "summary": "Full ORBAT or one unit roster.",
                "access": "Everyone",
                "panel": "/",
            },
            {
                "name": "orbatcard",
                "usage": "/orbatcard",
                "summary": "Member service record card.",
                "access": "Everyone",
                "panel": "/orbat/members",
            },
            {
                "name": "orbatconfig",
                "usage": "/orbatconfig",
                "summary": "Units, ranks, positions, settings hub.",
                "access": "Administrator",
                "panel": "/orbat/units",
            },
            {
                "name": "orbatmember",
                "usage": "/orbatmember",
                "summary": "Edit member unit, rank, position, note.",
                "access": "Administrator",
                "panel": "/orbat/members",
            },
            {
                "name": "orbatsync",
                "usage": "/orbatsync",
                "summary": "Re-pull members from Discord.",
                "access": "Administrator",
                "panel": "/",
            },
            {
                "name": "orbatclear",
                "usage": "/orbatclear",
                "summary": "Delete all units (members kept).",
                "access": "Administrator",
                "panel": "/orbat/units",
            },
        ],
    },
    {
        "category": "Panel sync",
        "commands": [
            {
                "name": "botpanel sync",
                "usage": "/botpanel sync",
                "summary": "Pull channels, roles, and all members into the panel database.",
                "access": "Administrator",
                "panel": "/orbat/settings",
            },
            {
                "name": "orbatsync",
                "usage": "/orbatsync",
                "summary": "Same as /botpanel sync (full server snapshot).",
                "access": "Administrator",
                "panel": "/orbat/members",
            },
        ],
    },
    {
        "category": "Utility",
        "commands": [
            {
                "name": "help",
                "usage": "/help",
                "summary": "Command list in Discord.",
                "access": "Everyone",
                "panel": "/commands",
            },
        ],
    },
]
