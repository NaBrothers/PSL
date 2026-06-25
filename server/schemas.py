from pydantic import BaseModel
from typing import List, Optional


class PlayerListItem(BaseModel):
    id: int
    qq: int
    name: str
    has_pin: bool


class SetupPinRequest(BaseModel):
    qq: int
    pin: str


class LoginRequest(BaseModel):
    qq: int
    pin: str


class LoginResponse(BaseModel):
    token: str
    user: "UserInfo"


class UserInfo(BaseModel):
    id: int
    qq: int
    name: str
    money: int
    formation: str


LoginResponse.model_rebuild()
