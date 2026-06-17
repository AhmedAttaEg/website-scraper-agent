from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from db.connection import get_db
from db.repository import (
    create_conversation,
    get_conversations_by_session,
    get_messages_by_conversation,
    delete_conversation,
    update_conversation_title,
)

router = APIRouter()


@router.get("/conversations")
async def list_conversations(
    session_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
):
    conversations = await get_conversations_by_session(session, session_id)
    return {"conversations": conversations}


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(
    conversation_id: str,
    session: AsyncSession = Depends(get_db),
):
    result = await get_messages_by_conversation(session, conversation_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return result


@router.delete("/conversations/{conversation_id}")
async def remove_conversation(
    conversation_id: str,
    session: AsyncSession = Depends(get_db),
):
    deleted = await delete_conversation(session, conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"deleted": True}


@router.patch("/conversations/{conversation_id}")
async def rename_conversation(
    conversation_id: str,
    body: dict,
    session: AsyncSession = Depends(get_db),
):
    title = body.get("title")
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    result = await update_conversation_title(session, conversation_id, title)
    if result is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return result
