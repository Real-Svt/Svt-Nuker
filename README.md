<div align="center">

# SvT-Nuker

**A fast, safe-by-default Discord server nuker for the terminal.**

Purple/blue console UI · backup before destruction · one-command full nuke · restore from JSON

[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![discord.py](https://img.shields.io/badge/discord.py-2.3.2%2B-5865F2?logo=discord&logoColor=white)](https://github.com/Rapptz/discord.py)
[![License](https://img.shields.io/badge/license-MIT-A855F7)](#license)

</div>

---

## What it is

SvT-Nuker is an interactive CLI tool that wipes and rebuilds a Discord server from your terminal. It talks to Discord through a bot token, shows you the guild's permissions and size, and lets you run a full destruction cycle — or just one step of it — from a numbered menu.

It never nukes blind: a JSON backup of channels, roles and emojis is written **before** anything is deleted, and every run leaves a report in `logs/`.

## Features

- **Full nuke in one flow** — backup → delete channels → delete roles → ban members → create channels → spam → rename server
- **Per-step actions** — run only the delete, ban, create or rename step you want
- **Automatic backup** — full structure dump to `backups/` before destruction, plus a run report in `logs/`
- **Restore** — rebuild channels, categories and roles from any saved backup
- **Dry-run mode** — print the exact plan and change nothing
- **Permission audit** — checks the bot's role and flags missing permissions before you commit
- **Guild picker** — by ID, by name substring, or `list` to browse
- **Concurrency control** — configurable delay and worker count, with jitter to stay under rate limits
- **Ctrl+C safe** — stops immediately, still writes the report
- **Webhook spam fallback** — uses webhooks when available, plain sends otherwise
- **Colored UI** — purple/blue gradient logo, no external dependencies for it; respects `NO_COLOR`

## Menu
