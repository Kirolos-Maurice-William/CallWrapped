# Step 9: Captured Test Session Scoring Report

**Session Folder:** `2026-09-27_1803`  
**Source Labels File:** `labels_DRAFT.csv`  
**Evaluation Date:** 2026-09-27 19:33:42  
**STT Engine:** AssemblyAI Universal-3.5 Pro (Native Code-Switching)  
**Epistemic Engine:** Groq LPU (`qwen/qwen3.8-27b`)  

## 1. Executive Metric Summary

| Metric | Result | Target Benchmark | Status |
|---|---|---|---|
| **Micro WER (Corpus)** | **40.18%** | Beat 30.8% baseline | ⚠️ REVIEW |
| **Macro WER (Clip Avg)** | **42.07%** | Informational | — |
| **Clean Audio Micro WER** | **40.18%** | Beat 25.1% baseline | ⚠️ REVIEW |
| **Clean Audio Macro WER** | **42.07%** | Informational | — |
| **Number Accuracy** | n/a (0 samples) | ≥ 90% | — |
| **Topical Accuracy** | **87.5%** (7/8) | ≥ 80% (topical rows only) | ✅ PASS |
| **Null Detection Accuracy** | **25.0%** (1/4) | ≥ 80% (null_topic rows only) | ⚠️ REVIEW |
| **Topical Coverage** | **Model: 96.3% / Human: 73.9%** | Model vs Human audio share | ℹ️ REPORTED |
| **Claim Agreement** | **41.7%** | ≥ 75% | ⚠️ REVIEW |
| **Anger Agreement** | **100.0%** | Tolerance (mild/high) | ✅ PASS |
| **False-Anger Rate** | **0.0%** (0/12) | ≤ 15% | ✅ PASS |
| **Scored Clips** | **12** | Non-empty reference | ✅ COMPLETE |
| **Skipped Clips** | **0** | Empty reference | ℹ️ EXCLUDED |


## 2. Contradiction Pairs & Referee Gate Triggers

| Pair ID | Speaker A | Claim A | Speaker B | Claim B | Referee Triggered? | Search Query | Verdict Stance |
|---|---|---|---|---|---|---|---|
| `pair_1` | 2xDanger | عارفين جد عن حد حد فكر فيلم سبايدر مان نوي هوم فاكرين لما سبايدر مان مسح ذكرته عشان محدش يفتكره | Mostafa | عم لا الدكتور هو المسح زاكر | 🛑 NO (Filtered/Suppressed) | — | Suppressed (casual_mention) |
| `pair_2` | 2xDanger | يا عم هو أنا مسح زكرته بنفسه سمعت زمان مسح زكرته عشان ما حدش يفتكره دكتور سترينج مسح ذكرة سبايدرمان | Drago | إذا أنت صاحبه هو اللي لماذا ذكرتها إذا عال | 🛑 NO (Filtered/Suppressed) | — | Suppressed (casual_mention) |


### Dispute Detail: `pair_1`

- **Speaker A (2xDanger):** "عارفين جد عن حد حد فكر فيلم سبايدر مان نوي هوم فاكرين لما سبايدر مان مسح ذكرته عشان محدش يفتكره"
- **Speaker B (Mostafa):** "عم لا الدكتور هو المسح زاكر"
- **Referee Gate Decision:** 🛑 **Suppressed** (casual_mention, Confidence: 95%)


### Dispute Detail: `pair_2`

- **Speaker A (2xDanger):** "يا عم هو أنا مسح زكرته بنفسه سمعت زمان مسح زكرته عشان ما حدش يفتكره دكتور سترينج مسح ذكرة سبايدرمان"
- **Speaker B (Drago):** "إذا أنت صاحبه هو اللي لماذا ذكرتها إذا عال"
- **Referee Gate Decision:** 🛑 **Suppressed** (casual_mention, Confidence: 95%)


## 3. Detailed Per-Clip Scoring Table

| Clip ID | Speaker | Loud | WER | Human Reference (`correct_text`) | AssemblyAI Raw (`asr_text`) | Topic (Pred/True) | Claim (Pred/True) | Anger (Pred/True) |
|---|---|---|---|---|---|---|---|---|
| `clip_002` | 2xDanger | normal | **66.7%** | انا هبدأ دلوقتي | ما أبدأ دلوقتي. | null_topic / null_topic | No / No | none / none |
| `clip_003` | Mostafa | normal | **33.3%** | ماشي أنا كده وقفت هو انا لوهو واقف وأنا وقفته حاجة هتحصل؟ | ماشي أنا كده وقفت فأنا لو أوقع واقف وأنا وقفته حاجة تحصل؟ | personal / null_topic | No / No | none / none |
| `clip_005` | 2xDanger | normal | **41.2%** | عارفين يا جدعان حد فاكرفيلم سبايدرمان نوي هوم  فاكرين لما سبايدر مان مسح ذكرته عشان محدش يفتكره | عارفين جد عن حد حد فكر فيلم سبايدر مان نوي هوم فاكرين لما سبايدر مان مسح ذكرته عشان محدش يفتكره | movies / movies | No / Yes | none / none |
| `clip_006` | Drago | normal | **7.7%** | آه ده لا ما هو مش هو اللي مسح ذكرته بنفسه ده صاحبه. | آه ده لا ما هو مش هو اللي مسح ذكرته بنفسه ده صح. | movies / movies | No / Yes | none / none |
| `clip_007` | Drago | normal | **0.0%** | لا لا لا | لا لا لا | null_topic / movies | No / Yes | none / none |
| `clip_008` | 2xDanger | normal | **38.5%** | يا عم هوالمسح زكرته بنفسه سبايدر مان مسح زكرته عشان ما حدش يفتكره | يا عم هو أنا مسح زكرته بنفسه سمعت زمان مسح زكرته عشان ما حدش يفتكره | movies / movies | No / Yes | none / none |
| `clip_009` | Mostafa | normal | **28.6%** | يا عم لا الدكتور هو المسح زاكرته | عم لا الدكتور هو المسح زاكر | movies / movies | No / Yes | none / none |
| `clip_010` | مستر سلطع | normal | **44.4%** | ياسطا حط راسه في الزيت حط راسه في الزيت | يا استحط راسه في الزه حط راسه في الزه | movies / null_topic | No / No | none / none |
| `clip_011` | 2xDanger | normal | **10.0%** | يا عم دكتور سترنج مش هو اللي مسح ذكرة سبايدرمان | يا عم دكتور سترينج مش هو اللي مسح ذكرة سبايدرمان | movies / movies | Yes / Yes | none / none |
| `clip_013` | مستر سلطع | normal | **83.3%** | الزيت ياسطا الزيت هو المسح البطاطس | إزاي تياف؟ إزاي تروح لمازح البطاطس؟ | movies / null_topic | No / No | none / none |
| `clip_014` | Drago | normal | **87.5%** | يا جدعان صاحبه هو المسح ذاكرته يا جدعان | إذا أنت صاحبه هو اللي لماذا ذكرتها إذا عال | movies / movies | No / Yes | none / none |
| `clip_016` | 2xDanger | normal | **63.6%** | يا جدعان اسمعوا مني سبايدرمان هو المسح ذاكرته عشان محدش يفتكره | أكيد عين اسمعوا مني سبايدر مانها هو اللي مسح ذاكرتش محدش يفتكره | movies / movies | No / Yes | none / none |

