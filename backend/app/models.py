import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from app.database import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

def get_utc_now():
    return datetime.now(timezone.utc)

class Call(Base):
    __tablename__ = "calls"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    title = Column(String(255), default="Voice Call")
    started_at = Column(DateTime, default=get_utc_now)
    ended_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, default=0)
    status = Column(String(50), default="active")  # active, completed

    participants = relationship("Participant", back_populates="call", cascade="all, delete-orphan")
    transcript_turns = relationship("TranscriptTurn", back_populates="call", cascade="all, delete-orphan")
    analysis_events = relationship("AnalysisEvent", back_populates="call", cascade="all, delete-orphan")
    claims = relationship("Claim", back_populates="call", cascade="all, delete-orphan")
    arguments = relationship("Argument", back_populates="call", cascade="all, delete-orphan")


class Participant(Base):
    __tablename__ = "participants"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    call_id = Column(String(36), ForeignKey("calls.id"), nullable=False)
    name = Column(String(100), nullable=False)
    audio_stream_id = Column(String(50), nullable=False)  # e.g., stream_a, stream_b
    speaking_time_ms = Column(Integer, default=0)

    call = relationship("Call", back_populates="participants")
    turns = relationship("TranscriptTurn", back_populates="participant")


class TranscriptTurn(Base):
    __tablename__ = "transcript_turns"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    call_id = Column(String(36), ForeignKey("calls.id"), nullable=False)
    speaker_id = Column(String(36), ForeignKey("participants.id"), nullable=True)
    speaker_name = Column(String(100), nullable=False)
    start_ms = Column(Integer, default=0)
    end_ms = Column(Integer, default=0)
    text = Column(Text, nullable=False)
    language = Column(String(20), default="mixed")  # ar, en, mixed
    created_at = Column(DateTime, default=get_utc_now)

    call = relationship("Call", back_populates="transcript_turns")
    participant = relationship("Participant", back_populates="turns")
    analysis_event = relationship("AnalysisEvent", back_populates="turn", uselist=False)


class AnalysisEvent(Base):
    __tablename__ = "analysis_events"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    call_id = Column(String(36), ForeignKey("calls.id"), nullable=False)
    turn_id = Column(String(36), ForeignKey("transcript_turns.id"), nullable=False)
    topic = Column(String(50), default="other")
    intent = Column(String(50), default="statement")
    heat_score = Column(Float, default=0.0)
    is_claim = Column(Boolean, default=False)
    is_disagreement = Column(Boolean, default=False)
    created_at = Column(DateTime, default=get_utc_now)

    call = relationship("Call", back_populates="analysis_events")
    turn = relationship("TranscriptTurn", back_populates="analysis_event")


class Claim(Base):
    __tablename__ = "claims"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    call_id = Column(String(36), ForeignKey("calls.id"), nullable=False)
    speaker_id = Column(String(36), nullable=True)
    turn_id = Column(String(36), nullable=True)
    text = Column(Text, nullable=False)
    topic = Column(String(50), default="other")
    status = Column(String(50), default="pending")  # pending, verified, contradicted, inconclusive
    confidence = Column(Float, default=0.0)
    created_at = Column(DateTime, default=get_utc_now)

    call = relationship("Call", back_populates="claims")
    fact_check = relationship("FactCheck", back_populates="claim", uselist=False)


class FactCheck(Base):
    __tablename__ = "fact_checks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    call_id = Column(String(36), nullable=False)
    claim_id = Column(String(36), ForeignKey("claims.id"), nullable=False)
    result = Column(String(50), default="inconclusive")  # supported, contradicted, inconclusive
    confidence = Column(Float, default=0.0)
    sources = Column(JSON, default=list)
    evidence = Column(Text, default="")
    interrupted = Column(Boolean, default=False)
    interruption_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=get_utc_now)

    claim = relationship("Claim", back_populates="fact_check")


class Argument(Base):
    __tablename__ = "arguments"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    call_id = Column(String(36), ForeignKey("calls.id"), nullable=False)
    topic = Column(String(50), default="other")
    start_ms = Column(Integer, default=0)
    end_ms = Column(Integer, default=0)
    participants = Column(JSON, default=list)  # list of speaker names
    claim_a = Column(Text, nullable=True)
    claim_b = Column(Text, nullable=True)
    heat_peak = Column(Float, default=0.0)
    resolution = Column(Text, nullable=True)
    created_at = Column(DateTime, default=get_utc_now)

    call = relationship("Call", back_populates="arguments")
