"""
Shareable Wrapped Recap Card Renderer.

Generates static social-card PNGs (1080x1350 portrait) for CallWrapped session recaps
using Pillow with runtime RAQM check and Arabic RTL reshaping fallback.
All rendering executes off-loop via asyncio.to_thread with zero disk persistence.
"""

import io
import re
import logging
import asyncio
import functools
import unicodedata
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Union

from PIL import Image, ImageDraw, ImageFont, features

logger = logging.getLogger("RecapCard")

# ---------------------------------------------------------------------------
# 1. Runtime RAQM check (research-verified trap)
# ---------------------------------------------------------------------------
RAQM_AVAILABLE: bool = features.check("raqm")
if RAQM_AVAILABLE:
    logger.info("[RecapCard] Arabic rendering: RAQM native")
else:
    logger.info("[RecapCard] Arabic rendering: fallback reshaper+bidi")


# ---------------------------------------------------------------------------
# 2. Font bundling & paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
FONTS_DIR = PROJECT_ROOT / "assets" / "fonts"

FONT_ARABIC_BOLD = "NotoSansArabic-Bold.ttf"
FONT_ARABIC_REGULAR = "NotoSansArabic-Regular.ttf"
FONT_LATIN_BOLD = "NotoSans-Bold.ttf"

CARD_WIDTH = 1080
CARD_HEIGHT = 1350


@functools.lru_cache(maxsize=32)
def get_font(font_name: str, size: int) -> Union[ImageFont.FreeTypeFont, ImageFont.ImageFont]:
    """Loads and caches bundled TrueType fonts relative to project root."""
    font_path = FONTS_DIR / font_name
    if font_path.exists():
        try:
            return ImageFont.truetype(str(font_path), size)
        except Exception as e:
            logger.warning(f"[RecapCard] Failed loading font {font_path}: {e}")
    # Fallback to Arabic bold or default
    alt_path = FONTS_DIR / FONT_ARABIC_BOLD
    if alt_path.exists() and font_name != FONT_ARABIC_BOLD:
        try:
            return ImageFont.truetype(str(alt_path), size)
        except Exception:
            pass
    logger.critical("[RecapCard] Arabic font unavailable — card will have tofu characters. Check assets/fonts/ directory.")
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# 3. Data structures
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SpeakerStat:
    """Per-speaker session performance metrics."""
    name: str
    talk_seconds: float
    share_pct: float
    streak_seconds: float
    angry_episodes: int
    first_anger_quote: Optional[str] = None


@dataclass(frozen=True)
class TopicStat:
    """Topic classification breakdown item."""
    topic_key: str
    display_name: str
    pct: float


@dataclass(frozen=True)
class RecapCardPayload:
    """Input payload for generating a Wrapped recap social card."""
    session_title: str
    period_label: str
    speaker_stats: List[SpeakerStat]
    top_topics: List[Union[TopicStat, Tuple[str, str, float]]]
    coverage_note: str = ""
    micro_tags: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 4. Text cleaning, emoji stripping, and Arabic shaping
# ---------------------------------------------------------------------------
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA70-\U0001FAFF"  # symbols and pictographs extended-A
    "\U00002600-\U000026FF"  # misc symbols
    "\U00002B50"             # star
    "\U0000FE0F"             # variation selector
    "]+",
    flags=re.UNICODE
)

ARABIC_INDIC_DIGITS_TRANS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def ensure_latin_digits(text: str) -> str:
    """Replaces Arabic-Indic digits with Latin digits 0-9 everywhere."""
    if not text:
        return ""
    return str(text).translate(ARABIC_INDIC_DIGITS_TRANS)


