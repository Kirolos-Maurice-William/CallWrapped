"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  CheckCircle2,
  XCircle,
  ExternalLink,
  Volume2,
  Play,
  RotateCcw,
  ShieldCheck,
  Award,
  ChevronDown,
  ChevronUp,
  FastForward,
  Copy,
  Check,
  Radio,
  ShieldOff,
  Sparkles,
} from "lucide-react";

import {
  AnalyticsState,
  SpeakerAnalytics,
  formatDurationHuman,
  formatStreakMMSS,
  TOPIC_DISPLAY_NAMES,
  TOPIC_COLORS,
} from "../components/AnalyticsWidgets";

import { DisputesPanel, DisputeCard } from "../components/DisputesPanel";
import { CallWrappedModal } from "../components/CallWrappedModal";
import { PipelineFlow, ActivePipelineStage } from "../components/PipelineFlow";

interface LatencyMetrics {
  stt_ms?: number;
  llm_ms?: number;
  search_ms?: number;
  tts_ms?: number;
  total_ms?: number;
}

interface SpeakerStats {
  turns: number;
  verified: number;
  refuted: number;
}

interface DisputeInfo {
  event_id?: string;
  correlation_id?: string;
  timestamp: number;
  disputed_attribute?: string;
  speaker_a?: string;
  claim_a?: string;
  speaker_a_status?: string;
  speaker_b?: string;
  claim_b?: string;
  speaker_b_status?: string;
  winner?: string;
  loser?: string;
  correct_fact?: string;
  confidence?: number;
  evidence_strength?: string;
  status?: string;
  source_url?: string;
  source_title?: string;
  spoken_intervention?: string;
  spoken_intervention_en?: string;
  why_i_spoke?: string[];
  latency?: LatencyMetrics;
  t_perceived_ms?: number;
}

interface PendingOfferState {
  offer_id: string;
  entity: string;
  speaker_a: string;
  claim_a: string;
  speaker_b: string;
  claim_b: string;
  prompt_ar: string;
  prompt_en: string;
  prefetch_domain: string;
  prefetch_ready: boolean;
  countdown_sec: number;
}

interface Turn {
  speaker_name: string;
  text: string;
  timestamp: number;
  stt_ms?: number;
  correlation_id?: string;
  tag?: "claim" | "conflict" | "confirm" | "referee" | "loud";
  tag_label?: string;
}

interface DemoScenario {
  id: string;
  label: string;
  shortTitle: string;
  latency: LatencyMetrics;
  preTurns: Turn[];
  offer: PendingOfferState | null;
  confirmTurn?: Turn;
  postTurns: Turn[];
  resolvedDispute: DisputeInfo;
  disputeCard: DisputeCard;
  leaderboard: {
    "Verified Claims": number;
    "Disputed Claims": number;
    Speakers: Record<string, SpeakerStats>;
  };
  analytics: AnalyticsState;
}

