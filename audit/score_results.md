# Step 9: Captured Test Session Scoring Report

**Session Folder:** `test_score_session_7xz30djq`  
**Source Labels File:** `labels_DRAFT.csv`  
**Evaluation Date:** 2026-09-26 15:46:37  
**STT Engine:** AssemblyAI Universal-3.5 Pro (Native Code-Switching)  
**Epistemic Engine:** Groq LPU (`qwen/qwen3.8-27b`)  

## 1. Executive Metric Summary

| Metric | Result | Target Benchmark | Status |
|---|---|---|---|
| **Overall WER** | **16.72%** | Beat 30.8% baseline | ✅ PASS |
| **Clean Audio WER** | **16.72%** | Beat 25.1% baseline | ✅ PASS |
| **Number Accuracy** | **100.0%** (0/0) | ≥ 90% | ✅ PASS |
| **Topic Classification** | **33.3%** | ≥ 80% | ⚠️ REVIEW |
| **Claim Agreement** | **100.0%** | ≥ 75% | ✅ PASS |
| **Anger Agreement** | **100.0%** | Tolerance (mild/high) | ✅ PASS |
| **False-Anger Rate** | **0.0%** | ≤ 15% | ✅ PASS |
| **Scored Clips** | **3** | Non-empty reference | ✅ COMPLETE |
| **Skipped Clips** | **1** | Empty reference | ℹ️ EXCLUDED |

## 3. Detailed Per-Clip Scoring Table

| Clip ID | Speaker | Loud | WER | Human Reference (`correct_text`) | AssemblyAI Raw (`asr_text`) | Topic (Pred/True) | Claim (Pred/True) | Anger (Pred/True) |
|---|---|---|---|---|---|---|---|---|
| `clip_001` | Ahmed | normal | **12.5%** | لكن تميزت في الفترة الأخيرة هي رياضة السباحة بالزعانف تابعونا النهارده في حلم جديد وإحلم معانا | لكن تميزت في الفترة الأخيرة هي رياضة استباحة بالزعانف تبعونا النهاردة في حلم جديد واحلم معانا | other / sports | No / No | none / none |
| `clip_002` | Tamer | normal | **28.6%** | سلامات عليكم حكلمكو النهارده عن ال uncertainty | السلام عليكم. أكلمكم النهاردة عن ال uncertainty. | other / other | No / No | none / none |
| `clip_003` | Kareem | normal | **9.1%** | فهو لا يعدو كونه سلوكا وكل سلوك على ضوء الحتمية السيكولوجية | فهو لا يعد كونه سلوكا وكل سلوك على ضوء الحتمية السيكولوجية | other / movies | No / No | none / none |


## 4. Skipped Clips (Unlabeled by Human)

| Clip ID | Filename | Speaker | Reason |
|---|---|---|---|
| `clip_004` | `unlabeled_clip.wav` | Ziad | Empty correct_text (unlabeled by human) |

