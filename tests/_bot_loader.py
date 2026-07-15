"""Shared helpers for importing bot.py in tests without running the Discord loop."""

from __future__ import annotations

import os
import sys
import types


def _decorator(*_args, **_kwargs):
    def wrap(func):
        setattr(func, "autocomplete", _decorator)
        setattr(func, "error", _decorator)
        setattr(func, "command", _decorator)
        return func

    return wrap


class _FakeBase:
    def __init__(self, *_args, **_kwargs):
        pass

    def __init_subclass__(cls, **_kwargs):
        pass

    def __call__(self, *_args, **_kwargs):
        return None

    def __getattr__(self, _name):
        return _FakeBase()


class _FakeEnum:
    def __getattr__(self, name):
        return name


class _FakeIntents:
    @classmethod
    def default(cls):
        return cls()


class _FakeEmbed(_FakeBase):
    def add_field(self, *_args, **_kwargs):
        return self

    def set_thumbnail(self, *_args, **_kwargs):
        return self

    def set_footer(self, *_args, **_kwargs):
        return self

    def set_image(self, *_args, **_kwargs):
        return self

    def set_author(self, *_args, **_kwargs):
        return self


class _FakeHTTPException(Exception):
    def __init__(self, message="HTTP error", *, status=500):
        super().__init__(message)
        self.status = status


class _FakeTree:
    command = staticmethod(_decorator)
    context_menu = staticmethod(_decorator)
    interaction_check = staticmethod(lambda func: func)

    def add_command(self, *_args, **_kwargs):
        return None

    async def sync(self, *_args, **_kwargs):
        return []

    def __getattr__(self, _name):
        return _decorator


class _FakeBot(_FakeBase):
    def __init__(self, *_args, **_kwargs):
        self.tree = _FakeTree()
        self.guilds = []
        self.user = None

    event = staticmethod(lambda func: func)
    command = staticmethod(_decorator)
    group = staticmethod(_decorator)
    listen = staticmethod(_decorator)

    def get_channel(self, *_args, **_kwargs):
        return None

    def get_guild(self, *_args, **_kwargs):
        return None

    def run(self, *_args, **_kwargs):
        return None


class _FakeGroup(_FakeBase):
    command = staticmethod(_decorator)

    def add_command(self, *_args, **_kwargs):
        return None


class _FakeChoice(_FakeBase):
    @classmethod
    def __class_getitem__(cls, _item):
        return cls


class _FakeLoop:
    def __init__(self, func):
        self.func = func

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)

    def start(self, *_args, **_kwargs):
        return None

    def is_running(self):
        return False

    def cancel(self):
        return None


