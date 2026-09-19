import os
import sys
import time
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

import httpx
import discord
from discord.ext import commands, voice_recv

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bot.config import config
from bot.audio.dave_patch import apply_dave_patch
from bot.audio.sink import MultiUserAudioSink
from bot.ai.stt import transcriber
from bot.ai.tts import voice_speaker
from bot.arbitration.detector import dispute_detector
from bot.arbitration.verifier import fact_verifier

# Apply DAVE E2EE protocol patch immediately
apply_dave_patch()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("DiscordVoiceBot")

# Bot Setup
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix=config.COMMAND_PREFIX, intents=intents)


class GuildCallState:
    """Manages active call state, mode, speaker stats, and dialogue turns per server."""

    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        self.voice_client: Optional[voice_recv.VoiceRecvClient] = None
        self.text_channel: Optional[discord.TextChannel] = None
        self.sink: Optional[MultiUserAudioSink] = None
        self.turns: List[Dict[str, Any]] = []
        self.dispute_count: int = 0
        self.speaker_stats: Dict[str, Dict[str, int]] = {}  # {name: {"turns": X, "wins": Y, "losses": Z}}
        self.mode: str = "referee"  # Options: 'referee' (default), 'echo', 'assistant'
        self.is_arbitrating: bool = False

    def record_speaker_turn(self, name: str):
        if name not in self.speaker_stats:
            self.speaker_stats[name] = {"turns": 0, "wins": 0, "losses": 0}
        self.speaker_stats[name]["turns"] += 1


guild_states: Dict[int, GuildCallState] = {}


def get_guild_state(guild_id: int) -> GuildCallState:
    if guild_id not in guild_states:
        guild_states[guild_id] = GuildCallState(guild_id)
    return guild_states[guild_id]


async def sync_to_web_dashboard(endpoint: str, payload: dict):
    """Broadcasts call events to the FastAPI backend so Next.js Frontend updates in real time."""
    if not config.BACKEND_API_URL:
        return
    try:
        url = f"{config.BACKEND_API_URL.rstrip('/')}/api/{endpoint.lstrip('/')}"
        async with httpx.AsyncClient(timeout=1.5) as client:
            await client.post(url, json=payload)
    except Exception:
        pass  # Dashboard is optional in local testing


async def on_user_speech_finished(guild_id: int, user_id: int, user_name: str, wav_bytes: bytes):
    """
    Asynchronous per-user speech callback.
    1. Transcribes with AssemblyAI Universal-3.5 Pro + Groq dialect corrector.
    2. Broadcasts to text channel and live Web Dashboard.
    3. Handles current bot mode:
       - 'echo': repeats verbally for testing.
       - 'referee': checks for factual disputes, speaks verified verdict with citations.
       - 'assistant': responds to direct queries.
    """
    state = get_guild_state(guild_id)
    if not state.voice_client or not state.voice_client.is_connected():
        return

    # 1. Transcribe speech
    text = await transcriber.transcribe_wav(wav_bytes)
    if not text or len(text.strip()) < 2:
        return

    state.record_speaker_turn(user_name)
    logger.info(f"🗣️ [{state.mode.upper()}] {user_name}: {text}")

    # 2. Output to text channel
    if state.text_channel:
        try:
            await state.text_channel.send(f"🗣️ **{user_name}**: {text}")
        except Exception as e:
            logger.debug(f"Could not send to text channel: {e}")

    # 3. Add to sliding dialogue history
    current_turn = {
        "speaker_id": str(user_id),
        "speaker_name": user_name,
        "text": text,
        "time": time.time()
    }
    state.turns.append(current_turn)
    if len(state.turns) > 20:
        state.turns.pop(0)

    # 4. Sync live turn to Web Dashboard
    asyncio.create_task(sync_to_web_dashboard("turns", {
        "speaker_name": user_name,
        "text": text,
        "timestamp": time.time()
    }))

    # 5. Handle Bot Mode
    if state.mode == "echo":
        # Testing mode: repeats user speech
        asyncio.create_task(voice_speaker.speak(
            state.voice_client,
            f"{user_name} بيقول: {text}"
        ))
        return

    elif state.mode == "referee":
        # Referee mode: check for disputes with recent opposing turn
        if state.is_arbitrating:
            return

        opposing_turn = None
        for turn in reversed(state.turns[:-1]):
            if turn["speaker_id"] != str(user_id):
                if time.time() - turn["time"] <= 60:
                    opposing_turn = turn
                    break

        if opposing_turn:
            asyncio.create_task(process_potential_dispute(state, opposing_turn, current_turn))


