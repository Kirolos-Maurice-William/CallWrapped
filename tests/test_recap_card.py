"""
Acceptance Test Suite for Shareable Wrapped Recap Card Renderer and !card Command.
Tests:
a) Unit: RAQM check, Arabic shaping, emoji cleaning, Latin digit enforcement, and truncation
b) Unit: Synthetic payload rendering (2 speakers with Arabic names, 1 frustration receipt,
   mixed Arabic/English topics) -> PNG bytes > 10KB, dimensions 1080x1350, save audit/card_sample.png
c) Async: render_recap_card_async off-thread execution
d) Unit: build_card_payload_from_session (empty session -> None; populated -> RecapCardPayload)
e) Unit: !card command with empty session -> sends Arabic notice, no card generated
f) Unit: !card command with populated session -> attaches discord.File(filename="callwrapped_recap.png")
"""

import io
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import tests._setup

from PIL import Image

from bot.ui.recap_card_renderer import (
    RAQM_AVAILABLE,
    SpeakerStat,
    TopicStat,
    RecapCardPayload,
    shape_for_pillow,
    clean_emoji,
    ensure_latin_digits,
    truncate_text,
    draw_text,
    render_recap_card_png,
    render_recap_card_async,
    build_card_payload_from_session,
    CARD_WIDTH,
    CARD_HEIGHT,
)


