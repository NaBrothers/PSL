import json


def test_sqlite_initialization_imports_players(db):
    cursor = db.cursor()
    assert cursor.execute("select * from players") == 499
    assert cursor.execute("select * from players where name = 'L. Messi'") == 1
    player = cursor.fetchone()
    cursor.close()

    assert player[2] == "L. Messi"
    assert player[7] == 86


def test_user_money_global_items_and_offline(core_modules, make_user):
    User = core_modules["model.user"].User
    Global = core_modules["model.globalAttr"].Global
    Item = core_modules["model.item"].Item
    Offline = core_modules["model.offline"].Offline

    user = make_user(10001, "alice", money=5000)
    assert user.money == 5000

    user.spend(1200)
    assert User.getUserByQQ(10001).money == 3800
    user.earn(700)
    assert User.getUserByQQ(10001).money == 4500

    assert Global.get("season", 1) == 1
    Global.set("season", 2)
    assert Global.get("season") == 2

    Item.addItem(user, 0, 0, 2)
    Item.addItem(user, 0, 0, 3)
    items = Item.getItemsByQQandType(user.qq, 0)
    assert len(items.entries) == 1
    assert items.entries[0].count == 5

    Offline.send(user, "hello\nworld")
    messages = Offline.get(user)
    assert len(messages) == 1
    assert "hello" in str(messages[0])
    Offline.remove(user)
    assert Offline.get(user) == []


def test_card_bag_insert_many_and_card_rehydration(core_modules, make_user):
    User = core_modules["model.user"].User
    Player = core_modules["model.player"].Player
    Card = core_modules["model.card"].Card
    Bag = core_modules["model.bag"].Bag

    user = make_user(10002, "bob", money=0)
    messi = Player.getPlayerByID(158023)
    assert messi.Name == "L. Messi"

    card = Card.new(messi, user, star=3)
    card_id = Bag.addToBag(user, card)
    loaded = Card.getCardByID(card_id)

    assert loaded.player.Name == "L. Messi"
    assert loaded.user.qq == user.qq
    assert loaded.star == 3
    assert loaded.breach == 0
    assert loaded.ext_abilities == {}

    ids = Bag.addToBagMany(user, [Card.new(messi, user), Card.new(messi, user)])
    assert len(ids) == 2
    assert ids[0] != ids[1]
    bag = Bag.getBag(User.getUserByQQ(user.qq))
    assert len(bag.cards) == 3

    loaded.set("ext_abilities", json.dumps({"Speed": 2}))
    loaded.set("breach", 4)
    loaded = Card.getCardByID(card_id)
    assert loaded.ext_abilities == {"Speed": 2}
    assert loaded.breach == 4


def test_formation_schedule_league_and_challenge_times(core_modules, make_user):
    User = core_modules["model.user"].User
    Player = core_modules["model.player"].Player
    Card = core_modules["model.card"].Card
    Bag = core_modules["model.bag"].Bag
    Formation = core_modules["model.formation"].Formation
    League = core_modules["model.league"].League
    Schedule = core_modules["model.schedule"].Schedule
    ChallengeTimes = core_modules["model.challenge_times"].ChallengeTimes

    user1 = make_user(10003, "home", money=0)
    user2 = make_user(10004, "away", money=0)

    player_ids = [158023, 188545, 20801, 190871, 192985, 200389, 231747, 212831, 209331, 192448, 167495]
    for player_id in player_ids:
        player = Player.getPlayerByID(player_id)
        if player is not None:
            Bag.addToBag(user1, Card.new(player, user1, star=1))

    formation = Formation.getFormation(user1)
    assert len(formation.cards) == Formation.PLAYERS_COUNT
    assert formation.isValid() is False

    League.addUser(user1.qq)
    League.addUser(user2.qq)
    assert League.getCount() == 2
    league = League.getLeague()
    assert len(league.entries) == 2

    Schedule.addEntry((1, 1, user1.qq, user2.qq, 0, 0, 0))
    current = Schedule.getCurrentRound()
    assert len(current.entries) == 1
    entry = Schedule.getCurrentEntry(user1)
    assert entry.home.qq == user1.qq
    entry.set("finished", 1)
    entry.set("home_goal", 2)
    entry.set("away_goal", 1)
    assert Schedule.getRecentCondition(user1, 5) == "/~r胜/"
    assert Schedule.getRecentCondition(user2, 5) == "/~b负/"

    times = ChallengeTimes.getTimes(user1)
    assert times.user.qq == user1.qq
    assert times.times > 0
    times.setTimes(1)
    assert ChallengeTimes.getTimes(user1).times == 1
