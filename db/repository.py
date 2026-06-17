from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from db.models import Conversation, Message, ToolCall, ScrapeResult


async def create_conversation(
    session: AsyncSession,
    session_id: str,
    title: str = "New Conversation",
) -> Conversation:
    conversation = Conversation(session_id=session_id, title=title)
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation


async def get_conversations_by_session(
    session: AsyncSession,
    session_id: str,
) -> list[dict]:
    stmt = (
        select(Conversation)
        .where(Conversation.session_id == session_id)
        .order_by(Conversation.updated_at.desc())
    )
    result = await session.execute(stmt)
    conversations = result.scalars().all()

    result_list = []
    for conv in conversations:
        count_stmt = (
            select(func.count())
            .select_from(Message)
            .where(Message.conversation_id == conv.id)
        )
        count_result = await session.execute(count_stmt)
        message_count = count_result.scalar()
        result_list.append(
            {
                "id": conv.id,
                "title": conv.title,
                "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
                "message_count": message_count,
            }
        )
    return result_list


async def create_message(
    session: AsyncSession,
    conversation_id: str,
    role: str,
    content: Optional[str] = None,
    reasoning: Optional[str] = None,
    urls_attached: Optional[list[str]] = None,
) -> Message:
    message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        reasoning=reasoning,
        urls_attached=urls_attached,
    )
    session.add(message)
    await session.commit()
    await session.refresh(message)
    return message


async def get_messages_by_conversation(
    session: AsyncSession,
    conversation_id: str,
) -> Optional[dict]:
    conv_stmt = select(Conversation).where(Conversation.id == conversation_id)
    conv_result = await session.execute(conv_stmt)
    conversation = conv_result.scalar_one_or_none()
    if not conversation:
        return None

    msg_stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .options(selectinload(Message.tool_calls))
    )
    msg_result = await session.execute(msg_stmt)
    messages = msg_result.scalars().all()

    return {
        "conversation_id": conversation.id,
        "title": conversation.title,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "reasoning": m.reasoning,
                "urls_attached": m.urls_attached,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "tool_name": tc.tool_name,
                        "tool_input": tc.tool_input,
                        "output_summary": tc.tool_output_summary,
                        "sequence_order": tc.sequence_order,
                        "called_at": tc.called_at.isoformat() if tc.called_at else None,
                    }
                    for tc in m.tool_calls
                ],
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }


async def create_tool_call(
    session: AsyncSession,
    message_id: str,
    conversation_id: str,
    tool_name: str,
    tool_input: dict,
    tool_output_summary: Optional[str] = None,
    sequence_order: int = 0,
) -> ToolCall:
    tool_call = ToolCall(
        message_id=message_id,
        conversation_id=conversation_id,
        tool_name=tool_name,
        tool_input=tool_input,
        tool_output_summary=tool_output_summary,
        sequence_order=sequence_order,
    )
    session.add(tool_call)
    await session.commit()
    await session.refresh(tool_call)
    return tool_call


async def create_scrape_result(
    session: AsyncSession,
    conversation_id: str,
    message_id: str,
    url: str,
    raw_html: str,
    tool_call_id: Optional[str] = None,
    page_title: Optional[str] = None,
) -> ScrapeResult:
    scrape_result = ScrapeResult(
        conversation_id=conversation_id,
        message_id=message_id,
        tool_call_id=tool_call_id,
        url=url,
        page_title=page_title,
        raw_html=raw_html,
    )
    session.add(scrape_result)
    await session.commit()
    await session.refresh(scrape_result)
    return scrape_result


async def delete_conversation(
    session: AsyncSession,
    conversation_id: str,
) -> bool:
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    result = await session.execute(stmt)
    conversation = result.scalar_one_or_none()
    if not conversation:
        return False
    await session.delete(conversation)
    await session.commit()
    return True


async def update_conversation_title(
    session: AsyncSession,
    conversation_id: str,
    title: str,
) -> Optional[dict]:
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    result = await session.execute(stmt)
    conversation = result.scalar_one_or_none()
    if not conversation:
        return None
    conversation.title = title
    conversation.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(conversation)
    return {
        "id": conversation.id,
        "title": conversation.title,
        "updated_at": conversation.updated_at.isoformat()
        if conversation.updated_at
        else None,
    }
