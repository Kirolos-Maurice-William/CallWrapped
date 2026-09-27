# Step 9: Captured Test Session Scoring Report

**Session Folder:** `2026-09-27_1808`  
**Source Labels File:** `labels_DRAFT.csv`  
**Evaluation Date:** 2026-09-27 20:08:02  
**STT Engine:** AssemblyAI Universal-3.5 Pro (Native Code-Switching)  
**Epistemic Engine:** Groq LPU (`qwen/qwen3.8-27b`)  

## 1. Executive Metric Summary

| Metric | Result | Target Benchmark | Status |
|---|---|---|---|
| **Micro WER (Corpus)** | **36.92%** | Beat 30.8% baseline | ⚠️ REVIEW |
| **Macro WER (Clip Avg)** | **52.24%** | Informational | — |
| **Clean Audio Micro WER** | **36.92%** | Beat 25.1% baseline | ⚠️ REVIEW |
| **Clean Audio Macro WER** | **52.24%** | Informational | — |
| **Number Accuracy** | **85.2%** (23/27) | ≥ 90% | ⚠️ REVIEW |
| **Topical Accuracy** | **95.2%** (20/21) | ≥ 80% (topical rows only) | ✅ PASS |
| **Null Detection Accuracy** | **100.0%** (1/1) | ≥ 80% (null_topic rows only) | ✅ PASS |
| **Topical Coverage** | **Model: 98.1% / Human: 99.2%** | Model vs Human audio share | ℹ️ REPORTED |
| **Claim Agreement** | **59.1%** | ≥ 75% | ⚠️ REVIEW |
| **Anger Agreement** | **18.2%** | Tolerance (mild/high) | ⚠️ REVIEW |
| **False-Anger Rate** | **0.0%** (0/4) | ≤ 15% | ✅ PASS |
| **Scored Clips** | **22** | Non-empty reference | ✅ COMPLETE |
| **Skipped Clips** | **0** | Empty reference | ℹ️ EXCLUDED |


## 2. Contradiction Pairs & Referee Gate Triggers

*0 pairs evaluated (no contradiction claim_pair labeled in session).*

## 3. Detailed Per-Clip Scoring Table

