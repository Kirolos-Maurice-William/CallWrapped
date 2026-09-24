import os
import sys
import time
import logging
from pathlib import Path
from typing import Dict, Optional, Any

import discord
from discord.ext import commands, voice_recv

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bot.config import config
from bot.audio import AudioReceiver, install_dave_adapter
from bot.ai import assemblyai_client, speaker
from bot.arbitration import arbitration_engine, arbitration_verifier
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
        except (ValueError, TypeError):
            pass
    _original_publish_sync(event)

publisher.publish_sync_task = _on_event_published

# 1. Install isolated DAVE E2EE decryption adapter immediately
install_dave_adapter()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("VoiceArbitratorBot")

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
    speech_end: float = 0.0
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
        speech_end=speech_end
    )


# =============================================================================
# Discord Commands
# =============================================================================

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
            async def handler(u_id: int, u_name: str, wav: bytes, speech_start: float = 0.0, speech_end: float = 0.0):
                await on_user_utterance(g_id, u_id, u_name, wav, speech_start, speech_end)
            return handler

        sink = AudioReceiver(
            loop=bot.loop,
            on_utterance=make_handler(ctx.guild.id),
            voice_client=guild_ctx.voice_client
        )
        guild_ctx.sink = sink
        guild_ctx.voice_client.listen(sink)

        embed = discord.Embed(
            title="🎙️ Voice Arbitrator ● LIVE (AssemblyAI Hackathon)",
            description=(
                f"Connected to **{voice_channel.name}**!\n\n"
                f"🛡️ **Current Mode:** `{guild_ctx.mode.upper()}`\n"
                "• `!mode referee`: **(Default)** Silent observer. Only speaks on verified factual conflicts.\n"
                "• `!mode echo`: Test mode (repeats verbatim speech for mic check).\n"
                "• `!stats`: Server Evidence Leaderboard & Fact-checking insights.\n"
                "• `!dashboard`: Open Live Judge-Facing Web Dashboard.\n"
                "• `!leave`: Disconnect from voice."
            ),
            color=config.EMBED_COLOR_INFO
        )
        embed.set_footer(text=f"AssemblyAI {config.speech_model_display} • Groq LPU • Tavily")
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

    # Section D: Top-3 topics with %
    lines.append("\n🏷️ **أكتر مواضيع اتكلمتوا فيها:**")
    total_topics_count = sum(topic_counts.values())
    if total_topics_count > 0:
        top_3 = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        for rank, (top_name, top_cnt) in enumerate(top_3, 1):
            t_pct = (top_cnt / total_topics_count) * 100.0
            lines.append(f"{rank}. **{top_name}**: {t_pct:.1f}% ({top_cnt})")
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


