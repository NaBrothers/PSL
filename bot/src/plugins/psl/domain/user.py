"""Pure domain model for user account."""

from dataclasses import dataclass


@dataclass
class UserData:
    id: int
    qq: int
    name: str
    level: int = 0
    money: int = 0
    formation: str = "442"
    is_admin: bool = False
