import server.database
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from server.dependencies import get_current_user
from server.services.inbox import InboxService

router = APIRouter(prefix="/api", tags=["inbox"])


def _inbox_svc():
    return InboxService(server.database.db)


@router.get("/inbox")
def get_inbox(page: int = 1, page_size: int = 20, user=Depends(get_current_user)):
    svc = _inbox_svc()
    messages = svc.get_messages(user["qq"], page, page_size)
    return {"messages": messages}


@router.get("/inbox/unread")
def get_unread(user=Depends(get_current_user)):
    svc = _inbox_svc()
    count = svc.get_unread_count(user["qq"])
    return {"count": count}


class MarkReadRequest(BaseModel):
    message_id: Optional[int] = None


@router.post("/inbox/read")
def mark_read(req: MarkReadRequest, user=Depends(get_current_user)):
    svc = _inbox_svc()
    svc.mark_read(user["qq"], req.message_id)
    return {"ok": True}


@router.post("/inbox/delete-read")
def delete_read(user=Depends(get_current_user)):
    svc = _inbox_svc()
    svc.delete_read(user["qq"])
    return {"ok": True}
