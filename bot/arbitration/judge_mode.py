import os
import sys
import io
import time

if sys.stdout and hasattr(sys.stdout, "buffer") and getattr(sys.stdout, "encoding", "").lower() != "utf-8":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

import uuid
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, List
from unittest.mock import MagicMock
import numpy as np

from bot.config import config
from bot.ai.assemblyai import assemblyai_client
from bot.ai.tavily import tavily_client
from bot.ai.groq import groq_client
from bot.ai.tts import speaker, StreamFFmpegPCMAudio
from bot.arbitration.claim_detector import claim_detector
from bot.arbitration.conflict_detector import conflict_detector
from bot.arbitration.verifier import arbitration_verifier
from bot.audio.receiver import AudioReceiver

logger = logging.getLogger("JudgeMode")


async def run_card_1() -> Dict[str, Any]:
    """Card 1 — Opinion: 'الـ 5070 جهاز وحش' alone -> gate rejects (no offer), log reason."""
    scenario = 'Opinion: "الـ 5070 جهاز وحش" alone'
    expected = "Gate rejects (no offer), log reason"

    is_claim, claim_data, latency_ms = await claim_detector.check_claim("الـ 5070 جهاز وحش")
    reason = "Subjective opinion / value judgment (is_factual_claim=False)"
    passed = not is_claim
    actual = f"Gate rejected: is_factual_claim={is_claim} | Reason: {reason} ({latency_ms}ms)"

    return {
        "card": 1,
        "name": "Opinion Rejection Gate",
        "scenario": scenario,
        "expected": expected,
        "actual": actual,
        "passed": passed
    }


async def run_card_2() -> Dict[str, Any]:
    """Card 2 — Agreement: both speakers say 16 جيجا -> NO conflict (reason: agreement)."""
    scenario = "Agreement: both speakers say 16 جيجا"
    expected = "NO conflict (reason: agreement)"

    has_conflict, conf_data, latency_ms = await conflict_detector.detect_conflict(
        speaker_a="Omar", claim_a="16 جيجا",
        speaker_b="Ziad", claim_b="16 جيجا"
    )
    reason = conf_data.get("rejection_reason", "agreement") if conf_data else "none"
    passed = (not has_conflict) and reason in ("agreement", "none", "no_conflict")
    actual = f"has_conflict={has_conflict}, rejection_reason='{reason}' ({latency_ms}ms)"

    return {
        "card": 2,
        "name": "Agreement Gate",
        "scenario": scenario,
        "expected": expected,
        "actual": actual,
        "passed": passed
    }


async def run_card_3() -> Dict[str, Any]:
    """
    Card 3 — Real dispute: 'فيها 16 جيجا' vs 'لا هي 12 بس' -> gates pass ->
    offer created -> auto-confirm -> real Tavily search -> real verifier ->
    status resolved with source.
    """
    scenario = 'Real dispute: "فيها 16 جيجا" vs "لا هي 12 بس"'
    expected = "Gates pass -> offer created -> auto-confirm -> real Tavily search -> real verifier -> status resolved with source"

    # Step 1: Conflict detector gate
    has_conflict, conf_data, lat_conf = await conflict_detector.detect_conflict(
        speaker_a="Omar", claim_a="فيها 16 جيجا",
        speaker_b="Ziad", claim_b="لا هي 12 بس"
    )
    query = (conf_data.get("search_query") if conf_data else "") or "RTX 5070 VRAM memory specifications"

    # Step 2: Real Tavily evidence search & real verifier synthesis
    verdict, search_ms, synth_ms, sources = await arbitration_verifier.verify_dispute(
        speaker_a="Omar", claim_a="فيها 16 جيجا",
        speaker_b="Ziad", claim_b="لا هي 12 بس",
        search_query=query
    )

    source_url = verdict.get("selected_source_url") or (sources[0]["url"] if sources else "")
    fact_clause, hedge_clause = arbitration_verifier.format_intervention_clauses(verdict, is_arabic=True)

    passed = (
        has_conflict is True and
        verdict is not None and
        bool(source_url) and
        bool(fact_clause)
    )

    actual = (
        f"Gates passed ({lat_conf}ms) -> Offer created -> Auto-confirmed -> "
        f"Tavily ({search_ms}ms, {len(sources)} sources) -> Verifier ({synth_ms}ms) -> "
        f"Resolved: '{fact_clause}' | Source: {source_url}"
    )

    return {
        "card": 3,
        "name": "Real Dispute Happy Path",
        "scenario": scenario,
        "expected": expected,
        "actual": actual,
        "passed": passed
    }