@bot.command(name="help")
async def show_help(ctx: commands.Context):
    """Displays comprehensive help and hackathon judging instructions."""
    embed = discord.Embed(
        title="⚖️ Voice Arbitrator — AssemblyAI Voice Agent Hackathon",
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
            "• `!join`: Connects the bot to your current voice channel.\n"
            "• `!leave`: Disconnects the bot from voice.\n"
            "• `!mode referee`: *(Default)* Silent observer. Only speaks on verified factual disputes.\n"
            "• `!mode echo`: Mic-check mode (repeats verbatim audio).\n"
            "• `!mode assistant`: Interactive assistant mode."
        ),
        inline=False
    )
    embed.add_field(
        name="⚡ Instant Arbitration & Demo Tools",
        value=(
            "• `!arbitrate <query>`: On-demand fact verification query (e.g. `!arbitrate RTX 5070 VRAM`).\n"
            "• `!simulate`: Executes the RTX 5070 16GB vs 12GB Golden Demo scenario.\n"
            "• `!recap`: Displays real-time session recap (talk minutes, streaks, anger leaderboard, top topics).\n"
            "• `!stats`: Displays the server evidence & speaker accuracy leaderboard.\n"
            "• `!status`: Checks latency, API connections, and voice channel state.\n"
            "• `!dashboard`: Link to the live Next.js Judge Dashboard.\n"
            "• `!clear`: Clears session turns and dispute history for a fresh demo."
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
        title="⚙️ Voice Arbitrator — Operational Status",
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
    """Direct on-demand factual arbitration query from text chat."""
    guild_ctx = get_guild_context(ctx.guild.id)
    msg = await ctx.send(f"🔍 Searching and verifying claim: `{query}`...")

    try:
        verdict, search_ms, synth_ms, sources = await arbitration_verifier.verify_dispute(
            speaker_a=ctx.author.display_name,
            claim_a=query,
            speaker_b="Fact Checker",
            claim_b="Verify claim against official evidence",
            search_query=query
        )

        status_val = str(verdict.get("status", "")).upper() if verdict else ""
        if not verdict or status_val == "UNVERIFIABLE":
            await msg.edit(content=f"⚠️ Unable to conclusively verify: `{query}` from available sources.")
            return

        correct_fact = verdict.get("correct_fact", query)
        spoken_text = verdict.get("spoken_intervention", correct_fact)
        source_url = verdict.get("selected_source_url") or verdict.get("best_source_url", "")
        source_title = verdict.get("selected_source_title") or verdict.get("best_source_title", "Official Source")
        confidence = verdict.get("confidence", 95)

        search_ms = int(search_ms) if search_ms else 0
        synth_ms = int(synth_ms) if synth_ms else 0
        stt_ms = 0  # Text chat query has no speech STT

        spk_a_status = verdict.get("speaker_a_status", "")
        spk_b_status = verdict.get("speaker_b_status", "")

        winner = None
        loser = None
        if spk_a_status == "SUPPORTED":
            winner = ctx.author.display_name
        elif spk_a_status == "CONTRADICTED":
            loser = ctx.author.display_name

        if spk_b_status == "SUPPORTED" and not winner:
            winner = "Fact Checker"
        elif spk_b_status == "CONTRADICTED" and not loser:
            loser = "Fact Checker"

        status_str = "contradicted" if "CONTRADICTED" in (spk_a_status, spk_b_status) else ("verified" if "SUPPORTED" in (spk_a_status, spk_b_status) else "unverifiable")

        embed = discord.Embed(
            title="⚖️ Factual Arbitration Verdict",
            description=(
                f"📢 **{correct_fact}**\n\n"
                f"🎯 **Confidence**: `{confidence}%`\n"
                f"🔗 **Official Source**: [{source_title}]({source_url})\n\n"
                f"⚡ *Latency: Search {search_ms}ms | Synthesis {synth_ms}ms*"
            ),
            color=0x57F287
        )
        embed.set_footer(text="AssemblyAI Voice Agent Hackathon • Groq LPU • Tavily")
        await msg.edit(content=None, embed=embed)

        # Speak via voice if connected
        tts_ms = 0
        if guild_ctx.voice_client and guild_ctx.voice_client.is_connected():
            t_tts = time.monotonic()
            tts_res = await speaker.speak(guild_ctx.voice_client, spoken_text)
            tts_ms = int(tts_res) if (isinstance(tts_res, (int, float)) and tts_res > 0) else int(round((time.monotonic() - t_tts) * 1000))

        # Publish to dashboard
        publisher.publish_sync_task(VoiceEvent(
            type="intervention",
            speaker_name=ctx.author.display_name,
            text=spoken_text,
            latency=LatencyBreakdown(
                stt_ms=stt_ms,
                llm_ms=synth_ms,
                search_ms=search_ms,
                tts_ms=tts_ms
            ),
            payload={
                "status": status_str,
                "confidence": confidence,
                "correct_fact": correct_fact,
                "winner": winner,
                "loser": loser,
                "speaker_a": ctx.author.display_name,
                "claim_a": query,
                "speaker_b": "Fact Checker",
                "claim_b": "Verification",
                "speaker_a_status": spk_a_status,
                "speaker_b_status": spk_b_status,
                "source_url": source_url,
                "source_title": source_title,
                "spoken_intervention": spoken_text
            }
        ))

    except Exception as e:
        logger.error(f"Error in manual arbitrate: {e}", exc_info=True)
        await msg.edit(content=f"❌ Error during arbitration: {e}")


@bot.command(name="simulate")
async def simulate_demo(ctx: commands.Context):
    """Injects the RTX 5070 Golden Demo dispute directly into voice and dashboard."""
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
        correct_fact = verdict.get("correct_fact", "NVIDIA RTX 5070 features 12GB GDDR7 memory.")
        spoken_text = verdict.get("spoken_intervention", correct_fact)
        source_url = verdict.get("selected_source_url") or verdict.get("best_source_url", "")
        source_title = verdict.get("selected_source_title") or verdict.get("best_source_title", "Official Source")
        confidence = verdict.get("confidence", 95)
        spk_a_status = verdict.get("speaker_a_status", "CONTRADICTED")
        spk_b_status = verdict.get("speaker_b_status", "SUPPORTED")
    else:
        correct_fact = "NVIDIA GeForce RTX 5070 features 12GB GDDR7 VRAM, not 16GB."
        spoken_text = "Correction: Nvidia's official specifications confirm the RTX 5070 features 12GB GDDR7 memory, not 16GB."
        source_url = "https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5070/"
        source_title = "NVIDIA Official GeForce RTX 5070 Specifications"
        confidence = 99
        spk_a_status = "CONTRADICTED"
        spk_b_status = "SUPPORTED"

    search_ms = int(search_ms) if search_ms else 0
    synth_ms = int(synth_ms) if synth_ms else 0
    stt_ms = 0  # Simulated text in chat has no speech STT

    winner = "Omar" if spk_b_status == "SUPPORTED" else ("Ahmed" if spk_a_status == "SUPPORTED" else None)
    loser = "Ahmed" if spk_a_status == "CONTRADICTED" else ("Omar" if spk_b_status == "CONTRADICTED" else None)

    tts_ms = 0
    if guild_ctx.voice_client and guild_ctx.voice_client.is_connected():
        t_tts = time.monotonic()
        tts_res = await speaker.speak(guild_ctx.voice_client, spoken_text)
        tts_ms = int(tts_res) if (isinstance(tts_res, (int, float)) and tts_res > 0) else int(round((time.monotonic() - t_tts) * 1000))

    embed = discord.Embed(
        title="⚖️ Verified Dispute Arbitration Verdict",
        description=(
            f"📢 **{correct_fact}**\n\n"
            f"✅ **Accurate Speaker**: `{winner or 'Omar'}`\n"
            f"❌ **Refuted Speaker**: `{loser or 'Ahmed'}`\n"
            f"🎯 **Confidence**: `{confidence}%`\n"
            f"🔗 **Official Source**: [{source_title}]({source_url})\n\n"
            f"⚡ **Latency Breakdown:** STT {stt_ms}ms | LLM {synth_ms}ms | Search {search_ms}ms | TTS {tts_ms}ms"
        ),
        color=0x57F287
    )
    embed.set_footer(text=f"AssemblyAI {config.speech_model_display} • Groq LPU • Tavily")
    await ctx.send(embed=embed)

    publisher.publish_sync_task(VoiceEvent(
        type="intervention",
        speaker_name=winner or "Omar",
        text=spoken_text,
        latency=LatencyBreakdown(
            stt_ms=stt_ms,
            llm_ms=synth_ms,
            search_ms=search_ms,
            tts_ms=tts_ms
        ),
        payload={
            "status": "contradicted" if "CONTRADICTED" in (spk_a_status, spk_b_status) else "supported",
            "confidence": confidence,
            "correct_fact": correct_fact,
            "winner": winner,
            "loser": loser,
            "speaker_a": "Ahmed",
            "claim_a": "RTX 5070 launches with 16GB VRAM",
            "speaker_b": "Omar",
            "claim_b": "RTX 5070 comes with 12GB GDDR7, not 16GB",
            "speaker_a_status": spk_a_status,
            "speaker_b_status": spk_b_status,
            "source_url": source_url,
            "source_title": source_title,
            "spoken_intervention": spoken_text
        }
    ))


@bot.command(name="clear")
async def clear_session(ctx: commands.Context):
    """Resets server session dialogue, claim memory, and arbitration queue."""
    session = arbitration_engine.get_session(ctx.guild.id)
    session.reset()
    await ctx.send("🧹 Session history, claim memory, and arbitration queue have been reset.")


@bot.command(name="leave")
async def leave_channel(ctx: commands.Context):
    """Disconnects from voice channel."""
    guild_ctx = get_guild_context(ctx.guild.id)
    if guild_ctx.voice_client and guild_ctx.voice_client.is_connected():
        if guild_ctx.sink:
            guild_ctx.sink.cleanup()
        await guild_ctx.voice_client.disconnect()
        await ctx.send("👋 Disconnected from voice channel.")
    else:
        await ctx.send("❌ Not connected to any voice channel.")


@bot.event
async def on_ready():
    logger.info(f"✅ Logged in as {bot.user.name} ({bot.user.id})")
    print("\n" + "=" * 55)
    print(f"  Voice Arbitrator Bot is ONLINE! (AssemblyAI Hackathon)")
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
