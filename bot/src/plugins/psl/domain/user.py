"""Pure domain model for user account."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class UserData:
    id: int
    qq: int
    name: str
    level: int = 0
    money: int = 0
    formation: str = "442"
    is_admin: bool = False
    web_pin_hash: Optional[str] = None
