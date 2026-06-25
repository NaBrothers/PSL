"""Tests for server auth routes and utilities."""
import pytest
import sqlite3
import os

from server.auth import hash_pin, verify_pin, create_token, decode_token


class TestPinHashing:
    def test_hash_and_verify(self):
        h = hash_pin("1234")
        assert verify_pin("1234", h)

    def test_wrong_pin(self):
        h = hash_pin("1234")
        assert not verify_pin("5678", h)

    def test_different_hashes(self):
        h1 = hash_pin("1234")
        h2 = hash_pin("1234")
        assert h1 != h2

    def test_invalid_format(self):
        assert not verify_pin("1234", "garbage")


class TestJWT:
    def test_create_and_decode(self):
        token = create_token(123456789)
        payload = decode_token(token)
        assert payload["qq"] == 123456789

    def test_invalid_token(self):
        with pytest.raises(Exception):
            decode_token("invalid.token.here")


class TestAuthAPI:
    @pytest.fixture(autouse=True)
    def setup_db(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE users (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                QQ INTEGER NOT NULL UNIQUE,
                Name TEXT DEFAULT NULL,
                Level INTEGER DEFAULT NULL,
                Money INTEGER DEFAULT NULL,
                Formation TEXT DEFAULT '442',
                isAdmin INTEGER DEFAULT 0,
                WebPinHash TEXT DEFAULT NULL
            );
            INSERT INTO users (QQ, Name, Money) VALUES (10001, 'Alice', 5000);
            INSERT INTO users (QQ, Name, Money) VALUES (10002, 'Bob', 3000);
        """)
        conn.close()

        import server.database
        server.database.db = server.database.Database(db_path)

        from server.app import app
        from fastapi.testclient import TestClient
        self.client = TestClient(app)
        yield

    def test_list_players(self):
        resp = self.client.get("/api/players")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["name"] == "Alice"
        assert data[0]["has_pin"] is False

    def test_setup_pin(self):
        resp = self.client.post("/api/auth/setup-pin", json={"qq": 10001, "pin": "1234"})
        assert resp.status_code == 200
        resp2 = self.client.get("/api/players")
        alice = [p for p in resp2.json() if p["qq"] == 10001][0]
        assert alice["has_pin"] is True

    def test_setup_pin_invalid(self):
        resp = self.client.post("/api/auth/setup-pin", json={"qq": 10001, "pin": "abc"})
        assert resp.status_code == 400

    def test_setup_pin_already_set(self):
        self.client.post("/api/auth/setup-pin", json={"qq": 10001, "pin": "1234"})
        resp = self.client.post("/api/auth/setup-pin", json={"qq": 10001, "pin": "5678"})
        assert resp.status_code == 400

    def test_login_success(self):
        self.client.post("/api/auth/setup-pin", json={"qq": 10001, "pin": "1234"})
        resp = self.client.post("/api/auth/login", json={"qq": 10001, "pin": "1234"})
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["qq"] == 10001
        assert data["user"]["name"] == "Alice"

    def test_login_wrong_pin(self):
        self.client.post("/api/auth/setup-pin", json={"qq": 10001, "pin": "1234"})
        resp = self.client.post("/api/auth/login", json={"qq": 10001, "pin": "9999"})
        assert resp.status_code == 401

    def test_login_no_pin_set(self):
        resp = self.client.post("/api/auth/login", json={"qq": 10002, "pin": "1234"})
        assert resp.status_code == 400

    def test_me_with_token(self):
        self.client.post("/api/auth/setup-pin", json={"qq": 10001, "pin": "1234"})
        login_resp = self.client.post("/api/auth/login", json={"qq": 10001, "pin": "1234"})
        token = login_resp.json()["token"]
        resp = self.client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["qq"] == 10001

    def test_me_invalid_token(self):
        resp = self.client.get("/api/me", headers={"Authorization": "Bearer invalid"})
        assert resp.status_code == 401

    def test_me_no_token(self):
        resp = self.client.get("/api/me")
        assert resp.status_code == 401
