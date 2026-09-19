import os
import sys
import time
import asyncio
import logging
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional

import discord
from discord.ext import commands, voice_recv

# Ensure project root is in sys.path so app.services can be imported
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
backend_path = PROJECT_ROOT / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from discord_bot.config import config
from discord_bot.transcriber import transcriber
from discord_bot.audio_sink import MultiUserAudioSink
from discord_bot.dave_patch import apply_dave_patch
from app.services.groq_service import GroqService
from app.services.fact_checker_service import FactCheckerService
import edge_tts

# Apply DAVE E2EE decryption patch
apply_dave_patch()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("DiscordVoiceBot")

# Initialize Discord Bot
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix=config.COMMAND_PREFIX, intents=intents)

# Active intelligence services
groq_service = GroqService()
fact_checker = FactCheckerService()

class GuildCallState:
    """Manages call state, active voice client, and dialogue history per server."""
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        self.voice_client: Optional[voice_recv.VoiceRecvClient] = None
        self.text_channel: Optional[discord.TextChannel] = None
        self.sink: Optional[MultiUserAudioSink] = None
        self.turns: List[Dict[str, Any]] = []
        self.dispute_count: int = 0
        self.recognized_speakers: set = set()
        self.is_arbitrating = False

# Active guild states
guild_states: Dict[int, GuildCallState] = {}

def get_guild_state(guild_id: int) -> GuildCallState:
    if guild_id not in guild_states:
        guild_states[guild_id] = GuildCallState(guild_id)
    return guild_states[guild_id]


async def speak_text_in_voice(state: GuildCallState, text_to_speak: str):
    """Synthesizes text with Microsoft Edge-TTS (Salma) and speaks it into the Discord voice channel."""
    if not state.voice_client or not state.voice_client.is_connected():
        return
    try:
        temp_dir = Path(tempfile.gettempdir())
        temp_audio = temp_dir / f"tts_repeat_{int(time.time()*1000)}.mp3"
        communicate = edge_tts.Communicate(text_to_speak, config.TTS_VOICE)
        await communicate.save(str(temp_audio))

        # Wait if bot is already speaking
        for _ in range(40):
            if not state.voice_client.is_playing():
                break
            await asyncio.sleep(0.1)

        def after_play(error):
            if error:
                logger.error(f"Error playing voice repeat: {error}")
            try:
                if temp_audio.exists():
                    temp_audio.unlink()
            except Exception:
                pass

        audio_source = discord.FFmpegPCMAudio(str(temp_audio))
        state.voice_client.play(audio_source, after=after_play)
        logger.info(f"🔊 [Voice Echo] Spoke in call: '{text_to_speak}'")
    except Exception as e:
        logger.error(f"Failed to speak in voice: {e}")


async def on_user_speech_finished(guild_id: int, user_id: int, user_name: str, wav_bytes: bytes):
    """
    Called whenever a user finishes an utterance in the Discord voice channel.
    1. Transcribes speech with Groq Whisper Large v3 Turbo.
    2. Identifies the speaker by name.
    3. Analyzes dialogue for multi-party factual disputes.
    4. Speaks verified verdict into Discord voice channel via Salma TTS.
    """
    state = get_guild_state(guild_id)
    if not state.voice_client or not state.voice_client.is_connected():
        return

    logger.info(f"🎙️ [Audio Received] Processing {len(wav_bytes)} bytes for {user_name}...")
    # 1. Transcribe speech
    text = await transcriber.transcribe_wav(wav_bytes)
    if not text or len(text.strip()) < 2:
        logger.info(f"⚠️ [STT Ignored] No clear speech returned for {user_name}.")
        return

    from discord_bot.transcriber import is_hallucination
    if is_hallucination(text):
        logger.info(f"🛡️ [Suppressed Hallucination] Ignored: '{text}'")
        return

    state.recognized_speakers.add(user_name)
    logger.info(f"🗣️ [Recognized Speech] {user_name}: {text}")

    # 2. Output to text channel
    if state.text_channel:
        try:
            await state.text_channel.send(f"🗣️ **{user_name}**: {text}")
        except Exception as e:
            logger.warning(f"Could not send speech to text channel: {e}")

    # 3. Test Echo Mode: Repeat what the user said verbally into the call so they can verify!
    asyncio.create_task(
        speak_text_in_voice(state, f"أنت قولت: {text}")
    )

    # 4. Add to sliding dialogue history
    current_turn = {
        "speaker_id": str(user_id),
        "speaker_name": user_name,
        "text": text,
        "time": time.time()
    }
    state.turns.append(current_turn)

    # Keep last 15 turns
    if len(state.turns) > 15:
        state.turns.pop(0)

    # 4. Check for dispute with other participants
    if state.is_arbitrating:
        return

    # Look for the most recent opposing turn from a DIFFERENT user
    opposing_turn = None
    for turn in reversed(state.turns[:-1]):
        if turn["speaker_id"] != str(user_id):
            # Only consider turns within the last 50 seconds
            if time.time() - turn["time"] <= 50:
                opposing_turn = turn
                break

    if not opposing_turn:
        return

    # 5. Classify dispute using Groq LPU Gatekeeper
    asyncio.create_task(
        process_potential_dispute(state, opposing_turn, current_turn)
    )


