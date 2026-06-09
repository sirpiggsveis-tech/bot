"""Web control-panel API package for the Discord bot.

Runs in the same process as the discord.py bot (see project-root run.py) and
exposes a REST API consumed by the Cloudflare Pages frontend. The SQLite
database (orbat_db) remains the single source of truth.
"""
