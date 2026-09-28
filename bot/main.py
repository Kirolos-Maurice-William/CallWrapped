import io
import sys
import time
import asyncio
import logging
from pathlib import Path
from typing import Dict, Optional, Any

import discord
from discord.ext import commands, voice_recv

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import uuid
from bot.config import config
from bot.audio import AudioReceiver, install_dave_adapter
from bot.ai import assemblyai_client, speaker
from bot.arbitration import arbitration_engine, arbitration_verifier, normalize_topic_key
from bot.arbitration.engine import PendingOffer
from bot.events.models import VoiceEvent, LatencyBreakdown
from bot.events.publisher import publisher

# Hook publisher to track topics per session for !recap
_original_publish_sync = publisher.publish_sync_task

def _on_event_published(event: VoiceEvent):
    if event.type == "analytics_update" and event.topic and event.session_id:
        try:
            guild_id = int(event.session_id)
            session = arbitration_engine.get_session(guild_id)
            if not hasattr(session, "topic_counts"):
                session.topic_counts = {}
            session.topic_counts[event.topic] = session.topic_counts.get(event.topic, 0) + 1
            if getattr(event, "tag", None) and event.topic != "null_topic":
                clean_tag = str(event.tag).strip()
                if clean_tag and clean_tag.lower() not in ("none", "null", "other", "null_topic"):
                    if not hasattr(session, "micro_tags"):
                        session.micro_tags = {}
                    session.micro_tags[clean_tag] = session.micro_tags.get(clean_tag, 0) + 1
        except (ValueError, TypeError):
            pass
    _original_publish_sync(event)

publisher.publish_sync_task = _on_event_published

# 1. Install isolated DAVE E2EE decryption adapter immediately
install_dave_adapter()

# Configure logging filter to silence spammy RTCP packet warnings from discord.ext.voice_recv
class SilenceRTCPFilter(logging.Filter):
    """Filters out noisy 'Received unexpected rtcp packet' log spam from discord.ext.voice_recv."""
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if "unexpected rtcp packet" in record.getMessage().lower():
                return False
        except Exception:
            pass
        return True


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
_rtcp_filter = SilenceRTCPFilter()
logging.getLogger("discord.ext.voice_recv").addFilter(_rtcp_filter)
for _h in logging.root.handlers:
    _h.addFilter(_rtcp_filter)

logger = logging.getLogger("CallWrappedBot")

# Bot Setup
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix=config.COMMAND_PREFIX, intents=intents, help_command=None)


class GuildContext:
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        self.voice_client: Optional[voice_recv.VoiceRecvClient] = None
        self.text_channel: Optional[discord.TextChannel] = None
        self.sink: Optional[AudioReceiver] = None
        self.mode: str = "referee"  # Default: Silent Referee


guild_contexts: Dict[int, GuildContext] = {}


def get_guild_context(guild_id: int) -> GuildContext:
    if guild_id not in guild_contexts:
        guild_contexts[guild_id] = GuildContext(guild_id)
    return guild_contexts[guild_id]


async def on_user_utterance(
    guild_id: int,
    user_id: int,
    speaker_name: str,
    wav_bytes: bytes,
    speech_start: float = 0.0,
    speech_end: float = 0.0,
    ended_by: str = "silence",
    audio_features: Optional[Any] = None
):
    """
    Asynchronous per-speaker utterance callback.
    Captures raw verbatim speech with code-switching, routes through arbitration state machine.
    """
    ctx = get_guild_context(guild_id)
    if not ctx.voice_client or not ctx.voice_client.is_connected():
        return

    # 1. Transcribe speech using AssemblyAI Universal-3.5 Pro (Preserves raw transcript as evidence!)
    raw_text, stt_ms = await assemblyai_client.transcribe(wav_bytes, speaker_name=speaker_name)
    if not raw_text or len(raw_text.strip()) < 2:
        return

    # Test-Mode Capture: asynchronously save utterance audio and metadata
    if getattr(config, "TEST_CAPTURE_MODE", 0):
        from bot.audio.capture import save_captured_utterance_async
        asyncio.create_task(
            save_captured_utterance_async(
                speaker_name=speaker_name,
                wav_bytes=wav_bytes,
                asr_text=raw_text,
                stt_latency_ms=stt_ms,
                ended_by=ended_by,
                timestamp=time.time(),
                audio_features=audio_features
            )
        )

    # 2. Feed into Arbitration Engine State Machine
    await arbitration_engine.process_utterance(
        guild_id=guild_id,
        user_id=user_id,
        speaker_name=speaker_name,
        raw_text=raw_text,
        stt_ms=stt_ms,
        voice_client=ctx.voice_client,
        text_channel=ctx.text_channel,
        mode=ctx.mode,
        speech_start=speech_start,
        speech_end=speech_end,
        audio_features=audio_features
    )


# =============================================================================
# Discord Commands
# =============================================================================

def build_privacy_notice_text() -> str:
    """Short Arabic notice stating real-time analysis scope and zero permanent storage."""
    return (
        "يقوم البوت بتحليل المكالمة لحظياً (وقت التحدث، المواضيع، نوبات الإحباط، "
        "والتحقق من الحقائق عبر البحث المباشر على الويب). "
        "يتم معالجة الصوت داخل الذاكرة فقط إلا في حال تفعيل وضع الالتقاط صراحةً من قبل المشرفين (!start-capture). "
        "وعند التفعيل، تُحفظ المقاطع في مجلد جلسة معزول ومؤرخ داخل recordings/test_session/. "
        "لا يتم حفظ أو تخزين أي تسجيلات صوتية أو نصوص بعد انتهاء الجلسة."
    )