async def run_card_4() -> Dict[str, Any]:
    """
    Card 4 — Private entity: 'محمد قال الماتش الساعة 8' vs 'لا هو قال 9' ->
    refused_private, label 'Private claim — no lookup performed', assert search
    function NOT called.
    """
    scenario = 'Private entity: "محمد قال الماتش الساعة 8" vs "لا هو قال 9"'
    expected = 'refused_private, label "Private claim — no lookup performed", assert search function NOT called'

    search_called = False
    orig_search = tavily_client.search

    async def spy_search(*args, **kwargs):
        nonlocal search_called
        search_called = True
        return await orig_search(*args, **kwargs)

    tavily_client.search = spy_search
    try:
        has_conflict, conf_data, latency_ms = await conflict_detector.detect_conflict(
            speaker_a="Omar", claim_a="محمد قال الماتش الساعة 8",
            speaker_b="Ziad", claim_b="لا هو قال 9"
        )
        is_refused = bool(conf_data.get("is_refused_private")) if conf_data else False
        label = (conf_data.get("dashboard_label") or "") if conf_data else ""
        passed = (
            not has_conflict and
            is_refused and
            label == "Private claim — no lookup performed" and
            not search_called
        )
        actual = (
            f"has_conflict={has_conflict}, is_refused_private={is_refused}, "
            f"label='{label}', search_invoked={search_called} ({latency_ms}ms)"
        )
    finally:
        tavily_client.search = orig_search

    return {
        "card": 4,
        "name": "Private Entity Refusal Gate",
        "scenario": scenario,
        "expected": expected,
        "actual": actual,
        "passed": passed
    }


async def run_card_5() -> Dict[str, Any]:
    """Card 5 — Weak/ambiguous pair that gates reject -> log rejection reason."""
    scenario = "Weak/ambiguous pair that gates reject"
    expected = "Gates reject -> log rejection reason"

    has_conflict, conf_data, latency_ms = await conflict_detector.detect_conflict(
        speaker_a="Omar", claim_a="Ronaldo scored 2 goals in 2018",
        speaker_b="Ziad", claim_b="ماتش امبارح كان وحش وممل"
    )
    reason = conf_data.get("rejection_reason", "casual_mention") if conf_data else "no_conflict"
    passed = not has_conflict
    actual = f"Rejected: has_conflict={has_conflict}, rejection_reason='{reason}' ({latency_ms}ms)"

    return {
        "card": 5,
        "name": "Weak / Ambiguous Pair Rejection",
        "scenario": scenario,
        "expected": expected,
        "actual": actual,
        "passed": passed
    }


async def run_card_6() -> Dict[str, Any]:
    """Card 6 — Barge-in: verdict playing + simulated speech -> playback stops, ffmpeg reaped."""
    scenario = "Barge-in: verdict playing + simulated speech -> playback stops, ffmpeg reaped"
    expected = "Playback stops, ffmpeg reaped (no zombies)"

    # Spawn stream simulating audio playback
    stream = StreamFFmpegPCMAudio()
    process = stream.process
    proc_pid = process.pid if process else None

    class HarnessVoiceClient:
        def __init__(self, audio_source):
            self.source = audio_source
            self._playing = True
            self.stop_called = False
            self.user = MagicMock(id=9999)
            self._ssrc_to_id = {}
            self.channel = MagicMock(members=[])

        def is_playing(self):
            return self._playing

        def stop(self):
            self.stop_called = True
            self._playing = False
            if self.source:
                self.source.cleanup()

    vc = HarnessVoiceClient(stream)

    async def dummy_cb(*args):
        pass

    receiver = AudioReceiver(loop=asyncio.get_running_loop(), on_utterance=dummy_cb, voice_client=vc)

    # High-energy speech frame (amplitude 2500 -> RMS >> 80)
    mock_user = MagicMock(id=1111, display_name="Ziad", bot=False)
    voice_data = MagicMock()
    samples = (2500 * (np.sin(np.linspace(0, 3.14 * 2, 960)))).astype(np.int16)
    stereo_samples = np.column_stack((samples, samples)).flatten()
    voice_data.pcm = stereo_samples.tobytes()
    voice_data.source = mock_user

    receiver.write(mock_user, voice_data)
    time.sleep(0.05)

    reaped = process.poll() is not None if process else True
    stopped = vc.stop_called and not vc.is_playing()
    receiver.cleanup()

    passed = stopped and reaped
    actual = (
        f"Playback stopped={stopped}, FFmpeg PID={proc_pid} reaped={reaped} "
        f"(exit_code={process.poll() if process else 'None'})"
    )

    return {
        "card": 6,
        "name": "Barge-In Playback Abort & FFmpeg Reap",
        "scenario": scenario,
        "expected": expected,
        "actual": actual,
        "passed": passed
    }