def _install_discord_stubs():
    discord = types.ModuleType("discord")
    discord.Intents = _FakeIntents
    discord.Embed = _FakeEmbed
    discord.File = _FakeBase
    discord.Object = _FakeBase
    discord.Permissions = _FakeBase
    discord.PermissionOverwrite = _FakeBase
    discord.AllowedMentions = _FakeBase
    discord.SelectOption = _FakeBase
    discord.Forbidden = type("Forbidden", (Exception,), {})
    discord.NotFound = type("NotFound", (Exception,), {})
    discord.HTTPException = _FakeHTTPException
    discord.Color = _FakeEnum()
    discord.Colour = discord.Color
    discord.ButtonStyle = _FakeEnum()
    discord.TextStyle = _FakeEnum()
    discord.ChannelType = _FakeEnum()
    discord.InteractionType = _FakeEnum()
    discord.utils = types.SimpleNamespace(
        get=lambda iterable, **attrs: next(iter(iterable or []), None),
        utcnow=lambda: None,
    )

    for name in (
        "Attachment",
        "CategoryChannel",
        "Client",
        "Guild",
        "Interaction",
        "Member",
        "Message",
        "RawReactionActionEvent",
        "Role",
        "TextChannel",
        "Thread",
        "User",
    ):
        setattr(discord, name, type(name, (_FakeBase,), {}))

    ui = types.ModuleType("discord.ui")
    for name in ("Button", "Modal", "Select", "TextInput", "View"):
        setattr(ui, name, type(name, (_FakeBase,), {}))
    ui.button = _decorator
    ui.select = _decorator
    discord.ui = ui

    ext = types.ModuleType("discord.ext")
    commands = types.ModuleType("discord.ext.commands")
    commands.Bot = _FakeBot
    commands.Cog = type("Cog", (_FakeBase,), {})
    commands.Context = type("Context", (_FakeBase,), {})
    commands.when_mentioned = lambda *_args, **_kwargs: None
    commands.command = _decorator
    commands.group = _decorator
    commands.hybrid_command = _decorator
    commands.has_permissions = _decorator
    commands.is_owner = _decorator
    commands.autocomplete = _decorator
    commands.check = _decorator
    commands.choices = _decorator
    commands.default_permissions = _decorator
    commands.describe = _decorator
    commands.Group = _FakeGroup
    commands.Choice = _FakeChoice

    tasks = types.ModuleType("discord.ext.tasks")

    def loop(*_args, **_kwargs):
        return lambda func: _FakeLoop(func)

    tasks.loop = loop

    app_commands = types.ModuleType("discord.app_commands")
    app_commands.command = _decorator
    app_commands.autocomplete = _decorator
    app_commands.describe = _decorator
    app_commands.choices = _decorator
    app_commands.default_permissions = _decorator
    app_commands.checks = _FakeBase()
    app_commands.Group = _FakeGroup
    app_commands.Choice = _FakeChoice
    app_commands.Range = _FakeChoice
    app_commands.Transform = _FakeChoice
    app_commands.Transformer = type("Transformer", (_FakeBase,), {})

    sys.modules["discord"] = discord
    sys.modules["discord.ui"] = ui
    sys.modules["discord.ext"] = ext
    sys.modules["discord.ext.commands"] = commands
    sys.modules["discord.ext.tasks"] = tasks
    sys.modules["discord.app_commands"] = app_commands


def _install_runtime_dependency_stubs():
    requests = types.ModuleType("requests")

    class RequestException(Exception):
        pass

    class _Response:
        status_code = 200
        text = ""
        content = b""

        def json(self):
            return {}

        def raise_for_status(self):
            return None

    requests.get = lambda *_args, **_kwargs: _Response()
    requests.post = lambda *_args, **_kwargs: _Response()
    requests.put = lambda *_args, **_kwargs: _Response()
    requests.delete = lambda *_args, **_kwargs: _Response()
    requests.exceptions = types.SimpleNamespace(RequestException=RequestException)
    sys.modules.setdefault("requests", requests)


def import_bot_module():
    """Import bot.py once with the Discord runtime stubbed out.

    bot.py calls ``bot.run(DISCORD_TOKEN)`` and ``start_dashboard_server()`` at
    module import time, both of which would try to talk to Discord and bind
    sockets. We stub those side effects so we can exercise the pure CE XML
    generators that we care about for the regression tests.
    """
    if "bot" in sys.modules:
        return sys.modules["bot"]

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    os.environ.setdefault("DISCORD_TOKEN", "")
    os.environ.setdefault("WANDERING_DISABLE_RUNTIME", "1")
    _install_runtime_dependency_stubs()

    # Stub discord.ext.commands.Bot.run and the dashboard server so the import
    # does not block / fail on network access.
    try:
        import discord  # type: ignore
        from discord.ext import commands  # type: ignore
    except ModuleNotFoundError:
        _install_discord_stubs()
        import discord  # type: ignore
        from discord.ext import commands  # type: ignore

    def _noop(*_args, **_kwargs):
        return None

    commands.Bot.run = _noop  # type: ignore[attr-defined]
    if hasattr(discord, "Client"):
        discord.Client.run = _noop  # type: ignore[attr-defined]

    # Provide a fake dashboard module so the import does not call
    # start_dashboard_server() with the real Flask app.
    fake_dashboard = types.ModuleType("dashboard")
    fake_dashboard.bind_runtime_callbacks = _noop
    fake_dashboard.configure_dashboard_state_provider = _noop
    fake_dashboard.start_dashboard_server = _noop
    sys.modules.setdefault("dashboard", fake_dashboard)

    import bot  # type: ignore

    return bot