async def process_potential_dispute(
    state: GuildCallState,
    turn_a: Dict[str, Any],
    turn_b: Dict[str, Any]
):
    """Evaluates if two statements form a verifiable dispute and arbitrates with voice playback."""
    state.is_arbitrating = True
    try:
        speaker_a = turn_a["speaker_name"]
        claim_a = turn_a["text"]
        speaker_b = turn_b["speaker_name"]
        claim_b = turn_b["text"]

        dispute = await groq_service.classify_epistemic_dispute(
            speaker_a, claim_a, speaker_b, claim_b
        )

        if not dispute or not dispute.get("is_verifiable_dispute"):
            return

        search_query = dispute.get("search_query") or f"{claim_a} {claim_b}"
        summary = dispute.get("dispute_summary", "خلاف حول معلومة واقعية")
        logger.info(f"[Dispute Detected] ({speaker_a} vs {speaker_b}): {summary} -> Search: {search_query}")

        # Send alert embed to Discord text channel
        if state.text_channel:
            embed_alert = discord.Embed(
                title="⚖️ رصد خلاف واقعي بين المتحدثين",
                description=f"**{speaker_a}**: {claim_a}\n**{speaker_b}**: {claim_b}\n\n🔍 **موضوع البحث**: `{search_query}`",
                color=config.EMBED_COLOR_DISPUTE
            )
            embed_alert.set_footer(text="جاري التحقق من الأدلة الرسمية عبر محرك البحث...")
            await state.text_channel.send(embed=embed_alert)

        # 6. Fetch authoritative web evidence
        sources = await fact_checker._search_web_fast(search_query)
        if not sources:
            logger.warning("[Dispute] No search sources found.")
            return

        # 7. Grounded arbitration via Groq
        verdict = await groq_service.arbitrate_facts(claim_a, claim_b, sources)
        if not verdict or verdict.get("result") not in ["supported", "contradicted"]:
            return

        factual_truth = verdict.get("factual_truth", "")
        correct_speaker = verdict.get("correct_speaker", "neither")
        confidence = int(verdict.get("confidence", 0.9) * 100)

        # Determine winner name
        if correct_speaker == "speaker_a":
            winner = speaker_a
            loser = speaker_b
        elif correct_speaker == "speaker_b":
            winner = speaker_b
            loser = speaker_a
        else:
            winner = None
            loser = None

        state.dispute_count += 1

        # Formulate natural Egyptian Arabic spoken intervention
        if winner and loser:
            spoken_text = f"يا {loser}، {factual_truth}، و{winner} كلامه صح."
        else:
            spoken_text = f"الحقيقة هي: {factual_truth}."

        logger.info(f"[Verdict] {spoken_text}")

        # 8. Post Verdict Embed to Discord Text Channel
        if state.text_channel:
            source_link = sources[0].get("url", "") if sources else ""
            source_title = sources[0].get("title", "المصدر الرسمي") if sources else ""

            embed_verdict = discord.Embed(
                title="🏆 الحكم الفاصل والنتيجة الموثقة",
                description=f"📢 **{factual_truth}**\n\n" +
                            (f"✅ **الفائز بالمعلومة الصح**: `{winner}`\n" if winner else "") +
                            f"🎯 **نسبة التأكد**: `{confidence}%`\n" +
                            (f"🔗 **المصدر**: [{source_title}]({source_link})" if source_link else ""),
                color=config.EMBED_COLOR_VERDICT
            )
            embed_verdict.set_footer(text="تم التحكيم الصوتي الحي بواسطة الطرف الثالث")
            await state.text_channel.send(embed=embed_verdict)

        # 9. Synthesize Voice with Microsoft Edge-TTS (Salma)
        temp_dir = Path(tempfile.gettempdir())
        temp_audio = temp_dir / f"verdict_{int(time.time()*1000)}.mp3"
        communicate = edge_tts.Communicate(spoken_text, config.TTS_VOICE)
        await communicate.save(str(temp_audio))

        # 10. Play Audio directly into Discord Voice Channel
        if state.voice_client and state.voice_client.is_connected():
            while state.voice_client.is_playing():
                await asyncio.sleep(0.1)

            def after_play(error):
                if error:
                    logger.error(f"Error playing voice verdict: {error}")
                try:
                    if temp_audio.exists():
                        temp_audio.unlink()
                except Exception:
                    pass

            audio_source = discord.FFmpegPCMAudio(str(temp_audio))
            state.voice_client.play(audio_source, after=after_play)

    except Exception as e:
        logger.error(f"[Dispute Processing Error] {e}", exc_info=True)
    finally:
        state.is_arbitrating = False


