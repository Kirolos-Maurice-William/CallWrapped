from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime, timezone
from typing import List

from app.database import get_db
from app.models import Call, Participant, get_utc_now
from app.schemas import CallCreate, CallResponse, ParticipantResponse
from app.services.orchestrator import active_sessions

router = APIRouter(prefix="/api/calls", tags=["calls"])

@router.post("", response_model=CallResponse)
async def create_call(payload: CallCreate, db: AsyncSession = Depends(get_db)):
    call = Call(title=payload.title, status="active")
    db.add(call)
    await db.flush()

    p_a = Participant(
        call_id=call.id,
        name=payload.participant_a_name or "You",
        audio_stream_id="stream_a"
    )
    p_b = Participant(
        call_id=call.id,
        name=payload.participant_b_name or "Friend",
        audio_stream_id="stream_b"
    )
    db.add_all([p_a, p_b])
    await db.commit()
    await db.refresh(call)

    # Fetch with participants
    stmt = select(Participant).where(Participant.call_id == call.id)
    result = await db.execute(stmt)
    participants = result.scalars().all()

    return CallResponse(
        id=call.id,
        title=call.title,
        started_at=call.started_at,
        ended_at=call.ended_at,
        duration_ms=call.duration_ms,
        status=call.status,
        participants=[ParticipantResponse.model_validate(p) for p in participants]
    )

@router.get("/{call_id}", response_model=CallResponse)
async def get_call(call_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(Call).where(Call.id == call_id)
    result = await db.execute(stmt)
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    stmt_p = select(Participant).where(Participant.call_id == call_id)
    res_p = await db.execute(stmt_p)
    participants = res_p.scalars().all()

    return CallResponse(
        id=call.id,
        title=call.title,
        started_at=call.started_at,
        ended_at=call.ended_at,
        duration_ms=call.duration_ms,
        status=call.status,
        participants=[ParticipantResponse.model_validate(p) for p in participants]
    )

@router.post("/{call_id}/end", response_model=CallResponse)
async def end_call(call_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(Call).where(Call.id == call_id)
    result = await db.execute(stmt)
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    end_time = get_utc_now()
    call.ended_at = end_time
    call.status = "completed"
    
    # Calculate duration
    start = call.started_at
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    duration_seconds = (end_time - start).total_seconds()
    call.duration_ms = max(0, int(duration_seconds * 1000))

    await db.commit()
    await db.refresh(call)

    # Clean up active session orchestrator and peer audio sockets
    from app.routers.audio_stream import close_call_audio_sockets
    await close_call_audio_sockets(call_id)
    if call_id in active_sessions:
        await active_sessions[call_id].close()
        del active_sessions[call_id]

    stmt_p = select(Participant).where(Participant.call_id == call_id)
    res_p = await db.execute(stmt_p)
    participants = res_p.scalars().all()

    return CallResponse(
        id=call.id,
        title=call.title,
        started_at=call.started_at,
        ended_at=call.ended_at,
        duration_ms=call.duration_ms,
        status=call.status,
        participants=[ParticipantResponse.model_validate(p) for p in participants]
    )

@router.get("", response_model=List[CallResponse])
async def list_calls(db: AsyncSession = Depends(get_db)):
    stmt = select(Call).order_by(Call.started_at.desc()).limit(20)
    result = await db.execute(stmt)
    calls = result.scalars().all()

    responses = []
    for c in calls:
        stmt_p = select(Participant).where(Participant.call_id == c.id)
        res_p = await db.execute(stmt_p)
        participants = res_p.scalars().all()
        responses.append(CallResponse(
            id=c.id,
            title=c.title,
            started_at=c.started_at,
            ended_at=c.ended_at,
            duration_ms=c.duration_ms,
            status=c.status,
            participants=[ParticipantResponse.model_validate(p) for p in participants]
        ))
    return responses
