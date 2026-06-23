import importlib
import os
import sqlite3
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "bot" / "src" / "plugins" / "psl"


for path in (ROOT, PLUGIN_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


class FinishException(Exception):
    def __init__(self, message=None, kwargs=None):
        super().__init__(message)
        self.message = message
        self.kwargs = kwargs or {}


class DummyMatcher:
    def __init__(self):
        self.finished = []
        self.sent = []

    async def finish(self, message=None, **kwargs):
        self.finished.append((message, kwargs))
        raise FinishException(message, kwargs)

    async def send(self, message=None, **kwargs):
        self.sent.append((message, kwargs))


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "psl-test.db"
    monkeypatch.setenv("PSL_DB_PATH", str(path))
    return path


@pytest.fixture()
def db(db_path):
    from database.init_db import initialize_database

    conn = sqlite3.connect(db_path)
    initialize_database(conn)
    conn.close()

    import utils.database as database

    database = importlib.reload(database)
    yield database.g_database
    database.g_database.db.close()


@pytest.fixture()
def core_modules(db):
    for name in list(sys.modules):
        if name == "kernel" or name.startswith("kernel."):
            sys.modules.pop(name)
        elif name == "model" or name.startswith("model."):
            sys.modules.pop(name)
        elif name == "engine" or name.startswith("engine."):
            sys.modules.pop(name)
        elif name in {"utils.database", "utils.date"}:
            sys.modules.pop(name)

    module_names = [
        "utils.database",
        "model.globalAttr",
        "model.user",
        "model.player",
        "model.card",
        "model.bag",
        "model.item",
        "model.formation",
        "model.league",
        "model.schedule",
        "model.challenge_times",
        "model.offline",
        "model.transfer",
        "kernel.account",
        "kernel.pool",
        "kernel.lottery",
        "kernel.bag",
        "kernel.player",
        "kernel.formation",
        "kernel.transfer",
        "engine.team",
        "engine.game",
    ]
    loaded = {}
    for name in module_names:
        module = importlib.import_module(name)
        loaded[name] = importlib.reload(module)
    return loaded


@pytest.fixture()
def make_user(core_modules):
    User = core_modules["model.user"].User

    def _make_user(qq=10001, name="tester", money=1000000):
        user = User.addUser(qq, name)
        user.earn(money)
        return User.getUserByQQ(qq)

    return _make_user


@pytest.fixture()
def dummy_matcher():
    return DummyMatcher()
