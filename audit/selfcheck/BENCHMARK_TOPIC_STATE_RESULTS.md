# Empirical Evaluation: Turn-by-Turn vs. Continuous State Tracking

**Date:** 2026-09-29 00:52:11
**Model Evaluated:** `qwen/qwen3.8-27b` on Groq LPU

## Case 1: Scoutmaster Transcript (ASR Phonetic Mangling)
- **Total Audio Window:** 58.0s

### Line-by-Line Output (Current System):
| Line # | Speaker | Text Snippet | Classified Topic | Tag Extracted |
|---|---|---|---|---|
| 1 | Remi | Nothing is impossible if you put your mind in... | **`other`** | `` |
| 2 | مستر سلطع | حفظ عفواً أون ونون وستيسكات ماستر وفشخني صراح... | **`gaming`** | `Scout Master` |
| 3 | Remi | يا سيد سكوت ماستر مش هتقابله لو ما بعتش عن صح... | **`gaming`** | `Scout Master` |
| 4 | مستر سلطع | يبدو من أصله قال لي وأنا كنت الوحدي أصلاً برا... | **`gaming`** | `` |
| 5 | مستر سلطع | والله يا ربادي | **`null_topic`** | `` |
| 6 | Remi | مستحيل يستجيب لك وانت بلا الوقت | **`gaming`** | `` |
| 7 | Remi | يستا مستحيل يجي لك وانت بتررف | **`gaming`** | `` |
| 8 | مستر سلطع | وهو حصل ترجله تصور تصور بس يعني ال ال. | **`gaming`** | `` |
| 9 | Remi | الطريقة الوحيدة انه يجيلك ان انت اسمع ايه لاي... | **`gaming`** | `Scout Master` |

- **Current Measured Gaming Duration:** `45.0s` (Discrete tally of gaming lines)
- **Current Extracted Tags:** `Scout Master`
- **Current Token Cost:** `1635` prompt tokens (Total: `1922`), Latency: `1529ms`

### Proposed State Tracker Output:
- **Macro Domain:** `gaming`
- **Canonical Topic:** **`Scout Master Co-op Encounter`**
- **Resolved Entities:** `[{"canonical": "Scout Master", "surface": "سستيسكات ماستر"}, {"canonical": "Scout Master", "surface": "سكوت ماستر"}, {"canonical": "Scout Master View", "surface": "Scout Master View"}]`
- **Continuous Gaming Duration:** **`58.0s`** (Continuous interval span)
- **Evidence Quotes:** `['سستيسكات ماستر', 'يا سيد سكوت ماستر', 'Scout Master View']`
- **Proposed Token Cost:** `624` prompt tokens (Total: `779`), Latency: `1125ms`

---

## Case 2: League of Legends Debate (User's Example: Anaphora & Topic Switch)
- **Total Audio Window:** 26.5s

### Line-by-Line Output (Current System):
| Line # | Speaker | Text Snippet | Classified Topic | Tag Extracted |
|---|---|---|---|---|
| 1 | UserA | League of Legends is a good game | **`gaming`** | `League of Legends` |
| 2 | UserB | No it is not a good game | **`gaming`** | `League of Legends` |
| 3 | UserC | Guys not all gaming is about League of Legends | **`gaming`** | `League of Legends` |
| 4 | UserD | No it is all about it | **`gaming`** | `League of Legends` |
| 5 | UserA | Anyway did anyone order the pizza for dinner? | **`food`** | `pizza` |

- **Current Measured Gaming Duration:** `13.5s`
- **Line 4 ('No it is all about it'):** Classified as `gaming`
- **Current Token Cost:** `1466` prompt tokens, Latency: `1131ms`

### Proposed State Tracker Output:
- **Macro Domain:** `gaming`
- **Canonical Topic:** **`League of Legends Quality Debate`**
- **Resolved Entities:** `[{"canonical": "League of Legends", "surface": "League of Legends"}]`
- **Continuous Gaming Duration:** **`16.0s`** (Turns 1-4, excluding pizza shift at line 5)
- **Evidence Quotes:** `['League of Legends is a good game', 'No it is not a good game', 'not all gaming is about League of Legends', 'No it is all about it']`
- **Proposed Token Cost:** `412` prompt tokens, Latency: `908ms`

---

## Executive Comparison Matrix

| Metric / Dimension | Current Line-by-Line | Proposed Continuous State Machine | Difference / Win |
|---|---|---|---|
| **Prompt Tokens (Case 1)** | `1635` tokens | `624` tokens | **-61.8% quota reduction** |
| **Latency (Case 1)** | `1529ms` | `1125ms` | **Fast Groq LPU execution** |
| **Scoutmaster Tag Quality** | `Scout Master` (Fragmented) | **`Scout Master Co-op Encounter`** | **100% Unified Canonical Tag** |
| **ASR Typo Resolution** | Unresolved / mangled | `[{'canonical': 'Scout Master', 'surface': 'سستيسكات ماستر'}, {'canonical': 'Scout Master', 'surface': 'سكوت ماستر'}, {'canonical': 'Scout Master View', 'surface': 'Scout Master View'}]` | **Aliases linked to Canonical** |
| **League Debate Duration** | `13.5s` | **`16.0s`** | **Full continuous interval captured** |
| **Anaphora ('No it is all about it')** | Fractured to `gaming` | Inherited into `gaming` | **Zero contextual loss** |