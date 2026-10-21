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
    label: "01 / RTX 5070 VRAM",
    shortTitle: "NVIDIA RTX 5070 VRAM Capacity",
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
        tag_label: "CLAIM: 16GB VRAM",
      },
      {
        speaker_name: "Mostafa",
        text: "No, the 5070 is 12 gigs. The Ti is 16.",
        timestamp: Date.now() / 1000 - 37,
        stt_ms: 258,
        tag: "conflict",
        tag_label: "CONFLICT: 12GB vs 16GB",
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
      entity: "NVIDIA GeForce RTX 5070 VRAM",
      speaker_a: "2xDanger",
      claim_a: "RTX 5070 launches with 16GB VRAM",
      speaker_b: "Mostafa",
      claim_b: "RTX 5070 is 12GB GDDR7 (only the 5070 Ti is 16GB)",
      prompt_ar: "أشوفها؟",
      prompt_en: "Do I check?",
      prefetch_domain: "nvidia.com/en-us/geforce/graphics-cards/50-series",
      prefetch_ready: true,
      countdown_sec: 6,
    },
    confirmTurn: {
      speaker_name: "Mostafa",
      text: "شوفها يلا — check it!",
      timestamp: Date.now() / 1000 - 31,
      stt_ms: 210,
      tag: "confirm",
      tag_label: "CONSENT GRANTED",
    },
    postTurns: [
      {
        speaker_name: "CallWrapped Referee",
        text: "توضيح: كارت RTX 5070 نازل بـ 12 جيجا GDDR7، والـ 5070 Ti هو اللي بـ 16 جيجا.",
        timestamp: Date.now() / 1000 - 30,
        stt_ms: 0,
        tag: "referee",
        tag_label: "VERIFIED VERDICT",
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
        tag: "loud",
        tag_label: "+2.8σ ACOUSTIC SPIKE",
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
      disputed_attribute: "NVIDIA GeForce RTX 5070 — Memory Capacity",
      speaker_a: "2xDanger",
      claim_a: "Bro, I'm pretty sure the RTX 5070 has 16 gigs of VRAM.",
      speaker_a_status: "CONTRADICTED",
      speaker_b: "Mostafa",
      claim_b: "No, the 5070 is 12 gigs. The Ti is 16.",
      speaker_b_status: "SUPPORTED",
      winner: "Mostafa",
      loser: "2xDanger",
      correct_fact:
        "NVIDIA GeForce RTX 5070 ships with 12GB GDDR7 memory (192-bit bus). Only the RTX 5070 Ti carries 16GB GDDR7 (256-bit bus).",
      confidence: 99,
      evidence_strength: "TIER-1 OFFICIAL",
      status: "resolved",
      source_url:
        "https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5070-family/",
      source_title: "NVIDIA GeForce RTX 5070 Official Specifications",
      spoken_intervention:
        "توضيح: كارت RTX 5070 نازل بـ 12 جيجا GDDR7، والـ 5070 Ti هو اللي بـ 16 جيجا. المصدر الرسمي على الداشبورد.",
      spoken_intervention_en:
        "Quick check: The RTX 5070 ships with 12GB of GDDR7 memory, while the 5070 Ti has 16GB. Official NVIDIA specs are linked on the dashboard.",
      t_perceived_ms: 1164,
      why_i_spoke: [
        "Factual claim extracted regarding GPU VRAM specification",
        "Direct contradiction between 2xDanger (16GB) and Mostafa (12GB)",
        "Pre-fetched Tier-1 manufacturer spec sheet (nvidia.com) during consent offer",
        "Explicit voice confirmation («شوفها» / 'check it') received from Mostafa",
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
      source_name: "NVIDIA GeForce Official Specifications",
      source_url:
        "https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5070-family/",
      evidence_excerpt:
        "GeForce RTX 5070: 12GB GDDR7 (192-bit). GeForce RTX 5070 Ti: 16GB GDDR7 (256-bit).",
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
    label: "02 / UCL TITLES",
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
        tag_label: "CLAIM: 14 UCL TITLES",
      },
      {
        speaker_name: "Remi",
        text: "لا يا ابني بقوا 15 بعد نهائي ويمبلي قدام دورتموند!",
        timestamp: Date.now() / 1000 - 35,
        stt_ms: 238,
        tag: "conflict",
        tag_label: "CONFLICT: 14 vs 15",
      },
    ],
    offer: {
      offer_id: "off_ucl15",
      entity: "Real Madrid UEFA Champions League Titles",
      speaker_a: "Mostafa",
      claim_a: "Real Madrid has 14 Champions League titles",
      speaker_b: "Remi",
      claim_b: "Real Madrid has 15 titles after beating Dortmund at Wembley",
      prompt_ar: "أشوفها؟",
      prompt_en: "Do I check?",
      prefetch_domain: "uefa.com/uefachampionsleague/history",
      prefetch_ready: true,
      countdown_sec: 6,
    },
    confirmTurn: {
      speaker_name: "Remi",
      text: "شوفها كده يا حكم",
      timestamp: Date.now() / 1000 - 32,
      stt_ms: 195,
      tag: "confirm",
      tag_label: "CONSENT GRANTED",
    },
    postTurns: [
      {
        speaker_name: "CallWrapped Referee",
        text: "توضيح: ريال مدريد حقق البطولة رقم 15 في تاريخه بعد الفوز على دورتموند 2-0 في ويمبلي.",
        timestamp: Date.now() / 1000 - 30,
        stt_ms: 0,
        tag: "referee",
        tag_label: "VERIFIED VERDICT",
      },
    ],
    resolvedDispute: {
      event_id: "evt_ucl_15",
      timestamp: Date.now() / 1000 - 30,
      disputed_attribute: "Real Madrid — Total UEFA Champions League Titles",
      speaker_a: "Mostafa",
      claim_a: "ريال مدريد معاه 14 بطولة دوري أبطال أوروبا",
      speaker_a_status: "CONTRADICTED",
      speaker_b: "Remi",
      claim_b: "لا يا ابني بقوا 15 بعد نهائي ويمبلي قدام دورتموند",
      speaker_b_status: "SUPPORTED",
      winner: "Remi",
      loser: "Mostafa",
      correct_fact:
        "Real Madrid holds 15 UEFA Champions League titles, winning their 15th trophy on June 1, 2024 against Borussia Dortmund (2–0) at Wembley Stadium.",
      confidence: 99,
      evidence_strength: "TIER-1 OFFICIAL",
      status: "resolved",
      source_url: "https://www.uefa.com/uefachampionsleague/history/winners/",
      source_title: "UEFA Champions League Official History & Winners",
      spoken_intervention:
        "توضيح: ريال مدريد حقق البطولة رقم 15 في تاريخه بعد الفوز على بوروسيا دورتموند 2-0 في نهائي ويمبلي.",
      spoken_intervention_en:
        "Quick check: Real Madrid has 15 Champions League titles after defeating Borussia Dortmund 2-0 at Wembley.",
      t_perceived_ms: 1068,
      why_i_spoke: [
        "Numerical sports record dispute detected (14 vs 15 trophies)",
        "Authoritative source verified via uefa.com",
        "Confirmed by Remi in voice («شوفها»)",
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
    label: "03 / PRIVACY VETO",
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
        tag_label: "PRIVATE ENTITY VETO",
      },
    ],
    offer: null,
    postTurns: [],
    resolvedDispute: {
      event_id: "evt_privacy_refusal",
      timestamp: Date.now() / 1000 - 14,
      disputed_attribute: "Private Person Claim (أحمد — Personal Salary)",
      speaker_a: "2xDanger",
      claim_a: "أحمد صاحبنا قبض مرتب 80 ألف الشهر اللي فات",
      speaker_a_status: "REFUSED_PRIVATE",
      speaker_b: "Mostafa",
      claim_b: "لا هو قالي مرتبه 35 ألف بس",
      speaker_b_status: "REFUSED_PRIVATE",
      correct_fact:
        "Private claim — no web lookup or voice intervention performed. CallWrapped strictly ignores disputes about private individuals.",
      confidence: 100,
      evidence_strength: "PRIVACY GATE",
      status: "REFUSED_PRIVATE",
      why_i_spoke: [
        "FastGate classified target entity as PRIVATE INDIVIDUAL",
        "External web search blocked to prevent PII leakage or hallucination",
        "Silent pass — zero voice interruption",
      ],
    },
    disputeCard: {
      dispute_id: "disp_privacy_01",
      speaker_a: "2xDanger",
      claim_a: "أحمد صاحبنا قبض مرتب 80 ألف الشهر اللي فات",
      speaker_b: "Mostafa",
      claim_b: "لا هو قالي مرتبه 35 ألف بس",
      disputed_attribute: "Private Entity: أحمد",
      status: "refused_private",
      refusal_reason: "Private individual claim — zero web lookup performed",
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

const SPEAKER_ACCENTS: Record<string, string> = {
  Mostafa: "text-[#60a5fa] border-l-[#3b82f6]",
  "2xDanger": "text-[#f87171] border-l-[#ef4444]",
  Remi: "text-[#34d399] border-l-[#10b981]",
  "CallWrapped Referee": "text-[#fbbf24] border-l-[#f59e0b]",
  CallWrapped: "text-[#fbbf24] border-l-[#f59e0b]",
};

export default function CallWrappedDashboard() {
  const [activeTab, setActiveTab] = useState<"referee" | "wrapped">("referee");
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>("rtx5070");
  const [isConnected, setIsConnected] = useState(false);
  const [connectionType, setConnectionType] = useState<"ws" | "poll" | "demo">("demo");
  const [showRecapModal, setShowRecapModal] = useState(false);
  const [showDecisionTrace, setShowDecisionTrace] = useState(false);
  const [spokenLang, setSpokenLang] = useState<"ar" | "en">("ar");
  const [isSpeakingVerdict, setIsSpeakingVerdict] = useState(false);
  const [copiedSummary, setCopiedSummary] = useState(false);
  const [playingClip, setPlayingClip] = useState<string | null>(null);

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
  const [speechModel, setSpeechModel] = useState<string>("Universal-3.5 Pro");
  const [discordInviteUrl, setDiscordInviteUrl] = useState<string>(
    "https://discord.com/oauth2/authorize?client_id=1550926707517558864&permissions=36718592&scope=bot%20applications.commands"
  );
  const [factCheckModeBadge, setFactCheckModeBadge] = useState<string>("REFEREE: ARMED");

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
      // On public static hosts (like Vercel) without NEXT_PUBLIC_BACKEND_URL,
      // avoid hanging on non-existent :8000 port
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

  // Speak verdict using browser Web Speech API (works on Vercel with zero backend!)
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
    utter.rate = 1.02;
    utter.onstart = () => setIsSpeakingVerdict(true);
    utter.onend = () => setIsSpeakingVerdict(false);
    utter.onerror = () => setIsSpeakingVerdict(false);
    setIsSpeakingVerdict(true);
    window.speechSynthesis.speak(utter);
  };

  const handlePlayAudioEvidence = (clip: string) => {
    try {
      const { http } = getBackendBase();
      const url = `${http}/api/audio-evidence/${clip}`;
      const audio = new Audio(url);
      setPlayingClip(clip);
      audio.onended = () => setPlayingClip(null);
      audio.onerror = () => setPlayingClip(null);
      audio.play().catch(() => setPlayingClip(null));
    } catch {
      setPlayingClip(null);
    }
  };

  // Instant snapshot loader (Skip to Verdict)
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

  // Interactive 2-Stage Simulation Runner
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

      // 1. Stream pre-conflict utterances
      for (let i = 0; i < scenario.preTurns.length; i++) {
        if (simAbortRef.current !== runId) return;
        const turn = scenario.preTurns[i];
        setPipelineStage(turn.tag === "claim" || turn.tag === "conflict" ? "claim" : "asr");
        setLatency((prev) => ({
          ...prev,
          stt_ms: turn.stt_ms || 260,
          llm_ms: turn.tag ? 194 : prev.llm_ms,
        }));
        setTurns((prev) => [...prev, { ...turn, timestamp: Date.now() / 1000 }]);
        await sleep(i === 0 ? 450 : 750);
      }

      if (simAbortRef.current !== runId) return;

      // 2. If scenario has a 2-Stage Consent Offer, trigger Stage 1 ("Do I check?" / «أشوفها؟»)
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

        // Wait for either user clicking "Check It / شوفها" OR auto-confirm countdown
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

        // 3. User confirmed! Append confirmation turn
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

      // 4. Deliver Stage 2 Verified Verdict
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

      // 5. Stream post-verdict reactions
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

  // Manual click on "CHECK IT / شوفها" during Stage 1
  const handleConfirmOffer = () => {
    if (consentResolveRef.current) {
      consentResolveRef.current();
    } else if (pendingOffer) {
      applyScenarioInstant(selectedScenarioId);
    }
  };

  // Dismiss offer without checking
  const handleDismissOffer = () => {
    simAbortRef.current += 1;
    consentResolveRef.current = null;
    setPendingOffer(null);
    setOfferCountdown(0);
    setPipelineStage("idle");
    setIsSimulating(false);
    setDisputes((prev) =>
      prev.map((d) =>
        d.status === "offered"
          ? { ...d, status: "expired", refusal_reason: "Offer dismissed by user" }
          : d
      )
    );
  };

  // Connect to local backend if available; otherwise run interactive demo
  useEffect(() => {
    let isMounted = true;
    let pollInterval: NodeJS.Timeout | null = null;
    const { http, ws, canConnect } = getBackendBase();

    if (!canConnect) {
      setConnectionType("demo");
      if (!hasInitializedRef.current) {
        hasInitializedRef.current = true;
        runInteractiveDemo("rtx5070");
      }
      return;
    }

    const applyAnalytics = (rawAnalytics: any) => {
      if (!rawAnalytics) return;
      const mergedSpeakers: Record<string, SpeakerAnalytics> = {};
      if (rawAnalytics.speakers) {
        for (const [name, spk] of Object.entries(
          rawAnalytics.speakers as Record<string, any>
        )) {
          mergedSpeakers[name] = {
            speaker_name: spk.speaker_name || name,
            talk_seconds: Number(spk.talk_seconds || 0),
            longest_streak_seconds: Number(spk.longest_streak_seconds || 0),
            angry_episodes: Number(spk.angry_episodes || 0),
            anger_evidence:
              spk.anger_evidence || spk.first_anger_quote || undefined,
            anger_episodes_history: spk.anger_episodes_history || [],
            vulgarity_count: Number(spk.vulgarity_count || 0),
            vulgarity_terms: Array.isArray(spk.vulgarity_terms)
              ? spk.vulgarity_terms
              : [],
            banter_count: Number(spk.banter_count || 0),
            banter_terms: Array.isArray(spk.banter_terms) ? spk.banter_terms : [],
          };
        }
      }

      setAnalytics({
        topic_totals: rawAnalytics.topic_totals || {},
        speakers: mergedSpeakers,
        total_talk_seconds: Number(rawAnalytics.total_talk_seconds || 0),
        total_angry_episodes: Number(rawAnalytics.total_angry_episodes || 0),
        total_vulgarity_count: Number(rawAnalytics.total_vulgarity_count || 0),
        total_banter_count: Number(rawAnalytics.total_banter_count || 0),
        longest_streak: {
          speaker_name: rawAnalytics.longest_streak?.speaker_name || null,
          streak_seconds: Number(rawAnalytics.longest_streak?.streak_seconds || 0),
        },
      });
    };

    const applyBackendState = (d: any) => {
      if (!d) return;
      if (d.discord_invite_url) setDiscordInviteUrl(d.discord_invite_url);
      if (d.fact_check_mode_badge) setFactCheckModeBadge(d.fact_check_mode_badge);
      if (d.latency) setLatency(d.latency);
      if (Array.isArray(d.turns) && d.turns.length > 0) setTurns(d.turns);
      if (d.active_dispute) setActiveDispute(d.active_dispute);
      if (Array.isArray(d.disputes) && d.disputes.length > 0)
        setDisputes(d.disputes);
      if (d.leaderboard) setLeaderboard(d.leaderboard);
      if (d.analytics) applyAnalytics(d.analytics);
      if (d.active_offer) {
        setPendingOffer({
          offer_id: d.active_offer.offer_id || "live_offer",
          entity: d.active_offer.entity || "Factual Dispute",
          speaker_a: d.active_offer.speaker_a || "Speaker A",
          claim_a: d.active_offer.claim_a || "",
          speaker_b: d.active_offer.speaker_b || "Speaker B",
          claim_b: d.active_offer.claim_b || "",
          prompt_ar: "أشوفها؟",
          prompt_en: "Do I check?",
          prefetch_domain: "live web sources",
          prefetch_ready: true,
          countdown_sec: Math.round(d.active_offer.expires_in_seconds || 30),
        });
      }
    };

    const fetchLiveSnapshot = async () => {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 1200);
      try {
        const resLive = await fetch(`${http}/api/live`, {
          signal: controller.signal,
        });
        clearTimeout(timeout);
        if (resLive.ok) {
          const data = await resLive.json();
          if (isMounted) {
            setIsConnected(true);
            if (connectionType === "demo") setConnectionType("poll");
            const hasLiveActivity =
              (data.turns && data.turns.length > 0) ||
              data.active_dispute ||
              (data.disputes && data.disputes.length > 0);
            if (hasLiveActivity) {
              hasInitializedRef.current = true;
              applyBackendState(data);
            } else if (!hasInitializedRef.current) {
              hasInitializedRef.current = true;
              runInteractiveDemo("rtx5070");
            }
          }
        }
      } catch {
        clearTimeout(timeout);
        if (isMounted) {
          setIsConnected(false);
          setConnectionType("demo");
          if (!hasInitializedRef.current) {
            hasInitializedRef.current = true;
            runInteractiveDemo("rtx5070");
          }
        }
      }
    };

    const connectWebSocket = () => {
      try {
        const socket = new WebSocket(`${ws}/api/ws`);
        wsRef.current = socket;

        socket.onopen = () => {
          if (!isMounted) return;
          setIsConnected(true);
          setConnectionType("ws");
        };

        socket.onmessage = (event) => {
          if (!isMounted) return;
          try {
            const msg = JSON.parse(event.data);
            if (msg.type === "initial_state" && msg.data) {
              const hasLiveActivity =
                (msg.data.turns && msg.data.turns.length > 0) ||
                msg.data.active_dispute;
              if (hasLiveActivity) {
                simAbortRef.current += 1;
                setIsSimulating(false);
                applyBackendState(msg.data);
              }
            } else if (msg.live_state) {
              simAbortRef.current += 1;
              setIsSimulating(false);
              applyBackendState(msg.live_state);
            }
            if (msg.analytics) {
              applyAnalytics(msg.analytics);
            }
          } catch {
            // ignore malformed frame
          }
        };

        socket.onclose = () => {
          if (!isMounted) return;
          setIsConnected(false);
        };
      } catch {
        // fallback to demo/poll
      }
    };

    fetchLiveSnapshot();
    connectWebSocket();
    pollInterval = setInterval(fetchLiveSnapshot, 4000);

    return () => {
      isMounted = false;
      if (pollInterval) clearInterval(pollInterval);
      if (wsRef.current) wsRef.current.close();
    };
  }, [getBackendBase, runInteractiveDemo]);

  const handleReset = async () => {
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
    const { http, canConnect } = getBackendBase();
    if (canConnect) {
      try {
        await fetch(`${http}/api/reset`, { method: "POST" });
      } catch {
        // ignore
      }
    }
  };

  // Derived analytics for Call Wrapped view
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
  const angrySpeakers = speakerEntries.filter((s) => s.angry_episodes > 0);

  const handleCopyRecap = () => {
    const topTopic = topicalEntries[0]?.[0]?.toUpperCase() || "GENERAL";
    const text =
      `**CALLWRAPPED // SESSION DOSSIER**\n` +
      `• **Airtime:** ${formatDurationHuman(analytics.total_talk_seconds)} (${speakerEntries.length} speakers)\n` +
      `• **Monologue King:** ${analytics.longest_streak?.speaker_name || "—"} (${formatDurationHuman(analytics.longest_streak?.streak_seconds || 0)})\n` +
      `• **Fact Checks:** ${leaderboard["Verified Claims"]} verified · ${leaderboard["Disputed Claims"]} refuted\n` +
      `• **Top Topic:** ${topTopic}\n` +
      `• **Acoustic Spikes:** ${analytics.total_angry_episodes}`;
    navigator.clipboard.writeText(text);
    setCopiedSummary(true);
    setTimeout(() => setCopiedSummary(false), 2000);
  };

  return (
    <div className="min-h-screen bg-[#090a0d] text-[#e6e8ee] flex flex-col selection:bg-[#3b82f6] selection:text-white">
      {/* =================================================================== */}
      {/* 1. SHARP ARCHITECTURAL COMMAND BAR                                  */}
      {/* =================================================================== */}
      <header className="border-b border-[#1c2029] bg-[#090a0d]/95 backdrop-blur sticky top-0 z-40 px-4 md:px-6 h-14 flex items-center justify-between gap-4">
        {/* Brand Identity */}
        <div className="flex items-center gap-4 min-w-0">
          <div className="flex items-center gap-2.5">
            <div className="w-2.5 h-2.5 bg-[#3b82f6]" />
            <span className="font-display font-bold text-base tracking-tight text-white">
              CALLWRAPPED
            </span>
            <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[#7e8694] hidden sm:inline">
              // VOICE REFEREE
            </span>
          </div>

          <div className="hidden lg:flex items-center gap-2 pl-4 border-l border-[#1c2029] font-mono text-[11px]">
            <span
              className={`w-1.5 h-1.5 ${
                isSimulating
                  ? "bg-[#f59e0b] animate-ping"
                  : isConnected
                  ? "bg-[#10b981]"
                  : "bg-[#3b82f6]"
              }`}
            />
            <span className="text-[#9aa2b1] uppercase tracking-wider">
              {isSimulating
                ? "LIVE SIMULATION RUNNING"
                : isConnected
                ? "DISCORD VOICE LINKED"
                : "INTERACTIVE DEMO READY"}
            </span>
          </div>
        </div>

        {/* Center View Switcher: Most Important Stuff First */}
        <nav className="flex items-center border border-[#1c2029] bg-[#0e1015] p-0.5 font-mono text-xs">
          <button
            onClick={() => setActiveTab("referee")}
            className={`px-3.5 py-1.5 font-semibold uppercase tracking-wider transition-colors cursor-pointer flex items-center gap-2 ${
              activeTab === "referee"
                ? "bg-[#191d26] text-white border-b-2 border-[#3b82f6]"
                : "text-[#7e8694] hover:text-[#e6e8ee]"
            }`}
          >
            <span>01 / LIVE REFEREE</span>
            {pendingOffer && (
              <span className="px-1.5 py-0.2 bg-[#f59e0b] text-black font-bold text-[10px]">
                OFFER
              </span>
            )}
          </button>
          <button
            onClick={() => setActiveTab("wrapped")}
            className={`px-3.5 py-1.5 font-semibold uppercase tracking-wider transition-colors cursor-pointer flex items-center gap-2 ${
              activeTab === "wrapped"
                ? "bg-[#191d26] text-white border-b-2 border-[#3b82f6]"
                : "text-[#7e8694] hover:text-[#e6e8ee]"
            }`}
          >
            <span>02 / CALL WRAPPED</span>
            {analytics.total_talk_seconds > 0 && (
              <span className="text-[10px] text-[#3b82f6]">
                [{formatDurationHuman(analytics.total_talk_seconds)}]
              </span>
            )}
          </button>
        </nav>

        {/* Right Controls */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => runInteractiveDemo(selectedScenarioId)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#10b981] hover:bg-[#059669] text-black font-mono text-xs font-bold uppercase tracking-wider transition-colors cursor-pointer"
            title="Play 2-Stage Interactive Call Simulation"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
            <span className="hidden sm:inline">
              {isSimulating ? "Restart Demo" : "Run Demo"}
            </span>
          </button>

          {isSimulating && (
            <button
              onClick={() => applyScenarioInstant(selectedScenarioId)}
              className="flex items-center gap-1 px-2.5 py-1.5 bg-[#13161c] hover:bg-[#1c2029] border border-[#2a303c] text-[#e6e8ee] font-mono text-xs font-semibold uppercase tracking-wider transition-colors cursor-pointer"
              title="Skip animation and jump straight to resolved verdict"
            >
              <FastForward className="w-3.5 h-3.5 text-[#f59e0b]" />
              <span className="hidden md:inline">Skip</span>
            </button>
          )}

          <button
            onClick={handleReset}
            className="p-1.5 bg-[#0e1015] hover:bg-[#191d26] border border-[#1c2029] text-[#7e8694] hover:text-white transition-colors cursor-pointer"
            title="Clear Session"
          >
            <RotateCcw className="w-4 h-4" />
          </button>

          <a
            href={discordInviteUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="hidden md:flex items-center gap-1.5 px-3 py-1.5 bg-[#3b82f6] hover:bg-[#2563eb] text-white font-mono text-xs font-bold uppercase tracking-wider transition-colors"
          >
            <span>+ Discord</span>
          </a>
        </div>
      </header>

      {/* =================================================================== */}
      {/* 2. SINGLE-LINE TELEMETRY TICKER                                     */}
      {/* =================================================================== */}
      <PipelineFlow
        latency={latency}
        speechModel={speechModel}
        activeStage={pipelineStage}
      />

      {/* =================================================================== */}
      {/* 3. SCENARIO PICKER BAR (CLEAN & IMMEDIATE FOR VERCEL VISITORS)       */}
      {/* =================================================================== */}
      <div className="border-b border-[#1c2029] bg-[#0e1015] px-4 md:px-6 py-2 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 overflow-x-auto">
          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-[#7e8694] mr-1 shrink-0">
            SCENARIO:
          </span>
          {DEMO_SCENARIOS.map((sc) => {
            const active = selectedScenarioId === sc.id;
            return (
              <button
                key={sc.id}
                onClick={() => runInteractiveDemo(sc.id)}
                className={`px-2.5 py-1 font-mono text-[11px] font-semibold uppercase tracking-wider border transition-colors cursor-pointer shrink-0 ${
                  active
                    ? "border-[#3b82f6] bg-[#3b82f6]/15 text-white"
                    : "border-[#1c2029] bg-[#090a0d] text-[#7e8694] hover:text-[#e6e8ee] hover:border-[#2a303c]"
                }`}
              >
                {sc.label}
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-4 font-mono text-[11px] text-[#7e8694]">
          <span className="hidden sm:inline">
            CONSENT GATE:{" "}
            <strong className="text-[#e6e8ee]">«أشوفها؟» / &quot;DO I CHECK?&quot;</strong>
          </span>
          <button
            onClick={() => applyScenarioInstant(selectedScenarioId)}
            className="text-[#3b82f6] hover:underline uppercase text-[10px] font-bold tracking-wider cursor-pointer"
          >
            [Instant Snapshot →]
          </button>
        </div>
      </div>

      {/* =================================================================== */}
      {/* 4. MAIN WORKSPACE                                                   */}
      {/* =================================================================== */}
      {activeTab === "referee" ? (
        <main className="flex-1 max-w-[1440px] w-full mx-auto grid grid-cols-1 lg:grid-cols-12 lg:divide-x divide-[#1c2029] border-x border-[#1c2029]">
          {/* =============================================================== */}
          {/* LEFT PANE (5 COLS): CLEAN BORDERLESS VOICE STREAM               */}
          {/* =============================================================== */}
          <section className="lg:col-span-5 flex flex-col bg-[#090a0d] min-h-[540px] lg:h-[calc(100vh-134px)]">
            {/* Stream Header */}
            <div className="px-5 py-3 border-b border-[#1c2029] bg-[#0c0e13] flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Radio
                  className={`w-3.5 h-3.5 ${
                    isSimulating
                      ? "text-[#ef4444] animate-pulse"
                      : "text-[#10b981]"
                  }`}
                />
                <h2 className="font-mono text-xs font-bold uppercase tracking-[0.14em] text-[#e6e8ee]">
                  VOICE CHANNEL STREAM
                </h2>
              </div>
              <span className="font-mono text-[11px] text-[#7e8694]">
                {turns.length} TURNS • EN/AR
              </span>
            </div>

            {/* Utterance Feed (Flat, scannable rows — zero nested card bloat) */}
            <div
              ref={transcriptScrollRef}
              className="flex-1 overflow-y-auto divide-y divide-[#13161f]"
            >
              {turns.length > 0 ? (
                turns.map((t, idx) => {
                  const speakerStyle =
                    SPEAKER_ACCENTS[t.speaker_name] ||
                    "text-[#e6e8ee] border-l-[#3b82f6]";
                  const isReferee =
                    t.tag === "referee" ||
                    t.speaker_name.toLowerCase().includes("referee") ||
                    t.speaker_name.toLowerCase().includes("callwrapped");

                  return (
                    <div
                      key={idx}
                      className={`px-5 py-3.5 transition-colors border-l-2 ${speakerStyle} ${
                        isReferee
                          ? "bg-[#f59e0b]/[0.06]"
                          : t.tag === "conflict"
                          ? "bg-[#ef4444]/[0.05]"
                          : t.tag === "confirm"
                          ? "bg-[#10b981]/[0.05]"
                          : "hover:bg-[#0e1015]"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <div className="flex items-center gap-2">
                          <span
                            className="font-mono text-xs font-bold tracking-tight"
                            dir="auto"
                          >
                            {t.speaker_name}
                          </span>
                          {t.tag_label && (
                            <span
                              className={`font-mono text-[9px] font-bold px-1.5 py-0.5 uppercase tracking-wider border ${
                                t.tag === "conflict"
                                  ? "border-[#ef4444]/40 bg-[#ef4444]/15 text-[#f87171]"
                                  : t.tag === "claim"
                                  ? "border-[#3b82f6]/40 bg-[#3b82f6]/15 text-[#60a5fa]"
                                  : t.tag === "confirm"
                                  ? "border-[#10b981]/40 bg-[#10b981]/15 text-[#34d399]"
                                  : t.tag === "referee"
                                  ? "border-[#f59e0b]/40 bg-[#f59e0b]/15 text-[#fbbf24]"
                                  : "border-[#ef4444]/40 bg-[#ef4444]/15 text-[#f87171]"
                              }`}
                            >
                              {t.tag_label}
                            </span>
                          )}
                        </div>

                        <div className="flex items-center gap-2 font-mono text-[10px] text-[#525866]">
                          {t.stt_ms && t.stt_ms > 0 ? (
                            <span>{t.stt_ms}ms</span>
                          ) : null}
                          <span>
                            {new Date(t.timestamp * 1000).toLocaleTimeString(
                              [],
                              {
                                hour: "2-digit",
                                minute: "2-digit",
                                second: "2-digit",
                              }
                            )}
                          </span>
                        </div>
                      </div>

                      <p
                        dir="auto"
                        className={`text-sm leading-relaxed ${
                          isReferee
                            ? "text-white font-medium"
                            : "text-[#d0d5e0]"
                        }`}
                      >
                        {t.text}
                      </p>
                    </div>
                  );
                })
              ) : (
                <div className="h-full flex flex-col items-center justify-center p-8 text-center space-y-3">
                  <span className="font-mono text-xs uppercase tracking-[0.16em] text-[#525866]">
                    NO ACTIVE VOICE STREAM
                  </span>
                  <p className="text-xs text-[#7e8694] max-w-xs">
                    Start the interactive simulation or connect your Discord
                    voice channel to stream live bilingual utterances.
                  </p>
                  <button
                    onClick={() => runInteractiveDemo(selectedScenarioId)}
                    className="mt-2 px-4 py-2 bg-[#3b82f6] hover:bg-[#2563eb] text-white font-mono text-xs font-bold uppercase tracking-wider cursor-pointer"
                  >
                    ▶ Start Voice Simulation
                  </button>
                </div>
              )}
            </div>

            {/* Stream Footer */}
            <div className="px-5 py-2.5 border-t border-[#1c2029] bg-[#0c0e13] flex items-center justify-between font-mono text-[10px] text-[#68707e]">
              <span>ASR: ASSEMBLYAI {speechModel.toUpperCase()}</span>
              <span>DAVE E2EE DECRYPTED</span>
            </div>
          </section>

          {/* =============================================================== */}
          {/* RIGHT PANE (7 COLS): THE REFEREE STAGE (FOCUSED & UNCLUTTERED)  */}
          {/* =============================================================== */}
          <section className="lg:col-span-7 flex flex-col bg-[#090a0d] lg:h-[calc(100vh-134px)] overflow-y-auto">
            {/* Stage Header */}
            <div className="px-6 py-3 border-b border-[#1c2029] bg-[#0c0e13] flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <ShieldCheck className="w-4 h-4 text-[#3b82f6]" />
                <h2 className="font-mono text-xs font-bold uppercase tracking-[0.14em] text-[#e6e8ee]">
                  REFEREE ARBITRATION STAGE
                </h2>
              </div>
              <span className="font-mono text-[10px] uppercase tracking-wider text-[#7e8694]">
                {pendingOffer
                  ? "STAGE 1 // AWAITING CONSENT"
                  : activeDispute
                  ? "STAGE 2 // VERDICT LOCKED"
                  : "STAGE 0 // PASSIVE LISTENING"}
              </span>
            </div>

            {/* ============================================================= */}
            {/* STATE B: STAGE 1 — TWO-STAGE CONSENT OFFER («أشوفها؟»)        */}
            {/* ============================================================= */}
            {pendingOffer ? (
              <div className="p-6 md:p-8 space-y-6 border-b border-[#1c2029] bg-[#0e1015]">
                {/* Top Alert Strip */}
                <div className="flex flex-wrap items-center justify-between gap-4 border-l-4 border-[#f59e0b] pl-4 py-1">
                  <div>
                    <div className="font-mono text-[11px] font-bold uppercase tracking-[0.16em] text-[#f59e0b]">
                      STAGE 1 // FACTUAL CONTRADICTION DETECTED
                    </div>
                    <h3 className="text-xl md:text-2xl font-bold text-white font-display mt-0.5">
                      {pendingOffer.entity}
                    </h3>
                  </div>

                  <div className="text-right font-mono">
                    <span className="text-[10px] uppercase text-[#7e8694] block">
                      SPOKEN PROMPT IN VOICE
                    </span>
                    <span className="text-base font-bold text-[#f59e0b]">
                      «{pendingOffer.prompt_ar}» / &quot;{pendingOffer.prompt_en}&quot;
                    </span>
                  </div>
                </div>

                {/* Conflicting Claims Split */}
                <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-[#1c2029] border border-[#1c2029] bg-[#090a0d]">
                  <div className="p-5 space-y-2">
                    <div className="flex items-center justify-between font-mono text-[11px]">
                      <span className="font-bold text-[#f87171]">
                        {pendingOffer.speaker_a}
                      </span>
                      <span className="text-[#68707e]">CLAIM A</span>
                    </div>
                    <p dir="auto" className="text-base font-medium text-white">
                      “{pendingOffer.claim_a}”
                    </p>
                  </div>

                  <div className="p-5 space-y-2">
                    <div className="flex items-center justify-between font-mono text-[11px]">
                      <span className="font-bold text-[#60a5fa]">
                        {pendingOffer.speaker_b}
                      </span>
                      <span className="text-[#68707e]">CLAIM B</span>
                    </div>
                    <p dir="auto" className="text-base font-medium text-white">
                      “{pendingOffer.claim_b}”
                    </p>
                  </div>
                </div>

                {/* Parallel Pre-fetch Status */}
                <div className="px-4 py-3 border border-[#1c2029] bg-[#090a0d] flex flex-wrap items-center justify-between gap-2 font-mono text-xs">
                  <div className="flex items-center gap-2 text-[#10b981]">
                    <span className="w-2 h-2 bg-[#10b981] animate-pulse" />
                    <span>
                      SPECULATIVE PRE-FETCH READY ({pendingOffer.prefetch_domain})
                    </span>
                  </div>
                  <span className="text-[#7e8694]">
                    EDGE-TTS PRE-WARMED • READY IN &lt;1.2S
                  </span>
                </div>

                {/* Interactive Consent Action */}
                <div className="space-y-3">
                  <div className="flex flex-wrap items-center gap-3">
                    <button
                      onClick={handleConfirmOffer}
                      className="flex-1 py-3.5 px-6 bg-[#f59e0b] hover:bg-[#d97706] text-black font-mono text-sm font-bold uppercase tracking-wider transition-colors cursor-pointer flex items-center justify-center gap-3"
                    >
                      <span>✓ SAY &quot;CHECK IT&quot; / «شوفها» TO VERIFY NOW</span>
                      {offerCountdown > 0 && (
                        <span className="px-2 py-0.5 bg-black/20 text-black text-xs">
                          AUTO IN {offerCountdown}S
                        </span>
                      )}
                    </button>
                    <button
                      onClick={handleDismissOffer}
                      className="py-3.5 px-5 bg-[#090a0d] hover:bg-[#151821] border border-[#2a303c] text-[#9aa2b1] font-mono text-xs font-semibold uppercase tracking-wider transition-colors cursor-pointer"
                    >
                      Ignore
                    </button>
                  </div>
                  <p className="font-mono text-[11px] text-[#7e8694]">
                    CallWrapped never interrupts uninvited. It waits for a participant to say{" "}
                    <strong className="text-[#e6e8ee]">«شوفها»</strong> or{" "}
                    <strong className="text-[#e6e8ee]">&quot;check it&quot;</strong>.
                  </p>
                </div>
              </div>
            ) : activeDispute ? (
              /* ============================================================= */
              /* STATE C: STAGE 2 — VERIFIED VERDICT SCOREBOARD                */
              /* ============================================================= */
              <div className="divide-y divide-[#1c2029] border-b border-[#1c2029]">
                {/* 1. Primary Ground Truth Headline (Most Important Thing First) */}
                <div className="p-6 md:p-8 bg-[#0e1015] space-y-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      {activeDispute.status === "REFUSED_PRIVATE" ? (
                        <span className="px-2.5 py-1 bg-[#f59e0b]/15 border border-[#f59e0b]/40 text-[#f59e0b] font-mono text-xs font-bold uppercase tracking-wider flex items-center gap-1.5">
                          <ShieldOff className="w-3.5 h-3.5" />
                          <span>PRIVACY GATE // LOOKUP REFUSED</span>
                        </span>
                      ) : (
                        <span className="px-2.5 py-1 bg-[#10b981]/15 border border-[#10b981]/40 text-[#10b981] font-mono text-xs font-bold uppercase tracking-wider flex items-center gap-1.5">
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          <span>VERIFIED GROUND TRUTH</span>
                        </span>
                      )}
                      {activeDispute.evidence_strength && (
                        <span className="font-mono text-[11px] text-[#7e8694] px-2 py-0.5 border border-[#1c2029] bg-[#090a0d]">
                          {activeDispute.evidence_strength}
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-4 font-mono text-xs">
                      {activeDispute.t_perceived_ms && (
                        <span className="text-[#10b981] font-bold">
                          {activeDispute.t_perceived_ms}ms PERCEIVED
                        </span>
                      )}
                      {activeDispute.confidence && (
                        <span className="text-[#e6e8ee] font-bold">
                          {activeDispute.confidence}% CONFIDENCE
                        </span>
                      )}
                    </div>
                  </div>

                  {activeDispute.disputed_attribute && (
                    <div className="font-mono text-xs uppercase tracking-wider text-[#7e8694]">
                      TOPIC: {activeDispute.disputed_attribute}
                    </div>
                  )}

                  {/* Large, high-contrast fact statement */}
                  <p
                    dir="auto"
                    className="text-lg md:text-2xl font-bold text-white font-display leading-snug"
                  >
                    {activeDispute.correct_fact}
                  </p>

                  {/* Official Source Citation Bar */}
                  {activeDispute.source_url && (
                    <div className="pt-2 flex flex-wrap items-center justify-between gap-3">
                      <a
                        href={activeDispute.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-2 font-mono text-xs text-[#60a5fa] hover:underline"
                      >
                        <span>
                          SOURCE:{" "}
                          {activeDispute.source_title || activeDispute.source_url}
                        </span>
                        <ExternalLink className="w-3.5 h-3.5" />
                      </a>
                    </div>
                  )}
                </div>

                {/* 2. Side-by-Side Speaker Verdict Scoreboard */}
                <div className="grid grid-cols-1 sm:grid-cols-2 divide-y sm:divide-y-0 sm:divide-x divide-[#1c2029] bg-[#090a0d]">
                  {/* Speaker A */}
                  <div
                    className={`p-5 space-y-2 border-l-2 ${
                      activeDispute.speaker_a_status === "SUPPORTED"
                        ? "border-l-[#10b981]"
                        : activeDispute.speaker_a_status === "REFUSED_PRIVATE"
                        ? "border-l-[#68707e]"
                        : "border-l-[#ef4444]"
                    }`}
                  >
                    <div className="flex items-center justify-between font-mono text-xs">
                      <span className="font-bold text-white" dir="auto">
                        {activeDispute.speaker_a || "Speaker A"}
                      </span>
                      {activeDispute.speaker_a_status === "SUPPORTED" ? (
                        <span className="text-[#10b981] font-bold flex items-center gap-1">
                          <CheckCircle2 className="w-3.5 h-3.5" /> SUPPORTED
                        </span>
                      ) : activeDispute.speaker_a_status === "REFUSED_PRIVATE" ? (
                        <span className="text-[#7e8694] font-bold">
                          PRIVATE (SKIPPED)
                        </span>
                      ) : (
                        <span className="text-[#ef4444] font-bold flex items-center gap-1">
                          <XCircle className="w-3.5 h-3.5" /> CONTRADICTED
                        </span>
                      )}
                    </div>
                    <p dir="auto" className="text-sm text-[#c8ceda]">
                      “{activeDispute.claim_a}”
                    </p>
                  </div>

                  {/* Speaker B */}
                  <div
                    className={`p-5 space-y-2 border-l-2 ${
                      activeDispute.speaker_b_status === "SUPPORTED"
                        ? "border-l-[#10b981]"
                        : activeDispute.speaker_b_status === "REFUSED_PRIVATE"
                        ? "border-l-[#68707e]"
                        : "border-l-[#ef4444]"
                    }`}
                  >
                    <div className="flex items-center justify-between font-mono text-xs">
                      <span className="font-bold text-white" dir="auto">
                        {activeDispute.speaker_b || "Speaker B"}
                      </span>
                      {activeDispute.speaker_b_status === "SUPPORTED" ? (
                        <span className="text-[#10b981] font-bold flex items-center gap-1">
                          <CheckCircle2 className="w-3.5 h-3.5" /> SUPPORTED
                        </span>
                      ) : activeDispute.speaker_b_status === "REFUSED_PRIVATE" ? (
                        <span className="text-[#7e8694] font-bold">
                          PRIVATE (SKIPPED)
                        </span>
                      ) : (
                        <span className="text-[#ef4444] font-bold flex items-center gap-1">
                          <XCircle className="w-3.5 h-3.5" /> CONTRADICTED
                        </span>
                      )}
                    </div>
                    <p dir="auto" className="text-sm text-[#c8ceda]">
                      “{activeDispute.claim_b}”
                    </p>
                  </div>
                </div>

                {/* 3. Spoken Voice Output + Interactive Audio Trigger */}
                {activeDispute.spoken_intervention && (
                  <div className="p-5 bg-[#090a0d] space-y-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-wider text-[#9aa2b1]">
                        <Volume2 className="w-4 h-4 text-[#3b82f6]" />
                        <span>SPOKEN REFEREE INTERVENTION</span>
                      </div>

                      <div className="flex items-center gap-2">
                        {activeDispute.spoken_intervention_en && (
                          <div className="flex border border-[#1c2029] font-mono text-[10px]">
                            <button
                              onClick={() => setSpokenLang("ar")}
                              className={`px-2 py-0.5 cursor-pointer ${
                                spokenLang === "ar"
                                  ? "bg-[#3b82f6] text-white font-bold"
                                  : "bg-[#0e1015] text-[#7e8694]"
                              }`}
                            >
                              AR
                            </button>
                            <button
                              onClick={() => setSpokenLang("en")}
                              className={`px-2 py-0.5 cursor-pointer ${
                                spokenLang === "en"
                                  ? "bg-[#3b82f6] text-white font-bold"
                                  : "bg-[#0e1015] text-[#7e8694]"
                              }`}
                            >
                              EN
                            </button>
                          </div>
                        )}

                        <button
                          onClick={() => handleSpeakVerdict(undefined, spokenLang)}
                          className={`px-3 py-1 font-mono text-[11px] font-bold uppercase tracking-wider border transition-colors cursor-pointer flex items-center gap-1.5 ${
                            isSpeakingVerdict
                              ? "border-[#10b981] bg-[#10b981]/20 text-[#10b981]"
                              : "border-[#2a303c] bg-[#13161c] hover:bg-[#1c2029] text-white"
                          }`}
                        >
                          <Volume2 className="w-3.5 h-3.5" />
                          <span>
                            {isSpeakingVerdict ? "Stop Voice" : "Hear Verdict"}
                          </span>
                        </button>
                      </div>
                    </div>

                    <p
                      dir="auto"
                      className="text-sm md:text-base text-[#e6e8ee] border-l-2 border-[#3b82f6] pl-3.5 py-1"
                    >
                      “
                      {spokenLang === "en" && activeDispute.spoken_intervention_en
                        ? activeDispute.spoken_intervention_en
                        : activeDispute.spoken_intervention}
                      ”
                    </p>
                  </div>
                )}

                {/* 4. Collapsible Decision Trace (No unrequested text clutter) */}
                <div className="bg-[#090a0d]">
                  <button
                    onClick={() => setShowDecisionTrace((v) => !v)}
                    className="w-full px-5 py-3 flex items-center justify-between font-mono text-[11px] text-[#7e8694] hover:text-white transition-colors cursor-pointer"
                  >
                    <span>
                      DECISION TRACE & EPISTEMIC GATES (
                      {activeDispute.why_i_spoke?.length || 4} STEPS)
                    </span>
                    {showDecisionTrace ? (
                      <ChevronUp className="w-4 h-4" />
                    ) : (
                      <ChevronDown className="w-4 h-4" />
                    )}
                  </button>

                  {showDecisionTrace && (
                    <div className="px-5 pb-4 space-y-1.5 font-mono text-xs text-[#9aa2b1] border-t border-[#14171f] pt-3">
                      {(activeDispute.why_i_spoke || []).map((reason, idx) => (
                        <div key={idx} className="flex items-start gap-2.5">
                          <span className="text-[#10b981]">0{idx + 1}</span>
                          <span>{reason}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ) : (
              /* ============================================================= */
              /* STATE A: STAGE 0 — PASSIVE LISTENING / STANDBY                */
              /* ============================================================= */
              <div className="p-8 md:p-12 flex-1 flex flex-col justify-center space-y-8 border-b border-[#1c2029]">
                <div className="space-y-2 max-w-xl">
                  <div className="font-mono text-xs font-bold uppercase tracking-[0.16em] text-[#3b82f6]">
                    SILENT REFEREE // TWO-STAGE CONSENT PROTOCOL
                  </div>
                  <h3 className="text-2xl font-bold text-white font-display">
                    Listening for factual contradictions in voice.
                  </h3>
                  <p className="text-sm text-[#9aa2b1] leading-relaxed">
                    CallWrapped never barges into your call uninvited. When two
                    speakers state conflicting facts, it pre-fetches the answer
                    silently and asks{" "}
                    <span className="text-white font-mono">
                      «أشوفها؟» / &quot;Do I check?&quot;
                    </span>{" "}
                    before speaking.
                  </p>
                </div>

                {/* 3-Step Protocol Strip */}
                <div className="grid grid-cols-1 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-[#1c2029] border border-[#1c2029] bg-[#0e1015]">
                  <div className="p-4 space-y-1">
                    <span className="font-mono text-[10px] text-[#3b82f6] font-bold">
                      01 // DETECT
                    </span>
                    <p className="text-xs font-semibold text-white">
                      Catch Factual Conflict
                    </p>
                    <p className="text-[11px] text-[#7e8694]">
                      Extracts opposing claims via AssemblyAI 3.5 Pro + Groq LPU.
                    </p>
                  </div>
                  <div className="p-4 space-y-1">
                    <span className="font-mono text-[10px] text-[#f59e0b] font-bold">
                      02 // ASK & PRE-FETCH
                    </span>
                    <p className="text-xs font-semibold text-white">
                      «أشوفها؟» / &quot;Do I check?&quot;
                    </p>
                    <p className="text-[11px] text-[#7e8694]">
                      Pre-fetches Tavily evidence in the background while waiting.
                    </p>
                  </div>
                  <div className="p-4 space-y-1">
                    <span className="font-mono text-[10px] text-[#10b981] font-bold">
                      03 // RESOLVE
                    </span>
                    <p className="text-xs font-semibold text-white">
                      Sub-1.5s Spoken Verdict
                    </p>
                    <p className="text-[11px] text-[#7e8694]">
                      Say «شوفها» or &quot;check it&quot; for instant cited resolution.
                    </p>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-3">
                  <button
                    onClick={() => runInteractiveDemo(selectedScenarioId)}
                    className="px-5 py-3 bg-[#10b981] hover:bg-[#059669] text-black font-mono text-xs font-bold uppercase tracking-wider transition-colors cursor-pointer flex items-center gap-2"
                  >
                    <Play className="w-4 h-4 fill-current" />
                    <span>Run Interactive Demo</span>
                  </button>
                  <button
                    onClick={() => applyScenarioInstant(selectedScenarioId)}
                    className="px-5 py-3 bg-[#0e1015] hover:bg-[#191d26] border border-[#2a303c] text-white font-mono text-xs font-semibold uppercase tracking-wider transition-colors cursor-pointer"
                  >
                    View Instant Resolved State
                  </button>
                </div>
              </div>
            )}

            {/* Quick Summary Strip at bottom of Referee Stage */}
            <div className="mt-auto grid grid-cols-3 divide-x divide-[#1c2029] border-t border-[#1c2029] bg-[#0c0e13] font-mono text-xs">
              <div className="px-5 py-3 flex items-center justify-between">
                <span className="text-[10px] uppercase text-[#7e8694]">
                  VERIFIED CLAIMS
                </span>
                <span className="font-bold text-[#10b981]">
                  {leaderboard["Verified Claims"]}
                </span>
              </div>
              <div className="px-5 py-3 flex items-center justify-between">
                <span className="text-[10px] uppercase text-[#7e8694]">
                  CONTRADICTED
                </span>
                <span className="font-bold text-[#ef4444]">
                  {leaderboard["Disputed Claims"]}
                </span>
              </div>
              <button
                onClick={() => setActiveTab("wrapped")}
                className="px-5 py-3 flex items-center justify-between hover:bg-[#151821] text-[#3b82f6] font-bold transition-colors cursor-pointer"
              >
                <span className="text-[10px] uppercase">CALL WRAPPED</span>
                <span>VIEW STATS →</span>
              </button>
            </div>
          </section>
        </main>
      ) : (
        /* =================================================================== */
        /* VIEW 2: 02 / CALL WRAPPED & SESSION INTELLIGENCE                    */
        /* =================================================================== */
        <main className="flex-1 max-w-[1440px] w-full mx-auto border-x border-b border-[#1c2029] bg-[#090a0d] divide-y divide-[#1c2029]">
          {/* Top Dossier Header */}
          <div className="p-6 md:p-8 bg-[#0e1015] flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 font-mono text-xs text-[#3b82f6] uppercase tracking-[0.16em]">
                <Sparkles className="w-3.5 h-3.5" />
                <span>POST-CALL INTELLIGENCE & AWARDS</span>
              </div>
              <h2 className="text-2xl md:text-3xl font-bold text-white font-display mt-1">
                CALLWRAPPED // SESSION DOSSIER
              </h2>
            </div>

            <div className="flex items-center gap-3">
              <button
                onClick={handleCopyRecap}
                className="px-4 py-2.5 bg-[#3b82f6] hover:bg-[#2563eb] text-white font-mono text-xs font-bold uppercase tracking-wider flex items-center gap-2 transition-colors cursor-pointer"
              >
                {copiedSummary ? (
                  <>
                    <Check className="w-3.5 h-3.5" />
                    <span>COPIED DISCORD RECAP</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" />
                    <span>COPY DISCORD SUMMARY</span>
                  </>
                )}
              </button>
              <button
                onClick={() => setShowRecapModal(true)}
                className="px-4 py-2.5 bg-[#090a0d] hover:bg-[#151821] border border-[#2a303c] text-[#e6e8ee] font-mono text-xs font-semibold uppercase tracking-wider flex items-center gap-2 transition-colors cursor-pointer"
              >
                <Award className="w-3.5 h-3.5 text-[#f59e0b]" />
                <span>Shareable Card</span>
              </button>
            </div>
          </div>

          {/* 4-Pillar KPI Strip */}
          <div className="grid grid-cols-2 lg:grid-cols-4 divide-y lg:divide-y-0 divide-x divide-[#1c2029]">
            <div className="p-6">
              <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-[#7e8694] block">
                TOTAL AIRTIME
              </span>
              <span className="text-3xl font-bold text-white font-display mt-1 block">
                {formatDurationHuman(analytics.total_talk_seconds)}
              </span>
              <span className="font-mono text-xs text-[#3b82f6] mt-1 block">
                {speakerEntries.length} active participants
              </span>
            </div>

            <div className="p-6">
              <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-[#7e8694] block">
                MONOLOGUE KING
              </span>
              <span
                className="text-2xl font-bold text-white font-display mt-1 block truncate"
                dir="auto"
              >
                {analytics.longest_streak?.speaker_name || "—"}
              </span>
              <span className="font-mono text-xs text-[#f59e0b] mt-1 block">
                {formatStreakMMSS(analytics.longest_streak?.streak_seconds || 0)}{" "}
                uninterrupted streak
              </span>
            </div>

            <div className="p-6">
              <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-[#7e8694] block">
                REFEREE SCOREBOARD
              </span>
              <span className="text-3xl font-bold text-white font-display mt-1 block">
                {leaderboard["Verified Claims"]} VERIFIED
              </span>
              <span className="font-mono text-xs text-[#ef4444] mt-1 block">
                {leaderboard["Disputed Claims"]} claims contradicted
              </span>
            </div>

            <div className="p-6">
              <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-[#7e8694] block">
                ACOUSTIC FRICTION
              </span>
              <span className="text-3xl font-bold text-white font-display mt-1 block">
                {analytics.total_angry_episodes === 0
                  ? "CALM"
                  : `${analytics.total_angry_episodes} SPIKE`}
              </span>
              <span className="font-mono text-xs text-[#9aa2b1] mt-1 block">
                {analytics.total_angry_episodes === 0
                  ? "0 acoustic rage episodes"
                  : "Calibrated z-score arousal"}
              </span>
            </div>
          </div>

          {/* Unified Speaker Leaderboard (Talk Share + Fact Accuracy in ONE clean table) */}
          <div className="grid grid-cols-1 lg:grid-cols-12 divide-y lg:divide-y-0 lg:divide-x divide-[#1c2029]">
            <div className="lg:col-span-7 p-6 space-y-4">
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs font-bold uppercase tracking-[0.14em] text-[#e6e8ee]">
                  SPEAKER AIRTIME & FACT ACCURACY
                </span>
                <span className="font-mono text-[11px] text-[#7e8694]">
                  UNIFIED LEADERBOARD
                </span>
              </div>

              {speakerEntries.length > 0 ? (
                <div className="divide-y divide-[#1c2029] border border-[#1c2029]">
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
                      <div key={s.speaker_name} className="p-4 bg-[#0e1015] space-y-2">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex items-center gap-3">
                            <span
                              className="font-display font-bold text-base text-white"
                              dir="auto"
                            >
                              {s.speaker_name}
                            </span>
                            <span className="font-mono text-xs text-[#7e8694]">
                              {formatDurationHuman(s.talk_seconds)} (
                              {pct.toFixed(0)}%)
                            </span>
                          </div>

                          <div className="flex items-center gap-3 font-mono text-xs">
                            <span className="text-[#10b981] font-bold">
                              ✓ {acc.verified} TRUE
                            </span>
                            <span className="text-[#ef4444] font-bold">
                              ✕ {acc.refuted} FALSE
                            </span>
                            <span className="text-[#68707e]">
                              {acc.turns || "—"} turns
                            </span>
                          </div>
                        </div>

                        <div className="w-full h-1.5 bg-[#191d26]">
                          <div
                            className="h-full bg-[#3b82f6]"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="font-mono text-xs text-[#525866] py-6">
                  No speaker statistics recorded yet.
                </p>
              )}
            </div>

            {/* Right 5 Cols: Topics + Acoustic Anger Receipts */}
            <div className="lg:col-span-5 divide-y divide-[#1c2029]">
              {/* Topic Distribution */}
              <div className="p-6 space-y-4">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-bold uppercase tracking-[0.14em] text-[#e6e8ee]">
                    TOPIC DISTRIBUTION
                  </span>
                  <span className="font-mono text-[11px] text-[#7e8694]">
                    {topicalEntries.length} ACTIVE TOPICS
                  </span>
                </div>

                {totalTopicalCount > 0 ? (
                  <div className="space-y-3">
                    {topicalEntries.map(([topic, count], idx) => {
                      const pct = (count / totalTopicalCount) * 100;
                      const color = TOPIC_COLORS[idx % TOPIC_COLORS.length];
                      return (
                        <div key={topic} className="space-y-1">
                          <div className="flex justify-between text-xs">
                            <span className="font-medium text-[#e6e8ee] capitalize">
                              {topic}
                              {TOPIC_DISPLAY_NAMES[topic.toLowerCase()]
                                ? ` · ${TOPIC_DISPLAY_NAMES[topic.toLowerCase()]}`
                                : ""}
                            </span>
                            <span className="font-mono text-[#7e8694]">
                              {count} turns ({pct.toFixed(0)}%)
                            </span>
                          </div>
                          <div className="w-full h-1.5 bg-[#151821]">
                            <div
                              className={`h-full ${color}`}
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <p className="font-mono text-xs text-[#525866]">
                    No topics classified yet.
                  </p>
                )}
              </div>

              {/* Acoustic Anger & Frustration Receipts */}
              <div className="p-6 space-y-4">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-bold uppercase tracking-[0.14em] text-[#e6e8ee]">
                    ACOUSTIC ANGER RECEIPTS
                  </span>
                  <span className="font-mono text-[11px] text-[#ef4444]">
                    LATE FUSION (TEXT + Z-LOUDNESS)
                  </span>
                </div>

                {angrySpeakers.length > 0 ? (
                  <div className="space-y-3">
                    {angrySpeakers.map((s) => {
                      const quote =
                        s.anger_evidence ||
                        s.first_anger_quote ||
                        s.anger_episodes_history?.[0]?.quote;
                      const clip = s.anger_episodes_history?.[0]?.audio_clip;
                      const peakZ = s.anger_episodes_history?.[0]?.peak_z || 2.8;
                      return (
                        <div
                          key={s.speaker_name}
                          className="p-4 bg-[#0e1015] border-l-2 border-[#ef4444] space-y-2"
                        >
                          <div className="flex items-center justify-between font-mono text-xs">
                            <span className="font-bold text-white">
                              {s.speaker_name}
                            </span>
                            <span className="text-[#ef4444] font-bold">
                              +{peakZ.toFixed(1)}σ LOUDNESS SPIKE
                            </span>
                          </div>
                          {quote && (
                            <p
                              dir="auto"
                              className="text-sm text-[#d0d5e0] italic"
                            >
                              “{quote}”
                            </p>
                          )}
                          {clip && (
                            <button
                              onClick={() => handlePlayAudioEvidence(clip)}
                              className="inline-flex items-center gap-1.5 font-mono text-[11px] text-[#ef4444] hover:underline cursor-pointer"
                            >
                              <Volume2 className="w-3.5 h-3.5" />
                              <span>
                                {playingClip === clip
                                  ? "Playing WAV Receipt..."
                                  : `Play Audio Receipt (${clip})`}
                              </span>
                            </button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="p-4 bg-[#0e1015] border-l-2 border-[#10b981] font-mono text-xs text-[#10b981]">
                    0 acoustic anger episodes triggered this session.
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Dispute Log in Wrapped View */}
          <DisputesPanel disputes={disputes} />
        </main>
      )}

      {/* Shareable Modal */}
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
