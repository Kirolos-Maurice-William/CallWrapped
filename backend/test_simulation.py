import asyncio
import logging
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from app.database import init_db, AsyncSessionLocal
from app.models import Call, Participant
from app.services.orchestrator import get_call_orchestrator
from app.routers.dashboard import get_call_dashboard

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("simulation")

async def run_simulation():
    logger.info("--- STARTING END-TO-END SIMULATION ---")
    await init_db()

    # 1. Create a simulated call
    async with AsyncSessionLocal() as db:
        call = Call(title="Friday Movie & Football Chat", status="active")
        db.add(call)
        await db.flush()

        p_you = Participant(call_id=call.id, name="You", audio_stream_id="stream_a")
        p_friend = Participant(call_id=call.id, name="Friend", audio_stream_id="stream_b")
        db.add_all([p_you, p_friend])
        await db.commit()
        await db.refresh(call)
        call_id = call.id
        p_you_id = p_you.id
        p_friend_id = p_friend.id

    logger.info(f"Created Call: {call_id}")
    orchestrator = get_call_orchestrator(call_id)

    # 2. Simulate Turn 1: You make a factual claim about Inception movie release
    turn_1 = {
        "call_id": call_id,
        "speaker_id": p_you_id,
        "speaker_name": "You",
        "start_ms": 1000,
        "end_ms": 5000,
        "text": "بص يا عم أنا متأكد فيلم Inception نزل في 2015",
        "language": "mixed"
    }
    logger.info(f"\n[Turn 1] You: {turn_1['text']}")
    await orchestrator.handle_final(turn_1)
    await asyncio.sleep(1)

    # 3. Simulate Turn 2: Friend disagrees directly
    turn_2 = {
        "call_id": call_id,
        "speaker_id": p_friend_id,
        "speaker_name": "Friend",
        "start_ms": 5500,
        "end_ms": 9000,
        "text": "لا يا عم أنت فاهم غلط الفيلم نزل في 2010",
        "language": "ar"
    }
    logger.info(f"\n[Turn 2] Friend: {turn_2['text']}")
    await orchestrator.handle_final(turn_2)

    # Give fact checker and interruption time to process asynchronously
    logger.info("Waiting for async fact-checker and evidence retrieval...")
    await asyncio.sleep(5)

    # 4. Conclude Call and fetch Dashboard report
    async with AsyncSessionLocal() as db:
        dashboard = await get_call_dashboard(call_id, db)

    logger.info("\n==========================================")
    logger.info("           CALL DASHBOARD REPORT          ")
    logger.info("==========================================")
    logger.info(f"Title: {dashboard.title}")
    logger.info(f"Duration: {dashboard.formatted_duration}")
    logger.info("\n--- SPEAKING TIME ---")
    for s in dashboard.speakers:
        logger.info(f"{s.name}: {s.percentage}% ({s.duration_ms} ms)")

    logger.info("\n--- TOPICS ---")
    for t in dashboard.topics:
        logger.info(f"{t.topic}: {t.formatted_duration} ({t.percentage}%)")

    logger.info("\n--- ARGUMENTS ---")
    for a in dashboard.arguments:
        logger.info(f"Topic: {a.topic} | Claim A: '{a.claim_a}' vs Claim B: '{a.claim_b}'")

    logger.info("\n--- FACT CHECKS & LATENCY WATERFALL ---")
    logger.info(f"Total checked: {dashboard.total_claims_checked}")
    for fc in dashboard.fact_checks:
        logger.info(f"Result: {fc.result} | Confidence: {fc.confidence}")
        logger.info(f"Evidence: {fc.evidence}")
        logger.info(f"AI Interrupted: {fc.interrupted} | Words: {fc.interruption_text}")
        logger.info("Sources:")
        for src in fc.sources:
            logger.info(f"  - [{src.title}] {src.url}")

    logger.info("\n--- EXECUTIVE SUMMARY ---")
    logger.info(dashboard.summary)
    logger.info("==========================================")
    logger.info("HIGH PERFORMANCE SIMULATION COMPLETED!")

if __name__ == "__main__":
    asyncio.run(run_simulation())
