"""Bid routes - buy order endpoints."""

import server.database
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from server.dependencies import get_current_user
from server.services.bid import BidService, BidError
from server.services.transfer import TransferService

router = APIRouter(prefix="/api", tags=["bid"])


def _svc():
    return BidService(server.database.db)


class CreateBidRequest(BaseModel):
    player_name: Optional[str] = None
    star: int = 0
    position: Optional[str] = None
    style: Optional[str] = None
    max_price: int
    quantity: int = 1


class CancelBidRequest(BaseModel):
    bid_id: int


class SupplyRequest(BaseModel):
    bid_id: int
    card_id: int


@router.get("/bids")
def list_bids(page: int = 1, page_size: int = 20, user=Depends(get_current_user)):
    svc = _svc()
    return svc.list_bids(page=page, page_size=page_size, my_qq=user["qq"])


@router.post("/bids/create")
def create_bid(req: CreateBidRequest, user=Depends(get_current_user)):
    svc = _svc()
    try:
        return svc.create_bid(
            buyer_qq=user["qq"],
            player_name=req.player_name,
            star=req.star,
            position=req.position,
            style=req.style,
            max_price=req.max_price,
        )
    except BidError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/bids/cancel")
def cancel_bid(req: CancelBidRequest, user=Depends(get_current_user)):
    svc = _svc()
    try:
        return svc.cancel_bid(user["qq"], req.bid_id)
    except BidError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/bids/supply")
def supply_card(req: SupplyRequest, user=Depends(get_current_user)):
    svc = _svc()
    try:
        return svc.supply_card(user["qq"], req.bid_id, req.card_id)
    except BidError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/bids/{bid_id}/candidates")
def get_supply_candidates(bid_id: int, page: int = 1, page_size: int = 20, user=Depends(get_current_user)):
    svc = _svc()
    try:
        return svc.get_supply_candidates(user["qq"], bid_id, page=page, page_size=page_size)
    except BidError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/transfer/reference-price")
def get_reference_price(player_id: int, star: int, user=Depends(get_current_user)):
    svc = TransferService(server.database.db)
    return svc.get_reference_price(player_id, star)


@router.get("/players/search")
def search_players(q: str = "", user=Depends(get_current_user)):
    """Search player names from the players table for autocomplete."""
    if not q or len(q) < 1:
        return []
    rows = server.database.db.query_all(
        "SELECT DISTINCT Name FROM players WHERE Name LIKE ? LIMIT 20",
        (f"%{q}%",)
    )
    return [r[0] for r in rows]
