# Regression Ledger

Tracks every commit since base commit `701a7c0` ("step 10c: streaming TTS").
Format: Date | Commit Hash | What Changed | Proving Acceptance Test

| Date | Commit | What Changed | Acceptance Test |
|---|---|---|---|
| 2026-09-23 | `653cdaf` | Fix `!stats` KeyError on `disputed` key, audit dictionary keys with safe `.get(key, 0)` defaults | `tests/test_fix1_stats.py` |
| 2026-09-23 | `59b5e59` | Rewrite `parse_reset_duration` with ms-first compound accumulation (`h`, `m`, `s`) and harden key rotation | `tests/test_fix2_ratelimit.py` |
| 2026-09-23 | `e21879c` | Remove sync HTTP from property getters, await async analytics flush in `!recap`, warn on reset with non-empty buffer | `tests/test_fix3_eventloop.py` |
| 2026-09-23 | `792cb41` | Wire FastGate into referee pipeline start and support disagreement keywords | `tests/test_fix4_fastgate.py` |
| 2026-09-23 | `d03aff3` | Real measured latencies in `!arbitrate` and `!simulate`, dynamic winner/loser resolution, and source URL fallback | `tests/test_fix5_real_latencies.py`, `tests/test_fix6_arbitrate_keys.py` |
| 2026-09-23 | `10237b7` | Implement Arabic templates for spoken intervention verdicts (CONTRADICTED / SUPPORTED / UNVERIFIABLE) | `tests/test_fix7_arabic_verdicts.py` |
| 2026-09-23 | `05d592e` | Groq client hardening: ignore 11h daily reset header, zero remaining tokens on 429, retry key#2 | `tests/test_groq_rotation.py` |
| 2026-09-23 | `2fa11d4` | Correct model name references to `universal-3-5-pro` and dynamically display Groq model | `tests/test_assemblyai_capabilities.py` |
| 2026-09-23 | `ac96049` | Enforce English search queries in `CONFLICT_PROMPT` for cross-language evidence search | `tests/test_fix9_conflict_queries.py` |
| 2026-09-23 | `f2f8c00` | Deduplicate UTF-8 console output setup into `tests/_setup.py` across test suite | `tests._setup` / Test Suite Discovery |
| 2026-09-23 | `28db81a` | Add 429-TPD skip guards across Groq-dependent tests for free-tier quota resilience | `tests/test_split_classifier.py` |
| 2026-09-24 | `36111d1` | Harden TTS timing thresholds (0.20s) and 429-fallback detection across tests | `tests/test_streaming_tts.py` |
| 2026-09-24 | `281c759` | Wording polish: replace anger with frustration moments (`نوبات إحباط`), Arabic empty/zero-anger lines (P4) | `tests/test_recap.py` |
| 2026-09-24 | `e4d5f68` | Entity normalization in `ClaimMemory` stripping Arabic articles (`ال`), English articles, and prefixes (P6) | `tests/test_p6_entity_normalization.py` |
| 2026-09-24 | `226aca2` | Expand AssemblyAI keyterms to 54 items with Egyptian football, movies, music, and politics terms (P5) | `tests/test_p5_keyterms.py` |
| 2026-09-24 | `71f7ad2` | Implement `!clear` full reset clearing `claim_memory` and queue with drop warnings (P3) | `tests/test_p3_clear.py` |
| 2026-09-24 | `a0430c0` | Implement `!dashboard` command rendering live judge dashboard URL embed from config (P2) | `tests/test_p2_dashboard.py` |
| 2026-09-24 | `22b6578` | Implement privacy trio: voice join Arabic notice, `!privacy` command, and `!leave` full session reset (P1) | `tests/test_p1_privacy.py` |
| 2026-09-24 | `4004668` | Wrap `write_chunk` in `asyncio.to_thread` and make AudioSource non-blocking to prevent event loop stalls (BUG 1) | `tests/test_bug1_eventloop_tts.py` |
| 2026-09-24 | `802b25a` | Only invoke `record_anger` when anger is mild or high in batch analytics line handler (BUG 2) | `tests/test_bug2_batch_anger.py` |
| 2026-09-24 | `e5b3bbc` | Enforce `correct_fact` language matching speakers' language and strip doubled punctuation (BUG 3) | `tests/test_bug3_arabic_fact.py` |
| 2026-09-24 | `36baa6f` | Silence unexpected RTCP packet spam from `discord.ext.voice_recv` via `SilenceRTCPFilter` (BUG 4) | `tests/test_bug4_rtcp_filter.py` |
| 2026-09-24 | `cc681e4` | Add real Discord voice-channel live smoke test for streaming and barge-in | `tests/smoke_real_voice.py` |
| 2026-09-24 | `dccac0e` | Implement conflict authenticity gate and private entity refusal with Egyptian few-shots (Phase B) | `tests/test_phase_b_referee_gates.py` |
| 2026-09-24 | `83410c9` | Update spoken intervention templates to hedged social form in Arabic & English (Phase D) | `tests/test_fix7_arabic_verdicts.py`, `tests/test_bug3_arabic_fact.py` |
| 2026-09-24 | `3b61d48` | Unbuffered raw pipe with bufsize=0 and real voice-channel smoke test (verdict, barge-in, private refusal, 0 stalls) | `tests/smoke_real_voice.py`, `tests/test_barge_in.py` |
| 2026-09-24 | `6f0fa7c` | Implement Two-Stage Referee (detect & offer, background prefetch, voice/!check confirmation, 30s expiry, 180s cooldown, !start mode) | `tests/test_two_stage_referee.py`, `tests/smoke_real_voice.py` |
| 2026-09-24 | `837b1ce` | Two-clause streaming verdict and offer-time TTS pre-warming for <1800ms T_perceived | `tests/test_two_clause_prewarm.py`, `tests/smoke_real_voice.py` |
| 2026-09-24 | `95e993d` | Verifier fast-path grounding in Tavily include_answer and max_tokens=140 for sub-1s Groq synthesis | `tests/test_bug3_arabic_fact.py`, `tests/smoke_real_voice.py` |
| 2026-09-24 | `f21628f` | Tune max_tokens=180 to prevent JSON truncation 400 Bad Request error on Groq, grounded fast-path | `tests/test_bug3_arabic_fact.py`, `tests/smoke_real_voice.py` |
| 2026-09-25 | `cc0493e` | Dispute cards in `LIVE_STATE` (latest 5, newest first) covering offered/checking/resolved/expired/refused_private, exposed on `/api/live` and pushed over `/api/ws` (Phase 1) | `tests/test_dispute_cards_api.py` |
| 2026-09-25 | `9b6a199` | Add `DisputesPanel` rendering disputes with status badges, side-by-side claims, RTL-safe `dir="auto"`, and live WebSocket sync (Phase 2) | `npm run build`, `tests/test_dispute_cards_api.py` |
| 2026-09-25 | `6e11630` | Implement `TEST_CAPTURE_MODE` non-blocking clip factory, session log JSONL, and `!stop-capture` draft labeling CSV generator (Phase 3) | `tests/test_capture_mode.py`, `tests/test_barge_in.py` |
| 2026-09-25 | `447d9b0` | Implement 7-card Judge Attack Mode adversarial harness and `!judge-mode` Discord command (Phase 4) | `bot/arbitration/judge_mode.py`, `tests/test_judge_mode.py` |
| 2026-09-25 | `226c4d2` | Poll for background analytics task completion in discover suite; 89/89 tests passing green | `tests/test_fanout.py` |
| 2026-09-25 | `e2ff978` | Energy-trim trailing silence before upload (-1.23% WER improvement: 29.54% vs 30.77%, p50 -18ms) (EXP 1) | `tests/test_silence_trim.py`, `audit/exp1_silence_trim.py` |
| 2026-09-25 | `dafe5b0` | Keyterms ablation (expanded 160 terms won with 28.62% WER vs 29.54% on 54 terms, 90% numbers) (EXP 2) | `tests/test_p5_keyterms.py`, `audit/exp2_keyterms_ablation.py` |
| 2026-09-25 | `EXP3_HASH` | Custom spelling probe (44 mappings dropped Corpus WER to 22.15% and Clean WER to 19.40%, 90% numbers) (EXP 3) | `tests/test_custom_spelling.py`, `audit/exp3_custom_spelling.py` |