const DEMO_SCENARIOS: DemoScenario[] = [
  {
    id: "rtx5070",
    label: "RTX 5070 VRAM",
    shortTitle: "NVIDIA RTX 5070 Memory Capacity",
    latency: {
      stt_ms: 265,
      llm_ms: 194,
      search_ms: 520,
      tts_ms: 185,
      total_ms: 1164,
    },
    preTurns: [
      {
        speaker_name: "Mostafa",
        text: "يا شباب حد شاف ماتش السوبر؟ الأهلي غلب الزمالك 2-0 إمبارح",
        timestamp: Date.now() / 1000 - 55,
        stt_ms: 270,
      },
      {
        speaker_name: "2xDanger",
        text: "اه الماتش كان حريقة، إمام عاشور عمل ماتش عالي أوي",
        timestamp: Date.now() / 1000 - 50,
        stt_ms: 260,
      },
      {
        speaker_name: "Remi",
        text: "Good match honestly, defense was very solid.",
        timestamp: Date.now() / 1000 - 46,
        stt_ms: 250,
      },
      {
        speaker_name: "2xDanger",
        text: "Bro, I'm pretty sure the RTX 5070 has 16 gigs of VRAM.",
        timestamp: Date.now() / 1000 - 41,
        stt_ms: 272,
        tag: "claim",
        tag_label: "Claim",
      },
      {
        speaker_name: "Mostafa",
        text: "No, the 5070 is 12 gigs. The Ti is 16.",
        timestamp: Date.now() / 1000 - 37,
        stt_ms: 258,
        tag: "conflict",
        tag_label: "Disagreement",
      },
      {
        speaker_name: "2xDanger",
        text: "Nah, both are 16. شوف التسريبات بتاعت أمس كلها بتقول كده!",
        timestamp: Date.now() / 1000 - 33,
        stt_ms: 265,
      },
    ],
    offer: {
      offer_id: "off_rtx5070",
      entity: "NVIDIA RTX 5070 VRAM Specification",
      speaker_a: "2xDanger",
      claim_a: "RTX 5070 launches with 16GB VRAM",
      speaker_b: "Mostafa",
      claim_b: "RTX 5070 is 12GB GDDR7 (only the 5070 Ti is 16GB)",
      prompt_ar: "أشوفها؟",
      prompt_en: "Do I check?",
      prefetch_domain: "nvidia.com/geforce",
      prefetch_ready: true,
      countdown_sec: 6,
    },
    confirmTurn: {
      speaker_name: "Mostafa",
      text: "شوفها يلا — check it!",
      timestamp: Date.now() / 1000 - 31,
      stt_ms: 210,
      tag: "confirm",
      tag_label: "Confirmed",
    },
    postTurns: [
      {
        speaker_name: "CallWrapped Referee",
        text: "توضيح: كارت RTX 5070 نازل بـ 12 جيجا GDDR7، والـ 5070 Ti هو اللي بـ 16 جيجا.",
        timestamp: Date.now() / 1000 - 30,
        stt_ms: 0,
        tag: "referee",
        tag_label: "Spoken Verdict",
      },
      {
        speaker_name: "Mostafa",
        text: "Told you bro! NVIDIA never gives 16GB on the non-Ti 70 class.",
        timestamp: Date.now() / 1000 - 24,
        stt_ms: 245,
      },
      {
        speaker_name: "2xDanger",
        text: "Fuck this game, I lost the rank match again!",
        timestamp: Date.now() / 1000 - 18,
        stt_ms: 260,
      },
      {
        speaker_name: "Remi",
        text: "Calm down bro, we can duo queue League tonight and fix your rank.",
        timestamp: Date.now() / 1000 - 12,
        stt_ms: 255,
      },
    ],
    resolvedDispute: {
      event_id: "evt_golden_rtx5070",
      timestamp: Date.now() / 1000 - 30,
      disputed_attribute: "NVIDIA GeForce RTX 5070 VRAM Capacity",
      speaker_a: "2xDanger",
      claim_a: "Bro, I'm pretty sure the RTX 5070 has 16 gigs of VRAM.",
      speaker_a_status: "CONTRADICTED",
      speaker_b: "Mostafa",
      claim_b: "No, the 5070 is 12 gigs. The Ti is 16.",
      speaker_b_status: "SUPPORTED",
      winner: "Mostafa",
      loser: "2xDanger",
      correct_fact:
        "NVIDIA GeForce RTX 5070 ships with 12GB GDDR7 memory. Only the RTX 5070 Ti carries 16GB GDDR7.",
      confidence: 99,
      evidence_strength: "Official Manufacturer Specs",
      status: "resolved",
      source_url:
        "https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5070-family/",
      source_title: "NVIDIA GeForce RTX 5070 Family Specifications",
      spoken_intervention:
        "توضيح: كارت RTX 5070 نازل بـ 12 جيجا GDDR7، والـ 5070 Ti هو اللي بـ 16 جيجا. المصدر الرسمي على الداشبورد.",
      spoken_intervention_en:
        "Quick check: The RTX 5070 ships with 12GB of GDDR7 memory, while the 5070 Ti has 16GB.",
      t_perceived_ms: 1164,
      why_i_spoke: [
        "Factual claim detected regarding GPU memory capacity",
        "Direct contradiction between 2xDanger (16GB) and Mostafa (12GB)",
        "Verified against official manufacturer specifications on nvidia.com",
        "Consent confirmed in voice («شوفها» / 'check it')",
      ],
    },
    disputeCard: {
      dispute_id: "disp_golden_rtx5070",
      speaker_a: "2xDanger",
      claim_a: "Bro, I'm pretty sure the RTX 5070 has 16 gigs of VRAM.",
      speaker_b: "Mostafa",
      claim_b: "No, the 5070 is 12 gigs. The Ti is 16.",
      disputed_attribute: "RTX 5070 VRAM Capacity",
      status: "resolved",
      source_name: "NVIDIA Official Specifications",
      source_url:
        "https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5070-family/",
      evidence_excerpt:
        "GeForce RTX 5070: 12GB GDDR7. GeForce RTX 5070 Ti: 16GB GDDR7.",
      t_perceived_ms: 1164,
    },
    leaderboard: {
      "Verified Claims": 3,
      "Disputed Claims": 1,
      Speakers: {
        Mostafa: { turns: 14, verified: 2, refuted: 0 },
        "2xDanger": { turns: 18, verified: 1, refuted: 1 },
        Remi: { turns: 8, verified: 0, refuted: 0 },
      },
    },
    analytics: {
      topic_totals: { tech: 14, gaming: 9, football: 4 },
      speakers: {
        "2xDanger": {
          speaker_name: "2xDanger",
          talk_seconds: 96.0,
          longest_streak_seconds: 15.0,
          angry_episodes: 1,
          first_anger_quote: "Fuck this game, I lost the rank match again!",
          anger_episodes_history: [
            {
              timestamp: Date.now() / 1000 - 15,
              intensity: "mild",
              quote: "Fuck this game, I lost the rank match again!",
              loudness: 245,
              was_loud: true,
              peak_z: 2.8,
            },
          ],
          vulgarity_count: 2,
          vulgarity_terms: ["f*", "f**"],
        },
        Mostafa: {
          speaker_name: "Mostafa",
          talk_seconds: 45.0,
          longest_streak_seconds: 10.0,
          angry_episodes: 0,
          anger_episodes_history: [],
          vulgarity_count: 0,
          vulgarity_terms: [],
        },
        Remi: {
          speaker_name: "Remi",
          talk_seconds: 31.0,
          longest_streak_seconds: 8.0,
          angry_episodes: 0,
          anger_episodes_history: [],
          vulgarity_count: 0,
          vulgarity_terms: [],
        },
      },
      total_talk_seconds: 172.0,
      total_angry_episodes: 1,
      total_vulgarity_count: 2,
      total_banter_count: 3,
      longest_streak: {
        speaker_name: "2xDanger",
        streak_seconds: 15.0,
      },
    },
  },
  {
    id: "ucl",
    label: "UCL Titles",
    shortTitle: "Real Madrid Champions League Titles",
    latency: {
      stt_ms: 240,
      llm_ms: 178,
      search_ms: 480,
      tts_ms: 170,
      total_ms: 1068,
    },
    preTurns: [
      {
        speaker_name: "Mostafa",
        text: "ريال مدريد معاه 14 بطولة دوري أبطال أوروبا لحد دلوقتي",
        timestamp: Date.now() / 1000 - 40,
        stt_ms: 242,
        tag: "claim",
        tag_label: "Claim",
      },
      {
        speaker_name: "Remi",
        text: "لا يا ابني بقوا 15 بعد نهائي ويمبلي قدام دورتموند!",
        timestamp: Date.now() / 1000 - 35,
        stt_ms: 238,
        tag: "conflict",
        tag_label: "Disagreement",
      },
    ],
    offer: {
      offer_id: "off_ucl15",
      entity: "Real Madrid UEFA Champions League Titles",
      speaker_a: "Mostafa",
      claim_a: "Real Madrid has 14 Champions League titles",
      speaker_b: "Remi",
      claim_b: "Real Madrid has 15 titles after Wembley 2024",
      prompt_ar: "أشوفها؟",
      prompt_en: "Do I check?",
      prefetch_domain: "uefa.com/history",
      prefetch_ready: true,
      countdown_sec: 6,
    },
    confirmTurn: {
      speaker_name: "Remi",
      text: "شوفها كده يا حكم",
      timestamp: Date.now() / 1000 - 32,
      stt_ms: 195,
      tag: "confirm",
      tag_label: "Confirmed",
    },
    postTurns: [
      {
        speaker_name: "CallWrapped Referee",
        text: "توضيح: ريال مدريد حقق البطولة رقم 15 في تاريخه بعد الفوز على دورتموند 2-0 في ويمبلي.",
        timestamp: Date.now() / 1000 - 30,
        stt_ms: 0,
        tag: "referee",
        tag_label: "Spoken Verdict",
      },
    ],
    resolvedDispute: {
      event_id: "evt_ucl_15",
      timestamp: Date.now() / 1000 - 30,
      disputed_attribute: "Real Madrid Champions League Total Titles",
      speaker_a: "Mostafa",
      claim_a: "ريال مدريد معاه 14 بطولة دوري أبطال أوروبا",
      speaker_a_status: "CONTRADICTED",
      speaker_b: "Remi",
      claim_b: "لا يا ابني بقوا 15 بعد نهائي ويمبلي قدام دورتموند",
      speaker_b_status: "SUPPORTED",
      winner: "Remi",
      loser: "Mostafa",
      correct_fact:
        "Real Madrid holds 15 UEFA Champions League titles, winning their 15th on June 1, 2024 at Wembley.",
      confidence: 99,
      evidence_strength: "Official UEFA Records",
      status: "resolved",
      source_url: "https://www.uefa.com/uefachampionsleague/history/winners/",
      source_title: "UEFA Champions League Official Records",
      spoken_intervention:
        "توضيح: ريال مدريد حقق البطولة رقم 15 في تاريخه بعد الفوز على بوروسيا دورتموند 2-0 في نهائي ويمبلي.",
      spoken_intervention_en:
        "Quick check: Real Madrid holds 15 Champions League titles following their Wembley victory.",
      t_perceived_ms: 1068,
      why_i_spoke: [
        "Factual dispute on sports trophy record",
        "Authoritative source verified via uefa.com",
        "Verbal consent provided by Remi",
      ],
    },
    disputeCard: {
      dispute_id: "disp_ucl_15",
      speaker_a: "Mostafa",
      claim_a: "ريال مدريد معاه 14 بطولة دوري أبطال أوروبا",
      speaker_b: "Remi",
      claim_b: "بقوا 15 بعد نهائي ويمبلي قدام دورتموند",
      disputed_attribute: "Real Madrid UCL Titles",
      status: "resolved",
      source_name: "UEFA Official Records",
      source_url: "https://www.uefa.com/uefachampionsleague/history/winners/",
      evidence_excerpt:
        "Real Madrid claimed their 15th European Cup in 2024 at Wembley.",
      t_perceived_ms: 1068,
    },
    leaderboard: {
      "Verified Claims": 4,
      "Disputed Claims": 2,
      Speakers: {
        Remi: { turns: 11, verified: 2, refuted: 0 },
        Mostafa: { turns: 15, verified: 2, refuted: 1 },
        "2xDanger": { turns: 18, verified: 0, refuted: 1 },
      },
    },
    analytics: {
      topic_totals: { football: 12, tech: 8, gaming: 6 },
      speakers: {
        Mostafa: {
          speaker_name: "Mostafa",
          talk_seconds: 68.0,
          longest_streak_seconds: 14.0,
          angry_episodes: 0,
        },
        Remi: {
          speaker_name: "Remi",
          talk_seconds: 54.0,
          longest_streak_seconds: 11.0,
          angry_episodes: 0,
        },
        "2xDanger": {
          speaker_name: "2xDanger",
          talk_seconds: 42.0,
          longest_streak_seconds: 9.0,
          angry_episodes: 0,
        },
      },
      total_talk_seconds: 164.0,
      total_angry_episodes: 0,
      total_vulgarity_count: 0,
      total_banter_count: 2,
      longest_streak: {
        speaker_name: "Mostafa",
        streak_seconds: 14.0,
      },
    },
  },
  {
    id: "privacy",
    label: "Privacy Guard",
    shortTitle: "Private Personal Claim Refusal",
    latency: {
      stt_ms: 248,
      llm_ms: 92,
      search_ms: 0,
      tts_ms: 0,
      total_ms: 340,
    },
    preTurns: [
      {
        speaker_name: "2xDanger",
        text: "أحمد صاحبنا قبض مرتب 80 ألف الشهر اللي فات واشترى عربية",
        timestamp: Date.now() / 1000 - 20,
        stt_ms: 248,
      },
      {
        speaker_name: "Mostafa",
        text: "لا يا عم مستحيل، هو قالي مرتبه 35 ألف بس",
        timestamp: Date.now() / 1000 - 15,
        stt_ms: 252,
        tag: "conflict",
        tag_label: "Private Entity",
      },
    ],
    offer: null,
    postTurns: [],
    resolvedDispute: {
      event_id: "evt_privacy_refusal",
      timestamp: Date.now() / 1000 - 14,
      disputed_attribute: "Private Person Claim (Personal Salary)",
      speaker_a: "2xDanger",
      claim_a: "أحمد صاحبنا قبض مرتب 80 ألف الشهر اللي فات",
      speaker_a_status: "REFUSED_PRIVATE",
      speaker_b: "Mostafa",
      claim_b: "لا هو قالي مرتبه 35 ألف بس",
      speaker_b_status: "REFUSED_PRIVATE",
      correct_fact:
        "Private claim detected. CallWrapped automatically refuses external web searches on private individuals to protect user privacy.",
      confidence: 100,
      evidence_strength: "Privacy Gate",
      status: "REFUSED_PRIVATE",
      why_i_spoke: [
        "Entity identified as a private individual",
        "External search skipped to protect personal privacy",
        "Zero voice intervention executed",
      ],
    },
    disputeCard: {
      dispute_id: "disp_privacy_01",
      speaker_a: "2xDanger",
      claim_a: "أحمد صاحبنا قبض مرتب 80 ألف الشهر اللي فات",
      speaker_b: "Mostafa",
      claim_b: "لا هو قالي مرتبه 35 ألف بس",
      disputed_attribute: "Private Entity Claim",
      status: "refused_private",
      refusal_reason: "Private individual claim — web search skipped by privacy policy",
    },
    leaderboard: {
      "Verified Claims": 3,
      "Disputed Claims": 1,
      Speakers: {
        Mostafa: { turns: 15, verified: 2, refuted: 0 },
        "2xDanger": { turns: 19, verified: 1, refuted: 1 },
      },
    },
    analytics: {
      topic_totals: { personal: 2, tech: 14, gaming: 9 },
      speakers: {
        "2xDanger": {
          speaker_name: "2xDanger",
          talk_seconds: 96.0,
          longest_streak_seconds: 15.0,
          angry_episodes: 0,
        },
        Mostafa: {
          speaker_name: "Mostafa",
          talk_seconds: 48.0,
          longest_streak_seconds: 10.0,
          angry_episodes: 0,
        },
      },
      total_talk_seconds: 144.0,
      total_angry_episodes: 0,
      total_vulgarity_count: 0,
      total_banter_count: 1,
      longest_streak: {
        speaker_name: "2xDanger",
        streak_seconds: 15.0,
      },
    },
  },
];

