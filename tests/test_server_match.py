"""Tests for match service and routes."""
import pytest
import sqlite3
import os
import sys

BOT_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bot", "src", "plugins", "psl")
if BOT_SRC not in sys.path:
    sys.path.insert(0, BOT_SRC)

import server.database


def _create_test_db(tmp_path):
    """Create a test database with enough data to run a match."""
    db_path = str(tmp_path / "test_match.db")
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
            Age INTEGER DEFAULT 25,
            Photo TEXT, Nationality TEXT, Flag TEXT,
            Overall INTEGER,
            Potential INTEGER DEFAULT 85,
            Club TEXT DEFAULT 'TestFC', Club_Logo TEXT, Value TEXT, Wage TEXT, Special INTEGER DEFAULT 0,
            Preferred_Foot TEXT DEFAULT 'Right', Weak_Foot TEXT DEFAULT '3', Skill_Moves TEXT DEFAULT '3',
            International_Reputation TEXT DEFAULT '3', Work_Rate TEXT DEFAULT 'Medium/ Medium', Body_Type TEXT DEFAULT 'Normal',
            Real_Face TEXT DEFAULT 'No', Release_Clause TEXT DEFAULT '0',
            Position TEXT,
            Jersey_Number INTEGER DEFAULT 10, Height TEXT DEFAULT '180', Weight TEXT DEFAULT '75',
            LS TEXT, ST TEXT, RS TEXT, LW TEXT, LF TEXT, CF TEXT, RF TEXT, RW TEXT,
            LAM TEXT, CAM TEXT, RAM TEXT, LM TEXT, LCM TEXT, CM TEXT, RCM TEXT, RM TEXT,
            LWB TEXT, LDM TEXT, CDM TEXT, RDM TEXT, RWB TEXT,
            LB TEXT, LCB TEXT, CB TEXT, RCB TEXT, RB TEXT, GK TEXT,
            Likes INTEGER DEFAULT 0, Dislikes INTEGER DEFAULT 0, Following INTEGER DEFAULT 0,
            Crossing INTEGER DEFAULT 80, Finishing INTEGER DEFAULT 80, Heading_Accuracy INTEGER DEFAULT 75,
            Short_Passing INTEGER DEFAULT 82, Volleys INTEGER DEFAULT 75, Dribbling INTEGER DEFAULT 80,
            Curve INTEGER DEFAULT 78, FK_Accuracy INTEGER DEFAULT 70, Long_Passing INTEGER DEFAULT 78,
            Ball_Control INTEGER DEFAULT 82, Acceleration INTEGER DEFAULT 80, Sprint_Speed INTEGER DEFAULT 80,
            Agility INTEGER DEFAULT 78, Reactions INTEGER DEFAULT 82, Balance INTEGER DEFAULT 78,
            Shot_Power INTEGER DEFAULT 80, Jumping INTEGER DEFAULT 75, Stamina INTEGER DEFAULT 80,
            Strength INTEGER DEFAULT 75, Long_Shots INTEGER DEFAULT 78, Aggression INTEGER DEFAULT 70,
            Interceptions INTEGER DEFAULT 60, Positioning INTEGER DEFAULT 80, Vision INTEGER DEFAULT 80,
            Penalties INTEGER DEFAULT 75, Composure INTEGER DEFAULT 82, Defensive_Awareness INTEGER DEFAULT 55,
            Standing_Tackle INTEGER DEFAULT 55, Sliding_Tackle INTEGER DEFAULT 50,
            GK_Diving INTEGER DEFAULT 10, GK_Handling INTEGER DEFAULT 10, GK_Kicking INTEGER DEFAULT 15,
            GK_Positioning INTEGER DEFAULT 10, GK_Reflexes INTEGER DEFAULT 10
        );
        CREATE TABLE cards (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            Player INTEGER NOT NULL,
            User INTEGER NOT NULL,
            Star INTEGER NOT NULL DEFAULT 1,
            Style TEXT NOT NULL DEFAULT '力量',
            Status INTEGER DEFAULT 2,
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
        CREATE TABLE "global" (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            Name TEXT NOT NULL,
            Value TEXT NOT NULL
        );

        INSERT INTO users (QQ, Name, Money, Formation) VALUES (10001, 'Home Team', 50000, '442');
        INSERT INTO users (QQ, Name, Money, Formation) VALUES (10002, 'Away Team', 50000, '442');
    """)

    # Create 11 players for GK, defenders, midfielders, forwards
    positions = ['GK', 'LB', 'CB', 'CB', 'RB', 'LM', 'CM', 'CM', 'RM', 'CF', 'ST']
    for i, pos in enumerate(positions):
        pid = i + 1
        gk_vals = "85, 85, 80, 85, 85" if pos == 'GK' else "10, 10, 15, 10, 10"
        def_vals = "80, 80, 78" if pos in ('LB', 'CB', 'RB') else "55, 55, 50"
        conn.execute(f"""
            INSERT INTO players (PrimaryID, ID, Name, Overall, Position,
                GK_Diving, GK_Handling, GK_Kicking, GK_Positioning, GK_Reflexes,
                Defensive_Awareness, Standing_Tackle, Sliding_Tackle)
            VALUES ({pid}, {pid}, 'Player{pid}', 85, '{pos}',
                {gk_vals}, {def_vals})
        """)

    # Create cards and team for both users
    card_id = 1
    for qq in [10001, 10002]:
        for i in range(11):
            player_id = i + 1
            style = 'gloves' if positions[i] == 'GK' else 'hunter'
            conn.execute(
                "INSERT INTO cards (ID, Player, User, Star, Style, Status) VALUES (?, ?, ?, 1, ?, 2)",
                (card_id, player_id, qq, style)
            )
            conn.execute(
                "INSERT INTO team (User, Card, Position) VALUES (?, ?, ?)",
                (qq, card_id, i)
            )
            card_id += 1

    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def match_db(tmp_path):
    db_path = _create_test_db(tmp_path)

    os.environ["PSL_DB_PATH"] = db_path

    import utils.database
    old_conn = utils.database.g_database.db
    utils.database.g_database.db = sqlite3.connect(db_path, check_same_thread=False)
    utils.database.g_database.db.execute("PRAGMA journal_mode=WAL")
    utils.database.g_database.db.isolation_level = None

    server.database.db = server.database.Database(db_path)
    yield server.database.db
    utils.database.g_database.db = old_conn


class TestMatchService:
    def test_quick_match(self, match_db):
        from server.services.match import MatchService
        svc = MatchService(match_db)
        result = svc.run_quick_match(10001, 10002)
        assert result.home_name == "Home Team"
        assert result.away_name == "Away Team"
        assert result.home_score >= 0
        assert result.away_score >= 0
        assert isinstance(result.report, str)
        assert len(result.report) > 0

    def test_ten_matches(self, match_db):
        from server.services.match import MatchService
        svc = MatchService(match_db)
        result = svc.run_ten_matches(10001, 10002)
        assert len(result.results) == 10
        assert result.wins + result.draws + result.losses == 10

    def test_odds(self, match_db):
        from server.services.match import MatchService
        svc = MatchService(match_db)
        result = svc.run_odds(10001, 10002, samples=5)
        assert result.home_win_odds > 0
        assert result.samples == 5


class TestMatchAPI:
    @pytest.fixture(autouse=True)
    def setup(self, match_db):
        from server.app import app
        from fastapi.testclient import TestClient
        from server.auth import create_token
        self.client = TestClient(app)
        self.token = create_token(10001)
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_list_opponents(self):
        resp = self.client.get("/api/matches/opponents", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Away Team"

    def test_quick_match(self):
        resp = self.client.post("/api/matches", json={"opponent_id": 2, "mode": "quick"}, headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "home_score" in data
        assert "away_score" in data
        assert "report" in data
        assert len(data["report"]) > 0

    def test_match_invalid_opponent(self):
        resp = self.client.post("/api/matches", json={"opponent_id": 999, "mode": "quick"}, headers=self.headers)
        assert resp.status_code == 404