# ==========================================
# Discord Commands
# ==========================================

@bot.event
async def on_ready():
    logger.info(f"✅ Logged in as {bot.user.name} ({bot.user.id})")
    logger.info(f"Prefix: {config.COMMAND_PREFIX}")
    print("\n" + "="*50)
    print(f"  AI Third Participant Discord Bot is ONLINE!")
    print(f"  Logged in as: {bot.user.name}")
    print(f"  Type '{config.COMMAND_PREFIX}join' in any channel to start!")
    print("="*50 + "\n")


@bot.command(name="join", aliases=["j", "انضم", "ادخل"])
async def cmd_join(ctx: commands.Context):
    """Joins the caller's voice channel and begins multi-user voice arbitration."""
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.reply("⚠️ لازم تكون داخل Voice Channel في السيرفر الأول عشان أقدر ادخل معاك!")
        return

    voice_channel = ctx.author.voice.channel
    state = get_guild_state(ctx.guild.id)
    state.text_channel = ctx.channel

    # Disconnect existing connection if in another channel
    if state.voice_client and state.voice_client.is_connected():
        if state.voice_client.channel.id != voice_channel.id:
            await state.voice_client.disconnect()
        else:
            await ctx.reply(f"🎙️ أنا موجود بالفعل في روم `{voice_channel.name}` وبستمع لكل المتحدثين!")
            return

    msg = await ctx.send(f"⏳ جاري الانضمام إلى `{voice_channel.name}` وتجهيز محرك الصوت DAVE...")

    try:
        # Connect using voice_recv.VoiceRecvClient for receiving individual user audio
        voice_client: voice_recv.VoiceRecvClient = await voice_channel.connect(
            cls=voice_recv.VoiceRecvClient
        )
        state.voice_client = voice_client

        # Create multi-user audio callback wrapper
        async def handle_utterance(user_id: int, user_name: str, wav_bytes: bytes):
            await on_user_speech_finished(ctx.guild.id, user_id, user_name, wav_bytes)

        # Attach MultiUserAudioSink with direct voice_client reference
        sink = MultiUserAudioSink(bot.loop, handle_utterance, voice_client)
        state.sink = sink
        voice_client.listen(sink)

        # Log members in channel
        humans = [m.display_name for m in voice_channel.members if not m.bot]
        logger.info(f"🎙️ [Connected] Joined '{voice_channel.name}' with members: {humans}")

        embed = discord.Embed(
            title="🎙️ الطرف الثالث (المحكم الذكي) انضم للروم!",
            description=(
                f"أهلاً بكم! أنا متصل الآن في قناة **`{voice_channel.name}`**.\n\n"
                "✨ **المميزات المفعلة**:\n"
                "• التعرف على أسماء كل المتحدثين تلقائياً.\n"
                "• دعم أي عدد من المتحدثين في الروم (أكثر من 2).\n"
                "• تفريغ صوتي فوري عبر **AssemblyAI** (مع دعم اللهجة المصرية والعربية).\n"
                "• التدخل والتحكيم الصوتي بصوت **سلمى** عند حدوث خلاف واقعي.\n\n"
                f"للمغادرة: اكتب `{config.COMMAND_PREFIX}leave`"
            ),
            color=config.EMBED_COLOR_INFO
        )
        embed.set_footer(text="تحدثوا بشكل طبيعي باللغة العربية أو الإنجليزية!")
        await msg.edit(content=None, embed=embed)

    except Exception as e:
        logger.error(f"Failed to connect to voice channel: {e}", exc_info=True)
        await msg.edit(content=f"❌ حدث خطأ أثناء الانضمام: `{e}`")


