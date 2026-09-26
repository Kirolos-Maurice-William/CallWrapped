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
| 2026-09-25 | `0ac14ef` | Custom spelling probe (44 mappings dropped Corpus WER to 22.15% and Clean WER to 19.40%, 90% numbers) (EXP 3) | `tests/test_custom_spelling.py`, `audit/exp3_custom_spelling.py` |
| 2026-09-25 | `22521f3` | Selective Groq correction probe: 0 number corruption verified, but +1.54% WER degradation (23.69% vs 22.15%); rejected per evidence (EXP 4) | `audit/exp4_selective_groq_correction.py` |
| 2026-09-25 | `3322304` | Language config probe (fixed language_code='ar' matched 22.15% WER with +92ms faster p50 and cleaner WER 19.40% vs 21.07%) (EXP 5) | `audit/exp5_language_config.py` |
| 2026-09-25 | `dd42bfe` | Final production STT config (silence trim + 160 keyterms + 44 custom_spelling); 95/95 tests green | `audit/run_hearing_test.py`, `tests/` |
| 2026-09-25 | `a973204` | Replace wildcard allow_origins with settings.CORS_ORIGINS (Phase 1) | `backend/app/main.py`, full suite 95/95 OK |
| 2026-09-25 | `932f2cf` | Restore two-stage referee invariant in `!arbitrate` and `!simulate` (Phase 2) | `bot/main.py`, `tests/test_fix5_real_latencies.py`, `tests/test_fix6_arbitrate_keys.py`, full suite 95/95 OK |
| 2026-09-25 | `0c35b20` | Bound complete_chat_sync rate limit sleep to 2.0s max (Phase 3) | `bot/ai/groq.py`, `tests/test_fix2_ratelimit.py`, full suite 96/96 OK |
| 2026-09-26 | `027216a` | Branding sweep to CallWrapped and Universal model fallback (Phase 4) | `bot/`, `backend/`, `frontend/`, `tests/test_fix1_stats.py`, full suite 96/96 OK |
| 2026-09-26 | `da1cec3` | Dead code cleanup, privacy text update, and pruned dependencies (Phase 5) | `bot/`, `backend/`, `tests/`, `requirements.txt`, full suite 96/96 OK |
| 2026-09-26 | `7edf883` | WebSocket origin check on `/api/ws` closing unauthorized origins with code 1008 (Phase 1 / SEC-01) | `tests/test_verify_dashboard_websocket_alive.py`, full suite 99/99 OK |
| 2026-09-26 | `6d0d025` | Enforce 180s cooldown check in `!arbitrate` with remaining-time reply (Phase 2 / INV-01) | `tests/test_arbitrate_cooldown.py`, full suite 100/100 OK |
| 2026-09-26 | `6b93ac1` | Complete repo-wide branding sweep to CallWrapped and synchronize `.env.example` with active configuration (Phase 3 / BRD-01 + CFG-01) | `git grep -in "voice arbitrator"` -> 0 hits, full suite 100/100 OK |
| 2026-09-26 | `2bf3fb8` | Complete `!help` command roster, integrate Fact Check Mode header badge in dashboard, remove unused `is_on`, track `audit/` reports (Phase 4 / DOC-01 + CON-01) | `npm run build` OK, full suite 100/100 OK, git status clean |
| 2026-09-26 | `dac9b02` | Session-isolated test capture with per-session timestamped folders and draft labels CSV (Phase 1) | `tests/test_capture_mode.py`, `tests/test_barge_in.py`, full suite 101/101 OK |
| 2026-09-26 | `ca7fa7e` | Safe recordings migration clustering stacked clips by >10-minute gap, preserving human labels (Phase 2) | `tests/test_migrate_recordings.py`, full suite 104/104 OK |
| 2026-09-26 | `2b5df7f` | Document TEST_CAPTURE_MODE in .env.example, update !help with per-session folders, verify !privacy (Phase 3) | `tests/test_p1_privacy.py`, full suite 104/104 OK |
| 2026-09-26 | `3416d10` | Auto-finalize active capture on !leave and !clear, report CSV path to Discord (Phase 1 / CAP-02) | `tests/test_capture_mode.py`, full suite 105/105 OK |
| 2026-09-26 | `f0b16cc` | Graceful OSError degradation with capture_failed status in capture save, synchronize ledger (Phase 2 / CAP-01 + REG-01) | `tests/test_capture_mode.py`, full suite 105/105 OK |
| 2026-09-26 | `2999aca` | Rehearse Step 9 scoring tool against smoke-labeled session and generate score_results.md (Phase 4) | `audit/score_results.md`, full suite 107/107 OK |
| 2026-09-26 | `a89c920` | Isolate test_score_test_session to tempfile and regenerate rehearsal score_results.md (Phase 1 / TRACE-01) | `tests/test_score_test_session.py`, full suite 107/107 OK |
| 2026-09-26 | `30e4c84` | Report both micro corpus WER and macro clip WER with micro headline (Phase 2 / TRACE-03) | `audit/score_results.md`, full suite 107/107 OK |
| 2026-09-26 | `5ee2d46` | Add __main__ guard in check_numbers, remove unused imports and unreferenced finalize_capture_if_active (Phase 3 / TRACE-02 + TRACE-04) | `audit/check_numbers.py`, full suite 107/107 OK |
| 2026-09-26 | `3ec4d59` | Implement topic/anger parity with batched classifier, 0-denominator protection, and missing column tolerance (Phase 4) | `tests/test_score_test_session.py`, full suite 107/107 OK |
| 2026-09-26 | `b876ee2` | Add third Groq API key (GROQ_API_KEY_3) to rotation pool and dynamic cascade retry | `bot/ai/groq.py`, `tests/test_groq_rotation.py`, full suite 108/108 OK |
| 2026-09-26 | `d2beac6` | Configure fourth Groq API key (GROQ_API_KEY_4) in rotation pool without live tests | `bot/config.py`, `backend/app/config.py`, `bot/ai/groq.py`, `.env.example` |
| 2026-09-26 | `audit` | OpenRouter Qwen 3.8 27B emergency fallback evaluation (VERDICT: COMPATIBLE, 5/5 claims, 2/2 twin pairs, 1242ms p50, insurance doc only) | `audit/openrouter_probe.py`, `audit/OPENROUTER_EVALUATION.md`, `.env.example` |
| 2026-09-26 | `32d934d` | Add 401/403 invalid key cascade and permanent removal from pool, dynamic discovery from i=2, 4-way rotation test | `tests/test_groq_rotation.py`, full suite 110/110 OK |
| 2026-09-26 | `24db55c` | Score Batch 1 captured session (39.59% micro WER, 100% num acc, 0 false anger, 92% claim agreement, 0 false referee triggers) | `audit/score_results_batch1.md`, full suite 110/110 OK |

















