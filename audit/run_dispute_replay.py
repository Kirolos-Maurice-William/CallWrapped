import sys
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

base_dir = Path(__file__).resolve().parent.parent
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

from bot.arbitration.dispute_replay import (
    load_session_events,
    replay_session,
    format_decision_timeline,
)
from bot.arbitration.dispute_tracker import DisputeTracker


def run_all_replays():
    base_dir = Path(__file__).resolve().parent.parent
    recordings_dir = base_dir / "recordings" / "test_session"
    shadow_dir = base_dir / "audit" / "shadow"
    shadow_dir.mkdir(parents=True, exist_ok=True)

    sessions = [
        ("World Cup (Escalation / Multi-party)", recordings_dir / "2026-09-27_1806", shadow_dir / "world_cup_shadow.jsonl", True),
        ("Batch 1 (Casual / Personal Life)", recordings_dir / "2026-09-26_1817", shadow_dir / "batch1_shadow.jsonl", False),
        ("Movies (Spider-Man Cluster)", recordings_dir / "2026-09-27_1803", shadow_dir / "movies_shadow.jsonl", True),
    ]

    summary_rows = []

    for name, s_folder, shadow_log, should_offer in sessions:
        print(f"\n{'=' * 80}")
        print(f"=== REPLAYING SESSION: {name} ===")
        print(f"Folder: {s_folder.name}")
        print(f"Shadow Log: {shadow_log.relative_to(base_dir)}")
        print(f"{'=' * 80}\n")

        # Clear shadow log file if exists
        if shadow_log.exists():
            shadow_log.unlink()

        events = load_session_events(s_folder)
        tracker, decisions = replay_session(events, shadow_log_path=shadow_log)

        # Print timeline
        timeline = format_decision_timeline(events, decisions)
        print(timeline)

        offer_decisions = [d for d in decisions if d.action == "request_offer"]
        tracker_offered = len(offer_decisions) > 0
        agree = (tracker_offered == should_offer)

        summary_rows.append({
            "session": name,
            "folder": s_folder.name,
            "events_count": len(events),
            "tracker_offered": tracker_offered,
            "should_offer": should_offer,
            "agree": agree,
            "offer_events": [d.thread.events[-1].event_id for d in offer_decisions if d.thread and d.thread.events],
        })

        if tracker_offered:
            print(f"\n[OFFER TRIGGERED] Total offers: {len(offer_decisions)}")
            for od in offer_decisions:
                print(f"  -> Event: {od.thread.events[-1].event_id if od.thread and od.thread.events else 'unknown'} | Score: {od.confidence:.4f} | State: {od.state}")
        else:
            print("\n[NO OFFER TRIGGERED] Zero offers across session.")

    print(f"\n{'=' * 80}")
    print("=== SHADOW AGREEMENT SUMMARY TABLE ===")
    print(f"{'=' * 80}\n")
    print("| Session | Events | Tracker Offered? | Should It Have? | Agree? |")
    print("|---|---|---|---|---|")
    for r in summary_rows:
        offered_str = "YES" if r["tracker_offered"] else "NO"
        should_str = "YES" if r["should_offer"] else "NO"
        agree_str = "AGREE ✅" if r["agree"] else "DISAGREE ⚠️"
        print(f"| {r['session']} (`{r['folder']}`) | {r['events_count']} | {offered_str} | {should_str} | {agree_str} |")


if __name__ == "__main__":
    run_all_replays()