class TestRecapCardRenderer(unittest.IsolatedAsyncioTestCase):

    def test_a_raqm_check_and_text_helpers(self):
        """
        Test a:
        - RAQM runtime check presence
        - Arabic shaping decision tree
        - Latin digit normalization
        - Emoji stripping and replacement
        - Grapheme-aware text truncation
        """
        print("\n=== TEST A: RAQM CHECK & TEXT TRANSFORMATION HELPERS ===")
        print(f"  RAQM runtime available: {RAQM_AVAILABLE}")
        self.assertIsInstance(RAQM_AVAILABLE, bool)

        # Arabic text shaping
        sample_ar = "أحمد تامر"
        shaped = shape_for_pillow(sample_ar)
        self.assertTrue(len(shaped) > 0)
        print(f"  Arabic input: '{sample_ar}' -> Shaped: '{shaped}' (RAQM={RAQM_AVAILABLE})")

        # Latin digits everywhere
        indic_text = "الجلسة ١٢٣ بنسبة ٦٢.٥%"
        latin_text = ensure_latin_digits(indic_text)
        self.assertEqual(latin_text, "الجلسة 123 بنسبة 62.5%")
        print(f"  Digit normalization: '{indic_text}' -> '{latin_text}'")

        # Emoji cleaning
        emoji_input = "👑 أحمد: 1.5m 🔥 نوبة غضب 😡 (62.5%) 😂"
        cleaned = clean_emoji(emoji_input)
        self.assertNotIn("👑", cleaned)
        self.assertNotIn("🔥", cleaned)
        self.assertNotIn("😡", cleaned)
        self.assertNotIn("😂", cleaned)
        self.assertIn("[Top]", cleaned)
        print(f"  Emoji cleaning: '{emoji_input}' -> '{cleaned}'")

        # Grapheme-aware truncation
        long_quote = "مش معقول كده خالص يا جماعة التحكيم كان متحيز جدا للفرقة التانية في الماتش ده"
        truncated = truncate_text(long_quote, max_chars=25)
        self.assertTrue(truncated.endswith("…"))
        self.assertLessEqual(len(truncated), 26)
        print(f"  Truncation: '{long_quote[:35]}...' -> '{truncated}'")

        print("PASS")

    def test_b_synthetic_payload_render_and_sample_png(self):
        """
        Test b (Acceptance Requirement):
        - Synthetic payload: 2 speakers with Arabic names, 1 frustration receipt, mixed Arabic/English topics
        - PNG bytes returned, size > 10KB
        - Open with PIL to verify dimensions = 1080x1350
        - Save test PNG to audit/card_sample.png for inspection
        """
        print("\n=== TEST B: SYNTHETIC PAYLOAD RENDERING & DIMENSIONS ===")

        payload = RecapCardPayload(
            session_title="ملخص المكالمة • CallWrapped",
            period_label="جلسة الأحد 28 سبتمبر 2026",
            speaker_stats=[
                SpeakerStat(
                    name="أحمد تامر",
                    talk_seconds=240.0,
                    share_pct=62.5,
                    streak_seconds=45.0,
                    angry_episodes=1,
                    first_anger_quote="مش طبيعي كده خالص يا جماعة!"
                ),
                SpeakerStat(
                    name="كريم الشناوي",
                    talk_seconds=144.0,
                    share_pct=37.5,
                    streak_seconds=25.0,
                    angry_episodes=0,
                    first_anger_quote=None
                ),
            ],
            top_topics=[
                TopicStat(topic_key="football", display_name="كورة وقدم (Football)", pct=55.0),
                TopicStat(topic_key="tech", display_name="تقنية وتكنولوجيا (Tech)", pct=35.0),
                TopicStat(topic_key="gaming", display_name="ألعاب وجيمينج (Gaming)", pct=10.0),
            ],
            coverage_note="نسبة التغطية الموضوعية: 90.0% (مستبعد جمل بدون موضوع)"
        )

        # Render PNG
        png_bytes = render_recap_card_png(payload)
        byte_size = len(png_bytes)
        print(f"  [PROOF] Generated PNG bytes size: {byte_size} bytes ({byte_size / 1024:.1f} KB)")

        # Verify size > 10KB
        self.assertGreater(byte_size, 10 * 1024, f"PNG size must be > 10KB, got {byte_size} bytes")

        # Open with PIL and verify dimensions
        img = Image.open(io.BytesIO(png_bytes))
        width, height = img.size
        print(f"  [PROOF] Image Dimensions: {width} x {height} (Format: {img.format})")
        self.assertEqual(width, CARD_WIDTH, f"Expected width {CARD_WIDTH}, got {width}")
        self.assertEqual(height, CARD_HEIGHT, f"Expected height {CARD_HEIGHT}, got {height}")
        self.assertEqual(img.format, "PNG")

        # Save to audit/card_sample.png for user inspection
        audit_dir = Path(__file__).resolve().parent.parent / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        sample_path = audit_dir / "card_sample.png"
        sample_path.write_bytes(png_bytes)
        self.assertTrue(sample_path.exists())
        print(f"  [PROOF] Saved inspection sample to: {sample_path.resolve()}")

        print("PASS")

    async def test_c_async_renderer_off_thread(self):
        """
        Test c:
        - Asynchronous rendering via asyncio.to_thread
        - Verifies non-blocking generation off the event loop
        """
        print("\n=== TEST C: ASYNC OFF-THREAD RENDERING ===")

        payload = RecapCardPayload(
            session_title="Quick Voice Session",
            period_label="Live Call Recap",
            speaker_stats=[
                SpeakerStat(name="Mostafa", talk_seconds=60.0, share_pct=100.0, streak_seconds=30.0, angry_episodes=0),
            ],
            top_topics=[
                TopicStat(topic_key="tech", display_name="Technology", pct=100.0)
            ],
            coverage_note="100% topical coverage"
        )

        png_bytes = await render_recap_card_async(payload)
        self.assertIsInstance(png_bytes, bytes)
        self.assertGreater(len(png_bytes), 10 * 1024)

        img = Image.open(io.BytesIO(png_bytes))
        self.assertEqual(img.size, (1080, 1350))
        print(f"  [PROOF] Async render successful: {len(png_bytes)} bytes, size {img.size}")
        print("PASS")

    def test_d_build_payload_from_session(self):
        """
        Test d:
        - Empty session -> returns None
        - Populated session -> returns RecapCardPayload with properly formatted fields
        """
        print("\n=== TEST D: BUILD PAYLOAD FROM SESSION STATE ===")

        # 1. Empty session
        empty_session = MagicMock()
        empty_session.stats_tracker.speakers = {}
        empty_session.speakers = {}
        empty_session.total_speak_seconds = 0.0
        empty_session.turns = []
        payload_empty = build_card_payload_from_session(empty_session)
        self.assertIsNone(payload_empty, "Empty session must return None")
        print("  ✓ Empty session correctly returns None")

        # 2. Populated session
        mock_spk1 = MagicMock()
        mock_spk1.speaker_name = "أحمد"
        mock_spk1.total_speak_seconds = 180.0
        mock_spk1.utterance_count = 10
        mock_spk1.longest_streak_seconds = 40.0
        mock_spk1.angry_episodes = 1
        mock_spk1.first_anger_quote = "ده مش منطقي!"

        mock_spk2 = MagicMock()
        mock_spk2.speaker_name = "Tamer"
        mock_spk2.total_speak_seconds = 120.0
        mock_spk2.utterance_count = 6
        mock_spk2.longest_streak_seconds = 20.0
        mock_spk2.angry_episodes = 0
        mock_spk2.first_anger_quote = None

        pop_session = MagicMock()
        pop_session.stats_tracker.speakers = {"101": mock_spk1, "102": mock_spk2}
        pop_session.speakers = pop_session.stats_tracker.speakers
        pop_session.topic_counts = {"football": 8, "tech": 4, "null_topic": 2}

        payload = build_card_payload_from_session(pop_session, session_title="Test Call")
        self.assertIsNotNone(payload)
        self.assertEqual(payload.session_title, "Test Call")
        self.assertEqual(len(payload.speaker_stats), 2)
        self.assertEqual(payload.speaker_stats[0].name, "أحمد")
        self.assertAlmostEqual(payload.speaker_stats[0].share_pct, 60.0, places=1)
        self.assertEqual(payload.speaker_stats[1].name, "Tamer")
        self.assertAlmostEqual(payload.speaker_stats[1].share_pct, 40.0, places=1)
        self.assertEqual(len(payload.top_topics), 2)
        self.assertIn("التغطية الموضوعية", payload.coverage_note)
        print("  ✓ Populated session correctly produces RecapCardPayload")
        print("PASS")

    async def test_e_card_command_empty_session(self):
        """
        Test e:
        - !card command with empty session state
        - Replies with 'مفيش بيانات في المكالمة دي لسه.'
        - No file is attached or sent
        """
        print("\n=== TEST E: !CARD COMMAND (EMPTY SESSION) ===")

        from bot.main import card_command
        from bot.arbitration import arbitration_engine

        mock_ctx = AsyncMock()
        mock_ctx.guild.id = 888777666
        mock_ctx.guild.name = "Empty Discord Server"

        # Ensure session is completely clean and empty
        session = arbitration_engine.get_session(mock_ctx.guild.id)
        session.reset()

        await card_command(mock_ctx)

        mock_ctx.send.assert_called_once_with("مفيش بيانات في المكالمة دي لسه.")
        print("  ✓ Empty session replied with expected Arabic notice and 0 files sent")
        print("PASS")

    async def test_f_card_command_populated_session(self):
        """
        Test f:
        - !card command with populated session state
        - Generates PNG card and attaches discord.File(filename='callwrapped_recap.png')
        - Verifies attachment file size > 10KB and image format/dimensions
        """
        print("\n=== TEST F: !CARD COMMAND (POPULATED SESSION ATTACHMENT) ===")

        from bot.main import card_command
        from bot.arbitration import arbitration_engine

        mock_ctx = AsyncMock()
        mock_ctx.guild.id = 888777555
        mock_ctx.guild.name = "Hackathon Cairo Voice"

        session = arbitration_engine.get_session(mock_ctx.guild.id)
        session.reset()

        # Populate session with test speakers and topic data
        class DummySpeaker:
            def __init__(self, name, speak_sec, streak_sec, anger_count=0, anger_quote=None):
                self.speaker_name = name
                self.speaker_id = name
                self.total_speak_seconds = speak_sec
                self.utterance_count = 5
                self.longest_streak_seconds = streak_sec
                self.angry_episodes = anger_count
                self.first_anger_quote = anger_quote

        session.stats_tracker.speakers = {
            "s1": DummySpeaker("Tamer", 150.0, 35.0, 1, "مش معقول كده!"),
            "s2": DummySpeaker("Mostafa", 100.0, 20.0, 0)
        }
        session.speakers = session.stats_tracker.speakers
        session.topic_counts = {"tech": 6, "football": 4}

        await card_command(mock_ctx)

        # Assert ctx.send was called with file keyword argument
        self.assertTrue(mock_ctx.send.called)
        call_kwargs = mock_ctx.send.call_args.kwargs
        self.assertIn("file", call_kwargs, "ctx.send must receive file argument")

        file_attached = call_kwargs["file"]
        self.assertEqual(file_attached.filename, "callwrapped_recap.png")

        # Read attached bytes and verify image
        attached_bytes = file_attached.fp.getvalue()
        print(f"  [PROOF] !card attached file: {file_attached.filename} ({len(attached_bytes)} bytes)")
        self.assertGreater(len(attached_bytes), 10 * 1024)

        img = Image.open(io.BytesIO(attached_bytes))
        self.assertEqual(img.size, (1080, 1350))
        self.assertEqual(img.format, "PNG")
        print(f"  [PROOF] Attachment verified: Dimensions={img.size}, Format={img.format}")

        print("PASS")

    def test_g_speaker_and_topic_overflow(self):
        """
        Test g (TRACE6-02):
        - When payload has >3 speakers (e.g. 5), card renders top 3 and footnote '+2 مشاركين إضافيين'
        - When payload has >3 topics (e.g. 5), card renders top 3 and footnote '+2 مواضيع إضافية'
        """
        print("\n=== TEST G: SPEAKER & TOPIC OVERFLOW (>3 ITEMS) ===")
        speakers = [
            SpeakerStat(name="أحمد", talk_seconds=180.0, share_pct=40.0, streak_seconds=45.0, angry_episodes=0),
            SpeakerStat(name="تامر", talk_seconds=120.0, share_pct=26.7, streak_seconds=30.0, angry_episodes=0),
            SpeakerStat(name="كريم", talk_seconds=90.0, share_pct=20.0, streak_seconds=15.0, angry_episodes=0),
            SpeakerStat(name="سارة", talk_seconds=40.0, share_pct=8.9, streak_seconds=10.0, angry_episodes=0),
            SpeakerStat(name="منى", talk_seconds=20.0, share_pct=4.4, streak_seconds=5.0, angry_episodes=0),
        ]
        topics = [
            TopicStat(topic_key="football", display_name="الكورة والرياضة", pct=35.0),
            TopicStat(topic_key="gaming", display_name="ألعاب الفيديو", pct=25.0),
            TopicStat(topic_key="tech", display_name="تكنولوجيا وبرمجة", pct=20.0),
            TopicStat(topic_key="movies", display_name="أفلام ومسلسلات", pct=12.0),
            TopicStat(topic_key="food", display_name="أكل ومطاعم", pct=8.0),
        ]
        payload = RecapCardPayload(
            session_title="سهرة الجيمينج",
            period_label="جلسة مع 5 متحدثين",
            speaker_stats=speakers,
            top_topics=topics,
            coverage_note="نسبة التغطية الموضوعية: 100.0%"
        )

        with patch("bot.ui.recap_card_renderer.draw_text", wraps=draw_text) as mock_draw:
            png_bytes = render_recap_card_png(payload)

        self.assertGreater(len(png_bytes), 10 * 1024)
        img = Image.open(io.BytesIO(png_bytes))
        self.assertEqual(img.size, (1080, 1350))

        drawn_texts = [call.args[2] for call in mock_draw.call_args_list if len(call.args) > 2]

        # Verify top 3 speakers are drawn, omitted are not
        self.assertIn("أحمد", drawn_texts)
        self.assertIn("تامر", drawn_texts)
        self.assertIn("كريم", drawn_texts)
        self.assertNotIn("سارة", drawn_texts)
        self.assertNotIn("منى", drawn_texts)
        self.assertIn("+2 مشاركين إضافيين", drawn_texts)

        # Verify top 3 topics are drawn, omitted are not
        self.assertIn("الكورة والرياضة", drawn_texts)
        self.assertIn("ألعاب الفيديو", drawn_texts)
        self.assertIn("تكنولوجيا وبرمجة", drawn_texts)
        self.assertNotIn("أفلام ومسلسلات", drawn_texts)
        self.assertNotIn("أكل ومطاعم", drawn_texts)
        self.assertIn("+2 مواضيع إضافية", drawn_texts)

        print("  [PROOF] Top 3 speakers drawn: أحمد, تامر, كريم (سارة and منى omitted)")
        print("  [PROOF] Speaker overflow footnote verified in drawn text: '+2 مشاركين إضافيين'")
        print("  [PROOF] Top 3 topics drawn: الكورة والرياضة, ألعاب الفيديو, تكنولوجيا وبرمجة")
        print("  [PROOF] Topic overflow footnote verified in drawn text: '+2 مواضيع إضافية'")
        print(f"  [PROOF] Rendered PNG verified: {len(png_bytes)} bytes, size {img.size}")
        print("PASS")


if __name__ == "__main__":
    unittest.main()