def clean_emoji(text: str) -> str:
    """Replaces or strips emoji characters that Pillow cannot render with color fonts."""
    if not text:
        return ""
    # Map common icons to clean text labels
    text = text.replace("👑", "[Top] ")
    text = text.replace("🔥", "")
    text = text.replace("😡", "")
    text = text.replace("🗣️", "")
    text = text.replace("🎙️", "")
    text = text.replace("💡", "")
    text = text.replace("😂", "")
    text = text.replace("⚖️", "")
    text = text.replace("⚡", "")
    text = EMOJI_PATTERN.sub("", text)
    return re.sub(r'\s+', ' ', text).strip()


def contains_arabic(text: str) -> bool:
    """Returns True if the text contains Arabic script code points."""
    if not text:
        return False
    return any(
        '\u0600' <= c <= '\u06ff' or
        '\u0750' <= c <= '\u077f' or
        '\u08a0' <= c <= '\u08ff' or
        '\ufb50' <= c <= '\ufdff' or
        '\ufe70' <= c <= '\ufeff'
        for c in text
    )


def shape_for_pillow(text: str) -> str:
    """
    Arabic text decision tree:
    - If RAQM available: returns logical text directly (no reshaping, no bidi).
    - If RAQM missing: reshapes connected letters via arabic_reshaper and reorders via python-bidi.
    """
    if not text:
        return ""
    if RAQM_AVAILABLE:
        return text
    if not contains_arabic(text):
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    except Exception as e:
        logger.warning(f"[RecapCard] Arabic reshaping fallback failed: {e}")
        return text


def truncate_text(text: str, max_chars: int = 40, ellipsis: str = "…") -> str:
    """
    Grapheme-aware text truncation preventing combining mark orphan splits.
    """
    if not text or len(text) <= max_chars:
        return text or ""
    cut_len = max(1, max_chars - len(ellipsis))
    cut = text[:cut_len]
    while cut and unicodedata.combining(cut[-1]) > 0:
        cut = cut[:-1]
    return cut.rstrip() + ellipsis


def format_mmss(seconds: float) -> str:
    """Formats seconds into m:ss string using Latin digits."""
    s = max(0, int(round(seconds)))
    return f"{s // 60}:{s % 60:02d}"


# ---------------------------------------------------------------------------
# 5. Drawing primitives & helpers
# ---------------------------------------------------------------------------
def draw_text(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[float, float],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: Any,
    anchor: Optional[str] = None
) -> Tuple[int, int]:
    """
    Draws text honoring the RAQM / reshaper decision tree.
    Returns (width, height) of the drawn text.
    """
    if not text:
        return (0, 0)
    cleaned = clean_emoji(ensure_latin_digits(text))
    is_ar = contains_arabic(cleaned)

    if is_ar and RAQM_AVAILABLE:
        kwargs: Dict[str, Any] = {"direction": "rtl", "language": "ar"}
        if anchor:
            kwargs["anchor"] = anchor
        draw.text(xy, cleaned, font=font, fill=fill, **kwargs)
        bbox = draw.textbbox((0, 0), cleaned, font=font, direction="rtl", language="ar")
    elif is_ar:
        shaped = shape_for_pillow(cleaned)
        kwargs = {}
        if anchor:
            kwargs["anchor"] = anchor
        draw.text(xy, shaped, font=font, fill=fill, **kwargs)
        bbox = draw.textbbox((0, 0), shaped, font=font)
    else:
        kwargs = {}
        if anchor:
            kwargs["anchor"] = anchor
        draw.text(xy, cleaned, font=font, fill=fill, **kwargs)
        bbox = draw.textbbox((0, 0), cleaned, font=font)

    w = int(bbox[2] - bbox[0])
    h = int(bbox[3] - bbox[1])
    return (w, h)


def measure_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont
) -> Tuple[int, int]:
    """Measures text bounding box dimensions."""
    if not text:
        return (0, 0)
    cleaned = clean_emoji(ensure_latin_digits(text))
    is_ar = contains_arabic(cleaned)
    if is_ar and RAQM_AVAILABLE:
        bbox = draw.textbbox((0, 0), cleaned, font=font, direction="rtl", language="ar")
    elif is_ar:
        shaped = shape_for_pillow(cleaned)
        bbox = draw.textbbox((0, 0), shaped, font=font)
    else:
        bbox = draw.textbbox((0, 0), cleaned, font=font)
    return (int(bbox[2] - bbox[0]), int(bbox[3] - bbox[1]))