export default function CallWrappedDashboard() {
  const [activeTab, setActiveTab] = useState<"referee" | "wrapped">("referee");
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>("rtx5070");
  const [isConnected, setIsConnected] = useState(false);
  const [showRecapModal, setShowRecapModal] = useState(false);
  const [showDecisionTrace, setShowDecisionTrace] = useState(false);
  const [spokenLang, setSpokenLang] = useState<"ar" | "en">("ar");
  const [isSpeakingVerdict, setIsSpeakingVerdict] = useState(false);
  const [copiedSummary, setCopiedSummary] = useState(false);

  // Pipeline & Referee State
  const [pipelineStage, setPipelineStage] = useState<ActivePipelineStage>("idle");
  const [latency, setLatency] = useState<LatencyMetrics>({
    stt_ms: 0,
    llm_ms: 0,
    search_ms: 0,
    tts_ms: 0,
    total_ms: 0,
  });
  const [turns, setTurns] = useState<Turn[]>([]);
  const [pendingOffer, setPendingOffer] = useState<PendingOfferState | null>(null);
  const [offerCountdown, setOfferCountdown] = useState<number>(0);
  const [activeDispute, setActiveDispute] = useState<DisputeInfo | null>(null);
  const [disputes, setDisputes] = useState<DisputeCard[]>([]);
  const [leaderboard, setLeaderboard] = useState<{
    "Verified Claims": number;
    "Disputed Claims": number;
    Speakers: Record<string, SpeakerStats>;
  }>({
    "Verified Claims": 0,
    "Disputed Claims": 0,
    Speakers: {},
  });
  const [analytics, setAnalytics] = useState<AnalyticsState>({
    topic_totals: {},
    speakers: {},
    total_talk_seconds: 0,
    total_angry_episodes: 0,
    total_vulgarity_count: 0,
    total_banter_count: 0,
    longest_streak: {
      speaker_name: null,
      streak_seconds: 0,
    },
  });

  const [isSimulating, setIsSimulating] = useState(false);
  const [discordInviteUrl, setDiscordInviteUrl] = useState<string>(
    "https://discord.com/oauth2/authorize?client_id=1550926707517558864&permissions=36718592&scope=bot%20applications.commands"
  );

  const transcriptScrollRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const simAbortRef = useRef<number>(0);
  const consentResolveRef = useRef<(() => void) | null>(null);
  const hasInitializedRef = useRef(false);

  const getBackendBase = useCallback(() => {
    const envUrl = process.env.NEXT_PUBLIC_BACKEND_URL;
    if (envUrl) {
      const clean = envUrl.replace(/\/$/, "");
      return {
        http: clean,
        ws: clean.replace(/^http/, "ws"),
        canConnect: true,
      };
    }
    if (typeof window !== "undefined") {
      const hostname = window.location.hostname || "localhost";
      const isLocal = hostname === "localhost" || hostname === "127.0.0.1";
      if (isLocal) {
        const port =
          window.location.port === "3000" || !window.location.port
            ? "8000"
            : window.location.port;
        return {
          http: `${window.location.protocol}//${hostname}:${port}`,
          ws: `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${hostname}:${port}`,
          canConnect: true,
        };
      }
      return {
        http: `${window.location.protocol}//${window.location.host}`,
        ws: `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}`,
        canConnect: false,
      };
    }
    return { http: "http://localhost:8000", ws: "ws://localhost:8000", canConnect: false };
  }, []);

  // Auto-scroll transcript
  useEffect(() => {
    if (transcriptScrollRef.current) {
      transcriptScrollRef.current.scrollTop = transcriptScrollRef.current.scrollHeight;
    }
  }, [turns]);

  // Voice playback using browser Web Speech API
  const handleSpeakVerdict = (textToSpeak?: string, lang: "ar" | "en" = spokenLang) => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    if (isSpeakingVerdict) {
      setIsSpeakingVerdict(false);
      return;
    }
    const text =
      textToSpeak ||
      (lang === "en" && activeDispute?.spoken_intervention_en
        ? activeDispute.spoken_intervention_en
        : activeDispute?.spoken_intervention || activeDispute?.correct_fact || "");
    if (!text) return;

    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = lang === "ar" ? "ar-EG" : "en-US";
    utter.rate = 1.0;
    utter.onstart = () => setIsSpeakingVerdict(true);
    utter.onend = () => setIsSpeakingVerdict(false);
    utter.onerror = () => setIsSpeakingVerdict(false);
    setIsSpeakingVerdict(true);
    window.speechSynthesis.speak(utter);
  };

  // Instant snapshot loader (Skip animation)
  const applyScenarioInstant = useCallback((scenarioId: string = selectedScenarioId) => {
    simAbortRef.current += 1;
    if (consentResolveRef.current) {
      consentResolveRef.current = null;
    }
    const scenario =
      DEMO_SCENARIOS.find((s) => s.id === scenarioId) || DEMO_SCENARIOS[0];
    setIsSimulating(false);
    setPendingOffer(null);
    setOfferCountdown(0);
    setPipelineStage("idle");
    setLatency(scenario.latency);
    const allTurns = [
      ...scenario.preTurns,
      ...(scenario.confirmTurn ? [scenario.confirmTurn] : []),
      ...scenario.postTurns,
    ];
    setTurns(allTurns);
    setActiveDispute(scenario.resolvedDispute);
    setDisputes([scenario.disputeCard]);
    setLeaderboard(scenario.leaderboard);
    setAnalytics(scenario.analytics);
  }, [selectedScenarioId]);

  // Two-Stage Interactive Simulation
  const runInteractiveDemo = useCallback(
    async (scenarioId: string = selectedScenarioId) => {
      const runId = ++simAbortRef.current;
      const scenario =
        DEMO_SCENARIOS.find((s) => s.id === scenarioId) || DEMO_SCENARIOS[0];

      setSelectedScenarioId(scenario.id);
      setIsSimulating(true);
      setActiveTab("referee");
      setTurns([]);
      setPendingOffer(null);
      setActiveDispute(null);
      setDisputes([]);
      setShowDecisionTrace(false);
      setLatency({ stt_ms: 0, llm_ms: 0, search_ms: 0, tts_ms: 0, total_ms: 0 });
      setPipelineStage("asr");

      const sleep = (ms: number) =>
        new Promise<void>((resolve) => setTimeout(resolve, ms));

      // 1. Stream pre-dispute turns
      for (let i = 0; i < scenario.preTurns.length; i++) {
        if (simAbortRef.current !== runId) return;
        const turn = scenario.preTurns[i];
        setPipelineStage(turn.tag ? "claim" : "asr");
        setLatency((prev) => ({
          ...prev,
          stt_ms: turn.stt_ms || 260,
          llm_ms: turn.tag ? 194 : prev.llm_ms,
        }));
        setTurns((prev) => [...prev, { ...turn, timestamp: Date.now() / 1000 }]);
        await sleep(i === 0 ? 400 : 700);
      }

      if (simAbortRef.current !== runId) return;

      // 2. If scenario has a consent offer, trigger Stage 1 ("Do I check?" / «أشوفها؟»)
      if (scenario.offer) {
        setPipelineStage("offer");
        setLatency({
          stt_ms: scenario.latency.stt_ms,
          llm_ms: scenario.latency.llm_ms,
          search_ms: scenario.latency.search_ms,
          tts_ms: 0,
          total_ms: (scenario.latency.stt_ms || 0) + (scenario.latency.llm_ms || 0),
        });
        setPendingOffer(scenario.offer);
        setDisputes([
          {
            ...scenario.disputeCard,
            status: "offered",
            t_perceived_ms: null,
          },
        ]);

        const totalWaitSec = scenario.offer.countdown_sec;
        setOfferCountdown(totalWaitSec);

        await new Promise<void>((resolve) => {
          consentResolveRef.current = resolve;
          let remaining = totalWaitSec;
          const timer = setInterval(() => {
            if (simAbortRef.current !== runId) {
              clearInterval(timer);
              resolve();
              return;
            }
            remaining -= 1;
            setOfferCountdown(Math.max(0, remaining));
            if (remaining <= 0) {
              clearInterval(timer);
              resolve();
            }
          }, 1000);
        });

        consentResolveRef.current = null;
        if (simAbortRef.current !== runId) return;

        // Append confirmation turn
        if (scenario.confirmTurn) {
          setTurns((prev) => [
            ...prev,
            { ...scenario.confirmTurn!, timestamp: Date.now() / 1000 },
          ]);
        }
        setPipelineStage("verdict");
        await sleep(350);
      }

      if (simAbortRef.current !== runId) return;

      // 3. Deliver Stage 2 Verified Verdict
      setPendingOffer(null);
      setOfferCountdown(0);
      setLatency(scenario.latency);
      setActiveDispute({
        ...scenario.resolvedDispute,
        timestamp: Date.now() / 1000,
      });
      setDisputes([scenario.disputeCard]);
      setLeaderboard(scenario.leaderboard);
      setAnalytics(scenario.analytics);

      // 4. Stream post-verdict reactions
      for (let i = 0; i < scenario.postTurns.length; i++) {
        if (simAbortRef.current !== runId) return;
        await sleep(650);
        if (simAbortRef.current !== runId) return;
        const turn = scenario.postTurns[i];
        setTurns((prev) => [...prev, { ...turn, timestamp: Date.now() / 1000 }]);
      }

      if (simAbortRef.current === runId) {
        setPipelineStage("idle");
        setIsSimulating(false);
      }
    },
    [selectedScenarioId]
  );

  const handleConfirmOffer = () => {
    if (consentResolveRef.current) {
      consentResolveRef.current();
    } else if (pendingOffer) {
      applyScenarioInstant(selectedScenarioId);
    }
  };

  const handleDismissOffer = () => {
    simAbortRef.current += 1;
    consentResolveRef.current = null;
    setPendingOffer(null);
    setOfferCountdown(0);
    setPipelineStage("idle");
    setIsSimulating(false);
  };

  // Initialize
  useEffect(() => {
    let isMounted = true;
    const { http, canConnect } = getBackendBase();

    if (!canConnect) {
      if (!hasInitializedRef.current) {
        hasInitializedRef.current = true;
        runInteractiveDemo("rtx5070");
      }
      return;
    }

    const checkLive = async () => {
      try {
        const res = await fetch(`${http}/api/live`, { signal: AbortSignal.timeout(1200) });
        if (res.ok && isMounted) {
          setIsConnected(true);
        }
      } catch {
        if (isMounted && !hasInitializedRef.current) {
          hasInitializedRef.current = true;
          runInteractiveDemo("rtx5070");
        }
      }
    };

    checkLive();
    return () => {
      isMounted = false;
      if (wsRef.current) wsRef.current.close();
    };
  }, [getBackendBase, runInteractiveDemo]);

  const handleReset = () => {
    simAbortRef.current += 1;
    consentResolveRef.current = null;
    setIsSimulating(false);
    setPendingOffer(null);
    setOfferCountdown(0);
    setActiveDispute(null);
    setDisputes([]);
    setTurns([]);
    setPipelineStage("idle");
    setLatency({ stt_ms: 0, llm_ms: 0, search_ms: 0, tts_ms: 0, total_ms: 0 });
  };

  const speakerEntries = Object.values(analytics.speakers || {}).sort(
    (a, b) => b.talk_seconds - a.talk_seconds
  );
  const topicalEntries = Object.entries(analytics.topic_totals || {})
    .filter(
      ([t]) =>
        t !== "null_topic" &&
        t !== "null" &&
        t !== "بدون موضوع" &&
        t !== "none"
    )
    .sort((a, b) => b[1] - a[1]);
  const totalTopicalCount = topicalEntries.reduce((acc, [, c]) => acc + c, 0);

  const handleCopyRecap = () => {
    const topTopic = topicalEntries[0]?.[0]?.toUpperCase() || "GENERAL";
    const text =
      `**CALLWRAPPED // SESSION DOSSIER**\n` +
      `• Airtime: ${formatDurationHuman(analytics.total_talk_seconds)} (${speakerEntries.length} speakers)\n` +
      `• Monologue King: ${analytics.longest_streak?.speaker_name || "—"}\n` +
      `• Fact Score: ${leaderboard["Verified Claims"]} verified, ${leaderboard["Disputed Claims"]} refuted\n` +
      `• Dominant Topic: ${topTopic}`;
    navigator.clipboard.writeText(text);
    setCopiedSummary(true);
    setTimeout(() => setCopiedSummary(false), 2000);
  };

  return (
    <div className="min-h-screen bg-[#0b0e14] text-[#f0f3f8] flex flex-col selection:bg-[#3b82f6] selection:text-white">
      {/* =================================================================== */}
      {/* 1. SINGLE CONSOLIDATED TOP BAR (NO 3 STACKED HEADERS)               */}
      {/* =================================================================== */}
      <header className="border-b border-[#1c2436] bg-[#0e131f] sticky top-0 z-40 px-4 md:px-6 h-14 flex items-center justify-between gap-4">
        {/* Brand & Connection State */}
        <div className="flex items-center gap-3 shrink-0">
          <div className="w-2.5 h-2.5 rounded-full bg-[#3b82f6]" />
          <span className="font-editorial text-base font-bold text-white tracking-tight">
            CALLWRAPPED
          </span>
          <span className="text-xs text-[#8e98ab] hidden lg:inline">
            Voice Referee
          </span>
        </div>

        {/* Center: Scenario Switcher Tabs */}
        <div className="flex items-center gap-1 bg-[#101522] p-1 rounded border border-[#1c2436] overflow-x-auto text-xs">
          <span className="text-[#626d80] text-[11px] font-medium px-2 uppercase tracking-wider hidden sm:inline">
            Scenario:
          </span>
          {DEMO_SCENARIOS.map((sc) => {
            const active = selectedScenarioId === sc.id;
            return (
              <button
                key={sc.id}
                onClick={() => runInteractiveDemo(sc.id)}
                className={`px-3 py-1 rounded text-xs font-medium transition-colors cursor-pointer shrink-0 ${
                  active
                    ? "bg-[#1c2436] text-white font-semibold shadow-sm"
                    : "text-[#8e98ab] hover:text-white"
                }`}
              >
                {sc.label}
              </button>
            );
          })}
        </div>

        {/* Right Actions */}
        <div className="flex items-center gap-2 shrink-0">
          {/* View Toggle */}
          <div className="flex items-center border border-[#1c2436] rounded bg-[#101522] p-0.5 text-xs font-medium">
            <button
              onClick={() => setActiveTab("referee")}
              className={`px-3 py-1 rounded transition-colors cursor-pointer ${
                activeTab === "referee"
                  ? "bg-[#1c2436] text-white"
                  : "text-[#8e98ab] hover:text-white"
              }`}
            >
              Referee View
            </button>
            <button
              onClick={() => setActiveTab("wrapped")}
              className={`px-3 py-1 rounded transition-colors cursor-pointer ${
                activeTab === "wrapped"
                  ? "bg-[#1c2436] text-white"
                  : "text-[#8e98ab] hover:text-white"
              }`}
            >
              Dossier
            </button>
          </div>

          <button
            onClick={() => runInteractiveDemo(selectedScenarioId)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#3b82f6] hover:bg-[#2563eb] text-white text-xs font-semibold rounded transition-colors cursor-pointer"
            title="Replay Interactive Voice Simulation"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
            <span className="hidden sm:inline">Replay</span>
          </button>

          <button
            onClick={() => applyScenarioInstant(selectedScenarioId)}
            className="p-1.5 bg-[#101522] hover:bg-[#161c2c] border border-[#1c2436] text-[#8e98ab] hover:text-white rounded transition-colors cursor-pointer"
            title="Skip to verified verdict immediately"
          >
            <FastForward className="w-3.5 h-3.5" />
          </button>

          <button
            onClick={handleReset}
            className="p-1.5 bg-[#101522] hover:bg-[#161c2c] border border-[#1c2436] text-[#8e98ab] hover:text-white rounded transition-colors cursor-pointer"
            title="Reset"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        </div>
      </header>

      {/* =================================================================== */}
      {/* 2. REFINED SUB-HEADER PIPELINE STATUS                               */}
      {/* =================================================================== */}
      <PipelineFlow latency={latency} activeStage={pipelineStage} />

      {/* =================================================================== */}
      {/* 3. MAIN WORKSPACE                                                   */}
      {/* =================================================================== */}
      {activeTab === "referee" ? (
        <main className="flex-1 max-w-[1440px] w-full mx-auto grid grid-cols-1 lg:grid-cols-12 lg:divide-x divide-[#1c2436] border-x border-[#1c2436]">
          {/* =============================================================== */}
          {/* LEFT COLUMN: CLEAN CONVERSATIONAL SPEECH FEED (15px Text)       */}
          {/* =============================================================== */}
          <section className="lg:col-span-5 flex flex-col bg-[#0b0e14] min-h-[500px] lg:h-[calc(100vh-100px)]">
            <div className="px-6 py-3 border-b border-[#1c2436] bg-[#101522] flex items-center justify-between text-xs">
              <span className="font-editorial text-xs font-bold uppercase tracking-wider text-white">
                Live Speech Transcript
              </span>
              <span className="text-[#8e98ab]">
                {turns.length} utterances
              </span>
            </div>

            {/* Conversation List */}
            <div
              ref={transcriptScrollRef}
              className="flex-1 overflow-y-auto divide-y divide-[#141b29] p-2"
            >
              {turns.length > 0 ? (
                turns.map((t, idx) => {
                  const isReferee =
                    t.tag === "referee" ||
                    t.speaker_name.toLowerCase().includes("referee");
                  return (
                    <div
                      key={idx}
                      className={`p-4 rounded transition-colors ${
                        isReferee
                          ? "bg-[#162033] border-l-2 border-l-[#f59e0b]"
                          : t.tag === "conflict"
                          ? "bg-[#1a1520] border-l-2 border-l-[#f43f5e]"
                          : t.tag === "confirm"
                          ? "bg-[#101f1c] border-l-2 border-l-[#10b981]"
                          : "hover:bg-[#101522] border-l-2 border-l-transparent"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2 mb-1.5 text-xs">
                        <div className="flex items-center gap-2">
                          <span
                            className="font-semibold text-white tracking-tight"
                            dir="auto"
                          >
                            {t.speaker_name}
                          </span>
                          {t.tag_label && (
                            <span
                              className={`text-[11px] font-medium px-2 py-0.5 rounded ${
                                t.tag === "conflict"
                                  ? "bg-[#f43f5e]/15 text-[#f43f5e]"
                                  : t.tag === "confirm"
                                  ? "bg-[#10b981]/15 text-[#10b981]"
                                  : t.tag === "referee"
                                  ? "bg-[#f59e0b]/15 text-[#f59e0b]"
                                  : "bg-[#3b82f6]/15 text-[#60a5fa]"
                              }`}
                            >
                              {t.tag_label}
                            </span>
                          )}
                        </div>

                        <span className="font-mono text-xs text-[#5e6b7d]">
                          {new Date(t.timestamp * 1000).toLocaleTimeString([], {
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </span>
                      </div>

                      {/* Natural Human Reading Font (15px) */}
                      <p
                        dir="auto"
                        className={`font-speech text-[15px] leading-relaxed ${
                          isReferee ? "text-white font-medium" : "text-[#d8e0ec]"
                        }`}
                      >
                        {t.text}
                      </p>
                    </div>
                  );
                })
              ) : (
                <div className="h-full flex flex-col items-center justify-center p-8 text-center space-y-3 text-sm text-[#7d8b9e]">
                  <p>Voice channel is currently silent.</p>
                  <button
                    onClick={() => runInteractiveDemo(selectedScenarioId)}
                    className="px-4 py-2 bg-[#3b82f6] text-white rounded text-xs font-semibold cursor-pointer"
                  >
                    Start Demo Simulation
                  </button>
                </div>
              )}
            </div>

            <div className="px-6 py-2.5 border-t border-[#1c2436] bg-[#101522] text-xs text-[#7d8b9e] flex justify-between">
              <span>Bilingual Code-Switching Active</span>
              <span>Discord E2EE MLS</span>
            </div>
          </section>

          {/* =============================================================== */}
          {/* RIGHT COLUMN: REFEREE STAGE (ONE FOCAL POINT, ZERO NOISE)       */}
          {/* =============================================================== */}
          <section className="lg:col-span-7 flex flex-col bg-[#0b0e14] lg:h-[calc(100vh-100px)] overflow-y-auto">
            {/* Top Stage Bar */}
            <div className="px-6 py-3 border-b border-[#1c2436] bg-[#101522] flex items-center justify-between text-xs">
              <span className="font-editorial text-xs font-bold uppercase tracking-wider text-white">
                Referee Verdict & Resolution
              </span>
              <span className="text-[#8e98ab]">
                {pendingOffer
                  ? "Stage 1: Awaiting Confirmation"
                  : activeDispute
                  ? "Stage 2: Verified Resolution"
                  : "Stage 0: Listening Passively"}
              </span>
            </div>

            {/* ============================================================= */}
            {/* STATE 1: PENDING OFFER («أشوفها؟» / "Do I check?")           */}
            {/* ============================================================= */}
            {pendingOffer ? (
              <div className="p-6 md:p-8 space-y-6 bg-[#101522] border-b border-[#1c2436]">
                <div className="border-l-4 border-l-[#f59e0b] pl-4 space-y-1">
                  <span className="text-xs font-bold uppercase tracking-wider text-[#f59e0b]">
                    Factual Disagreement Detected
                  </span>
                  <h3 className="font-editorial text-xl md:text-2xl font-bold text-white">
                    {pendingOffer.entity}
                  </h3>
                </div>

                {/* Opposing Claims */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="p-4 rounded bg-[#0b0e14] border border-[#1c2436] space-y-1">
                    <span className="text-xs text-[#f43f5e] font-semibold block">
                      {pendingOffer.speaker_a}
                    </span>
                    <p dir="auto" className="text-sm text-[#e2e8f0]">
                      “{pendingOffer.claim_a}”
                    </p>
                  </div>
                  <div className="p-4 rounded bg-[#0b0e14] border border-[#1c2436] space-y-1">
                    <span className="text-xs text-[#3b82f6] font-semibold block">
                      {pendingOffer.speaker_b}
                    </span>
                    <p dir="auto" className="text-sm text-[#e2e8f0]">
                      “{pendingOffer.claim_b}”
                    </p>
                  </div>
                </div>

                {/* Pre-fetch Status */}
                <div className="p-3 bg-[#0b0e14] border border-[#1c2436] rounded flex items-center justify-between text-xs">
                  <span className="text-[#10b981] font-medium flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-[#10b981] animate-pulse" />
                    Web evidence pre-fetched in background ({pendingOffer.prefetch_domain})
                  </span>
                  <span className="text-[#8e98ab]">Voice warm</span>
                </div>

                {/* Big Tactile Consent Button */}
                <div className="space-y-2">
                  <button
                    onClick={handleConfirmOffer}
                    className="w-full py-3.5 px-6 bg-[#f59e0b] hover:bg-[#d97706] text-black font-semibold text-sm rounded transition-colors cursor-pointer flex items-center justify-center gap-2 shadow-lg"
                  >
                    <span>✓ Say &quot;check it&quot; / «شوفها» to verify</span>
                    {offerCountdown > 0 && (
                      <span className="text-xs bg-black/15 px-2 py-0.5 rounded font-mono">
                        Auto in {offerCountdown}s
                      </span>
                    )}
                  </button>
                  <p className="text-xs text-[#8e98ab] text-center">
                    CallWrapped never interrupts uninvited. It only speaks when a participant asks.
                  </p>
                </div>
              </div>
            ) : activeDispute ? (
              /* ============================================================= */
              /* STATE 2: VERIFIED VERDICT (CLEAN, BOLD, AUTHORITATIVE)        */
              /* ============================================================= */
              <div className="divide-y divide-[#1c2436] bg-[#0b0e14]">
                {/* Clean Ground Truth Section */}
                <div className="p-6 md:p-8 space-y-4 bg-[#101522]">
                  <div className="flex items-center justify-between">
                    {activeDispute.status === "REFUSED_PRIVATE" ? (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#f59e0b]/10 text-[#f59e0b] text-xs font-semibold border border-[#f59e0b]/20">
                        <ShieldOff className="w-4 h-4" />
                        <span>Privacy Gate: Lookup Refused</span>
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#10b981]/10 text-[#10b981] text-xs font-semibold border border-[#10b981]/20">
                        <CheckCircle2 className="w-4 h-4" />
                        <span>Verified Ground Truth</span>
                      </span>
                    )}

                    {activeDispute.t_perceived_ms && (
                      <span className="font-mono text-xs text-[#8e98ab]">
                        {activeDispute.t_perceived_ms}ms perceived
                      </span>
                    )}
                  </div>

                  {/* Ground Truth in Bold Editorial Type */}
                  <h2
                    dir="auto"
                    className="font-editorial text-xl md:text-2xl font-bold text-white leading-snug"
                  >
                    {activeDispute.correct_fact}
                  </h2>

                  {/* Source Link */}
                  {activeDispute.source_url && (
                    <div className="pt-1">
                      <a
                        href={activeDispute.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1.5 text-xs text-[#3b82f6] hover:underline"
                      >
                        <span>Official Source: {activeDispute.source_title || "Official Documentation"}</span>
                        <ExternalLink className="w-3.5 h-3.5" />
                      </a>
                    </div>
                  )}
                </div>

                {/* Scoreboard Split: Supported vs Contradicted */}
                <div className="grid grid-cols-1 sm:grid-cols-2 divide-y sm:divide-y-0 sm:divide-x divide-[#1c2436] p-4 bg-[#0b0e14]">
                  {/* Speaker A */}
                  <div className="p-4 space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-semibold text-white">
                        {activeDispute.speaker_a || "Speaker A"}
                      </span>
                      {activeDispute.speaker_a_status === "SUPPORTED" ? (
                        <span className="text-[#10b981] font-semibold flex items-center gap-1">
                          <CheckCircle2 className="w-3.5 h-3.5" /> Supported
                        </span>
                      ) : activeDispute.speaker_a_status === "REFUSED_PRIVATE" ? (
                        <span className="text-[#8e98ab] font-medium">Private</span>
                      ) : (
                        <span className="text-[#f43f5e] font-semibold flex items-center gap-1">
                          <XCircle className="w-3.5 h-3.5" /> Contradicted
                        </span>
                      )}
                    </div>
                    <p dir="auto" className="text-sm text-[#d8e0ec]">
                      “{activeDispute.claim_a}”
                    </p>
                  </div>

                  {/* Speaker B */}
                  <div className="p-4 space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-semibold text-white">
                        {activeDispute.speaker_b || "Speaker B"}
                      </span>
                      {activeDispute.speaker_b_status === "SUPPORTED" ? (
                        <span className="text-[#10b981] font-semibold flex items-center gap-1">
                          <CheckCircle2 className="w-3.5 h-3.5" /> Supported
                        </span>
                      ) : activeDispute.speaker_b_status === "REFUSED_PRIVATE" ? (
                        <span className="text-[#8e98ab] font-medium">Private</span>
                      ) : (
                        <span className="text-[#f43f5e] font-semibold flex items-center gap-1">
                          <XCircle className="w-3.5 h-3.5" /> Contradicted
                        </span>
                      )}
                    </div>
                    <p dir="auto" className="text-sm text-[#d8e0ec]">
                      “{activeDispute.claim_b}”
                    </p>
                  </div>
                </div>

                {/* Spoken Voice Verdict Output */}
                {activeDispute.spoken_intervention && (
                  <div className="p-6 bg-[#0e131f] space-y-3">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-medium text-[#8e98ab] flex items-center gap-2">
                        <Volume2 className="w-4 h-4 text-[#3b82f6]" />
                        <span>Spoken Voice Intervention</span>
                      </span>

                      <div className="flex items-center gap-2">
                        {activeDispute.spoken_intervention_en && (
                          <div className="flex border border-[#1c2436] rounded text-[11px]">
                            <button
                              onClick={() => setSpokenLang("ar")}
                              className={`px-2 py-0.5 rounded-l cursor-pointer ${
                                spokenLang === "ar"
                                  ? "bg-[#3b82f6] text-white font-semibold"
                                  : "text-[#8e98ab]"
                              }`}
                            >
                              AR
                            </button>
                            <button
                              onClick={() => setSpokenLang("en")}
                              className={`px-2 py-0.5 rounded-r cursor-pointer ${
                                spokenLang === "en"
                                  ? "bg-[#3b82f6] text-white font-semibold"
                                  : "text-[#8e98ab]"
                              }`}
                            >
                              EN
                            </button>
                          </div>
                        )}

                        <button
                          onClick={() => handleSpeakVerdict(undefined, spokenLang)}
                          className={`px-3 py-1 rounded text-xs font-semibold border transition-colors cursor-pointer flex items-center gap-1.5 ${
                            isSpeakingVerdict
                              ? "bg-[#10b981]/15 border-[#10b981] text-[#10b981]"
                              : "bg-[#101522] border-[#1c2436] hover:bg-[#161c2c] text-white"
                          }`}
                        >
                          <Volume2 className="w-3.5 h-3.5" />
                          <span>{isSpeakingVerdict ? "Playing..." : "Hear Voice"}</span>
                        </button>
                      </div>
                    </div>

                    <p
                      dir="auto"
                      className="text-base text-white border-l-2 border-[#3b82f6] pl-3 py-0.5"
                    >
                      “
                      {spokenLang === "en" && activeDispute.spoken_intervention_en
                        ? activeDispute.spoken_intervention_en
                        : activeDispute.spoken_intervention}
                      ”
                    </p>
                  </div>
                )}

                {/* Collapsible Decision Trace (Keeps screen clean) */}
                <div className="bg-[#0b0e14]">
                  <button
                    onClick={() => setShowDecisionTrace((v) => !v)}
                    className="w-full px-6 py-3 flex items-center justify-between text-xs text-[#8e98ab] hover:text-white transition-colors cursor-pointer"
                  >
                    <span>
                      How the referee arrived at this verdict ({activeDispute.why_i_spoke?.length || 4} checks)
                    </span>
                    {showDecisionTrace ? (
                      <ChevronUp className="w-4 h-4" />
                    ) : (
                      <ChevronDown className="w-4 h-4" />
                    )}
                  </button>

                  {showDecisionTrace && (
                    <div className="px-6 pb-4 space-y-2 text-xs text-[#a0aec0] pt-1">
                      {(activeDispute.why_i_spoke || []).map((reason, idx) => (
                        <div key={idx} className="flex items-start gap-2">
                          <span className="text-[#3b82f6] font-mono">0{idx + 1}.</span>
                          <span>{reason}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ) : (
              /* ============================================================= */
              /* STATE 0: PASSIVE LISTENING                                    */
              /* ============================================================= */
              <div className="p-8 md:p-12 flex-1 flex flex-col justify-center space-y-6">
                <div className="space-y-2 max-w-lg">
                  <span className="text-xs uppercase font-bold tracking-wider text-[#3b82f6]">
                    Passive Voice Referee Mode
                  </span>
                  <h3 className="font-editorial text-2xl font-bold text-white">
                    Listening silently for factual disagreements.
                  </h3>
                  <p className="text-sm text-[#8e98ab] leading-relaxed">
                    When participants state contradictory facts in voice, CallWrapped queries authoritative web sources in the background and asks out loud:{" "}
                    <strong className="text-white">«أشوفها؟» / &quot;Do I check?&quot;</strong>
                  </p>
                </div>

                <div className="pt-2">
                  <button
                    onClick={() => runInteractiveDemo(selectedScenarioId)}
                    className="px-5 py-2.5 bg-[#3b82f6] hover:bg-[#2563eb] text-white rounded text-sm font-semibold transition-colors cursor-pointer inline-flex items-center gap-2"
                  >
                    <Play className="w-4 h-4 fill-current" />
                    <span>Run Demo Simulation</span>
                  </button>
                </div>
              </div>
            )}

            {/* Quick Fact Record Footer */}
            <div className="mt-auto grid grid-cols-3 divide-x divide-[#1c2436] border-t border-[#1c2436] bg-[#101522] text-xs">
              <div className="px-6 py-3 flex items-center justify-between">
                <span className="text-[#8e98ab]">Verified Facts</span>
                <span className="font-semibold text-[#10b981]">
                  {leaderboard["Verified Claims"]}
                </span>
              </div>
              <div className="px-6 py-3 flex items-center justify-between">
                <span className="text-[#8e98ab]">Contradicted</span>
                <span className="font-semibold text-[#f43f5e]">
                  {leaderboard["Disputed Claims"]}
                </span>
              </div>
              <button
                onClick={() => setActiveTab("wrapped")}
                className="px-6 py-3 flex items-center justify-between hover:bg-[#161c2c] text-[#3b82f6] font-semibold transition-colors cursor-pointer"
              >
                <span>Call Dossier</span>
                <span>View →</span>
              </button>
            </div>
          </section>
        </main>
      ) : (
        /* =================================================================== */
        /* VIEW 2: CALL WRAPPED & SESSION STATS                                */
        /* =================================================================== */
        <main className="flex-1 max-w-[1440px] w-full mx-auto border-x border-b border-[#1c2436] bg-[#0b0e14] divide-y divide-[#1c2436]">
          {/* Header */}
          <div className="p-6 md:p-8 bg-[#101522] flex flex-wrap items-center justify-between gap-4">
            <div>
              <span className="text-xs font-semibold uppercase tracking-wider text-[#3b82f6] flex items-center gap-2">
                <Sparkles className="w-4 h-4" />
                <span>Post-Call Wrapped Report</span>
              </span>
              <h2 className="font-editorial text-2xl md:text-3xl font-bold text-white mt-1">
                Session Intelligence Dossier
              </h2>
            </div>

            <div className="flex items-center gap-3">
              <button
                onClick={handleCopyRecap}
                className="px-4 py-2 bg-[#3b82f6] hover:bg-[#2563eb] text-white text-xs font-semibold rounded transition-colors cursor-pointer flex items-center gap-2"
              >
                {copiedSummary ? (
                  <>
                    <Check className="w-4 h-4" />
                    <span>Copied for Discord</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-4 h-4" />
                    <span>Copy Summary for Discord</span>
                  </>
                )}
              </button>
              <button
                onClick={() => setShowRecapModal(true)}
                className="px-4 py-2 bg-[#101522] hover:bg-[#161c2c] border border-[#1c2436] text-white text-xs font-semibold rounded transition-colors cursor-pointer flex items-center gap-2"
              >
                <Award className="w-4 h-4 text-[#f59e0b]" />
                <span>Open Card</span>
              </button>
            </div>
          </div>

          {/* Key Metric Strip */}
          <div className="grid grid-cols-2 lg:grid-cols-4 divide-y lg:divide-y-0 lg:divide-x divide-[#1c2436] bg-[#0e131f]">
            <div className="p-6">
              <span className="text-xs uppercase font-medium text-[#7d8b9e] block">
                Total Airtime
              </span>
              <span className="font-editorial text-2xl font-bold text-white mt-1 block">
                {formatDurationHuman(analytics.total_talk_seconds)}
              </span>
              <span className="text-xs text-[#3b82f6] mt-0.5 block">
                {speakerEntries.length} active speakers
              </span>
            </div>

            <div className="p-6">
              <span className="text-xs uppercase font-medium text-[#7d8b9e] block">
                Monologue King
              </span>
              <span className="font-editorial text-xl font-bold text-white mt-1 block truncate" dir="auto">
                {analytics.longest_streak?.speaker_name || "—"}
              </span>
              <span className="text-xs text-[#f59e0b] mt-0.5 block font-mono">
                {formatStreakMMSS(analytics.longest_streak?.streak_seconds || 0)} unbroken
              </span>
            </div>

            <div className="p-6">
              <span className="text-xs uppercase font-medium text-[#7d8b9e] block">
                Fact Accuracy
              </span>
              <span className="font-editorial text-2xl font-bold text-white mt-1 block">
                {leaderboard["Verified Claims"]} Verified
              </span>
              <span className="text-xs text-[#f43f5e] mt-0.5 block">
                {leaderboard["Disputed Claims"]} contradicted
              </span>
            </div>

            <div className="p-6">
              <span className="text-xs uppercase font-medium text-[#7d8b9e] block">
                Acoustic Mood
              </span>
              <span className="font-editorial text-2xl font-bold text-white mt-1 block">
                {analytics.total_angry_episodes === 0 ? "Calm" : `${analytics.total_angry_episodes} Spikes`}
              </span>
              <span className="text-xs text-[#8e98ab] mt-0.5 block">
                {analytics.total_angry_episodes === 0 ? "0 frustration spikes" : "Acoustic arousal detected"}
              </span>
            </div>
          </div>

          {/* Speaker Leaderboard */}
          <div className="p-6 md:p-8 space-y-4">
            <h3 className="font-editorial text-lg font-bold text-white">
              Speaker Airtime & Accuracy
            </h3>
            {speakerEntries.length > 0 ? (
              <div className="divide-y divide-[#1c2436] border border-[#1c2436] rounded">
                {speakerEntries.map((s) => {
                  const pct =
                    analytics.total_talk_seconds > 0
                      ? (s.talk_seconds / analytics.total_talk_seconds) * 100
                      : 0;
                  const acc = leaderboard.Speakers?.[s.speaker_name] || {
                    turns: 0,
                    verified: 0,
                    refuted: 0,
                  };
                  return (
                    <div key={s.speaker_name} className="p-4 bg-[#101522] space-y-2">
                      <div className="flex items-center justify-between text-sm">
                        <span className="font-medium text-white" dir="auto">
                          {s.speaker_name}
                        </span>
                        <div className="flex items-center gap-4 text-xs font-mono">
                          <span className="text-[#10b981]">✓ {acc.verified} True</span>
                          <span className="text-[#f43f5e]">✕ {acc.refuted} False</span>
                          <span className="text-[#8e98ab]">{formatDurationHuman(s.talk_seconds)}</span>
                        </div>
                      </div>
                      <div className="h-2 w-full bg-[#161c2c] rounded-full overflow-hidden">
                        <div
                          className="h-full bg-[#3b82f6] rounded-full"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-sm text-[#8e98ab]">No speaker statistics available yet.</p>
            )}
          </div>

          {/* Dispute Log */}
          <DisputesPanel disputes={disputes} />
        </main>
      )}

      {/* Full Modal */}
      <CallWrappedModal
        isOpen={showRecapModal}
        onClose={() => setShowRecapModal(false)}
        analytics={analytics}
        verifiedCount={leaderboard["Verified Claims"]}
        disputedCount={leaderboard["Disputed Claims"]}
      />
    </div>
  );
}