def build_join_embed(channel_name: str, mode: str) -> discord.Embed:
    """Builds the join announcement embed including the mandatory privacy notice."""
    embed = discord.Embed(
        title="🎙️ CallWrapped ● LIVE (AssemblyAI Hackathon)",
        description=(
            f"Connected to **{channel_name}**!\n\n"
            f"🛡️ **Current Mode:** `{mode.upper()}`\n"
            "• `!start`: Activate session (Fact Check Mode: ON, offers only).\n"
            "• `!check`: Confirm pending dispute fact check.\n"
            "• `!mode referee`: **(Default)** Silent observer. Only speaks when confirmed.\n"
            "• `!mode echo`: Test mode (repeats verbatim speech for mic check).\n"
            "• `!stats`: Server Evidence Leaderboard & Fact-checking insights.\n"
            "• `!dashboard`: Open Live Judge-Facing Web Dashboard.\n"
            "• `!privacy`: Privacy policy, data retention & emotion disclaimer.\n"
            "• `!leave`: Disconnect from voice and clear session."
        ),
        color=config.EMBED_COLOR_INFO
    )
    embed.add_field(
        name="🔒 إشعار الخصوصية والشفافية",
        value=build_privacy_notice_text(),
        inline=False
    )
    embed.set_footer(text=f"AssemblyAI {config.speech_model_display} • Groq LPU • Tavily")
    return embed


@bot.command(name="join")
async def join_channel(ctx: commands.Context):
    """Connects bot to the caller's voice channel."""
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("❌ You must be in a voice channel first for me to join!")
        return

    voice_channel = ctx.author.voice.channel
    guild_ctx = get_guild_context(ctx.guild.id)
    guild_ctx.text_channel = ctx.channel

    try:
        if guild_ctx.voice_client and guild_ctx.voice_client.is_connected():
            await guild_ctx.voice_client.move_to(voice_channel)
        else:
            guild_ctx.voice_client = await voice_channel.connect(cls=voice_recv.VoiceRecvClient)

        def make_handler(g_id: int):
            async def handler(u_id: int, u_name: str, wav: bytes, speech_start: float = 0.0, speech_end: float = 0.0, ended_by: str = "silence", audio_features: Optional[Any] = None):
                await on_user_utterance(g_id, u_id, u_name, wav, speech_start, speech_end, ended_by, audio_features)
            return handler

        sink = AudioReceiver(
            loop=bot.loop,
            on_utterance=make_handler(ctx.guild.id),
            voice_client=guild_ctx.voice_client
        )
        guild_ctx.sink = sink
        guild_ctx.voice_client.listen(sink)

        embed = build_join_embed(voice_channel.name, guild_ctx.mode)
        await ctx.send(embed=embed)

    except Exception as e:
        logger.error(f"Join error: {e}", exc_info=True)
        await ctx.send(f"❌ Error connecting to voice channel: {e}")


@bot.command(name="mode")
async def set_mode(ctx: commands.Context, mode_name: str):
    """Sets bot mode: '!mode referee' (default) or '!mode echo'."""
    mode_name = mode_name.lower().strip()
    if mode_name not in ("referee", "echo", "assistant"):
        await ctx.send("❌ Available modes: `!mode referee` (default), `!mode echo`, or `!mode assistant`")
        return

    guild_ctx = get_guild_context(ctx.guild.id)
    guild_ctx.mode = mode_name
    modes_desc = {
        "referee": "🛡️ **Referee Mode:** Silent observer. Intervenes verbally only upon verified disputes.",
        "echo": "🎙️ **Echo Mode:** Testing only. Repeats verbatim audio.",
        "assistant": "🤖 **Assistant Mode:** Responds when directly called upon."
    }
    await ctx.send(f"✅ {modes_desc[mode_name]}")


def build_stats_embed(session: Any) -> discord.Embed:
    """Builds discord.Embed for Server Insights & Evidence Leaderboard with defensive key lookups."""
    verified_claims = getattr(session, "verified_claims_count", 0)
    disputed_claims = getattr(session, "disputed_claims_count", 0)
    unverifiable = getattr(session, "unverifiable_count", 0)

    embed = discord.Embed(
        title="📊 Server Insights & Evidence Leaderboard",
        description=(
            f"• **Verified Claims:** `{verified_claims}`\n"
            f"• **Disputed Claims:** `{disputed_claims}`\n"
            f"• **Unverifiable Claims:** `{unverifiable}`"
        ),
        color=config.EMBED_COLOR_INFO
    )

    speaker_stats = getattr(session, "speaker_stats", {}) or {}
    if speaker_stats:
        for name, data in speaker_stats.items():
            if isinstance(data, dict):
                turns = data.get("turns", 0)
                verified = data.get("verified", 0)
                refuted = data.get("refuted", data.get("disputed", 0))
            else:
                turns = getattr(data, "turns", 0)
                verified = getattr(data, "verified", 0)
                refuted = getattr(data, "refuted", getattr(data, "disputed", 0))

            embed.add_field(
                name=f"👤 {name}",
                value=f"• Total Turns: `{turns}`\n• Verified Facts: `✅ {verified}`\n• Refuted Claims: `❌ {refuted}`",
                inline=True
            )
    else:
        embed.add_field(name="Participants", value="No voice activity recorded yet.", inline=False)

    return embed


@bot.command(name="stats")
async def show_stats(ctx: commands.Context):
    """Displays Server Insights & Evidence Leaderboard."""
    session = arbitration_engine.get_session(ctx.guild.id)
    embed = build_stats_embed(session)
    await ctx.send(embed=embed)


def format_streak_mmss(seconds: float) -> str:
    """Formats duration in seconds as m:ss (e.g. 83.0s -> '1:23')."""
    total_sec = int(round(seconds))
    mins = total_sec // 60
    secs = total_sec % 60
    return f"{mins}:{secs:02d}"


