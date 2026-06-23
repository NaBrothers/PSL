"""Pure domain model for a FIFA player (base data, no DB access)."""

from dataclasses import dataclass


@dataclass
class PlayerData:
    id: int
    name: str
    age: int
    overall: int
    position: str
    height: str
    weight: str
    nationality: str = ""
    club: str = ""

    # Technical
    crossing: int = 0
    finishing: int = 0
    heading_accuracy: int = 0
    short_passing: int = 0
    volleys: int = 0
    dribbling: int = 0
    curve: int = 0
    fk_accuracy: int = 0
    long_passing: int = 0
    ball_control: int = 0

    # Physical
    acceleration: int = 0
    sprint_speed: int = 0
    agility: int = 0
    reactions: int = 0
    balance: int = 0
    shot_power: int = 0
    jumping: int = 0
    stamina: int = 0
    strength: int = 0
    long_shots: int = 0

    # Mental
    aggression: int = 0
    interceptions: int = 0
    positioning: int = 0
    vision: int = 0
    penalties: int = 0
    composure: int = 0

    # Defending
    defensive_awareness: int = 0
    standing_tackle: int = 0
    sliding_tackle: int = 0

    # GK
    gk_diving: int = 0
    gk_handling: int = 0
    gk_kicking: int = 0
    gk_positioning: int = 0
    gk_reflexes: int = 0

    @property
    def price(self) -> int:
        x = self.overall - 74 if self.overall >= 80 else 6
        return int(0.0131*x**5 - 0.6118*x**4 + 11.189*x**3 - 55.238*x**2 + 123.16*x - 29.137)
