# Self-Supervision Traceback #6: Shareable Wrapped Recap Card (Pillow + RAQM / RTL Rendering)

**Audit Date:** 2026-09-28  
**Review Type:** Hostile Traceback of Session Claims (`14576a4` -> `910e507`)  
**Scope:** Commits `9923f7a` (`feat(ui): add shareable Wrapped recap card generator with RAQM check, Arabic RTL rendering, bundled fonts, and !card command`) and `910e507` (`docs(ledger): update recap card generator commit hash in REGRESSION_LEDGER.md`)  
**Review Mode:** Read-Only on project code; report to `audit/selfcheck/TRACEBACK_6.md` only.

---

## 1. Commit and Diff Summary

```text
git diff 14576a4..910e507 --stat
 REGRESSION_LEDGER.md                    |   2 +
 assets/fonts/LICENSE                    |   9 +
 assets/fonts/NotoSans-Bold.ttf          | Bin 0 -> 575740 bytes
 assets/fonts/NotoSansArabic-Bold.ttf    | Bin 0 -> 248468 bytes
 assets/fonts/NotoSansArabic-Regular.ttf | Bin 0 -> 240456 bytes
 audit/card_sample.png                   | Bin 0 -> 88809 bytes
 bot/main.py                             |  26 ++
 bot/ui/__init__.py                      |   1 +
 bot/ui/recap_card_renderer.py           | 598 ++++++++++++++++++++++++++++++++
 requirements.txt                        |   3 +
 tests/test_recap_card.py                | 321 +++++++++++++++++
 11 files changed, 960 insertions(+)
```

---

## 2. Claim-by-Claim Verification

### Claim 1 — Runtime RAQM Check & Dual-Path Arabic Rendering
- **Report Claim:**
  - Evaluates `features.check("raqm")` at module load and logs active path (`"[RecapCard] Arabic rendering: RAQM native"` or `"... fallback reshaper+bidi"`).
  - If RAQM is available: passes logical Unicode text directly with `direction="rtl", language="ar"`.
  - If RAQM is missing: falls back to `arabic_reshaper` + `python-bidi`, avoiding the Pillow `KeyError: 'setting text direction, language or font features is not supported without libraqm'` trap.
