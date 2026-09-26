# Step 9: Captured Test Session Scoring Report

**Session Folder:** `2026-09-26_1817`  
**Source Labels File:** `labels_DRAFT.csv`  
**Evaluation Date:** 2026-09-26 20:05:32  
**STT Engine:** AssemblyAI Universal-3.5 Pro (Native Code-Switching)  
**Epistemic Engine:** Groq LPU (`qwen/qwen3.8-27b`)  

## 1. Executive Metric Summary

| Metric | Result | Target Benchmark | Status |
|---|---|---|---|
| **Micro WER (Corpus)** | **40.10%** | Beat 30.8% baseline | ⚠️ REVIEW |
| **Macro WER (Clip Avg)** | **51.62%** | Informational | — |
| **Clean Audio Micro WER** | **40.10%** | Beat 25.1% baseline | ⚠️ REVIEW |
| **Clean Audio Macro WER** | **51.62%** | Informational | — |
| **Number Accuracy** | **100.0%** (3/3) | ≥ 90% | ✅ PASS |
| **Topical Accuracy** | **85.7%** (6/7) | ≥ 80% (topical rows only) | ✅ PASS |
| **Null Detection Accuracy** | **77.8%** (14/18) | ≥ 80% (null_topic rows only) | ⚠️ REVIEW |
| **Topical Coverage** | **Model: 62.6% / Human: 45.2%** | Model vs Human audio share | ℹ️ REPORTED |
| **Claim Agreement** | **96.0%** | ≥ 75% | ✅ PASS |
| **Anger Agreement** | **100.0%** | Tolerance (mild/high) | ✅ PASS |
| **False-Anger Rate** | **0.0%** (0/25) | ≤ 15% | ✅ PASS |
| **Scored Clips** | **25** | Non-empty reference | ✅ COMPLETE |
| **Skipped Clips** | **0** | Empty reference | ℹ️ EXCLUDED |

## 2. Contradiction Pairs & Referee Gate Triggers

*0 pairs evaluated (no contradiction claim_pair labeled in session).*

## 3. Detailed Per-Clip Scoring Table

