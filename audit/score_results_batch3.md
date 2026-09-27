# Step 9: Captured Test Session Scoring Report

**Session Folder:** `2026-09-27_1806`  
**Source Labels File:** `labels_DRAFT.csv`  
**Evaluation Date:** 2026-09-27 19:49:30  
**STT Engine:** AssemblyAI Universal-3.5 Pro (Native Code-Switching)  
**Epistemic Engine:** Groq LPU (`qwen/qwen3.8-27b`)  

## 1. Executive Metric Summary

| Metric | Result | Target Benchmark | Status |
|---|---|---|---|
| **Micro WER (Corpus)** | **44.69%** | Beat 30.8% baseline | ⚠️ REVIEW |
| **Macro WER (Clip Avg)** | **50.01%** | Informational | — |
| **Clean Audio Micro WER** | **44.69%** | Beat 25.1% baseline | ⚠️ REVIEW |
| **Clean Audio Macro WER** | **50.01%** | Informational | — |
| **Number Accuracy** | **100.0%** (3/3) | ≥ 90% | ✅ PASS |
| **Topical Accuracy** | **77.8%** (14/18) | ≥ 80% (topical rows only) | ⚠️ REVIEW |
| **Null Detection Accuracy** | **100.0%** (1/1) | ≥ 80% (null_topic rows only) | ✅ PASS |
| **Topical Coverage** | **Model: 99.2% / Human: 99.2%** | Model vs Human audio share | ℹ️ REPORTED |
| **Claim Agreement** | **42.1%** | ≥ 75% | ⚠️ REVIEW |
| **Anger Agreement** | **26.3%** | Tolerance (mild/high) | ⚠️ REVIEW |
| **False-Anger Rate** | **0.0%** (0/4) | ≤ 15% | ✅ PASS |
| **Scored Clips** | **19** | Non-empty reference | ✅ COMPLETE |
| **Skipped Clips** | **0** | Empty reference | ℹ️ EXCLUDED |


## 2. Contradiction Pairs & Referee Gate Triggers

*0 pairs evaluated (no contradiction claim_pair labeled in session).*

## 3. Detailed Per-Clip Scoring Table

| Clip ID | Speaker | Loud | WER | Human Reference (`correct_text`) | AssemblyAI Raw (`asr_text`) | Topic (Pred/True) | Claim (Pred/True) | Anger (Pred/True) |
|---|---|---|---|---|---|---|---|---|
| `clip_001` | Mostafa | normal | **100.0%** | ماشي | مش. | null_topic / null_topic | No / No | none / none |
| `clip_002` | مستر سلطع | normal | **38.5%** | ماشي يا عم اقول أقول له مصر كسبت كاس العالم يا ولدي الايه | نعم يا عم أقول له مصر لكذب تكاس العالم يا ولدي | football / football | No / Yes | none / mild |
| `clip_003` | 2xDanger | normal | **33.3%** | يلا هبدأ اهو تلت اثنين واحد | يلا هبدأوا تلت اثنين واحد | football / other | No / No | none / none |
| `clip_005` | 2xDanger | normal | **80.0%** | يا جدعان عرفين ان اللي كسب كاس العالم هي اسبانيا | عقد عنا عارفين الكسب كسر عالم هي أسبانيا؟ | football / football | No / Yes | none / none |
| `clip_006` | Mostafa | normal | **50.0%** | لا لا لا لا اللي كسب كاس العالم هي استراليا | لا لا لا لا نكسب كسل عالم استراليا | football / football | No / Yes | none / mild |
| `clip_007` | Drago | normal | **50.0%** | لاالأرجنتين الأرجنتين يا جدعان. | الأرجنتين الأرجنتين يا جناحان. | football / football | No / Yes | none / mild |
| `clip_008` | مستر سلطع | normal | **16.7%** | لا مصر حتى فيها الواد ويليام والواد ويليام كان بيطلع في مصر | لا مصر حتى الواد ويليام والواد ويليام كان بيرجع في مصر | football / football | Yes / Yes | none / mild |
| `clip_009` | 2xDanger | normal | **18.8%** | يا جدعان أنتوا مجنين ولا إيه؟ أسبانيا هي لي كسبت آخر نسخة في كسر عالم 2026 | يعني أنا أنتوا مجنين ولا إيه؟ أسبانيا قال لي كسبت آخر نسخة في كسر عالم 2026 | football / football | Yes / Yes | mild / high |
| `clip_010` | مستر سلطع | normal | **20.0%** | يا عم ويليام على الطلاق | يا عم ويليام على الصلاة | football / other | No / No | none / high |
| `clip_011` | Mostafa | normal | **50.0%** | لااا يجدع استراليا هي اللي كسبت | لا جبع السرالية هي اللي كسبت | football / football | Yes / Yes | none / mild |
| `clip_012` | Drago | normal | **66.7%** | انت قاصدك ويليم اللي كان اااا | انت عايزك كل يوم اللي كان من | football / other | No / No | none / none |
| `clip_013` | 2xDanger | normal | **58.3%** | يا عم استراليا مين وكوريا مين هي اسبانيا اللي كسبت كاس العالم | يا عم استراج يمين وولي يمون هي أسبانيا اللي كت بتكسر عالم | football / football | No / Yes | none / high |
| `clip_014` | Mostafa | normal | **40.0%** | يا عم لا ذا وليم اللي كان في مصر هو اللي كسب في كاس العالم | تعمل لا الدوليا من اللي كان في مصر هو اللي حسب كاس العالم | football / football | No / Yes | none / mild |
| `clip_015` | مستر سلطع | normal | **78.6%** | يا استا وليم الذنجي ذا وليم الذنجي ذا جامد جامد ويمين يمال ذا تعبان | يا أستا وليا مش زنج ده وليا مش زنج ده جامد جامد ويمين يا مال ده تعبان | football / football | No / Yes | none / mild |
| `clip_016` | 2xDanger | normal | **16.7%** | يا مين يا مال ايه بس يا عم انا بقولك هو اللي كسب كاس العالم منتخب اسبانيا الكورة | يا مين يا مال ايه بس يا عم انا بقولك اول كسب كسب العالم منتخب اسبانيا الكورة | football / football | Yes / Yes | none / high |
| `clip_017` | مستر سلطع | normal | **41.7%** | لا يا عم لا أنا مقتنع ان مصر مصر يسطا اللي كسبت | لا يا عم لا أنا كنت معه مصر مصر أنا فلكر | football / football | No / Yes | none / mild |
| `clip_018` | 2xDanger | normal | **28.6%** | يا عم أنتوا مش فاهيمن حاجة بقى | يا عم أنت مش تعمل حاجة بقى. | football / other | No / Yes | none / high |
| `clip_019` | Mostafa | normal | **87.5%** | لا منتخب البرزيل هو اللي كسب كاس العالم | لا، بنتي خبر رزي اللي هو الكسب كسل عال | football / football | No / Yes | none / mild |
| `clip_020` | Drago | normal | **75.0%** | لا يا جدعان الارجنتين | لا يتعلق بسرطين. | football / football | No / Yes | none / mild |