async def process_potential_dispute(state: GuildCallState, turn_a: Dict[str, Any], turn_b: Dict[str, Any]):
    """Analyzes opposing turns, queries web evidence, and speaks the verdict."""
    state.is_arbitrating = True
    try:
        speaker_a = turn_a["speaker_name"]
        claim_a = turn_a["text"]
        speaker_b = turn_b["speaker_name"]
        claim_b = turn_b["text"]

        # Step 1: Detect epistemic dispute via Groq LPU
        eval_result = await dispute_detector.check_dispute(speaker_a, claim_a, speaker_b, claim_b)
        if not eval_result or not eval_result.get("is_verifiable_dispute"):
            return

        search_query = eval_result.get("search_query")
        logger.info(f"⚖️ [Referee Intervening] Disputed query: '{search_query}'")

        # Step 2: Ground-truth web verification
        verdict = await fact_verifier.verify_and_arbitrate(speaker_a, claim_a, speaker_b, claim_b, search_query)
        if not verdict or verdict.get("status") != "supported":
            return

        factual_truth = verdict.get("factual_truth", "")
        correct_speaker = verdict.get("correct_speaker")
        confidence = verdict.get("confidence", 95)
        sources = verdict.get("sources", [])

        if correct_speaker == "speaker_a":
            winner, loser = speaker_a, speaker_b
        elif correct_speaker == "speaker_b":
            winner, loser = speaker_b, speaker_a
        else:
            winner, loser = None, None

        if winner:
            state.speaker_stats[winner]["wins"] += 1
        if loser:
            state.speaker_stats[loser]["losses"] += 1
        state.dispute_count += 1

        # Step 3: Natural Egyptian Arabic spoken intervention
        if winner and loser:
            spoken_text = f"يا {loser}، {factual_truth}، و{winner} كلامه صح."
        else:
            spoken_text = f"الحقيقة هي: {factual_truth}."

        # Step 4: Post Verdict Embed in Discord
        if state.text_channel:
            source_link = sources[0].get("url", "") if sources else ""
            source_title = sources[0].get("title", "المصدر الرسمي") if sources else ""

            embed = discord.Embed(
                title="🏆 الحكم الفاصل والنتيجة الموثقة",
                description=f"📢 **{factual_truth}**\n\n"
                            + (f"✅ **الفائز بالمعلومة الصح**: `{winner}`\n" if winner else "")
                            + f"🎯 **نسبة التأكد**: `{confidence}%`\n"
                            + (f"🔗 **المصدر**: [{source_title}]({source_link})" if source_link else ""),
                color=config.EMBED_COLOR_VERDICT
            )
            embed.set_footer(text="تم التحكيم الصوتي الحي بواسطة الطرف الثالث • AssemblyAI")
            await state.text_channel.send(embed=embed)

        # Step 5: Sync dispute to Web Dashboard
        asyncio.create_task(sync_to_web_dashboard("disputes", {
            "speaker_a": speaker_a,
            "claim_a": claim_a,
            "speaker_b": speaker_b,
            "claim_b": claim_b,
            "truth": factual_truth,
            "winner": winner,
            "confidence": confidence,
            "sources": sources
        }))

        # Step 6: Speak into Discord call
        await voice_speaker.speak(state.voice_client, spoken_text)

    except Exception as e:
        logger.error(f"[Dispute Processing Error] {e}", exc_info=True)
    finally:
        state.is_arbitrating = False


# =============================================================================
# Discord Commands
# =============================================================================

@bot.command(name="join")
async def join_channel(ctx: commands.Context):
    """Joins the user's current voice channel."""
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("❌ لازم تكون في روم صوتي الأول عشان أنضم لك!")
        return

    voice_channel = ctx.author.voice.channel
    state = get_guild_state(ctx.guild.id)
    state.text_channel = ctx.channel

    try:
        if state.voice_client and state.voice_client.is_connected():
            await state.voice_client.move_to(voice_channel)
        else:
            state.voice_client = await voice_channel.connect(cls=voice_recv.VoiceRecvClient)

        def make_utterance_handler(g_id: int):
            async def handler(u_id: int, u_name: str, wav_bytes: bytes):
                await on_user_speech_finished(g_id, u_id, u_name, wav_bytes)
            return handler

        sink = MultiUserAudioSink(
            loop=bot.loop,
            on_utterance=make_utterance_handler(ctx.guild.id),
            voice_client=state.voice_client
        )
        state.sink = sink
        state.voice_client.listen(sink)

        embed = discord.Embed(
            title="🎙️ الطرف الثالث (الحكم الصوتي الذكي) انضم للروم!",
            description=(
                f"أهلاً بكم في **{voice_channel.name}**!\n\n"
                f"🛡️ **الوضع الحالي:** `{state.mode.upper()}`\n"
                "• `!mode referee`: وضع الحكم (يستمع في صمت ويفصل الخلافات فقط).\n"
                "• `!mode echo`: وضع الاختبار (يكرر الكلام لفحص المايك).\n"
                "• `!stats`: عرض لوحة شرف الفائزين بالمعلومات الصح.\n"
                "• `!dashboard`: فتح لوحة المتابعة الحية على الويب.\n"
                "• `!leave`: مغادرة الروم الصوتي."
            ),
            color=config.EMBED_COLOR_INFO
        )
        embed.set_footer(text="Powered by AssemblyAI Universal-3.5 Pro & Groq LPU")
        await ctx.send(embed=embed)

    except Exception as e:
        logger.error(f"Join error: {e}", exc_info=True)
        await ctx.send(f"❌ حدث خطأ أثناء الاتصال: {e}")