| Clip ID | Speaker | Loud | WER | Human Reference (`correct_text`) | AssemblyAI Raw (`asr_text`) | Topic (Pred/True) | Claim (Pred/True) | Anger (Pred/True) |
|---|---|---|---|---|---|---|---|---|
| `clip_001` | 2xDanger | normal | **0.0%** | Start capture | Start capture. | gaming / null_topic | No / No | none / none |
| `clip_002` | 2xDanger | normal | **100.0%** | هو دلوقتي بيسجل صوتنا | عند الوقت هو بيسكر صوتنا | tech / null_topic | No / No | none / none |
| `clip_003` | Mostafa | normal | **100.0%** | هممم زي الفل | 嗯，这个。 | null_topic / null_topic | No / No | none / none |
| `clip_004` | 2xDanger | normal | **33.3%** | ازيك يا مصطفى عامل يا مصطفى | من زيك يا مصطفى عامل يا مصطفى | null_topic / null_topic | No / No | none / none |
| `clip_005` | Mostafa | normal | **77.8%** | الحمدالله يا حج عبد كيرو اه يا حلاو  ايهه | الحمد لله زاكي حق كيرو آه حلو إيه. | null_topic / null_topic | No / No | none / none |
| `clip_006` | 2xDanger | normal | **62.5%** | هو ليه لقط صيني لقط صيني من أولها | هو لي لا أتصيني لا أتصيني من أولها | null_topic / null_topic | No / No | none / none |
| `clip_007` | Mostafa | normal | **77.8%** | مش عارف سلام عليكم كل سنة و انتوا طيبين | شعر السلام عليكم إلى أكبر كل سنة وانتوا طيبين | null_topic / null_topic | No / No | none / none |
| `clip_008` | 2xDanger | normal | **100.0%** | بص بص بص انا افتحلك ستريم | بس بس بس بس أنا أفتح لك ستريم | tech / tech | No / No | none / none |
| `clip_009` | Mostafa | normal | **0.0%** | طيب | طيب. | null_topic / null_topic | No / No | none / none |
| `clip_010` | Mostafa | normal | **37.5%** | اهم حاجة بس ميجبش الصوت من الستريم تمام | أنا حاجة بس ما أجيبش الصوت من الستريم تمام. | tech / tech | No / No | none / none |
| `clip_011` | 2xDanger | normal | **0.0%** | شايف | شايف. | null_topic / null_topic | No / No | none / none |
| `clip_012` | Mostafa | normal | **100.0%** | زي الفل | نظير طول. | null_topic / null_topic | No / No | none / none |
| `clip_013` | Mostafa | normal | **100.0%** | زي الفل | مزيد فون. | null_topic / null_topic | No / No | none / none |
| `clip_014` | 2xDanger | normal | **43.2%** | هتلاقيه بيكتب هنا كل شوية هتلاقيه بيبدأ أول ما يخلص هتلاقيه كتبهم هنا فاحنا ادي الجمل الهتظهر و احنا هنعمل الكوريكشن و هنقول هي كانت لاود ولا انجري ولا مش عارف ايه و كل الكلام الجميل ده | هتلاقي بيكتب هنا كل شوية هتلاقي بيبدأ أول ما يخلص هتلاقي كتبهم هنا فاحنا هذي الجملة تظهر واحنا هنعمل الكوريكشن ونقول هيك هتلاود ولا أنغري ولا مش عارف ايه وكل الكلام الجميل ده | tech / tech | No / No | none / none |
| `clip_015` | 2xDanger | normal | **33.3%** | كده احسن لنا | كده أسهل لنا | tech / tech | No / No | none / none |
| `clip_016` | Mostafa | normal | **200.0%** | لذيذ | لا أزيزي. | null_topic / null_topic | No / No | none / none |
| `clip_017` | 2xDanger | normal | **5.9%** | طيب تعالى نخلي ده تعالى نتكلم شوية كمان عادي بعد كده ايه بعد كده نروح افلين وعملين | طيب تعالى نخلي ده تعالى نتكلم شوية كمان عادي بعد كده ايه بعد كده منروح افلين وعملين | personal / null_topic | No / No | none / none |
| `clip_018` | Mostafa | normal | **57.9%** | ياعم خير هو صح بي بيشد بينا ولا لا لما أتكلم و اقولك ميسي اتولد سنة الفين و عشرين | نعم بخير هو صح بيشد بنا ولا لا لما أكلم أقولك إني مست ولد سنة ألفين وعشرين | personal / football | No / No | none / none |
| `clip_019` | 2xDanger | normal | **8.3%** | لا دي مش دلوقتي خلينا نتكلم عادي فكك من بتاعت ميسي ورونالدو | لا دي مش دلوقتي خلينا نتكلم عادي فكك من تحت ميسي ورونالدو | football / football | No / No | none / none |
| `clip_020` | 2xDanger | normal | **7.7%** | مش دلوقتي ما احنا عايزين كلبات عادية وكلبات خناء وكلبات مش عارف ايه | مش دلوقتي ما احنا عايزين كلبات عليا وكلبات خناء وكلبات مش عارف ايه | football / null_topic | No / No | none / none |
| `clip_021` | Mostafa | normal | **5.9%** | ياعم ما دي خناق ان انا اقولك ميسي تولد سنة 2020 وانت تقولي لا ما خناق به | نعم ما دي خناق ان انا اقولك ميسي تولد سنة 2020 وانت تقولي لا ما خناق به | football / football | Yes / No | none / none |
| `clip_022` | 2xDanger | normal | **25.0%** | لا ما خلينا دلوقتي عادي خلينا دلوقتي عادي | لا ما خلينا الوقت عادي خلينا الوقت عادي | null_topic / null_topic | No / No | none / none |
| `clip_023` | Mostafa | normal | **100.0%** | ماشي | مش. | null_topic / null_topic | No / No | none / none |
| `clip_024` | 2xDanger | normal | **14.3%** | أظن كده كفاية لأول حاجة هنعمل بقى | أظن كده كفاية الأول حاجة هنعمل بقى | null_topic / null_topic | No / No | none / none |
| `clip_025` | Mostafa | normal | **0.0%** | تمام | تمام. | null_topic / null_topic | No / No | none / none |