- **Code Trace:**
  - [`bot/ui/recap_card_renderer.py:27-31`](file:///g:/CallWrapper/bot/ui/recap_card_renderer.py#L27-L31):
    `RAQM_AVAILABLE = features.check("raqm")` checked at top level. Logging executes immediately on import.
  - [`bot/ui/recap_card_renderer.py:161-180`](file:///g:/CallWrapper/bot/ui/recap_card_renderer.py#L161-L180):
    `shape_for_pillow(text)` returns `text` immediately if `RAQM_AVAILABLE` is True. If False, runs `arabic_reshaper.reshape(text)` then `get_display(reshaped)`.
  - [`bot/ui/recap_card_renderer.py:222-241`](file:///g:/CallWrapper/bot/ui/recap_card_renderer.py#L222-L241):
    `draw_text()` only supplies `direction="rtl", language="ar"` when `RAQM_AVAILABLE` is True. When False, draws reshaped text without direction flags.
- **Verdict:** **VERIFIED**.

---

### Claim 2 — Bundled TrueType Fonts & License
- **Report Claim:**
  - Bundled Arabic-capable TrueType fonts directly into repo under SIL Open Font License 1.1: `NotoSansArabic-Bold.ttf`, `NotoSansArabic-Regular.ttf`, and `NotoSans-Bold.ttf`.
  - Loaded via relative path from project root (`Path(__file__).resolve().parent.parent.parent / "assets" / "fonts"`).
  - Note license in `assets/fonts/LICENSE`.
  - Strips/replaces emoji characters to prevent Pillow tofu boxes.
  - Replaces Arabic-Indic digits with Latin digits everywhere.
  - Grapheme-aware text truncation (`truncate_text()`) preventing orphan combining marks.
- **Code Trace:**
  - [`assets/fonts/LICENSE:1-9`](file:///g:/CallWrapper/assets/fonts/LICENSE#L1-L9): SIL OFL 1.1 license document present.
  - Fonts verified in `assets/fonts/`: `NotoSansArabic-Bold.ttf` (248KB), `NotoSansArabic-Regular.ttf` (240KB), `NotoSans-Bold.ttf` (575KB).
  - [`bot/ui/recap_card_renderer.py:37-38`](file:///g:/CallWrapper/bot/ui/recap_card_renderer.py#L37-L38): `PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent`, `FONTS_DIR = PROJECT_ROOT / "assets" / "fonts"`.
  - [`bot/ui/recap_card_renderer.py:102-144`](file:///g:/CallWrapper/bot/ui/recap_card_renderer.py#L102-L144): `clean_emoji()` strips/replaces emoji using Unicode ranges and string replacements (`👑` -> `"[Top] "`).
  - [`bot/ui/recap_card_renderer.py:119-126`](file:///g:/CallWrapper/bot/ui/recap_card_renderer.py#L119-L126): `ensure_latin_digits()` translates Arabic-Indic digits `٠١٢٣٤٥٦٧٨٩` to `0123456789`.
  - [`bot/ui/recap_card_renderer.py:183-193`](file:///g:/CallWrapper/bot/ui/recap_card_renderer.py#L183-L193): `truncate_text()` checks `unicodedata.combining()` before cutting.
- **Verdict:** **VERIFIED**.

---

### Claim 3 — Card Layout & Off-Thread Asynchronous Execution
- **Report Claim:**
  - Input: `RecapCardPayload` (frozen dataclass) with `session_title`, `period_label`, `speaker_stats`, `top_topics`, `coverage_note`.
  - Output: PNG bytes (1080 × 1350 portrait format) via `BytesIO` with 0 disk writes.
  - Offloaded CPU-bound generation via `render_recap_card_async` using `asyncio.to_thread`.
  - Dark theme matching CallWrapped dashboard (header, speaker participation with `▰▱` blocks and streak record, frustration section with receipts, top-3 topics with rank pills, and footer).
- **Code Trace:**
  - [`bot/ui/recap_card_renderer.py:70-96`](file:///g:/CallWrapper/bot/ui/recap_card_renderer.py#L70-L96): `SpeakerStat`, `TopicStat`, `RecapCardPayload` defined as `@dataclass(frozen=True)`.
  - [`bot/ui/recap_card_renderer.py:281-462`](file:///g:/CallWrapper/bot/ui/recap_card_renderer.py#L281-L462): Canvas constructed as 1080 × 1350 RGB image. Uses `io.BytesIO()` buffer; `base.save(buf, format="PNG", optimize=True)` returns `buf.getvalue()`.
  - [`bot/ui/recap_card_renderer.py:465-469`](file:///g:/CallWrapper/bot/ui/recap_card_renderer.py#L465-L469): `render_recap_card_async` wraps `render_recap_card_png` in `asyncio.to_thread`.
- **Verdict:** **VERIFIED**.

---

### Claim 4 — `!card` Command Integration in `bot/main.py`
- **Report Claim:**
  - Command generates card from current session state and posts as `discord.File(fp=BytesIO(png_bytes), filename="callwrapped_recap.png")`.
  - If session is empty: sends text reply `"مفيش بيانات في المكالمة دي لسه."` without generating a card.
  - Documented in `!help`.
- **Code Trace:**
  - [`bot/main.py:451-473`](file:///g:/CallWrapper/bot/main.py#L451-L473): `@bot.command(name="card")` implemented. Calls `build_card_payload_from_session(session)`. If None, sends `"مفيش بيانات في المكالمة دي لسه."`. Otherwise renders async and sends `discord.File(fp=io.BytesIO(png_bytes), filename="callwrapped_recap.png")`.
  - [`bot/main.py:508`](file:///g:/CallWrapper/bot/main.py#L508): Added row `• !card: Generates a shareable Wrapped visual recap card (PNG).` in `show_help`.
- **Verdict:** **VERIFIED**.

---

### Claim 5 — Test Suite & Artifact Verification
- **Report Claim:**
  - Unit tests in `tests/test_recap_card.py` passed with 6/6 tests OK.
  - Synthetic payload generated PNG of size 88,809 bytes (86.7 KB), dimensions 1080 × 1350.
  - Inspection sample saved to `audit/card_sample.png`.
  - Full test suite passed (191 tests, 0 failures).
- **Code Trace:**
  - File [`audit/card_sample.png`](file:///g:/CallWrapper/audit/card_sample.png) exists on disk: 88,809 bytes, format PNG, dimensions 1080 × 1350 verified.
  - Suite execution verified: 191 tests passed in 176.039s.
- **Verdict:** **VERIFIED**.

---

## 3. Diff Quality Sweep & Hostile Findings

### Finding TRACE6-01: Dead/Unused Imports in New Modules (Severity: LOW / CODE HYGIENE)
- **Location:**
  - [`bot/ui/recap_card_renderer.py:11`](file:///g:/CallWrapper/bot/ui/recap_card_renderer.py#L11): `import math` (unused).
  - [`bot/ui/recap_card_renderer.py:17`](file:///g:/CallWrapper/bot/ui/recap_card_renderer.py#L17): `field` from `dataclasses` (unused).
  - [`tests/test_recap_card.py:14`](file:///g:/CallWrapper/tests/test_recap_card.py#L14): `import os` (unused).
  - [`tests/test_recap_card.py:17`](file:///g:/CallWrapper/tests/test_recap_card.py#L17): `patch` from `unittest.mock` (unused).
- **Impact:** Harmless, but flagged by static analysis / vulture. Should be cleaned up in next maintenance pass.

### Finding TRACE6-02: Hardcoded 3-Speaker Cap Without Overflow Notice (Severity: MEDIUM / DESIGN LIMIT)
- **Location:** [`bot/ui/recap_card_renderer.py:341`](file:///g:/CallWrapper/bot/ui/recap_card_renderer.py#L341):
  ```python
  speakers = list(payload.speaker_stats)[:3]
  ```
- **Analysis:** In voice channels with $>3$ participants, speakers ranked 4th and beyond are silently dropped from the card. There is no indicator (e.g. `+2 other speakers`) in the UI. While portrait layout has fixed vertical real estate, the session report did not explicitly disclose that speakers are capped at the top 3.
- **Impact:** Active speakers beyond the top 3 do not appear on the card.

### Finding TRACE6-03: Missing Exception Guard in `!card` Command (Severity: MEDIUM / RESILIENCE)
- **Location:** [`bot/main.py:469-472`](file:///g:/CallWrapper/bot/main.py#L469-L472):
  ```python
  png_bytes = await render_recap_card_async(payload)
  file = discord.File(fp=io.BytesIO(png_bytes), filename="callwrapped_recap.png")
  await ctx.send(file=file)
  ```
- **Analysis:** Unlike other main bot commands which wrap Discord channel dispatch and API calls in `try...except`, `card_command` has no error handling around the rendering or `ctx.send`. If Pillow fails or Discord file upload rejects (e.g. rate limit, connection drop), the command fails with an unhandled exception and the user receives no feedback.
- **Impact:** No user-facing error message on unexpected render or upload failure.

### Finding TRACE6-04: Font Loader Fallback to Low-Fidelity `load_default()` (Severity: LOW / RESILIENCE)
- **Location:** [`bot/ui/recap_card_renderer.py:64`](file:///g:/CallWrapper/bot/ui/recap_card_renderer.py#L64):
  `return ImageFont.load_default()`
- **Analysis:** In Pillow, `load_default()` is a 1-bit bitmap font that lacks Arabic Unicode glyphs. If the `assets/fonts/` directory were deleted or corrupt, text rendering would fail back to ASCII-only boxes without raising a descriptive error. (Mitigated because fonts are checked into the repository).

---

## 4. Honesty Audit & Verification Summary

| Claim | Status | Evidence / Notes |
| :--- | :--- | :--- |
| Runtime RAQM Check | **VERIFIED** | `features.check("raqm")` verified dynamically. Active path logged. |
| Arabic RTL Rendering | **VERIFIED** | Fallback to `arabic_reshaper` + `python-bidi` verified without libraqm. |
| Font Bundling | **VERIFIED** | 3 TrueType fonts + LICENSE committed in `assets/fonts/`. Loaded via relative project root. |
| Emoji Cleaning & Digit Normalization | **VERIFIED** | Emojis stripped/replaced; Latin digits enforced everywhere. |
| Grapheme-Aware Truncation | **VERIFIED** | `unicodedata.combining` prevents orphan marks. |
| Card Layout & Dimensions | **VERIFIED** | $1080 \times 1350$, $>10\text{KB}$ PNG via `BytesIO`. Sample saved to `audit/card_sample.png`. |
| Async Off-Thread Execution | **VERIFIED** | `asyncio.to_thread` used. No blocking calls on event loop. |
| `!card` Discord Command | **VERIFIED** | Populated session attaches file; empty session replies with Arabic text notice. |
| Full Test Suite | **VERIFIED** | 191/191 tests passed in 176.039s. |

---

## 5. What Would Break If This Diff Shipped As-Is?

Nothing would break in standard operation — the code passes all 191 regression tests, runs off-thread, and generates clean $1080 \times 1350$ PNG recap cards. However:
1. If a call has $>3$ participants, speakers beyond the 3rd would be silently omitted from the visual card without an overflow footnote.
2. If Discord file upload encounters a network timeout or file size rejection, the user receives no explanatory message because `!card` lacks a `try...except` block.
3. Four unused imports (`math`, `field`, `os`, `patch`) linger in the codebase.
