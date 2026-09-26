# Step 9: Captured Test Session Scoring Report

**Session Folder:** `2026-09-26_smoke_rehearsal`  
**Source Labels File:** `labels_DRAFT.csv`  
**Evaluation Date:** 2026-09-26 16:58:01  
**STT Engine:** AssemblyAI Universal-3.5 Pro (Native Code-Switching)  
**Epistemic Engine:** Groq LPU (`qwen/qwen3.8-27b`)  

## 1. Executive Metric Summary

| Metric | Result | Target Benchmark | Status |
|---|---|---|---|
| **Micro WER (Corpus)** | **12.28%** | Beat 30.8% baseline | ✅ PASS |
| **Macro WER (Clip Avg)** | **12.25%** | Informational | — |
| **Clean Audio Micro WER** | **12.28%** | Beat 25.1% baseline | ✅ PASS |
| **Clean Audio Macro WER** | **12.25%** | Informational | — |
| **Number Accuracy** | n/a (0 samples) | ≥ 90% | — |
| **Topic Classification** | **33.3%** | ≥ 80% | ⚠️ REVIEW |
| **Claim Agreement** | **100.0%** | ≥ 75% | ✅ PASS |
| **Anger Agreement** | **100.0%** | Tolerance (mild/high) | ✅ PASS |
| **False-Anger Rate** | **0.0%** (0/3) | ≤ 15% | ✅ PASS |
| **Scored Clips** | **3** | Non-empty reference | ✅ COMPLETE |
| **Skipped Clips** | **1** | Empty reference | ℹ️ EXCLUDED |

## 2. Contradiction Pairs & Referee Gate Triggers

*0 pairs evaluated (no contradiction claim_pair labeled in session).*

## 3. Detailed Per-Clip Scoring Table

| Clip ID | Speaker | Loud | WER | Human Reference (`correct_text`) | AssemblyAI Raw (`asr_text`) | Topic (Pred/True) | Claim (Pred/True) | Anger (Pred/True) |
|---|---|---|---|---|---|---|---|---|
| `clip_001` | Ahmed | normal | **7.7%** | أعزائي الشباب أهلا بيكم وحلقة جديدة وحلم جديد من إحلم معانا حنعيش النهارده في حلمنا مع مجموعة من الشباب متميز جدا في رياضة يمكن جديدة علينا | أعزائي الشباب أهلا بيكم وحلقة جديدة وحلم جديد من احلم معانا حنعيش النهاردة في حلمنا مع مجموعة من الشباب متميز جدا فريضة يمكن جديدة علينا | other / sports | No / No | none / none |
| `clip_002` | Omar | normal | **19.0%** | لو حد بص على ال الترجمة بتاعتها في القاموس حيلاقي عدم اليقين بس ده ترجمة مش دقيقة برضه هو يقين ناقص | لو حد بس على الترجمة بتاعتك في قاموس حيلاقي عدم اليقين بس ده ترجمة مش دقيقة برضه هو يقين ناقص | other / other | No / No | none / none |
| `clip_003` | Tamer | normal | **10.0%** | الأمر المؤكد إذا أن الخيال مهما انطلق بعيدا عن الواقع | الأمر المؤكد إذن أن الخيال مهما انطلق بعيدا عن الواقع | other / movies | No / No | none / none |


## 4. Skipped Clips (Unlabeled by Human)

| Clip ID | Filename | Speaker | Reason |
|---|---|---|---|
| `clip_004` | `1790426815_Ziad.wav` | Ziad | Empty correct_text (unlabeled by human) |