def draw_panel(
    draw: ImageDraw.ImageDraw,
    box: Tuple[int, int, int, int],
    bg_color: Tuple[int, int, int] = (20, 28, 46),
    border_color: Tuple[int, int, int] = (35, 48, 74),
    radius: int = 24
) -> None:
    """Draws a modern rounded panel container with border."""
    draw.rounded_rectangle(box, radius=radius, fill=bg_color, outline=border_color, width=2)


# ---------------------------------------------------------------------------
# 6. Card Layout Engine (1080 x 1350)
# ---------------------------------------------------------------------------
def render_recap_card_png(payload: RecapCardPayload) -> bytes:
    """
    Renders a shareable Wrapped recap card as PNG bytes.
    Pure CPU-bound rendering using Pillow.
    """
    # 1. Base image with elegant dark gradient background
    base = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), (11, 15, 25))
    draw = ImageDraw.Draw(base)

    # Subtle vertical background gradient
    for y in range(CARD_HEIGHT):
        ratio = y / CARD_HEIGHT
        r = int(11 + ratio * 8)
        g = int(15 + ratio * 10)
        b = int(25 + ratio * 16)
        draw.line([(0, y), (CARD_WIDTH, y)], fill=(r, g, b))

    # Decorative top glow accent (purple/cyan gradient line)
    for x in range(CARD_WIDTH):
        t = x / CARD_WIDTH
        r = int(139 * (1 - t) + 6 * t)
        g = int(92 * (1 - t) + 182 * t)
        b = int(246 * (1 - t) + 212 * t)
        draw.line([(x, 0), (x, 5)], fill=(r, g, b))

    # Load fonts
    font_badge = get_font(FONT_LATIN_BOLD, 18)
    font_title = get_font(FONT_ARABIC_BOLD, 46)
    font_subtitle = get_font(FONT_ARABIC_REGULAR, 22)
    font_section = get_font(FONT_ARABIC_BOLD, 22)
    font_speaker_name = get_font(FONT_ARABIC_BOLD, 28)
    font_stat_val = get_font(FONT_LATIN_BOLD, 22)
    font_stat_muted = get_font(FONT_ARABIC_REGULAR, 20)
    font_bar = get_font(FONT_ARABIC_BOLD, 22)
    font_quote = get_font(FONT_ARABIC_REGULAR, 24)
    font_footer = get_font(FONT_LATIN_BOLD, 17)
    font_coverage = get_font(FONT_ARABIC_REGULAR, 18)

    # -----------------------------------------------------------------------
    # Section A: Header (y: 50 to 180)
    # -----------------------------------------------------------------------
    # Pill badge: CALLWRAPPED 2026
    badge_text = "CALLWRAPPED  •  VOICE RECAP"
    draw.rounded_rectangle((48, 48, 360, 84), radius=18, fill=(28, 38, 62), outline=(139, 92, 246), width=1)
    draw_text(draw, (70, 56), badge_text, font_badge, fill=(192, 132, 252))

    # Session Title
    title_text = truncate_text(payload.session_title or "CallWrapped Recap", max_chars=40)
    draw_text(draw, (48, 100), title_text, font_title, fill=(255, 255, 255))

    # Period / Subtitle
    sub_text = truncate_text(payload.period_label or "ملخص الجلسة الصوتية وتفاعل المتحدثين", max_chars=60)
    draw_text(draw, (48, 160), sub_text, font_subtitle, fill=(148, 163, 184))

    # -----------------------------------------------------------------------
    # Section B: Speaker Participation (y: 210 to 600)
    # -----------------------------------------------------------------------
    draw_panel(draw, (48, 210, 1032, 610), bg_color=(18, 24, 40), border_color=(35, 48, 74), radius=24)
    draw_text(draw, (76, 232), "مشاركة المتحدثين  |  SPEAKER PARTICIPATION", font_section, fill=(6, 182, 212))

    speakers = list(payload.speaker_stats)[:3]  # Up to top 3
    if not speakers:
        draw_text(draw, (76, 320), "مفيش بيانات متحدثين مسجلة لسه.", font_quote, fill=(148, 163, 184))
    else:
        # Find streak leader
        streak_leader = max(speakers, key=lambda s: s.streak_seconds) if speakers else None
        leader_streak_sec = streak_leader.streak_seconds if streak_leader else 0.0

        spk_y = 280
        spk_gap = 100
        for i, spk in enumerate(speakers):
            curr_y = spk_y + i * spk_gap
            name = truncate_text(spk.name, max_chars=22)
            is_leader = (streak_leader and spk.name == streak_leader.name and leader_streak_sec > 0.0)

            # Name + Leader pill
            w_name, _ = draw_text(draw, (76, curr_y), name, font_speaker_name, fill=(255, 255, 255))
            if is_leader:
                pill_x = 76 + w_name + 14
                draw.rounded_rectangle((pill_x, curr_y + 2, pill_x + 130, curr_y + 32), radius=12, fill=(66, 48, 16), outline=(245, 158, 11), width=1)
                draw_text(draw, (pill_x + 12, curr_y + 6), "[TOP STREAK]", font_badge, fill=(245, 158, 11))

            # Stats line: Talk time (m:ss) + share %
            talk_str = format_mmss(spk.talk_seconds)
            pct_val = max(0.0, min(100.0, spk.share_pct))
            stat_line = f"{talk_str} ({pct_val:.1f}%)"
            w_stat, _ = measure_text(draw, stat_line, font_stat_val)
            draw_text(draw, (1004 - w_stat, curr_y + 4), stat_line, font_stat_val, fill=(226, 232, 240))

            # Block Progress Bar (▰▱) + streak record
            filled_blocks = int(round(pct_val / 10.0))
            filled_blocks = max(0, min(10, filled_blocks))
            bar_text = ("▰" * filled_blocks) + ("▱" * (10 - filled_blocks))
            draw_text(draw, (76, curr_y + 42), bar_text, font_bar, fill=(139, 92, 246))

            # Streak detail right-aligned
            streak_str = f"Streak: {format_mmss(spk.streak_seconds)}"
            w_stk, _ = measure_text(draw, streak_str, font_stat_muted)
            draw_text(draw, (1004 - w_stk, curr_y + 44), streak_str, font_stat_muted, fill=(148, 163, 184))

        # TRACE6-02: Overflow indicator for >3 speakers
        if len(payload.speaker_stats) > 3:
            omitted_spk = len(payload.speaker_stats) - 3
            overflow_spk_text = f"+{omitted_spk} مشاركين إضافيين"
            draw_text(draw, (76, 574), overflow_spk_text, font_stat_muted, fill=(148, 163, 184))

    # -----------------------------------------------------------------------
    # Section C: Frustration Moments & Receipts (y: 630 to 890)
    # -----------------------------------------------------------------------
    draw_panel(draw, (48, 630, 1032, 890), bg_color=(18, 24, 40), border_color=(35, 48, 74), radius=24)
    draw_text(draw, (76, 652), "نوبات الإحباط  |  FRUSTRATION & RECEIPTS", font_section, fill=(248, 113, 113))

    angry_speakers = [s for s in payload.speaker_stats if s.angry_episodes > 0]
    if angry_speakers:
        angry_speakers.sort(key=lambda s: s.angry_episodes, reverse=True)
        ang_y = 705
        for s in angry_speakers[:2]:  # Up to 2
            ep_word = "moment" if s.angry_episodes == 1 else "moments"
            spk_label = f"• {s.name}: {s.angry_episodes} {ep_word}"
            draw_text(draw, (76, ang_y), spk_label, font_speaker_name, fill=(254, 202, 202))

            if s.first_anger_quote:
                quote_clean = truncate_text(f'"{s.first_anger_quote}"', max_chars=48)
                draw_text(draw, (100, ang_y + 36), quote_clean, font_quote, fill=(248, 113, 113))
            ang_y += 82
    else:
        calm_msg = "محدش عصب في المكالمة دي... كده مش طبيعي!"
        calm_en = "Nobody got angry this call... suspicious!"
        draw_text(draw, (76, 725), calm_msg, font_quote, fill=(148, 163, 184))
        draw_text(draw, (76, 770), calm_en, font_stat_muted, fill=(100, 116, 139))

    # -----------------------------------------------------------------------
    # Section D: Top Topics (y: 910 to 1218)
    # -----------------------------------------------------------------------
    draw_panel(draw, (48, 910, 1032, 1218), bg_color=(18, 24, 40), border_color=(35, 48, 74), radius=24)
    draw_text(draw, (76, 932), "أكتر مواضيع اتكلمتوا فيها  |  TOP TOPICS", font_section, fill=(192, 132, 252))

    topics = list(payload.top_topics)[:3]
    if not topics:
        draw_text(draw, (76, 1010), "مفيش مواضيع مسجلة لسه.", font_quote, fill=(148, 163, 184))
    else:
        top_y = 985
        top_gap = 72
        for rank, topic in enumerate(topics, 1):
            curr_top_y = top_y + (rank - 1) * top_gap
            if isinstance(topic, (list, tuple)):
                key, dname, pct = topic[0], topic[1], float(topic[2])
            elif hasattr(topic, "display_name"):
                key, dname, pct = getattr(topic, "topic_key", ""), getattr(topic, "display_name", ""), float(getattr(topic, "pct", 0.0))
            else:
                key, dname, pct = str(topic), str(topic), 0.0

            # Rank number pill
            draw.rounded_rectangle((76, curr_top_y, 116, curr_top_y + 38), radius=10, fill=(35, 48, 74))
            draw_text(draw, (88, curr_top_y + 6), str(rank), font_stat_val, fill=(255, 255, 255))

            # Topic name
            name_text = truncate_text(dname or key, max_chars=32)
            draw_text(draw, (132, curr_top_y + 4), name_text, font_speaker_name, fill=(241, 245, 249))

            # Topic percentage
            pct_val = max(0.0, min(100.0, pct))
            pct_str = f"{pct_val:.1f}%"
            w_pct, _ = measure_text(draw, pct_str, font_stat_val)
            draw_text(draw, (1004 - w_pct, curr_top_y + 4), pct_str, font_stat_val, fill=(192, 132, 252))

            # Horizontal bar underneath
            bar_w = 872
            fill_w = max(4, int(bar_w * (pct_val / 100.0)))
            draw.rounded_rectangle((132, curr_top_y + 44, 1004, curr_top_y + 52), radius=4, fill=(30, 41, 59))
            draw.rounded_rectangle((132, curr_top_y + 44, 132 + fill_w, curr_top_y + 52), radius=4, fill=(139, 92, 246))

        # Fine-grained micro-tags or overflow indicator for >3 topics
        if getattr(payload, "micro_tags", None) and len(payload.top_topics) <= 3:
            tags_text = "  •  ".join(f"#{t}" for t in payload.micro_tags[:3])
            draw_text(draw, (76, 1184), tags_text, font_stat_muted, fill=(167, 139, 250))
        elif len(payload.top_topics) > 3:
            omitted_top = len(payload.top_topics) - 3
            overflow_topic_text = f"+{omitted_top} مواضيع إضافية"
            draw_text(draw, (76, 1184), overflow_topic_text, font_stat_muted, fill=(148, 163, 184))

    # -----------------------------------------------------------------------
    # Section E: Footer (y: 1230 to 1320)
    # -----------------------------------------------------------------------
    footer_text = "CallWrapped • AssemblyAI Speech AI • Groq LPU • Tavily Ground-Truth"
    w_ft, _ = measure_text(draw, footer_text, font_footer)
    draw_text(draw, (CARD_WIDTH // 2 - w_ft // 2, 1240), footer_text, font_footer, fill=(100, 116, 139))

    if payload.coverage_note:
        cov_note = truncate_text(payload.coverage_note, max_chars=60)
        w_cov, _ = measure_text(draw, cov_note, font_coverage)
        draw_text(draw, (CARD_WIDTH // 2 - w_cov // 2, 1272), cov_note, font_coverage, fill=(148, 163, 184))

    # Save to BytesIO buffer
    buf = io.BytesIO()
    base.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


async def render_recap_card_async(payload: RecapCardPayload) -> bytes:
    """
    Renders recap card in background thread pool to prevent blocking the event loop.
    """
    return await asyncio.to_thread(render_recap_card_png, payload)


# ---------------------------------------------------------------------------
# 7. Helper: Build RecapCardPayload from session state
# ---------------------------------------------------------------------------
def build_card_payload_from_session(
    session_state: Any,
    session_title: str = "ملخص المكالمة • CallWrapped",
    period_label: str = "جلسة صوتية حية"
) -> Optional[RecapCardPayload]:
    """
    Extracts session analytics from session_state into a validated RecapCardPayload.
    Returns None if the session has no data.
    """
    if not session_state:
        return None

    # 1. Extract speakers
    speakers = []
    stats_tracker = getattr(session_state, "stats_tracker", None)
    if stats_tracker and hasattr(stats_tracker, "speakers") and stats_tracker.speakers:
        speakers = list(stats_tracker.speakers.values())
    elif hasattr(session_state, "speakers") and session_state.speakers:
        spks = getattr(session_state, "speakers")
        speakers = list(spks.values()) if isinstance(spks, dict) else list(spks)
    elif isinstance(session_state, dict):
        if "stats_tracker" in session_state and hasattr(session_state["stats_tracker"], "speakers") and session_state["stats_tracker"].speakers:
            speakers = list(session_state["stats_tracker"].speakers.values())
        elif "speakers" in session_state and session_state["speakers"]:
            spks = session_state["speakers"]
            speakers = list(spks.values()) if isinstance(spks, dict) else list(spks)

    def _get_float(obj, attr, default=0.0):
        val = getattr(obj, attr, default)
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    def _get_int(obj, attr, default=0):
        val = getattr(obj, attr, default)
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    total_talk_sec = sum(_get_float(s, "total_speak_seconds", 0.0) for s in speakers)
    total_utterances = sum(_get_int(s, "utterance_count", 0) for s in speakers)

    # Empty session check
    if not speakers or (total_talk_sec == 0.0 and total_utterances == 0):
        return None

    speaker_stats: List[SpeakerStat] = []
    for spk in sorted(speakers, key=lambda s: _get_float(s, "total_speak_seconds", 0.0), reverse=True):
        name = getattr(spk, "speaker_name", None) or getattr(spk, "speaker_id", "Speaker")
        talk_sec = _get_float(spk, "total_speak_seconds", 0.0)
        pct = (talk_sec / total_talk_sec * 100.0) if total_talk_sec > 0 else 0.0
        streak = _get_float(spk, "longest_streak_seconds", 0.0)
        angry_eps = _get_int(spk, "angry_episodes", 0)
        quote = getattr(spk, "first_anger_quote", None)

        speaker_stats.append(
            SpeakerStat(
                name=str(name),
                talk_seconds=talk_sec,
                share_pct=pct,
                streak_seconds=streak,
                angry_episodes=angry_eps,
                first_anger_quote=quote
            )
        )

    # 2. Extract topics
    topic_counts: Dict[str, int] = {}
    if hasattr(session_state, "topic_counts") and session_state.topic_counts:
        for t, c in session_state.topic_counts.items():
            if t:
                topic_counts[t] = topic_counts.get(t, 0) + c
    elif isinstance(session_state, dict) and "topic_counts" in session_state:
        for t, c in session_state["topic_counts"].items():
            if t:
                topic_counts[t] = topic_counts.get(t, 0) + c

    if not topic_counts:
        topics_attr = getattr(session_state, "topics", None)
        if topics_attr is None and isinstance(session_state, dict):
            topics_attr = session_state.get("topics")
        if topics_attr:
            if isinstance(topics_attr, dict):
                for t, c in topics_attr.items():
                    if t:
                        topic_counts[t] = topic_counts.get(t, 0) + c
            elif isinstance(topics_attr, (list, tuple)):
                for t in topics_attr:
                    if t:
                        topic_counts[t] = topic_counts.get(t, 0) + 1

    if not topic_counts and hasattr(session_state, "turns") and session_state.turns:
        for turn in session_state.turns:
            t = turn.get("topic")
            if t:
                topic_counts[t] = topic_counts.get(t, 0) + 1

    # Extract micro-tags if available
    micro_tags_list: List[str] = []
    micro_tag_counts: Dict[str, int] = {}
    raw_micro_tags = getattr(session_state, "micro_tags", None)
    if raw_micro_tags is None and isinstance(session_state, dict):
        raw_micro_tags = session_state.get("micro_tags")
    if raw_micro_tags and isinstance(raw_micro_tags, dict):
        for tag, c in raw_micro_tags.items():
            if tag and str(tag).lower() not in ("none", "null", "other", "null_topic"):
                micro_tag_counts[str(tag)] = micro_tag_counts.get(str(tag), 0) + c
        sorted_micro = sorted(micro_tag_counts.items(), key=lambda x: x[1], reverse=True)
        micro_tags_list = [t for t, _ in sorted_micro]

    topical_counts = {t: c for t, c in topic_counts.items() if t not in ("null_topic", "null", "none", "بدون موضوع")}
    null_count = topic_counts.get("null_topic", 0) + topic_counts.get("null", 0) + topic_counts.get("بدون موضوع", 0)
    total_topical_count = sum(topical_counts.values())
    total_all_count = total_topical_count + null_count
    coverage_pct = (total_topical_count / total_all_count * 100.0) if total_all_count > 0 else 0.0

    from bot.arbitration.stats import TOPIC_DISPLAY_NAMES, compute_topic_importance

    # Extract continuous topic durations and intervals if present
    topic_durations: Dict[str, float] = {}
    if hasattr(session_state, "get_topic_durations") and callable(session_state.get_topic_durations):
        try:
            topic_durations = session_state.get_topic_durations() or {}
        except Exception:
            topic_durations = {}
    elif isinstance(session_state, dict) and "topic_durations" in session_state:
        topic_durations = session_state.get("topic_durations") or {}

    intervals = list(getattr(session_state, "completed_intervals", []))
    active_itv = getattr(session_state, "active_interval", None)
    if active_itv:
        intervals.append(active_itv)

    ranked_topics = compute_topic_importance(
        topic_durations=topic_durations,
        topic_counts=topic_counts,
        intervals=intervals,
        total_speakers=len(speaker_stats)
    )

    top_topics: List[TopicStat] = []
    for top_name, importance_score, t_pct in ranked_topics:
        display_name = TOPIC_DISPLAY_NAMES.get(top_name.lower(), top_name)
        if top_name.lower() in ("other", "عام") and micro_tags_list:
            display_name = f"أخرى ({micro_tags_list[0]})"
        top_topics.append(TopicStat(topic_key=top_name, display_name=display_name, pct=t_pct))

    coverage_note = f"نسبة التغطية الموضوعية: {coverage_pct:.1f}%" if total_all_count > 0 else ""

    return RecapCardPayload(
        session_title=session_title,
        period_label=period_label,
        speaker_stats=speaker_stats,
        top_topics=top_topics,
        coverage_note=coverage_note,
        micro_tags=micro_tags_list
    )
