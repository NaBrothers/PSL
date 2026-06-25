"""Tests for squad service and routes."""
import pytest
import sqlite3
import os

import server.database
from server.services.squad import SquadService, InvalidFormation, CardNotFound, SquadError


@pytest.fixture
def squad_db(tmp_path):
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
        CREATE TABLE players (
            PrimaryID INTEGER PRIMARY KEY,
            ID INTEGER,
            Name TEXT,
            Age INTEGER,
            Photo TEXT, Nationality TEXT, Flag TEXT,
            Overall INTEGER,
            Potential INTEGER,
            Club TEXT, Club_Logo TEXT, Value TEXT, Wage TEXT, Special INTEGER,
            Preferred_Foot TEXT, Weak_Foot TEXT, Skill_Moves TEXT,
            International_Reputation TEXT, Work_Rate TEXT, Body_Type TEXT,
            Real_Face TEXT, Release_Clause TEXT,
            Position TEXT,
            Jersey_Number INTEGER, Height TEXT, Weight TEXT,
            LS TEXT, ST TEXT, RS TEXT, LW TEXT, LF TEXT, CF TEXT, RF TEXT, RW TEXT,
            LAM TEXT, CAM TEXT, RAM TEXT, LM TEXT, LCM TEXT, CM TEXT, RCM TEXT, RM TEXT,
            LWB TEXT, LDM TEXT, CDM TEXT, RDM TEXT, RWB TEXT,
            LB TEXT, LCB TEXT, CB TEXT, RCB TEXT, RB TEXT, GK TEXT,
            Likes INTEGER, Dislikes INTEGER, Following INTEGER,
            Crossing INTEGER, Finishing INTEGER, Heading_Accuracy INTEGER,
            Short_Passing INTEGER, Volleys INTEGER, Dribbling INTEGER,
            Curve INTEGER, FK_Accuracy INTEGER, Long_Passing INTEGER,
            Ball_Control INTEGER, Acceleration INTEGER, Sprint_Speed INTEGER,
            Agility INTEGER, Reactions INTEGER, Balance INTEGER,
            Shot_Power INTEGER, Jumping INTEGER, Stamina INTEGER,
            Strength INTEGER, Long_Shots INTEGER, Aggression INTEGER,
            Interceptions INTEGER, Positioning INTEGER, Vision INTEGER,
            Penalties INTEGER, Composure INTEGER, Defensive_Awareness INTEGER,
            Standing_Tackle INTEGER, Sliding_Tackle INTEGER,
            GK_Diving INTEGER, GK_Handling INTEGER, GK_Kicking INTEGER,
            GK_Positioning INTEGER, GK_Reflexes INTEGER
        );
        CREATE TABLE cards (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            Player INTEGER NOT NULL,
            User INTEGER NOT NULL,
            Star INTEGER NOT NULL,
            Style TEXT NOT NULL,
            Status INTEGER DEFAULT 0,
            Appearance INTEGER DEFAULT 0,
            Goal INTEGER DEFAULT 0, Assist INTEGER DEFAULT 0,
            Tackle INTEGER DEFAULT 0, Save INTEGER DEFAULT 0,
            Total_Appearance INTEGER DEFAULT 0,
            Total_Goal INTEGER DEFAULT 0, Total_Assist INTEGER DEFAULT 0,
            Total_Tackle INTEGER DEFAULT 0, Total_Save INTEGER DEFAULT 0,
            Locked INTEGER DEFAULT 0,
            Ext_Abilities TEXT DEFAULT NULL,
            Breach INTEGER DEFAULT 0
        );
        CREATE TABLE team (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            User INTEGER NOT NULL,
            Card INTEGER NOT NULL,
            Position INTEGER NOT NULL
        );

        INSERT INTO users (QQ, Name, Money, Formation) VALUES (10001, 'Alice', 5000, '442');

        INSERT INTO players (PrimaryID, ID, Name, Overall, Position, Height, Weight,
            Crossing, Finishing, Heading_Accuracy, Short_Passing, Volleys, Dribbling,
            Curve, FK_Accuracy, Long_Passing, Ball_Control, Acceleration, Sprint_Speed,
            Agility, Reactions, Balance, Shot_Power, Jumping, Stamina, Strength,
            Long_Shots, Aggression, Interceptions, Positioning, Vision, Penalties,
            Composure, Defensive_Awareness, Standing_Tackle, Sliding_Tackle,
            GK_Diving, GK_Handling, GK_Kicking, GK_Positioning, GK_Reflexes)
        VALUES (1, 1, 'Messi', 93, 'RW', '170', '72',
            85, 95, 70, 92, 88, 96, 93, 94, 91, 96, 91, 80,
            91, 94, 95, 86, 68, 72, 69, 94, 44, 40, 93, 95, 75,
            96, 26, 35, 24, 6, 11, 15, 15, 8);
        INSERT INTO players (PrimaryID, ID, Name, Overall, Position, Height, Weight,
            Crossing, Finishing, Heading_Accuracy, Short_Passing, Volleys, Dribbling,
            Curve, FK_Accuracy, Long_Passing, Ball_Control, Acceleration, Sprint_Speed,
            Agility, Reactions, Balance, Shot_Power, Jumping, Stamina, Strength,
            Long_Shots, Aggression, Interceptions, Positioning, Vision, Penalties,
            Composure, Defensive_Awareness, Standing_Tackle, Sliding_Tackle,
            GK_Diving, GK_Handling, GK_Kicking, GK_Positioning, GK_Reflexes)
        VALUES (2, 2, 'Ronaldo', 91, 'ST', '187', '83',
            84, 94, 90, 82, 87, 88, 81, 76, 77, 92, 87, 91,
            87, 95, 70, 95, 95, 84, 78, 93, 63, 29, 95, 82, 85,
            95, 28, 32, 24, 7, 11, 15, 14, 11);

        INSERT INTO cards (Player, User, Star, Style, Status) VALUES (1, 10001, 3, '力量', 2);
        INSERT INTO cards (Player, User, Star, Style, Status) VALUES (2, 10001, 2, '速度', 2);
        INSERT INTO cards (Player, User, Star, Style, Status) VALUES (1, 10001, 1, '技术', 0);
    """)
    # Set up team: card 1 in pos 0, card 2 in pos 1, rest empty
    for i in range(11):
        card_id = i + 1 if i < 2 else 0
        conn.execute("INSERT INTO team (User, Card, Position) VALUES (10001, ?, ?)", (card_id, i))
    conn.commit()
    conn.close()

    server.database.db = server.database.Database(db_path)
    yield server.database.db


class TestSquadService:
    def test_get_squad(self, squad_db):
        svc = SquadService(squad_db)
        squad = svc.get_squad(10001)
        assert squad.formation == "442"
        assert len(squad.cards) == 11
        assert squad.cards[0] is not None
        assert squad.cards[0].name == "Messi"
        assert squad.cards[1] is not None
        assert squad.cards[1].name == "Ronaldo"
        assert squad.cards[2] is None

    def test_change_formation(self, squad_db):
        svc = SquadService(squad_db)
        svc.change_formation(10001, "433")
        squad = svc.get_squad(10001)
        assert squad.formation == "433"

    def test_change_formation_invalid(self, squad_db):
        svc = SquadService(squad_db)
        with pytest.raises(InvalidFormation):
            svc.change_formation(10001, "999")

    def test_swap_both_in_team(self, squad_db):
        svc = SquadService(squad_db)
        svc.swap_players(10001, 1, 2)
        squad = svc.get_squad(10001)
        assert squad.cards[0].name == "Ronaldo"
        assert squad.cards[1].name == "Messi"

    def test_swap_one_in_team(self, squad_db):
        svc = SquadService(squad_db)
        # card 3 is in bag (status=0), card 1 is in team (status=2)
        svc.swap_players(10001, 1, 3)
        squad = svc.get_squad(10001)
        assert squad.cards[0].id == 3

    def test_swap_neither_in_team(self, squad_db):
        svc = SquadService(squad_db)
        # card 3 is in bag, no other bag card -> need another
        squad_db.execute("INSERT INTO cards (Player, User, Star, Style, Status) VALUES (2, 10001, 1, '力量', 0)")
        with pytest.raises(SquadError):
            svc.swap_players(10001, 3, 4)

    def test_auto_squad(self, squad_db):
        svc = SquadService(squad_db)
        squad = svc.auto_squad(10001)
        filled = [c for c in squad.cards if c is not None]
        assert len(filled) >= 2


class TestSquadAPI:
    @pytest.fixture(autouse=True)
    def setup(self, squad_db):
        from server.app import app
        from fastapi.testclient import TestClient
        self.client = TestClient(app)
        # Create a token for auth
        from server.auth import create_token
        self.token = create_token(10001)
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_get_squad(self):
        resp = self.client.get("/api/squad", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["formation"] == "442"
        assert len(data["cards"]) == 11
        assert data["cards"][0]["name"] == "Messi"

    def test_change_formation(self):
        resp = self.client.post("/api/squad/formation", json={"formation": "433"}, headers=self.headers)
        assert resp.status_code == 200
        assert resp.json()["formation"] == "433"

    def test_change_formation_invalid(self):
        resp = self.client.post("/api/squad/formation", json={"formation": "999"}, headers=self.headers)
        assert resp.status_code == 400

    def test_swap(self):
        resp = self.client.post("/api/squad/swap", json={"card_id_1": 1, "card_id_2": 2}, headers=self.headers)
        assert resp.status_code == 200
        assert resp.json()["cards"][0]["name"] == "Ronaldo"

    def test_auto_squad(self):
        resp = self.client.post("/api/squad/auto", headers=self.headers)
        assert resp.status_code == 200
        filled = [c for c in resp.json()["cards"] if c is not None]
        assert len(filled) >= 2

    def test_get_squad_by_id(self):
        resp = self.client.get("/api/squad/1", headers=self.headers)
        assert resp.status_code == 200

    def test_unauthorized(self):
        resp = self.client.get("/api/squad")
        assert resp.status_code in (401, 422)
