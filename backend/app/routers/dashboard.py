from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Dict

from app.database import get_db
from app.models import Call, Participant, TranscriptTurn, AnalysisEvent, Claim, FactCheck, Argument
from app.schemas import (
    CallDashboardResponse, SpeakerStat, TopicStat, HeatedMoment,
    ArgumentResponse, FactCheckResponse, TranscriptTurnResponse, AnalysisEventResponse, SourceItem
)

router = APIRouter(prefix="/api/calls", tags=["dashboard"])

def format_ms(ms: int) -> str:
    seconds = int(ms / 1000)
    minutes = int(seconds / 60)
    remaining_sec = seconds % 60
    hours = int(minutes / 60)
    if hours > 0:
        return f"{hours}:{minutes % 60:02d}:{remaining_sec:02d}"
    return f"{minutes:02d}:{remaining_sec:02d}"

@router.get("/{call_id}/dashboard", response_model=CallDashboardResponse)
async def get_call_dashboard(call_id: str, db: AsyncSession = Depends(get_db)):
    # 1. Fetch Call
    stmt_call = select(Call).where(Call.id == call_id)
    res_call = await db.execute(stmt_call)
    call = res_call.scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    # 2. Fetch Participants
    stmt_p = select(Participant).where(Participant.call_id == call_id)
    participants = (await db.execute(stmt_p)).scalars().all()

    # 3. Fetch Turns with Analysis
    stmt_turns = (
        select(TranscriptTurn)
        .where(TranscriptTurn.call_id == call_id)
        .order_by(TranscriptTurn.start_ms.asc())
    )
    turns = (await db.execute(stmt_turns)).scalars().all()

    turn_ids = [t.id for t in turns]
    analysis_dict: Dict[str, AnalysisEvent] = {}
    if turn_ids:
        stmt_a = select(AnalysisEvent).where(AnalysisEvent.turn_id.in_(turn_ids))
        analysis_events = (await db.execute(stmt_a)).scalars().all()
        analysis_dict = {a.turn_id: a for a in analysis_events}

    # 4. Fetch Arguments
    stmt_args = select(Argument).where(Argument.call_id == call_id).order_by(Argument.start_ms.asc())
    arguments = (await db.execute(stmt_args)).scalars().all()

    # 5. Fetch Claims & Fact Checks
    stmt_claims = select(Claim).where(Claim.call_id == call_id)
    claims = (await db.execute(stmt_claims)).scalars().all()

    stmt_fc = select(FactCheck).where(FactCheck.call_id == call_id)
    fact_checks = (await db.execute(stmt_fc)).scalars().all()

    # --- Deterministic Calculations ---
    # Total Speaking Time
    total_speaking_ms = sum(p.speaking_time_ms for p in participants) or 1
    speakers_stat = []
    for p in participants:
        pct = round((p.speaking_time_ms / total_speaking_ms) * 100, 1)
        speakers_stat.append(SpeakerStat(
            name=p.name,
            duration_ms=p.speaking_time_ms,
            percentage=pct
        ))

    # Topic Durations (sum of turn durations tagged with each topic)
    topic_durations: Dict[str, int] = {}
    topic_counts: Dict[str, int] = {}
    for t in turns:
        dur = max(0, t.end_ms - t.start_ms)
        analysis = analysis_dict.get(t.id)
        topic = analysis.topic if analysis else "other"
        topic_durations[topic] = topic_durations.get(topic, 0) + dur
        topic_counts[topic] = topic_counts.get(topic, 0) + 1

    total_topic_duration = sum(topic_durations.values()) or 1
    topics_stat = []
    # Sort topics descending by duration
    for topic, dur in sorted(topic_durations.items(), key=lambda x: x[1], reverse=True):
        topics_stat.append(TopicStat(
            topic=topic.capitalize(),
            duration_ms=dur,
            formatted_duration=format_ms(dur),
            percentage=round((dur / total_topic_duration) * 100, 1),
            turn_count=topic_counts.get(topic, 0)
        ))

    # Heated Moments Detection (heat_score >= 0.6)
    heated_moments = []
    current_heat_group = []
    for t in turns:
        analysis = analysis_dict.get(t.id)
        if analysis and analysis.heat_score >= 0.6:
            current_heat_group.append((t, analysis))
        else:
            if current_heat_group:
                start_m = current_heat_group[0][0].start_ms
                end_m = current_heat_group[-1][0].end_ms
                max_heat = max(a[1].heat_score for a in current_heat_group)
                topic_h = current_heat_group[0][1].topic.capitalize()
                heated_moments.append(HeatedMoment(
                    topic=topic_h,
                    start_ms=start_m,
                    end_ms=end_m,
                    formatted_duration=format_ms(max(0, end_m - start_m)),
                    heat_score=max_heat,
                    description=f"High debate on {topic_h} between participants."
                ))
                current_heat_group = []
    if current_heat_group:
        start_m = current_heat_group[0][0].start_ms
        end_m = current_heat_group[-1][0].end_ms
        max_heat = max(a[1].heat_score for a in current_heat_group)
        topic_h = current_heat_group[0][1].topic.capitalize()
        heated_moments.append(HeatedMoment(
            topic=topic_h,
            start_ms=start_m,
            end_ms=end_m,
            formatted_duration=format_ms(max(0, end_m - start_m)),
            heat_score=max_heat,
            description=f"Debate on {topic_h} at call conclusion."
        ))

    # Fact-Check Summaries
    supported_cnt = sum(1 for fc in fact_checks if fc.result == "supported")
    contradicted_cnt = sum(1 for fc in fact_checks if fc.result == "contradicted")
    inconclusive_cnt = sum(1 for fc in fact_checks if fc.result == "inconclusive")

    fact_checks_response = []
    for fc in fact_checks:
        sources_list = []
        if isinstance(fc.sources, list):
            for s in fc.sources:
                sources_list.append(SourceItem(
                    title=s.get("title", "Source"),
                    url=s.get("url", "#"),
                    snippet=s.get("snippet", "")
                ))
        fact_checks_response.append(FactCheckResponse(
            id=fc.id,
            claim_id=fc.claim_id,
            result=fc.result,
            confidence=fc.confidence,
            sources=sources_list,
            evidence=fc.evidence,
            interrupted=fc.interrupted,
            interruption_text=fc.interruption_text
        ))

    # Turn Responses
    turns_response = []
    for t in turns:
        a_ev = analysis_dict.get(t.id)
        a_resp = None
        if a_ev:
            a_resp = AnalysisEventResponse(
                id=a_ev.id,
                turn_id=a_ev.turn_id,
                topic=a_ev.topic,
                intent=a_ev.intent,
                heat_score=a_ev.heat_score,
                is_claim=a_ev.is_claim,
                is_disagreement=a_ev.is_disagreement
            )
        turns_response.append(TranscriptTurnResponse(
            id=t.id,
            call_id=t.call_id,
            speaker_id=t.speaker_id,
            speaker_name=t.speaker_name,
            start_ms=t.start_ms,
            end_ms=t.end_ms,
            text=t.text,
            language=t.language,
            analysis=a_resp
        ))

    # Construct clean summary
    primary_topic = topics_stat[0].topic if topics_stat else "General"
    summary = (
        f"A {format_ms(call.duration_ms)} conversation focused predominantly on {primary_topic}. "
        f"{len(arguments)} direct disagreements were recorded with {len(fact_checks)} factual claims investigated."
    )

    return CallDashboardResponse(
        call_id=call.id,
        title=call.title,
        duration_ms=call.duration_ms,
        formatted_duration=format_ms(call.duration_ms),
        speakers=speakers_stat,
        topics=topics_stat,
        heated_moments=heated_moments,
        arguments=[ArgumentResponse.model_validate(a) for a in arguments],
        fact_checks=fact_checks_response,
        total_claims_checked=len(fact_checks),
        supported_count=supported_cnt,
        contradicted_count=contradicted_cnt,
        inconclusive_count=inconclusive_cnt,
        summary=summary,
        turns=turns_response
    )