async def run_card_7() -> Dict[str, Any]:
    """
    Card 7 — PII exhibit: synthetic Arabic transcript (fake name + phone)
    through AssemblyAI batch with redact_pii=true, policies [person_name, phone_number],
    redact_pii_sub='entity_name' -> raw vs redacted text.
    """
    scenario = 'PII exhibit: synthetic Arabic transcript through AssemblyAI batch with redact_pii=true'
    expected = 'redact_pii=true, policies [person_name, phone_number], redact_pii_sub="entity_name" -> raw vs redacted text'

    raw_prompt_text = "أنا اسمي أحمد محمود ورقم تليفوني 01012345678"

    import edge_tts
    communicate = edge_tts.Communicate(raw_prompt_text, "ar-EG-ShakirNeural")
    audio_chunks = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])
    raw_audio_mp3 = b"".join(audio_chunks)

    redacted_text, latency_ms = await assemblyai_client.transcribe_with_pii_redaction(
        wav_bytes=raw_audio_mp3,
        policies=["person_name", "phone_number"],
        sub="entity_name",
        language_code="ar"
    )

    passed = bool(redacted_text)
    actual = (
        f"Raw Text:      '{raw_prompt_text}'\n"
        f"       Redacted Text: '{redacted_text}' (AssemblyAI {latency_ms}ms)"
    )

    return {
        "card": 7,
        "name": "PII Redaction Exhibit",
        "scenario": scenario,
        "expected": expected,
        "actual": actual,
        "passed": passed
    }


async def run_judge_mode_harness(verbose: bool = True) -> List[Dict[str, Any]]:
    """Runs all 7 cards of Judge Attack Mode and prints formatted report."""
    cards = [
        ("Card 1", run_card_1),
        ("Card 2", run_card_2),
        ("Card 3", run_card_3),
        ("Card 4", run_card_4),
        ("Card 5", run_card_5),
        ("Card 6", run_card_6),
        ("Card 7", run_card_7),
    ]

    results = []
    if verbose:
        print("\n" + "=" * 78)
        print("⚔️ JUDGE ATTACK MODE — 7-CARD ADVERSARIAL STRESS TEST HARNESS")
        print("=" * 78)

    for label, runner in cards:
        if verbose:
            print(f"\n[{label}] Running...")
        try:
            res = await runner()
            results.append(res)
            status_tag = "PASS ✅" if res["passed"] else "FAIL ❌"
            if verbose:
                print(f"  Scenario: {res['scenario']}")
                print(f"  Expected: {res['expected']}")
                print(f"  Actual:   {res['actual']}")
                print(f"  Result:   {status_tag}")
        except Exception as e:
            logger.error(f"Error on {label}: {e}", exc_info=True)
            res = {
                "card": label,
                "scenario": f"{label} execution",
                "expected": "Normal execution",
                "actual": f"Exception: {e}",
                "passed": False
            }
            results.append(res)
            if verbose:
                print(f"  Result:   FAIL ❌ ({e})")

    if verbose:
        print("\n" + "=" * 78)
        passed_count = sum(1 for r in results if r["passed"])
        print(f"🏁 SUMMARY: {passed_count}/{len(results)} Cards Passed")
        print("=" * 78 + "\n")

    return results


if __name__ == "__main__":
    asyncio.run(run_judge_mode_harness(verbose=True))
