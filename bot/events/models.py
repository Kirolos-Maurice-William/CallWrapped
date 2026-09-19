import time
import uuid
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field


class LatencyBreakdown(BaseModel):
    stt_ms: Optional[int] = None
    llm_ms: Optional[int] = None
    search_ms: Optional[int] = None
    tts_ms: Optional[int] = None
    total_ms: Optional[int] = None


class EvidenceSource(BaseModel):
    url: str
    domain: str
    title: str
    snippet: str
    source_tier: int = 1  # 1: Official, 2: Tech Press, 3: General, 4: Other


class ClaimEvaluation(BaseModel):
    speaker_name: str
    claim_text: str
    status: str  # "CONTRADICTED" | "SUPPORTED" | "UNVERIFIABLE"


class VoiceEvent(BaseModel):
    """
    Unified Event Schema for the AssemblyAI Voice Agent Hackathon.
    Streams from Discord Bot -> FastAPI Event Hub -> Next.js Live Dashboard.
    """
    event_id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:10]}")
    session_id: str = "hackathon_live_session"
    correlation_id: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)
    type: str  # "transcript" | "claim" | "dispute" | "verification" | "intervention"
    speaker_id: Optional[str] = None
    speaker_name: str
    text: str
    timings: Optional[Dict[str, float]] = None
    latency: Optional[LatencyBreakdown] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