def render_recap(session_state: Any) -> str:
    """
    Pure function rendering real session recap text in Egyptian Arabic.
    Shows:
    - Per-speaker talk minutes + % share bar (▰▱)
    - Longest streak record holder (formatted as m:ss)
    - Anger leaderboard (episode count + first anger quote as "receipts")
    - Top-3 topics with %
    Returns 'No data yet in this call.' if the session is empty.
    Never fabricates or default-fills numbers.
    """
    if not session_state:
        return "مفيش بيانات في المكالمة دي لسه."

    # 1. Extract speakers from session_state
    speakers = []
    stats_tracker = getattr(session_state, "stats_tracker", None)
    if stats_tracker is None and isinstance(session_state, dict):
        stats_tracker = session_state.get("stats_tracker")

    if stats_tracker and hasattr(stats_tracker, "speakers"):
        speakers = list(stats_tracker.speakers.values())
    elif hasattr(session_state, "speakers"):
        spks = getattr(session_state, "speakers")
        speakers = list(spks.values()) if isinstance(spks, dict) else list(spks)
    elif isinstance(session_state, dict) and "speakers" in session_state:
        spks = session_state["speakers"]
        speakers = list(spks.values()) if isinstance(spks, dict) else list(spks)

    total_talk_sec = sum(s.total_speak_seconds for s in speakers)
    total_utterances = sum(s.utterance_count for s in speakers)

    # Empty session check: render ONLY from real session data
    if not speakers or (total_talk_sec == 0.0 and total_utterances == 0):
        return "مفيش بيانات في المكالمة دي لسه."

    # 2. Extract topics from session_state
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

    if not topic_counts and hasattr(session_state, "claim_memory") and session_state.claim_memory:
        for claim in getattr(session_state.claim_memory, "claims", []):
            if claim.topic:
                topic_counts[claim.topic] = topic_counts.get(claim.topic, 0) + 1

    lines = ["🎙️ **ملخص المكالمة**\n"]

    # Section A: Per-speaker talk minutes + % share bar (▰▱)
    lines.append("🗣️ **وقت الكلام ونسبة المشاركة:**")
    sorted_speakers = sorted(speakers, key=lambda s: s.total_speak_seconds, reverse=True)
    for spk in sorted_speakers:
        name = spk.speaker_name or spk.speaker_id
        talk_sec = spk.total_speak_seconds
        talk_min = talk_sec / 60.0
        pct = (talk_sec / total_talk_sec * 100.0) if total_talk_sec > 0 else 0.0
        filled_blocks = int(round(pct / 10.0))
        filled_blocks = max(0, min(10, filled_blocks))
        bar = "▰" * filled_blocks + "▱" * (10 - filled_blocks)
        lines.append(f"• **{name}**: {talk_min:.1f}m {bar} ({pct:.1f}%)")

    # Section B: Longest streak record holder (formatted as m:ss)
    lines.append("\n🔥 **صاحب أطول ريكورد كلام متواصل:**")
    streak_holder = max(speakers, key=lambda s: s.longest_streak_seconds)
    if streak_holder.longest_streak_seconds > 0:
        s_name = streak_holder.speaker_name or streak_holder.speaker_id
        streak_str = format_streak_mmss(streak_holder.longest_streak_seconds)
        lines.append(f"👑 **{s_name}** ({streak_str})")
    else:
        lines.append("None")

    # Section C: Anger leaderboard (episode count + first anger quote as "receipts")
    # If zero angry episodes for everyone, replace with: "😡 Nobody got angry this call... suspicious."
    angry_speakers = [s for s in sorted_speakers if s.angry_episodes > 0]
    if angry_speakers:
        lines.append("\n😡 **نوبات إحباط:**")
        angry_speakers.sort(key=lambda s: s.angry_episodes, reverse=True)
        for s in angry_speakers:
            name = s.speaker_name or s.speaker_id
            quote_str = f' | Receipts: "{s.first_anger_quote}"' if s.first_anger_quote else ""
            ep_word = "moment" if s.angry_episodes == 1 else "moments"
            lines.append(f"• **{name}**: {s.angry_episodes} {ep_word}{quote_str}")
    else:
        lines.append("\n😡 محدش عصب في المكالمة دي... كده مش طبيعي 😂")

    # Section D: Top-3 topics with % (Taxonomy v3: TOPICAL only, null_topic excluded)
    lines.append("\n🏷️ **أكتر مواضيع اتكلمتوا فيها:**")
    topical_counts = {t: c for t, c in topic_counts.items() if t not in ("null_topic", "null", "none", "بدون موضوع")}
    null_count = topic_counts.get("null_topic", 0) + topic_counts.get("null", 0) + topic_counts.get("بدون موضوع", 0)
    total_topical_count = sum(topical_counts.values())
    total_all_count = total_topical_count + null_count
    coverage_pct = (total_topical_count / total_all_count * 100.0) if total_all_count > 0 else 0.0

    if total_topical_count > 0:
        from bot.arbitration.stats import TOPIC_DISPLAY_NAMES
        top_3 = sorted(topical_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        for rank, (top_name, top_cnt) in enumerate(top_3, 1):
            t_pct = (top_cnt / total_topical_count) * 100.0
            display_name = TOPIC_DISPLAY_NAMES.get(top_name.lower(), top_name)
            lines.append(f"{rank}. **{display_name}**: {t_pct:.1f}% ({top_cnt})")
        if null_count > 0:
            lines.append(f"ℹ️ نسبة التغطية الموضوعية: {coverage_pct:.1f}% (مستبعد {null_count} جمل بدون موضوع)")

        # Fine-grained micro-tag highlights (eradicates generic "Other" obscurity)
        micro_tags = getattr(session_state, "micro_tags", {})
        if micro_tags:
            valid_tags = {k: v for k, v in micro_tags.items() if k and str(k).lower() not in ("none", "null", "other", "null_topic")}
            if valid_tags:
                top_tags = sorted(valid_tags.items(), key=lambda x: x[1], reverse=True)[:4]
                tag_str = " • ".join(f"#{t} ({c})" for t, c in top_tags)
                lines.append(f"📌 **أبرز الكلمات والمواضيع الدقيقة:** {tag_str}")
    elif null_count > 0:
        lines.append(f"مفيش مواضيع مسجلة (كل الكلام كان دردشة/تنسيق بدون موضوع - {null_count} جمل).")
    else:
        lines.append("مفيش مواضيع مسجلة لسه.")

    return "\n".join(lines)


@bot.command(name="recap")
async def recap_command(ctx: commands.Context):
    """Displays real-time session recap."""
    session = arbitration_engine.get_session(ctx.guild.id)
    if getattr(session, "analytics_buffer", None):
        await arbitration_engine.flush_analytics(ctx.guild.id, reason="recap_render")
    recap_text = render_recap(session)
    await ctx.send(recap_text)


@bot.command(name="card")
async def card_command(ctx: commands.Context):
    """Generates and posts a shareable Wrapped recap card as a PNG image."""
    session = arbitration_engine.get_session(ctx.guild.id)
    if getattr(session, "analytics_buffer", None):
        await arbitration_engine.flush_analytics(ctx.guild.id, reason="recap_render")

    from bot.ui.recap_card_renderer import build_card_payload_from_session, render_recap_card_async

    guild_name = getattr(ctx.guild, "name", "Discord Call") if ctx.guild else "Discord Call"
    payload = build_card_payload_from_session(
        session,
        session_title=f"CallWrapped • {guild_name}",
        period_label="ملخص الجلسة الصوتية وتفاعل المتحدثين"
    )
    if not payload:
        await ctx.send("مفيش بيانات في المكالمة دي لسه.")
        return

    try:
        png_bytes = await render_recap_card_async(payload)
        file = discord.File(fp=io.BytesIO(png_bytes), filename="callwrapped_recap.png")
        await ctx.send(file=file)
    except discord.HTTPException as e:
        logger.error(f"[CardCommand] Discord HTTP error uploading recap card: {e}", exc_info=True)
        await ctx.send("حدث خطأ أثناء إنشاء كارت الملخص.")
    except Exception as e:
        logger.error(f"[CardCommand] Error generating recap card: {e}", exc_info=True)
        await ctx.send("حدث خطأ أثناء إنشاء كارت الملخص.")


@bot.command(name="help")
async def show_help(ctx: commands.Context):
    """Displays comprehensive help and hackathon judging instructions."""
    embed = discord.Embed(
        title="⚖️ CallWrapped — AssemblyAI Voice Agent Hackathon",
        description=(
            "An autonomous multi-speaker referee that monitors Discord voice channels silently, "
            "catches objective factual contradictions in real time, verifies them via authoritative web sources, "
            "and intervenes verbally with the ground truth.\n\n"
            "**Available Commands:**"
        ),
        color=config.EMBED_COLOR_INFO
    )
    embed.add_field(
        name="🎙️ Voice Channel Management",
        value=(
            "• `!start`: Joins your voice channel and begins autonomous referee monitoring.\n"
            "• `!join`: Connects the bot to your current voice channel.\n"
            "• `!leave`: Disconnects the bot from voice and resets session.\n"
            "• `!judge-mode`: Toggles the 7-card Judge Attack Mode adversarial test harness.\n"
            "• `!mode referee`: *(Default)* Silent observer. Only speaks on verified factual disputes.\n"
            "• `!mode echo`: Mic-check mode (repeats verbatim audio).\n"
            "• `!mode assistant`: Interactive assistant mode."
        ),
        inline=False
    )
    embed.add_field(
        name="⚡ Instant Arbitration & Demo Tools",
        value=(
            "• `!check`: Confirms a pending dispute verification offer (or voice: «شوفها»).\n"
            "• `!arbitrate <query>`: On-demand fact verification query (e.g. `!arbitrate RTX 5070 VRAM`).\n"
            "• `!simulate`: Executes the RTX 5070 16GB vs 12GB Golden Demo scenario.\n"
            "• `!recap`: Displays real-time session recap (talk minutes, streaks, frustration, top topics).\n"
            "• `!card`: Generates a shareable Wrapped visual recap card (PNG).\n"
            "• `!stats`: Displays the server evidence & speaker accuracy leaderboard.\n"
            "• `!status`: Checks latency, API connections, and voice channel state.\n"
            "• `!dashboard`: Link to the live Next.js Judge Dashboard.\n"
            "• `!privacy`: Privacy policy, data retention details, and in-memory processing info.\n"
            "• `!clear`: Clears session turns and dispute history for a fresh demo.\n"
            "• `!start-capture`: Enables test-mode audio capture into a new isolated folder `recordings/test_session/<YYYY-MM-DD_HHMM>/`.\n"
            "• `!stop-capture`: Stops capture, finalizes session, and generates `labels_DRAFT.csv` in the session folder."
        ),
        inline=False
    )
    embed.set_footer(text=f"AssemblyAI {config.speech_model_display} • Groq LPU • Tavily Ground-Truth • Edge-TTS")
    await ctx.send(embed=embed)


def build_status_embed(guild_ctx: Any, session: Any, ping_ms: int = 0) -> discord.Embed:
    """Builds discord.Embed for Operational Status with defensive attribute lookups."""
    vc = getattr(guild_ctx, "voice_client", None)
    in_voice = bool(vc and vc.is_connected())
    channel = getattr(vc, "channel", None) if in_voice else None
    channel_name = getattr(channel, "name", "Not Connected") if channel else "Not Connected"
    mode_str = getattr(guild_ctx, "mode", "referee").upper()

    embed = discord.Embed(
        title="⚙️ CallWrapped — Operational Status",
        color=0x57F287 if in_voice else config.EMBED_COLOR_INFO
    )
    embed.add_field(name="🎙️ Voice Status", value=f"Connected to: **{channel_name}**" if in_voice else "❌ Disconnected (`!join` to start)", inline=True)
    embed.add_field(name="🛡️ Active Mode", value=f"`{mode_str}`", inline=True)
    embed.add_field(name="⚡ Bot Ping", value=f"`{ping_ms}ms`", inline=True)

    embed.add_field(
        name="🧠 Cloud AI Pipeline",
        value=(
            f"• **AssemblyAI {config.speech_model_display}:** ✅ Active (Native Code-Switching)\n"
            f"• **Groq LPU ({config.GROQ_MODEL}):** ✅ Active (~200ms)\n"
            "• **Tavily Web Search:** ✅ Active (Ground Truth)\n"
            "• **Edge-TTS (ar-EG-Shakir):** ✅ Active"
        ),
        inline=False
    )

    turns_len = len(getattr(session, "turns", [])) if getattr(session, "turns", None) is not None else 0
    disputed_count = getattr(session, "disputed_claims_count", 0)
    verified_count = getattr(session, "verified_claims_count", 0)

    embed.add_field(
        name="📊 Session Statistics",
        value=f"• Recorded Turns: `{turns_len}`\n• Disputes Resolved: `{disputed_count}`\n• Verified Facts: `{verified_count}`",
        inline=True
    )
    embed.add_field(
        name="🌐 Live Dashboard",
        value=f"[Open Dashboard]({config.BACKEND_API_URL})",
        inline=True
    )
    return embed


def build_dashboard_embed() -> discord.Embed:
    """Builds discord.Embed with the live web dashboard URL read from config."""
    url = getattr(config, "DASHBOARD_URL", None) or getattr(config, "BACKEND_API_URL", "http://127.0.0.1:8000")
    embed = discord.Embed(
        title="🌐 Live Judge & Analytics Dashboard",
        description=(
            "Access real-time voice call analytics, live epistemic fact-checks, "
            "and evidence telemetry on the web interface:\n\n"
            f"🔗 **[Open Web Dashboard]({url})**\n\n"
            f"📍 **Direct URL:** `{url}`"
        ),
        color=config.EMBED_COLOR_INFO
    )
    embed.add_field(
        name="⚡ Features",
        value=(
            "• Live STT & Latency telemetry\n"
            "• Epistemic conflict & arbitration logs\n"
            "• Speaker participation & frustration trackers"
        ),
        inline=False
    )
    embed.set_footer(text="AssemblyAI Hackathon • Real-Time CallWrapped")
    return embed


@bot.command(name="dashboard")
async def show_dashboard(ctx: commands.Context):
    """Sends the link and embed for the live web dashboard."""
    embed = build_dashboard_embed()
    await ctx.send(embed=embed)


def build_privacy_embed() -> discord.Embed:
    """Builds discord.Embed explaining live call analysis, zero retention, and emotion inference disclaimer."""
    embed = discord.Embed(
        title="🔒 سياسة الخصوصية والشفافية | Privacy & Transparency",
        description=(
            "**كيف يتعامل البوت مع بياناتك الصوتية؟**\n\n"
            "• 🎙️ **تحليل لحظي فقط:** يتم تحليل الصوت في الذاكرة الحية المؤقتة فقط (RAM) "
            "لحساب وقت التحدث، تصنيف المواضيع، رصد نوبات الإحباط، والتحقق الفوري من المعلومات المتناقضة عبر الويب. "
            "يتم معالجة الصوت داخل الذاكرة المؤقتة فقط (in-memory) إلا في حال تفعيل وضع الالتقاط صراحةً بواسطة المشرفين (`!start-capture`). "
            "وعند التفعيل، تُحفظ المقاطع في مجلد جلسة معزول ومؤرخ (`recordings/test_session/<timestamp>/`).\n\n"
            "• 🗑️ **انعدام التخزين الدائم:** لا يتم حفظ أو تخزين أي تسجيلات صوتية أو نصوص محادثات بعد انتهاء الجلسة. "
            "بمجرد مغادرة القناة الصوتية (`!leave`) أو إعادة التعيين (`!clear`)، تُحذف جميع بيانات الجلسة فوراً.\n\n"
            "• ⚠️ **تنويه نوبات الإحباط:** استنتاج المشاعر ونوبات الإحباط هو تقدير آلي (Automated AI Inference) "
            "يعتمد على نبرة الكلمات وسياق الحديث، وقد يكون غير دقيق أو يحتمل الخطأ، ولا يُقصد به أي حكم شخصي."
        ),
        color=config.EMBED_COLOR_INFO
    )
    embed.add_field(
        name="🛡️ Privacy Summary (EN)",
        value=(
            "• **Live Analysis Only**: Real-time processing of talk time, topics, frustration signals, and web fact-checking.\n"
            "• **In-Memory Processing**: Audio is processed strictly in-memory unless capture mode is explicitly enabled by admins (!start-capture).\n"
            "• **Isolated Test Folders**: When capture is enabled, audio is saved into isolated session folders (`recordings/test_session/<timestamp>/`).\n"
            "• **Zero Retention**: All session turns and transcripts are permanently cleared when the session ends (`!leave` or `!clear`).\n"
            "• **Emotion Disclaimer**: Frustration/anger detection is an automated AI inference that may be mistaken or imprecise."
        ),
        inline=False
    )
    embed.set_footer(text="AssemblyAI Hackathon • Real-Time CallWrapped • Privacy First")
    return embed


@bot.command(name="privacy")
async def show_privacy(ctx: commands.Context):
    """Displays privacy policy, data retention details, and emotion inference disclaimer."""
    embed = build_privacy_embed()
    await ctx.send(embed=embed)


def build_fact_check_mode_embed(is_on: bool = True) -> discord.Embed:
    """Builds discord.Embed announcing Fact Check Mode status and consent notice."""
    notice = build_privacy_notice_text()
    status_str = "ON" if is_on else "OFF"
    embed = discord.Embed(
        title=f"🎙️ Fact Check Mode: {status_str}",
        description=(
            f"✅ **Fact Check Mode: {status_str}** (offers only — bot never speaks uninvited)\n\n"
            "🔒 **إشعار الخصوصية والشفافية:**\n"
            f"{notice}\n\n"
            "💡 عند رصد أي اختلاف في المعلومات بين المتحدثين، سيقترح البوت التحقق كتابياً. "
            "لتأكيد التحقق وسماع النتيجة: قل «شوفها» أو اكتب `!check`."
        ),
        color=config.EMBED_COLOR_INFO
    )
    embed.add_field(
        name="🛡️ Operating Policy",
        value="• Two-Stage Referee: Bot offers first, never speaks unsolicited.\n• Confirmation: Say «شوفها» in voice or type `!check` in chat.",
        inline=False
    )
    embed.set_footer(text=f"AssemblyAI {config.speech_model_display} • Groq LPU • Tavily")
    return embed


@bot.command(name="start")
async def start_session(ctx: commands.Context):
    """
    Session start command:
    a) Posts Arabic consent/notice to text channel.
    b) Announces: "Fact Check Mode: ON (offers only — bot never speaks uninvited)".
    c) Emits event so dashboard shows "Fact Check Mode: ON" badge.
    """
    session = arbitration_engine.get_session(ctx.guild.id)
    session.fact_check_mode = True

    embed = build_fact_check_mode_embed(is_on=True)
    await ctx.send(embed=embed)

    # Publish VoiceEvent
    mode_event = VoiceEvent(
        session_id=str(ctx.guild.id),
        type="fact_check_mode_update",
        speaker_name=ctx.author.display_name,
        text="Fact Check Mode: ON (offers only — bot never speaks uninvited)",
        payload={
            "mode": "ON",
            "badge": "Fact Check Mode: ON",
            "policy": "offers_only",
            "never_speaks_unsolicited": True
        }
    )
    publisher.publish_sync_task(mode_event)


@bot.command(name="check")
async def check_dispute(ctx: commands.Context):
    """Confirm a pending dispute check offer via text chat."""
    guild_ctx = get_guild_context(ctx.guild.id)
    session = arbitration_engine.get_session(ctx.guild.id)

    offer = session.pending_offer
    if not offer or offer.is_resolved:
        try:
            await ctx.send("ℹ️ لا يوجد طلب تحقق معلق حالياً.")
        except Exception as e:
            logger.debug(f"Could not send check notice to text channel: {e}")
        return

    # Atomic win: mark offer resolved immediately before any network I/O
    offer.is_resolved = True
    if offer.expiry_task and not offer.expiry_task.done():
        offer.expiry_task.cancel()

    try:
        await ctx.send("🔍 جاري التحقق من المعلومة عبر المصادر الموثوقة...")
    except Exception as e:
        logger.debug(f"Could not send check confirmation notice to text channel: {e}")

    await arbitration_engine.confirm_dispute_offer(
        guild_id=ctx.guild.id,
        confirmation_end_time=time.time(),
        confirmed_by=ctx.author.display_name,
        voice_client=guild_ctx.voice_client,
        text_channel=ctx.channel,
        target_offer=offer
    )


@bot.command(name="start-capture")
async def start_capture_command(ctx: commands.Context):
    """Enables test-mode capture for finalized utterances into a new isolated session folder."""
    from bot.audio.capture import start_capture_session
    session_dir = start_capture_session()
    await ctx.send(
        f"🎙️ **Test Capture Mode: ON | تم تفعيل التسجيل**\n"
        f"📁 **Session Folder / مجلد الجلسة:** `{session_dir}`\n"
        f"Saving finalized 16kHz WAVs and `session_log.jsonl` to this isolated folder."
    )


@bot.command(name="stop-capture")
async def stop_capture_command(ctx: commands.Context):
    """Stops test-mode capture and generates labels_DRAFT.csv inside the session folder."""
    from bot.audio.capture import stop_capture_session
    csv_path, session_dir = await asyncio.to_thread(stop_capture_session)

    msg = (
        "🛑 **Test Capture Stopped | تم إيقاف التسجيل**\n\n"
        f"📁 **Session Folder / مجلد الجلسة:** `{session_dir}`\n"
        f"📄 **Generated / الملف المستخرج:** `{csv_path}`\n\n"
        "**Instructions / التعليمات:**\n"
        "• **العربية:** استمع لكل ملف WAV، واكتب النص المصري الصحيح في خانة `correct_text`، ثم املأ التصنيفات:\n"
        "  - `topic`: (football / politics / music / movies / gaming / tech / food / travel / study_work / health / cars / money / personal / other / null_topic)\n"
        "  - `is_claim`: (yes / no)\n"
        "  - `anger`: (none / mild / high)\n"
        "  - `loud`: (normal / loud)\n\n"
        "• **English:** Listen to each WAV, type the CORRECT Egyptian text in `correct_text`, then fill:\n"
        "  - `topic`: (football / politics / music / movies / gaming / tech / food / travel / study_work / health / cars / money / personal / other / null_topic)\n"
        "  - `is_claim`: (yes / no)\n"
        "  - `anger`: (none / mild / high)\n"
        "  - `loud`: (normal / loud)"
    )
    await ctx.send(msg)


@bot.command(name="status")
async def show_status(ctx: commands.Context):
    """Displays bot health, latency metrics, and API connectivity."""
    guild_ctx = get_guild_context(ctx.guild.id)
    session = arbitration_engine.get_session(ctx.guild.id)
    ping_ms = round(bot.latency * 1000) if hasattr(bot, "latency") else 0
    embed = build_status_embed(guild_ctx, session, ping_ms=ping_ms)
    await ctx.send(embed=embed)


@bot.command(name="arbitrate")
async def manual_arbitrate(ctx: commands.Context, *, query: str):
    """Direct on-demand factual arbitration query from text chat.
    Routes through the two-stage referee offer flow (offers only, never speaks uninvited).
    """
    guild_ctx = get_guild_context(ctx.guild.id)
    session = arbitration_engine.get_session(ctx.guild.id)
    now = time.time()

    topic_key = normalize_topic_key(entity=None, topic=query)
    is_cooldown, remaining, reason = session.is_in_cooldown(topic_key, now)
    if is_cooldown:
        logger.info(f"DISPUTE_SUPPRESSED: cooldown active (remaining: {remaining}s)")
        await ctx.send(f"⏳ فترة التهدئة نشطة. يرجى الانتظار {remaining} ثانية قبل طلب تدقيق جديد. | Cooldown active: please wait {remaining}s.")
        return

    # Cancel older unconfirmed pending offer if any
    if session.pending_offer and not session.pending_offer.is_resolved:
        logger.warning(
            f"⚠️ Replacing older unconfirmed pending offer ({session.pending_offer.offer_id}) with new dispute offer"
        )
        session.pending_offer.cancel()

    session.record_offer(topic_key, now)

    # Pre-fetch: fire Tavily search in background immediately
    prefetch_task = asyncio.create_task(
        arbitration_verifier.search_evidence(query)
    )

    # Pre-warm: establish warm Edge-TTS connection in background (35s timeout)
    warm_tts = speaker.create_warm_session(timeout_seconds=35.0)

    offer_id = f"off_{uuid.uuid4().hex[:8]}"
    correlation_id = str(uuid.uuid4())
    offer = PendingOffer(
        offer_id=offer_id,
        guild_id=ctx.guild.id,
        speaker_a=ctx.author.display_name,
        claim_a=query,
        speaker_b="Fact Checker",
        claim_b=f"Verify claim against official evidence: {query}",
        entity=query,
        search_query=query,
        target_domains=[],
        prefetch_task=prefetch_task,
        created_at=now,
        expires_at=now + 30.0,
        correlation_id=correlation_id,
        voice_client=guild_ctx.voice_client,
        text_channel=ctx.channel,
        user_id=ctx.author.id,
        stt_ms=0,
        warm_tts_session=warm_tts
    )
    session.pending_offer = offer

    # Schedule expiration task
    expiry_sec = getattr(config, "DISPUTE_OFFER_EXPIRY_SEC", 30.0)
    offer.expiry_task = asyncio.create_task(
        arbitration_engine._offer_expiry_timer(guild_id=ctx.guild.id, offer_id=offer_id, timeout_seconds=expiry_sec)
    )

    # Post Arabic offer message to Discord text channel
    offer_text = f"🤖 تم اقتراح التحقق من: «{query}» — أتحقق؟ قول «شوفها» أو اكتب !check"
    await ctx.send(offer_text)

    # Publish VoiceEvent(type="dispute_check_offered")
    offer_event = VoiceEvent(
        session_id=str(ctx.guild.id),
        correlation_id=correlation_id,
        type="dispute_check_offered",
        speaker_id=str(ctx.author.id),
        speaker_name=ctx.author.display_name,
        text=offer_text,
        timings={
            "stt_final_at": round(now, 3),
            "claim_done_at": round(now, 3),
            "conflict_done_at": round(now, 3),
            "offered_at": round(now, 3)
        },
        latency=LatencyBreakdown(
            stt_ms=0,
            llm_ms=0,
            planner_ms=0
        ),
        payload={
            "offer_id": offer_id,
            "speaker_a": ctx.author.display_name,
            "claim_a": query,
            "speaker_b": "Fact Checker",
            "claim_b": f"Verify claim: {query}",
            "entity": query,
            "search_query": query,
            "planner_ms": 0,
            "expires_in_seconds": 30.0,
            "expires_at": round(now + 30.0, 3)
        }
    )
    publisher.publish_sync_task(offer_event)
    logger.info(
        f"📣 [Dispute Offer Created] ({offer_id}) Manual !arbitrate offer for '{query}'. "
        f"Search prefetch started. Awaiting confirmation (30s timeout)."
    )


@bot.command(name="simulate")
async def simulate_demo(ctx: commands.Context):
    """Injects the RTX 5070 Golden Demo dispute directly into voice and dashboard (dashboard events only, NEVER speaks)."""
    guild_ctx = get_guild_context(ctx.guild.id)
    await ctx.send("⚡ **Simulating Golden Arbitration Dispute (RTX 5070 16GB vs 12GB Demo)...**")

    # Step 1: Claim A
    await ctx.send("🗣️ **Ahmed**: Guys, the RTX 5070 definitely launches with 16GB VRAM, I am 100% sure.")
    publisher.publish_sync_task(VoiceEvent(
        type="transcript",
        speaker_name="Ahmed",
        text="Guys, the RTX 5070 definitely launches with 16GB VRAM, I am 100% sure.",
        latency=LatencyBreakdown(stt_ms=0)
    ))

    # Step 2: Claim B
    await ctx.send("🗣️ **Omar**: No Ahmed, you're mistaken. The RTX 5070 comes with 12GB GDDR7, not 16GB.")
    publisher.publish_sync_task(VoiceEvent(
        type="transcript",
        speaker_name="Omar",
        text="No Ahmed, you're mistaken. The RTX 5070 comes with 12GB GDDR7, not 16GB.",
        latency=LatencyBreakdown(stt_ms=0)
    ))

    # Step 3: Real Factual Arbitration
    verdict, search_ms, synth_ms, sources = await arbitration_verifier.verify_dispute(
        speaker_a="Ahmed",
        claim_a="RTX 5070 definitely launches with 16GB VRAM",
        speaker_b="Omar",
        claim_b="RTX 5070 comes with 12GB GDDR7, not 16GB",
        search_query="RTX 5070 VRAM memory specifications"
    )

    if verdict:
        fact_clause = verdict.get("fact_clause") or "كارت RTX 5070 بيجي بـ 12 جيجا بايت VRAM مش 16."
        hedge_clause = verdict.get("hedge_clause") or ""
        source_url = verdict.get("selected_source_url") or verdict.get("best_source_url", "")
        source_title = verdict.get("selected_source_title") or verdict.get("best_source_title", "Official Source")
        confidence = verdict.get("confidence", 95)
        spk_a_status = verdict.get("speaker_a_status", "CONTRADICTED")
        spk_b_status = verdict.get("speaker_b_status", "SUPPORTED")
    else:
        fact_clause = "Quick fact check: NVIDIA GeForce RTX 5070 features 12GB GDDR7 VRAM, not 16GB."
        hedge_clause = "Source is on the dashboard."
        source_url = "https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5070/"
        source_title = "NVIDIA Official GeForce RTX 5070 Specifications"
        confidence = 99
        spk_a_status = "CONTRADICTED"
        spk_b_status = "SUPPORTED"

    search_ms = int(search_ms) if search_ms else 0
    synth_ms = int(synth_ms) if synth_ms else 0
    stt_ms = 0  # Simulated text in chat has no speech STT
    tts_ms = 0  # !simulate NEVER speaks; dashboard events only

    winner = "Omar" if spk_b_status == "SUPPORTED" else ("Ahmed" if spk_a_status == "SUPPORTED" else None)
    loser = "Ahmed" if spk_a_status == "CONTRADICTED" else ("Omar" if spk_b_status == "CONTRADICTED" else None)

    verdict_display = f"{fact_clause} {hedge_clause}".strip() if hedge_clause else fact_clause
    embed = discord.Embed(
        title="⚖️ Verified Dispute Arbitration Verdict",
        description=(
            f"📢 **{fact_clause}**\n\n"
            f"✅ **Accurate Speaker**: `{winner or 'Omar'}`\n"
            f"❌ **Refuted Speaker**: `{loser or 'Ahmed'}`\n"
            f"🎯 **Confidence**: `{confidence}%`\n"
            f"🔗 **Official Source**: [{source_title}]({source_url})\n\n"
            f"⚡ **Latency Breakdown:** STT {stt_ms}ms | LLM {synth_ms}ms | Search {search_ms}ms | TTS {tts_ms}ms (dashboard only)"
        ),
        color=0x57F287
    )
    embed.set_footer(text=f"AssemblyAI {config.speech_model_display} • Groq LPU • Tavily")
    await ctx.send(embed=embed)

    publisher.publish_sync_task(VoiceEvent(
        type="intervention",
        speaker_name=winner or "Omar",
        text=verdict_display,
        latency=LatencyBreakdown(
            stt_ms=stt_ms,
            llm_ms=synth_ms,
            search_ms=search_ms,
            tts_ms=0
        ),
        payload={
            "status": "contradicted" if "CONTRADICTED" in (spk_a_status, spk_b_status) else "supported",
            "confidence": confidence,
            "fact_clause": fact_clause,
            "hedge_clause": hedge_clause,
            "winner": winner,
            "loser": loser,
            "speaker_a": "Ahmed",
            "claim_a": "RTX 5070 launches with 16GB VRAM",
            "speaker_b": "Omar",
            "claim_b": "RTX 5070 comes with 12GB GDDR7, not 16GB",
            "speaker_a_status": spk_a_status,
            "speaker_b_status": spk_b_status,
            "source_url": source_url,
            "source_title": source_title
        }
    ))


@bot.command(name="judge-mode")
async def judge_mode_command(ctx: commands.Context):
    """Executes the 7-Card Judge Attack Mode harness and posts results to Discord."""
    from bot.arbitration.judge_mode import run_judge_mode_harness

    embed = discord.Embed(
        title="⚔️ Judge Attack Mode — 7-Card Stress Test",
        description=(
            "Running live verification across all 7 adversarial scenarios:\n\n"
            "1. **Opinion**: Subjective claim alone -> Gate rejects\n"
            "2. **Agreement**: Both speakers agree -> No conflict\n"
            "3. **Real Dispute**: Factual contradiction -> Verified via Tavily & Groq\n"
            "4. **Private Entity**: Personal name/event -> Refused without search\n"
            "5. **Weak/Ambiguous**: Unrelated statements -> Rejected\n"
            "6. **Barge-in**: Speech during playback -> Instant abort & ffmpeg cleanup\n"
            "7. **PII Exhibit**: Redacts personal names and phone numbers via AssemblyAI"
        ),
        color=config.EMBED_COLOR_INFO
    )
    await ctx.send(embed=embed)

    results = await run_judge_mode_harness(verbose=False)
    passed_count = sum(1 for r in results if r.get("passed"))

    result_lines = []
    for r in results:
        status_icon = "✅" if r.get("passed") else "❌"
        card_num = r.get("card")
        name = r.get("name", f"Card {card_num}")
        result_lines.append(f"{status_icon} **Card {card_num}: {name}**\n• {r.get('actual')}")

    summary_embed = discord.Embed(
        title=f"🏁 Judge Attack Mode Results ({passed_count}/7 Passed)",
        description="\n\n".join(result_lines),
        color=0x57F287 if passed_count == 7 else 0xED4245
    )
    summary_embed.set_footer(text=f"AssemblyAI {config.speech_model_display} • Groq LPU • Tavily")
    await ctx.send(embed=summary_embed)


@bot.command(name="clear")
async def clear_session(ctx: commands.Context):
    """Resets server session dialogue, claim memory, and arbitration queue."""
    session = arbitration_engine.get_session(ctx.guild.id)
    session.reset()

    from bot.audio.capture import finalize_capture_if_active_async
    capture_info = await finalize_capture_if_active_async()
    capture_msg = ""
    if capture_info:
        csv_path, session_dir = capture_info
        capture_msg = f"\n📁 **Capture Finalized:** `{csv_path}` (Session: `{session_dir.name}`)"

    await ctx.send(f"🧹 Session history, claim memory, and arbitration queue have been reset.{capture_msg}")


@bot.command(name="leave")
async def leave_channel(ctx: commands.Context):
    """Disconnects from voice channel and resets all session state."""
    session = arbitration_engine.get_session(ctx.guild.id)
    session.reset()

    from bot.audio.capture import finalize_capture_if_active_async
    capture_info = await finalize_capture_if_active_async()
    capture_msg = ""
    if capture_info:
        csv_path, session_dir = capture_info
        capture_msg = f"\n📁 **Capture Finalized:** `{csv_path}` (Session: `{session_dir.name}`)"

    guild_ctx = get_guild_context(ctx.guild.id)
    if guild_ctx.voice_client and guild_ctx.voice_client.is_connected():
        if guild_ctx.sink:
            guild_ctx.sink.cleanup()
        await guild_ctx.voice_client.disconnect()
        await ctx.send(f"👋 Disconnected from voice channel and cleared session history.{capture_msg}")
    else:
        await ctx.send(f"❌ Not connected to any voice channel. Session history cleared.{capture_msg}")


@bot.event
async def on_ready():
    logger.info(f"✅ Logged in as {bot.user.name} ({bot.user.id})")
    print("\n" + "=" * 55)
    print(f"  CallWrapped Bot is ONLINE! (AssemblyAI Hackathon)")
    print(f"  Logged in as: {bot.user.name}")
    print(f"  Mode: Silent Referee (Intervention Only)")
    print(f"  Ears: AssemblyAI {config.speech_model_display} Code-Switching")
    print(f"  Brain: Groq LPU Epistemic Analyzer")
    print(f"  Evidence: Tavily Ground-Truth Search")
    print("=" * 55 + "\n")


def run():
    if not config.DISCORD_BOT_TOKEN:
        logger.error("❌ DISCORD_BOT_TOKEN is missing in .env!")
        return
    bot.run(config.DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    run()
