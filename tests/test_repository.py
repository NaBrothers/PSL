"""Tests for repository layer - parameterized SQL."""

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "bot" / "src" / "plugins" / "psl"
for path in (ROOT, PLUGIN_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


@pytest.fixture()
def repo_db(tmp_path):
    db_path = str(tmp_path / "repo-test.db")
    os.environ["PSL_DB_PATH"] = db_path
    from database.init_db import initialize_database
    conn = sqlite3.connect(db_path)
    initialize_database(conn)
    conn.close()

    from repository.base import Database
    db = Database(db_path)
    yield db
    db.close()


class TestPlayerRepository:
    def test_get_by_id(self, repo_db):
        from repository.player_repo import PlayerRepository
        repo = PlayerRepository(repo_db)
        player = repo.get_by_id(158023)
        assert player is not None
        assert player.name == "L. Messi"
        assert player.overall == 93

    def test_get_by_id_not_found(self, repo_db):
        from repository.player_repo import PlayerRepository
        repo = PlayerRepository(repo_db)
        assert repo.get_by_id(999999) is None

    def test_get_by_ids(self, repo_db):
        from repository.player_repo import PlayerRepository
        repo = PlayerRepository(repo_db)
        players = repo.get_by_ids([158023, 188545])
        assert len(players) == 2

    def test_search_by_name(self, repo_db):
        from repository.player_repo import PlayerRepository
        repo = PlayerRepository(repo_db)
        results = repo.search_by_name("Messi")
        assert len(results) >= 1
        assert any(p.name == "L. Messi" for p in results)


class TestUserRepository:
    def test_create_and_get(self, repo_db):
        from repository.user_repo import UserRepository
        repo = UserRepository(repo_db)
        user = repo.create(10001, "Alice")
        assert user.qq == 10001
        assert user.name == "Alice"

        loaded = repo.get_by_qq(10001)
        assert loaded.qq == 10001

    def test_update_money(self, repo_db):
        from repository.user_repo import UserRepository
        repo = UserRepository(repo_db)
        repo.create(10002, "Bob")
        repo.update_money(10002, 5000)
        user = repo.get_by_qq(10002)
        assert user.money == 5000

        repo.update_money(10002, -2000)
        user = repo.get_by_qq(10002)
        assert user.money == 3000

    def test_set_formation(self, repo_db):
        from repository.user_repo import UserRepository
        repo = UserRepository(repo_db)
        repo.create(10003, "Charlie")
        repo.set_formation(10003, "433")
        user = repo.get_by_qq(10003)
        assert user.formation == "433"


class TestCardRepository:
    def test_create_and_get(self, repo_db):
        from repository.card_repo import CardRepository
        from repository.user_repo import UserRepository
        user_repo = UserRepository(repo_db)
        user_repo.create(10004, "Dave")

        card_repo = CardRepository(repo_db)
        card_id = card_repo.create(158023, 10004, 3, "sniper")
        assert card_id > 0

        card = card_repo.get_by_id(card_id)
        assert card is not None
        assert card.player.name == "L. Messi"
        assert card.star == 3
        assert card.style == "sniper"
        assert card.user_qq == 10004

    def test_update(self, repo_db):
        from repository.card_repo import CardRepository
        from repository.user_repo import UserRepository
        user_repo = UserRepository(repo_db)
        user_repo.create(10005, "Eve")

        card_repo = CardRepository(repo_db)
        card_id = card_repo.create(158023, 10005, 1, "hunter")
        card_repo.update(card_id, Star=3, Breach=2)

        card = card_repo.get_by_id(card_id)
        assert card.star == 3
        assert card.breach == 2

    def test_delete(self, repo_db):
        from repository.card_repo import CardRepository
        from repository.user_repo import UserRepository
        user_repo = UserRepository(repo_db)
        user_repo.create(10006, "Frank")

        card_repo = CardRepository(repo_db)
        card_id = card_repo.create(158023, 10006, 1, "basic")
        card_repo.delete(card_id)
        assert card_repo.get_by_id(card_id) is None

    def test_get_by_user(self, repo_db):
        from repository.card_repo import CardRepository
        from repository.user_repo import UserRepository
        user_repo = UserRepository(repo_db)
        user_repo.create(10007, "Grace")

        card_repo = CardRepository(repo_db)
        card_repo.create(158023, 10007, 1, "sniper")
        card_repo.create(188545, 10007, 2, "hunter")

        cards = card_repo.get_by_user(10007)
        assert len(cards) == 2
