from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
from datetime import datetime

# --- Call Schemas ---
class CallCreate(BaseModel):
    title: Optional[str] = "Voice Call"
    participant_a_name: str = "You"
    participant_b_name: str = "Friend"

class ParticipantResponse(BaseModel):
    id: str
    name: str
    audio_stream_id: str
    speaking_time_ms: int

    class Config:
        from_attributes = True

class CallResponse(BaseModel):
    id: str
    title: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_ms: int
    status: str
    participants: List[ParticipantResponse] = []

    class Config:
        from_attributes = True

# --- Transcript & Analysis Schemas ---
class TranscriptTurnCreate(BaseModel):
    call_id: str
    speaker_id: Optional[str] = None
    speaker_name: str
    start_ms: int
    end_ms: int
    text: str
    language: str = "mixed"

class AnalysisEventResponse(BaseModel):
    id: str
    turn_id: str
    topic: str
    intent: str
    heat_score: float
    is_claim: bool
    is_disagreement: bool

    class Config:
        from_attributes = True

class TranscriptTurnResponse(BaseModel):
    id: str
    call_id: str
    speaker_id: Optional[str]
    speaker_name: str
    start_ms: int
    end_ms: int
    text: str
    language: str
    analysis: Optional[AnalysisEventResponse] = None

    class Config:
        from_attributes = True

# --- Claims & Fact-Checks ---
class SourceItem(BaseModel):
    title: str
    url: str
    snippet: str

class FactCheckResponse(BaseModel):
    id: str
    claim_id: str
    result: str  # supported, contradicted, inconclusive
    confidence: float
    sources: List[SourceItem] = []
    evidence: str
    interrupted: bool
    interruption_text: Optional[str] = None

    class Config:
        from_attributes = True

class ClaimResponse(BaseModel):
    id: str
    speaker_id: Optional[str]
    turn_id: Optional[str]
    text: str
    topic: str
    status: str
    confidence: float
    fact_check: Optional[FactCheckResponse] = None

    class Config:
        from_attributes = True

# --- Arguments & Dashboard ---
class ArgumentResponse(BaseModel):
    id: str
    topic: str
    start_ms: int
    end_ms: int
    participants: List[str]
    claim_a: Optional[str] = None
    claim_b: Optional[str] = None
    heat_peak: float
    resolution: Optional[str] = None

    class Config:
        from_attributes = True

class TopicStat(BaseModel):
    topic: str
    duration_ms: int
    formatted_duration: str
    percentage: float
    turn_count: int

class SpeakerStat(BaseModel):
    name: str
    duration_ms: int
    percentage: float

class HeatedMoment(BaseModel):
    topic: str
    start_ms: int
    end_ms: int
    formatted_duration: str
    heat_score: float
    description: str

class CallDashboardResponse(BaseModel):
    call_id: str
    title: str
    duration_ms: int
    formatted_duration: str
    speakers: List[SpeakerStat]
    topics: List[TopicStat]
    heated_moments: List[HeatedMoment]
    arguments: List[ArgumentResponse]
    fact_checks: List[FactCheckResponse]
    total_claims_checked: int
    supported_count: int
    contradicted_count: int
    inconclusive_count: int
    summary: str
    turns: List[TranscriptTurnResponse]
