import server.database
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from server.dependencies import get_current_user
from server.services.transfer import TransferService, TransferError

router = APIRouter(prefix="/api", tags=["transfer"])


@router.get("/transfer")
def list_market(page: int = 1, user=Depends(get_current_user)):
    svc = TransferService(server.database.db)
    return svc.list_market(page=page)


class ListRequest(BaseModel):
    card_id: int
    price: int


@router.post("/transfer/list")
def list_card(req: ListRequest, user=Depends(get_current_user)):
    svc = TransferService(server.database.db)
    try:
        return svc.list_card(user["qq"], req.card_id, req.price)
    except TransferError as e:
        raise HTTPException(status_code=400, detail=str(e))


class BuyRequest(BaseModel):
    card_id: int


@router.post("/transfer/buy")
def buy_card(req: BuyRequest, user=Depends(get_current_user)):
    svc = TransferService(server.database.db)
    try:
        return svc.buy_card(user["qq"], req.card_id)
    except TransferError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/transfer/cancel")
def cancel_listing(req: BuyRequest, user=Depends(get_current_user)):
    svc = TransferService(server.database.db)
    try:
        return svc.cancel_listing(user["qq"], req.card_id)
    except TransferError as e:
        raise HTTPException(status_code=400, detail=str(e))
