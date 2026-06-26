import server.database
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List
from server.dependencies import get_current_user
from server.services.transfer import TransferService, TransferError

router = APIRouter(prefix="/api", tags=["transfer"])


def _svc():
    return TransferService(server.database.db)


@router.get("/transfer")
def list_market(page: int = 1, page_size: int = 20, query: str = "",
                position: str = "", min_star: int = 0, style: str = "",
                sort_by: str = "overall", user=Depends(get_current_user)):
    svc = _svc()
    return svc.list_market(page=page, page_size=page_size, query=query,
                           position=position, min_star=min_star, style=style, sort_by=sort_by)


class ListRequest(BaseModel):
    card_id: int
    price: int = 0


class BatchListItem(BaseModel):
    card_id: int
    price: int = 0


class BatchListRequest(BaseModel):
    cards: List[BatchListItem]


@router.post("/transfer/list")
def list_card(req: ListRequest, user=Depends(get_current_user)):
    svc = _svc()
    try:
        return svc.list_card(user["qq"], req.card_id, req.price)
    except TransferError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/transfer/batch-list")
def batch_list(req: BatchListRequest, user=Depends(get_current_user)):
    svc = _svc()
    return svc.batch_list(user["qq"], [item.dict() for item in req.cards])


class BuyRequest(BaseModel):
    card_id: int


class BatchBuyRequest(BaseModel):
    card_ids: List[int]


@router.post("/transfer/buy")
def buy_card(req: BuyRequest, user=Depends(get_current_user)):
    svc = _svc()
    try:
        return svc.buy_card(user["qq"], req.card_id)
    except TransferError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/transfer/batch-buy")
def batch_buy(req: BatchBuyRequest, user=Depends(get_current_user)):
    svc = _svc()
    return svc.batch_buy(user["qq"], req.card_ids)


@router.post("/transfer/cancel")
def cancel_listing(req: BuyRequest, user=Depends(get_current_user)):
    svc = _svc()
    try:
        return svc.cancel_listing(user["qq"], req.card_id)
    except TransferError as e:
        raise HTTPException(status_code=400, detail=str(e))