| Clip ID | Speaker | Loud | WER | Human Reference (`correct_text`) | AssemblyAI Raw (`asr_text`) | Topic (Pred/True) | Claim (Pred/True) | Anger (Pred/True) |
|---|---|---|---|---|---|---|---|---|
| `clip_001` | مستر سلطع | normal | **12.5%** | يا عم أقول لك اثنين تلت مليون يجيبولك أرض يجيبولك مية وخمسين فداء عأود بس زراعي. | يا عم أقول لك اثنين تلت مليون يجيبولك أرض يجيبولك مية وخمسين فداء عود بس بزراعة. | other / other | No / Yes | none / mild |
| `clip_002` | 2xDanger | normal | **66.7%** | ماشي يلاهبدا اهو ثلاثة اثنين واحد | يلا أبدأ وثلاثة اثنين واحد | other / other | No / No | none / none |
| `clip_003` | مستر سلطع | normal | **83.3%** | ماشي ياسطا ذا 150 فدان دول با حوال اثنين ثلاثة مليون ياعم | يا أستاذ الماء وخمسين فده دول بحوالي اثنين تلت مليون يا عم. | other / other | Yes / Yes | none / mild |
| `clip_004` | 2xDanger | normal | **40.0%** | يا عم مفيش الكلام ذا | يا عمي مفيش الكلام ده | other / other | No / Yes | none / mild |
| `clip_005` | Mostafa | normal | **55.6%** | ياعم لا ذا القيراط الواحد بااثنين الف بالفين جنيه | يا عم لا ده الإيرات الواحد باثنين ألف بألفين جنيه. | other / other | Yes / Yes | none / mild |
| `clip_006` | مستر سلطع | normal | **60.0%** | قيراط قيراط الواحد بخمسين الف | وراتن راتن بخمسين ألف. | other / other | Yes / Yes | none / mild |
| `clip_007` | 2xDanger | normal | **0.0%** | يا جدعان لو بتتكلموا عن الفدان الزراعي مفيش فدان زراعي ولا حتى الفدان اللي تبني عليه بهالأسعار دي | يا جدعان لو بتتكلموا عن الفدان الزراعي مفيش فدان زراعي ولا حتى الفدان اللي تبني عليه بهالأسعار دي | other / other | No / Yes | none / mild |
| `clip_008` | مستر سلطع | normal | **87.5%** | يا سطا ما تكتب على البتاع ماتتاكد يلا لو شفت الأسعار بس الزراعي يلا مش البنا | يلا طالما تنقم على اللي بتاعها تؤكد يلا من ما شفتي يلا البقاسة بس زراعة يلا مش بونا | other / other | No / No | none / mild |
| `clip_009` | Drago | normal | **18.2%** | هو مش كان بعشر تلاف مش كان بعشر تلاف يا جدعان | ومش كان بعشر تلاف مش كان بعشر تلاف يا جدعان | other / other | No / Yes | none / none |
| `clip_010` | 2xDanger | normal | **5.9%** | يا عم عشرة آلاف إيه قال فدانة يبقى سعره سبعين تمانين ألف جنيه في مصر على الاقل. | يا عم عشرة آلاف إيه قال فدانة يبقى سعره سبعين تمانين ألف جنيه في مصر على قال. | other / other | Yes / Yes | none / high |
| `clip_011` | مستر سلطع | normal | **100.0%** | عشرة الاف ايه انت الاخر اقعد بقى | عشان كده اتنين وانت الله كمان | other / other | No / No | none / high |
| `clip_012` | Mostafa | normal | **22.2%** | ياعم لا ده الفدان الواحد بخمسين ألف يا شباب. | يعمل لا ده الفدناني الواحد بخمسين ألف يا شباب. | other / other | Yes / Yes | none / mild |
| `clip_014` | مستر سلطع | normal | **47.4%** | لا سعر ثمانين ألف جنيه مين ياعم هو اسمه ايه ده الأرض 150 فدان وبعدين يسطا السعر غير البونا | لا تعمل ثمانين ألف جنيه عم هو اسمه هذا ال الارض ما خففت فدان وبعدين يحصل السعر غير البقرة. | other / other | No / Yes | none / mild |
| `clip_015` | 2xDanger | normal | **66.7%** | منين تقولي الفدان الزراعي ب 150 فدان ب 2 مليون جنيه ياعم هاتهم وانا هشتريهم | من انت قولي الفدان الزراعي 150 فدان ب2 مليون جنيه عاملوا عادهم انا اشتريهم | other / other | Yes / Yes | none / high |
| `clip_016` | Drago | normal | **200.0%** | اممممم | Mm-hmm. | null_topic / null_topic | No / No | none / none |
| `clip_017` | Drago | normal | **100.0%** | مش شاري | بالشالي. | null_topic / other | No / Yes | none / none |
| `clip_018` | مستر سلطع | normal | **72.7%** | يا عم ما تش بوص او ما تشتري يابا ما تشتري | يا عم ما تجي بوسع بدأوا نشتري اشتري يا عم اشتري | other / other | No / No | none / mild |
| `clip_019` | 2xDanger | normal | **10.0%** | ها أنا بقول لك وريني المية وخمسين فدانهم واثنين مليون جنيه دولة مستحيلي بقى الأسعار دي موجودة وأنا أشتريهم اقل | ها أنا بقول لك وريني المية وخمسين فدانهم واثنين مليون جنيه دولة مستعيلي بقى الأسعار دي موجودة وأنا أشتريهم قال | other / other | No / Yes | none / high |
| `clip_020` | مستر سلطع | normal | **0.0%** | ما تكتب عن نت يا عبد ما تشوف على ال شوف على ال شوف على الفي الفيسبوك. | ما تكتب عن نت يا عبد ما تشوف على ال شوف على ال شوف على الفي الفيسبوك. | other / other | No / No | none / mild |
| `clip_021` | 2xDanger | normal | **11.8%** | أقل مائة وخمسين فدان مائة وخمسين فدان دولة يبقوا مثلاً يعدوا خمسين ستين مليون جنيه مسترايح اوي. | أقل مائة وخمسين فدان مائة وخمسين فدان دولة يبقوا مثلاً يعدوا خمسين ستين مليون جنيه مستراي حاوي. | other / other | Yes / Yes | none / mild |
| `clip_022` | مستر سلطع | normal | **77.8%** | دا لو بونا يا عم احنا بنكلم في زراعة | دال أبونا يا عم أرضي كلام الأزراحة | other / other | No / Yes | none / mild |
| `clip_023` | 2xDanger | normal | **11.1%** | لا لا لا ولا لو فدان زراعي أو فدان أو فدان بونة مفيش الاسعار اللي أنت بتقولها دي. | لا لا لا ولا لو فدان زراعي أو فدان أو فدان بنا مفيش الأصغر اللي أنت بتقولها دي. | other / other | No / Yes | none / high |