@bot.command(name="leave", aliases=["l", "اخرج", "مغادرة"])
async def cmd_leave(ctx: commands.Context):
    """Stops listening and disconnects from the voice channel."""
    state = get_guild_state(ctx.guild.id)
    if state.voice_client and state.voice_client.is_connected():
        if state.sink:
            state.sink.cleanup()
        await state.voice_client.disconnect()
        state.voice_client = None
        state.sink = None
        state.turns.clear()
        await ctx.reply("👋 تم الخروج من القناة الصوتية وحفظ الجلسة بنجاح.")
    else:
        await ctx.reply("⚠️ البوت غير متصل بأي قناة صوتية حالياً.")


@bot.command(name="status", aliases=["الحالة", "stats"])
async def cmd_status(ctx: commands.Context):
    """Displays active participants, call status, and recognized speakers."""
    state = get_guild_state(ctx.guild.id)
    is_connected = state.voice_client and state.voice_client.is_connected()
    channel_name = state.voice_client.channel.name if is_connected else "غير متصل"
    speakers_str = ", ".join(state.recognized_speakers) if state.recognized_speakers else "لا يوجد متحدثين حتى الآن"

    embed = discord.Embed(
        title="📊 حالة المساعد الذكي (الطرف الثالث)",
        color=config.EMBED_COLOR_INFO
    )
    embed.add_field(name="القناة الصوتية", value=f"`{channel_name}`", inline=True)
    embed.add_field(name="حالة الاتصال", value="🟢 نشط ومستمع" if is_connected else "🔴 غير متصل", inline=True)
    embed.add_field(name="عدد الخلافات المحكومة", value=f"`{state.dispute_count}`", inline=True)
    embed.add_field(name="المتحدثين المسجلين", value=f"`{speakers_str}`", inline=False)
    embed.add_field(name="الجمل الأخيرة المحفوظة", value=f"`{len(state.turns)} جملة`", inline=True)

    await ctx.reply(embed=embed)


@bot.command(name="clear", aliases=["مسح"])
async def cmd_clear(ctx: commands.Context):
    """Clears recent conversation history buffer."""
    state = get_guild_state(ctx.guild.id)
    state.turns.clear()
    await ctx.reply("🧹 تم مسح سجل المحادثة المؤقت بنجاح.")


def main():
    token = config.DISCORD_BOT_TOKEN
    if not token or token == "your_discord_bot_token_here":
        print("\n" + "!"*60)
        print(" [ERROR] DISCORD_BOT_TOKEN is missing!")
        print(" Please add your Discord Bot Token to backend/.env like this:")
        print(" DISCORD_BOT_TOKEN=MTE5OT...")
        print(" You can create a free bot token at:")
        print(" https://discord.com/developers/applications")
        print("!"*60 + "\n")
        sys.exit(1)

    bot.run(token)


if __name__ == "__main__":
    main()