@bot.command(name="mode")
async def set_mode(ctx: commands.Context, mode_name: str):
    """Switches bot mode: '!mode referee', '!mode echo', or '!mode assistant'."""
    mode_name = mode_name.lower().strip()
    if mode_name not in ("referee", "echo", "assistant"):
        await ctx.send("❌ الأوضاع المتاحة: `!mode referee` أو `!mode echo` أو `!mode assistant`")
        return

    state = get_guild_state(ctx.guild.id)
    state.mode = mode_name
    descriptions = {
        "referee": "🛡️ **وضع الحكم (الافتراضي):** هستمع في صمت، ومش هتدخل إلا لو اختلفتوا في معلومة واقعية!",
        "echo": "🎙️ **وضع التجربة:** هكرر كل كلامكم في الروم الصوتي للتأكد من المايك وجودة التفريغ.",
        "assistant": "🤖 **وضع المساعد:** هجاوبكم لما تسألوني مباشرة."
    }
    await ctx.send(f"✅ تم تفعيل: {descriptions[mode_name]}")


@bot.command(name="stats")
async def show_stats(ctx: commands.Context):
    """Displays server dispute scoreboard and speaker stats."""
    state = get_guild_state(ctx.guild.id)
    if not state.speaker_stats:
        await ctx.send("📊 لسه مفيش إحصائيات للمكالمة الحالية. اتكلموا في الروم الأول!")
        return

    embed = discord.Embed(
        title="📊 لوحة إحصائيات الحوار والتحكيم",
        description=f"⚔️ **إجمالي الخلافات المحسومة:** `{state.dispute_count}`",
        color=config.EMBED_COLOR_INFO
    )
    for name, s in state.speaker_stats.items():
        embed.add_field(
            name=f"👤 {name}",
            value=f"• جمل منطوقة: `{s['turns']}`\n• إجابات صح: `✅ {s['wins']}`\n• هبدات مكذوبة: `❌ {s['losses']}`",
            inline=True
        )
    await ctx.send(embed=embed)


@bot.command(name="dashboard")
async def show_dashboard(ctx: commands.Context):
    """Sends the link to the live Web Dashboard."""
    embed = discord.Embed(
        title="🌐 لوحة المتابعة الحية (Web Dashboard)",
        description=(
            f"يمكنك متابعة تفريغ المكالمة لحظياً، ومصادر التحكيم، والإحصائيات عبر الرابط:\n\n"
            f"🔗 **[فتح لوحة التحكم]({config.BACKEND_API_URL})**"
        ),
        color=config.EMBED_COLOR_INFO
    )
    await ctx.send(embed=embed)


@bot.command(name="leave")
async def leave_channel(ctx: commands.Context):
    """Disconnects bot from voice channel."""
    state = get_guild_state(ctx.guild.id)
    if state.voice_client and state.voice_client.is_connected():
        if state.sink:
            state.sink.cleanup()
        await state.voice_client.disconnect()
        await ctx.send("👋 خرجت من الروم الصوتي. مع السلامة!")
    else:
        await ctx.send("❌ أنا مش متصل بأي روم صوتي حالياً.")


@bot.event
async def on_ready():
    logger.info(f"✅ Logged in as {bot.user.name} ({bot.user.id})")
    logger.info(f"Prefix: {config.COMMAND_PREFIX}")
    print("\n" + "=" * 50)
    print(f"  AI Third Participant Discord Bot is ONLINE!")
    print(f"  Logged in as: {bot.user.name}")
    print(f"  AssemblyAI Universal-3.5 Pro + Groq LPU Ready")
    print("=" * 50 + "\n")


def run():
    if not config.DISCORD_BOT_TOKEN:
        logger.error("❌ DISCORD_BOT_TOKEN is missing in .env!")
        return
    bot.run(config.DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    run()
