"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  Scale,
  Zap,
  CheckCircle2,
  XCircle,
  ExternalLink,
  Radio,
  Activity,
  Volume2,
  Play,
  Users,
  ShieldCheck,
  Search,
  Cpu,
  Award,
  HelpCircle,
  RotateCcw,
  Clock,
  Flame,
  Smile,
  PieChart,
  Crown
} from "lucide-react";

import {
  AnalyticsState,
  SpeakerAnalytics,
  formatDurationHuman,
  formatStreakMMSS,
  TOPIC_DISPLAY_NAMES,
  TOPIC_COLORS
} from "../components/AnalyticsWidgets";

import { DisputesPanel, DisputeCard } from "../components/DisputesPanel";
import { CallWrappedModal } from "../components/CallWrappedModal";
import { PipelineFlow } from "../components/PipelineFlow";

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
  why_i_spoke?: string[];
  latency?: LatencyMetrics;
}

interface Turn {
  speaker_name: string;
  text: string;
  timestamp: number;
  stt_ms?: number;
  correlation_id?: string;
}

const GOLDEN_DEMO_DATA = {
  latency: {
    stt_ms: 265,
    llm_ms: 194,
    search_ms: 520,
    tts_ms: 185,
    total_ms: 1164,
  },
  activeDispute: {
    event_id: "evt_golden_rtx5070",
    timestamp: Date.now() / 1000 - 45,
    speaker_a: "Ahmed",
    claim_a: "Bro, I'm pretty sure the RTX 5070 has 16 gigs of VRAM.",
    speaker_a_status: "CONTRADICTED",
    speaker_b: "Mohamed",
    claim_b: "No, the 5070 is 12 gigs. The Ti is 16.",
    speaker_b_status: "SUPPORTED",
    winner: "Mohamed",
    loser: "Ahmed",
    correct_fact: "NVIDIA GeForce RTX 5070 has 12GB GDDR7 memory (192-bit bus), while RTX 5070 Ti has 16GB GDDR7 (256-bit bus).",
    confidence: 99,
    evidence_strength: "HIGH",
    status: "resolved",
    source_url: "https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5070-family/",
    source_title: "NVIDIA GeForce RTX 5070 Family Official Specifications",
    spoken_intervention: "Correction: the RTX 5070 has 12GB of GDDR7 memory. The RTX 5070 Ti has 16GB. Source is on the dashboard.",
    why_i_spoke: [
      "Factual claim detected regarding GPU memory capacity",
      "Direct contradiction between Ahmed (16GB) and Mohamed (12GB)",
      "Tier-1 official manufacturer source verified (nvidia.com)",
      "Evidence confidence high (99%) — Evidence strength: HIGH",
      "Autonomous voice intervention triggered via Edge Neural ar-EG-Shakir"
    ]
  },
  disputes: [
    {
      dispute_id: "disp_golden_rtx5070",
      speaker_a: "Ahmed",
      claim_a: "Bro, I'm pretty sure the RTX 5070 has 16 gigs of VRAM.",
      speaker_b: "Mohamed",
      claim_b: "No, the 5070 is 12 gigs. The Ti is 16.",
      disputed_attribute: "RTX 5070 VRAM Capacity",
      status: "resolved",
      source_name: "NVIDIA GeForce Official Specifications",
      source_url: "https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5070-family/",
      evidence_excerpt: "GeForce RTX 5070 — 12GB GDDR7 memory (192-bit bus). GeForce RTX 5070 Ti — 16GB GDDR7 memory (256-bit bus).",
      t_perceived_ms: 1164
    }
  ],
  disputesHistory: [
    {
      timestamp: Date.now() / 1000 - 180,
      speaker_a: "Ahmed",
      claim_a: "RTX 5070 has 16GB VRAM",
      speaker_a_status: "CONTRADICTED",
      speaker_b: "Mohamed",
      claim_b: "RTX 5070 has 12GB VRAM",
      speaker_b_status: "SUPPORTED",
      correct_fact: "NVIDIA RTX 5070 has 12GB GDDR7, while 5070 Ti has 16GB GDDR7.",
      source_url: "https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5070-family/"
    }
  ],
  leaderboard: {
    "Verified Claims": 3,
    "Disputed Claims": 1,
    Speakers: {
      "Mohamed": { turns: 14, verified: 2, refuted: 0 },
      "Ahmed": { turns: 18, verified: 1, refuted: 1 },
      "Kareem": { turns: 8, verified: 0, refuted: 0 }
    }
  },
  analytics: {
    topic_totals: { tech: 14, gaming: 9, football: 4 },
    speakers: {
      "Ahmed": {
        speaker_name: "Ahmed",
        talk_seconds: 52.4,
        longest_streak_seconds: 14.8,
        angry_episodes: 0,
        anger_episodes_history: []
      },
      "Mohamed": {
        speaker_name: "Mohamed",
        talk_seconds: 38.6,
        longest_streak_seconds: 10.2,
        angry_episodes: 0,
        anger_episodes_history: []
      },
      "Kareem": {
        speaker_name: "Kareem",
        talk_seconds: 24.1,
        longest_streak_seconds: 6.8,
        angry_episodes: 0,
        anger_episodes_history: []
      }
    },
    total_talk_seconds: 115.1,
    total_angry_episodes: 0,
    total_vulgarity_count: 0,
    total_banter_count: 2,
    longest_streak: {
      speaker_name: "Ahmed",
      streak_seconds: 14.8
    }
  },
  turns: [
    { speaker_name: "Ahmed", text: "Bro, I'm pretty sure the RTX 5070 has 16 gigs of VRAM.", timestamp: Date.now() / 1000 - 45, stt_ms: 272 },
    { speaker_name: "Mohamed", text: "No, the 5070 is 12 gigs. The Ti is 16.", timestamp: Date.now() / 1000 - 41, stt_ms: 258 },
    { speaker_name: "Ahmed", text: "Nah, both are 16. Check the leak from yesterday.", timestamp: Date.now() / 1000 - 37, stt_ms: 265 },
    { speaker_name: "CallWrapped (AI Referee)", text: "Correction: the RTX 5070 has 12GB of GDDR7 memory. The RTX 5070 Ti has 16GB. Source is on the dashboard.", timestamp: Date.now() / 1000 - 35, stt_ms: 0 },
    { speaker_name: "Mohamed", text: "Told you bro! NVIDIA never gives 16GB on the non-Ti 70 class.", timestamp: Date.now() / 1000 - 28, stt_ms: 245 },
    { speaker_name: "Ahmed", text: "Fair enough, my bad. What about League tonight?", timestamp: Date.now() / 1000 - 20, stt_ms: 260 }
  ]
};

export default function CallWrappedDashboard() {
  const [isConnected, setIsConnected] = useState(false);
  const [connectionType, setConnectionType] = useState<"ws" | "poll">("poll");
  const [showRecapModal, setShowRecapModal] = useState(false);
  const hasLoadedOnce = useRef(false);

  const [latency, setLatency] = useState<LatencyMetrics>({
    stt_ms: 0,
    llm_ms: 0,
    search_ms: 0,
    tts_ms: 0,
    total_ms: 0,
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
  const [turns, setTurns] = useState<Turn[]>([]);
  const [activeDispute, setActiveDispute] = useState<DisputeInfo | null>(null);
  const [disputes, setDisputes] = useState<DisputeCard[]>([]);
  const [disputesHistory, setDisputesHistory] = useState<DisputeInfo[]>([]);
  const [leaderboard, setLeaderboard] = useState<{
    "Verified Claims": number;
    "Disputed Claims": number;
    Speakers: Record<string, SpeakerStats>;
  }>({
    "Verified Claims": 0,
    "Disputed Claims": 0,
    Speakers: {},
  });
  const [isSimulating, setIsSimulating] = useState(false);
  const [speechModel, setSpeechModel] = useState<string>("Universal-3.5 Pro");
  const [discordInviteUrl, setDiscordInviteUrl] = useState<string>(
    "https://discord.com/oauth2/authorize?client_id=1550926707517558864&permissions=36718592&scope=bot%20applications.commands"
  );
  const [factCheckModeBadge, setFactCheckModeBadge] = useState<string>("Fact Check Mode: OFF");

  const applyGoldenDemo = () => {
    setLatency(GOLDEN_DEMO_DATA.latency);
    setActiveDispute(GOLDEN_DEMO_DATA.activeDispute as DisputeInfo);
    setDisputes(GOLDEN_DEMO_DATA.disputes as DisputeCard[]);
    setDisputesHistory(GOLDEN_DEMO_DATA.disputesHistory as DisputeInfo[]);
    setLeaderboard(GOLDEN_DEMO_DATA.leaderboard);
    setAnalytics(GOLDEN_DEMO_DATA.analytics as AnalyticsState);
    setTurns(GOLDEN_DEMO_DATA.turns as Turn[]);
  };

  const formatModelName = (modelId?: string) => {
    if (!modelId) return "AssemblyAI Universal";
    const parts = modelId.split("-");
    if (parts.length >= 3 && parts[0] === "universal") {
      const version = parts.length >= 3 && /^\d+$/.test(parts[2]) ? `${parts[1]}.${parts[2]}` : parts[1];
      const rest = parts.length >= 4 ? parts.slice(3).map(p => p.charAt(0).toUpperCase() + p.slice(1)).join(" ") : (parts.includes("pro") ? "Pro" : "");
      return `Universal-${version} ${rest}`.trim();
    }
    return modelId.replace("-", " ");
  };

  const transcriptScrollRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const getBackendBase = () => {
    if (typeof window !== "undefined") {
      const hostname = window.location.hostname || "localhost";
      const port = window.location.port === "3000" ? "8000" : (window.location.port || "8000");
      return {
        http: `${window.location.protocol}//${hostname}:${port}`,
        ws: `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${hostname}:${port}`
      };
    }
    return { http: "http://localhost:8000", ws: "ws://localhost:8000" };
  };

  useEffect(() => {
    if (transcriptScrollRef.current) {
      transcriptScrollRef.current.scrollTop = transcriptScrollRef.current.scrollHeight;
    }
  }, [turns]);

  useEffect(() => {
    let isMounted = true;
    let pollInterval: NodeJS.Timeout | null = null;
    const { http, ws } = getBackendBase();

    const getReceiptsCache = (): Record<string, string> => {
      if (typeof window === "undefined") return {};
      try {
        return JSON.parse(localStorage.getItem("receipts_cache") || "{}");
      } catch {
        return {};
      }
    };

    const saveReceiptToCache = (speaker: string, quote: string) => {
      if (typeof window === "undefined" || !speaker || !quote) return;
      try {
        const cache = getReceiptsCache();
        cache[speaker] = quote;
        localStorage.setItem("receipts_cache", JSON.stringify(cache));
      } catch {
        // ignore
      }
    };

    const applyAnalytics = (rawAnalytics: any, rawEvent?: any) => {
      if (!rawAnalytics) return;
      const cache = getReceiptsCache();

      if (rawEvent) {
        const quote = rawEvent.anger_evidence || rawEvent.payload?.anger_evidence || rawEvent.payload?.first_anger_quote;
        if (quote && rawEvent.speaker_name) {
          saveReceiptToCache(rawEvent.speaker_name, quote);
          cache[rawEvent.speaker_name] = quote;
        }
      }

      const mergedSpeakers: Record<string, SpeakerAnalytics> = {};
      if (rawAnalytics.speakers) {
        for (const [name, spk] of Object.entries(rawAnalytics.speakers as Record<string, any>)) {
          mergedSpeakers[name] = {
            speaker_name: spk.speaker_name || name,
            talk_seconds: Number(spk.talk_seconds || 0),
            longest_streak_seconds: Number(spk.longest_streak_seconds || 0),
            angry_episodes: Number(spk.angry_episodes || 0),
            anger_evidence: spk.anger_evidence || spk.first_anger_quote || cache[name] || undefined,
            anger_episodes_history: spk.anger_episodes_history || [],
            vulgarity_count: Number(spk.vulgarity_count || 0),
            vulgarity_terms: Array.isArray(spk.vulgarity_terms) ? spk.vulgarity_terms : [],
            banter_count: Number(spk.banter_count || 0),
            banter_terms: Array.isArray(spk.banter_terms) ? spk.banter_terms : []
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
          streak_seconds: Number(rawAnalytics.longest_streak?.streak_seconds || 0)
        }
      });
    };

    const fetchLiveSnapshot = async () => {
      try {
        const [resLive, resAnalytics] = await Promise.all([
          fetch(`${http}/api/live`),
          fetch(`${http}/api/analytics`)
        ]);

        if (resLive.ok) {
          hasLoadedOnce.current = true;
          const data = await resLive.json();
          if (isMounted) {
            setIsConnected(true);
            if (data.assemblyai_model) setSpeechModel(formatModelName(data.assemblyai_model));
            if (data.discord_invite_url) setDiscordInviteUrl(data.discord_invite_url);
            if (data.fact_check_mode_badge) setFactCheckModeBadge(data.fact_check_mode_badge);
            else if (data.fact_check_mode) setFactCheckModeBadge(`Fact Check Mode: ${data.fact_check_mode}`);
            if (data.latency) setLatency(data.latency);
            if (data.turns) setTurns(data.turns);
            if (data.active_dispute) setActiveDispute(data.active_dispute);
            if (data.disputes) setDisputes(data.disputes);
            if (data.disputes_history) setDisputesHistory(data.disputes_history);
            if (data.leaderboard) setLeaderboard(data.leaderboard);
            if (data.analytics) applyAnalytics(data.analytics);
          }
        }

        if (resAnalytics.ok) {
          const aData = await resAnalytics.json();
          if (isMounted && aData) {
            applyAnalytics(aData);
          }
        }
      } catch (err) {
        if (isMounted) {
          setIsConnected(false);
          if (!hasLoadedOnce.current) {
            hasLoadedOnce.current = true;
            applyGoldenDemo();
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
              const d = msg.data;
              if (d.assemblyai_model) setSpeechModel(formatModelName(d.assemblyai_model));
              if (d.discord_invite_url) setDiscordInviteUrl(d.discord_invite_url);
              if (d.fact_check_mode_badge) setFactCheckModeBadge(d.fact_check_mode_badge);
              else if (d.fact_check_mode) setFactCheckModeBadge(`Fact Check Mode: ${d.fact_check_mode}`);
              if (d.latency) setLatency(d.latency);
              if (d.turns) setTurns(d.turns);
              if (d.active_dispute) setActiveDispute(d.active_dispute);
              if (d.disputes) setDisputes(d.disputes);
              if (d.disputes_history) setDisputesHistory(d.disputes_history);
              if (d.leaderboard) setLeaderboard(d.leaderboard);
              if (d.analytics) applyAnalytics(d.analytics);
            } else if (msg.live_state) {
              const d = msg.live_state;
              if (d.assemblyai_model) setSpeechModel(formatModelName(d.assemblyai_model));
              if (d.discord_invite_url) setDiscordInviteUrl(d.discord_invite_url);
              if (d.fact_check_mode_badge) setFactCheckModeBadge(d.fact_check_mode_badge);
              else if (d.fact_check_mode) setFactCheckModeBadge(`Fact Check Mode: ${d.fact_check_mode}`);
              if (d.latency) setLatency(d.latency);
              if (d.turns) setTurns(d.turns);
              if (d.active_dispute) setActiveDispute(d.active_dispute);
              if (d.disputes) setDisputes(d.disputes);
              if (d.disputes_history) setDisputesHistory(d.disputes_history);
              if (d.leaderboard) setLeaderboard(d.leaderboard);
              if (d.analytics) applyAnalytics(d.analytics, msg.event);
            }

            if (msg.analytics) {
              applyAnalytics(msg.analytics, msg.event);
            }

            if (msg.type === "analytics_update" && msg.event) {
              applyAnalytics(msg.analytics || analytics, msg.event);
            }

            if (msg.type === "fact_check_mode_update" || msg.event?.type === "fact_check_mode_update") {
              const badge = msg.event?.payload?.badge || msg.payload?.badge;
              const mode = msg.event?.payload?.mode || msg.payload?.mode;
              if (badge) setFactCheckModeBadge(badge);
              else if (mode) setFactCheckModeBadge(`Fact Check Mode: ${mode}`);
            }
          } catch (e) {
            console.error("WS message parse error:", e);
          }
        };

        socket.onclose = () => {
          if (!isMounted) return;
          setConnectionType("poll");
          setTimeout(connectWebSocket, 3000);
        };

        socket.onerror = () => {
          socket.close();
        };
      } catch (e) {
        setConnectionType("poll");
      }
    };

    fetchLiveSnapshot();
    connectWebSocket();
    pollInterval = setInterval(fetchLiveSnapshot, 2500);

    return () => {
      isMounted = false;
      if (pollInterval) clearInterval(pollInterval);
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  // Trigger Demo Replay
  const handleTriggerReplay = async () => {
    setIsSimulating(true);
    const { http } = getBackendBase();
    try {
      await fetch(`${http}/api/demo/run`, { method: "POST" });
    } catch (e) {
      console.error("Failed to start replay:", e);
    } finally {
      setTimeout(() => setIsSimulating(false), 8000);
    }
  };

  // Reset Session
  const handleReset = async () => {
    const { http } = getBackendBase();
    try {
      await fetch(`${http}/api/reset`, { method: "POST" });
      setActiveDispute(null);
      setTurns([]);
      setDisputesHistory([]);
      setLeaderboard({
        "Verified Claims": 0,
        "Disputed Claims": 0,
        Speakers: {},
      });
      setLatency({
        stt_ms: 0,
        llm_ms: 0,
        search_ms: 0,
        tts_ms: 0,
        total_ms: 0,
      });
      setAnalytics({
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
      if (typeof window !== "undefined") {
        localStorage.removeItem("receipts_cache");
      }
    } catch (e) {
      console.error("Failed to reset:", e);
    }
  };

  // Topic totals calculations
  const topicalEntries = Object.entries(analytics.topic_totals || {}).filter(
    ([t]) => t !== "null_topic" && t !== "null" && t !== "بدون موضوع" && t !== "none"
  );
  const nullCount =
    (analytics.topic_totals?.["null_topic"] || 0) +
    (analytics.topic_totals?.["null"] || 0) +
    (analytics.topic_totals?.["بدون موضوع"] || 0);
  const totalTopicalCount = topicalEntries.reduce((acc, [, c]) => acc + c, 0);
  const totalAllTopics = totalTopicalCount + nullCount;
  const topicalCoveragePct = totalAllTopics > 0 ? (totalTopicalCount / totalAllTopics) * 100 : 0;
  const sortedTopics = topicalEntries.sort((a, b) => b[1] - a[1]);

  // Speaker entries
  const speakerEntries = Object.values(analytics.speakers || {}).sort((a, b) => b.talk_seconds - a.talk_seconds);
  const hasSpeakers = speakerEntries.length > 0;
  const angrySpeakers = speakerEntries.filter((s) => s.angry_episodes > 0);

  return (
    <div className="min-h-screen bg-[#1e1f22] text-[#F2F3F5] flex flex-col font-sans selection:bg-[#5865F2] selection:text-white">
      {/* 1. TOP HEADER & STATUS BAR (DISCORD DARK) */}
      <header className="border-b border-[#383a40] bg-[#1e1f22]/95 backdrop-blur sticky top-0 z-50 px-4 md:px-8 py-3.5 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-[#5865F2] text-white shadow-lg shadow-[#5865F2]/25">
            <Scale className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg md:text-xl font-black tracking-tight text-[#F2F3F5]">
                CALLWRAPPED
              </h1>
              <span className="text-[11px] font-semibold tracking-wider uppercase px-2 py-0.5 rounded-md bg-[#5865F2]/10 text-[#5865F2] border border-[#5865F2]/25">
                AI Voice Referee
              </span>
            </div>
            <p className="text-xs text-[#949BA4] hidden sm:block">
              Multi-Speaker Discord E2EE • {speechModel} Code-Switching • Groq LPU • Tavily Ground-Truth
            </p>
          </div>
        </div>

        {/* Live Indicator & Controls */}
        <div className="flex items-center gap-2 sm:gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#2b2d31] border border-[#383a40] text-xs">
            <span className={`w-2.5 h-2.5 rounded-full ${isConnected ? "bg-[#23A55A] animate-pulse" : "bg-[#F23F43]"}`} />
            <span className="font-semibold text-[#DBDEE1]">
              {isConnected ? (connectionType === "ws" ? "VOICE CONNECTED" : "POLLING ACTIVE") : "DISCONNECTED"}
            </span>
          </div>

          {/* Fact Check Mode Badge */}
          <div
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-full border text-xs font-semibold tracking-wide transition-all ${
              factCheckModeBadge.toUpperCase().includes("ON")
                ? "bg-[#23A55A]/15 border-[#23A55A]/30 text-[#23A55A] shadow-sm shadow-[#23A55A]/10"
                : "bg-[#2b2d31] border-[#383a40] text-[#949BA4]"
            }`}
            title="Fact Check Mode policy: offers only, zero uninvited speech"
          >
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>{factCheckModeBadge}</span>
          </div>

          {/* Discord Bot Invite */}
          <a
            href={discordInviteUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#5865F2] hover:bg-[#4752C4] text-white text-xs font-semibold shadow-md shadow-[#5865F2]/25 transition-all cursor-pointer"
            title="Invite CallWrapped Bot to your Discord Server"
          >
            <svg className="w-3.5 h-3.5 fill-current" viewBox="0 0 24 24">
              <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994.021-.041.001-.09-.041-.106a13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.929 1.793 8.18 1.793 12.061 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.894.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.028zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/>
            </svg>
            <span className="hidden sm:inline">Add to Discord</span>
            <span className="sm:hidden">Invite</span>
          </a>

          {/* Live Demo Replay */}
          <button
            onClick={handleTriggerReplay}
            disabled={isSimulating}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#23A55A] hover:bg-[#1f9450] disabled:opacity-50 text-white text-xs font-semibold shadow-md shadow-[#23A55A]/20 transition-all cursor-pointer"
            title="Replay RTX 5070 Live Demo Session"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
            <span>{isSimulating ? "Replaying Demo..." : "Demo Replay"}</span>
          </button>

          {/* Open CallWrapped Modal Button */}
          <button
            onClick={() => setShowRecapModal(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#2b2d31] hover:bg-[#383a40] border border-[#383a40] text-[#F2F3F5] text-xs font-semibold transition-all cursor-pointer"
            title="Open Spotify-style CallWrapped session recap card"
          >
            <Award className="w-3.5 h-3.5 text-[#F0B232]" />
            <span className="hidden sm:inline">CallWrapped Card</span>
          </button>

          {/* Reset Session */}
          <button
            onClick={handleReset}
            className="p-1.5 rounded-lg bg-[#2b2d31] hover:bg-[#383a40] text-[#949BA4] hover:text-[#F2F3F5] border border-[#383a40] transition-colors"
            title="Reset Session Data"
          >
            <RotateCcw className="w-4 h-4" />
          </button>
        </div>
      </header>

      {/* 2. REAL-TIME LATENCY PIPELINE FLOW */}
      <PipelineFlow latency={latency} speechModel={speechModel} />

      {/* 3. MAIN DASHBOARD COMMAND CENTER (2-COLUMN GRID) */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 md:p-6">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          
          {/* ======================================================== */}
          {/* LEFT COLUMN: LIVE ARBITRATION + DISPUTES + TRANSCRIPT (7 COLS) */}
          {/* ======================================================== */}
          <div className="lg:col-span-7 flex flex-col space-y-6">

            {/* HERO ACTIVE EVIDENCE ARBITRATION CARD */}
            <div className="relative rounded-2xl bg-[#2b2d31] border-2 border-[#23A55A]/40 shadow-xl shadow-black/40 p-5 md:p-6 overflow-hidden">
              <div className="flex items-center justify-between gap-3 border-b border-[#383a40] pb-4 mb-5">
                <div className="flex items-center gap-2.5">
                  <span className="p-2 rounded-xl bg-[#23A55A]/20 text-[#23A55A] border border-[#23A55A]/30">
                    <ShieldCheck className="w-5 h-5" />
                  </span>
                  <div>
                    <h2 className="text-base font-bold text-[#F2F3F5] tracking-wide flex items-center gap-2">
                      EVIDENCE-BASED ARBITRATION
                      <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-[#23A55A]/20 text-[#23A55A] border border-[#23A55A]/30 animate-pulse">
                        VERIFIED
                      </span>
                    </h2>
                    <p className="text-xs text-[#949BA4]">
                      Contradiction caught, verified against authoritative sources, and settled via voice intervention.
                    </p>
                  </div>
                </div>

                {activeDispute?.confidence && (
                  <div className="text-right">
                    <span className="text-[10px] text-[#949BA4] uppercase font-mono block">Confidence</span>
                    <span className="text-sm font-bold text-[#23A55A] font-mono">{activeDispute.confidence}%</span>
                  </div>
                )}
              </div>

              {activeDispute ? (
                <div className="space-y-4">
                  {/* OPPOSING CLAIMS COMPARISON */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {/* Claim A */}
                    <div className={`p-4 rounded-xl border transition-all ${
                      activeDispute.speaker_a_status === "SUPPORTED"
                        ? "bg-[#23A55A]/10 border-[#23A55A]/40"
                        : "bg-[#F23F43]/10 border-[#F23F43]/40"
                    }`}>
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-semibold text-[#DBDEE1] flex items-center gap-1.5">
                          <Users className="w-3.5 h-3.5 text-[#949BA4]" />
                          {activeDispute.speaker_a || "Speaker A"}
                        </span>
                        {activeDispute.speaker_a_status === "SUPPORTED" ? (
                          <span className="flex items-center gap-1 text-[11px] font-bold text-[#23A55A]">
                            <CheckCircle2 className="w-3.5 h-3.5" /> SUPPORTED
                          </span>
                        ) : (
                          <span className="flex items-center gap-1 text-[11px] font-bold text-[#F23F43]">
                            <XCircle className="w-3.5 h-3.5" /> CONTRADICTED
                          </span>
                        )}
                      </div>
                      <p dir="auto" className="text-sm font-medium text-[#F2F3F5]">
                        "{activeDispute.claim_a}"
                      </p>
                    </div>

                    {/* Claim B */}
                    <div className={`p-4 rounded-xl border transition-all ${
                      activeDispute.speaker_b_status === "SUPPORTED"
                        ? "bg-[#23A55A]/10 border-[#23A55A]/40"
                        : "bg-[#F23F43]/10 border-[#F23F43]/40"
                    }`}>
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-semibold text-[#DBDEE1] flex items-center gap-1.5">
                          <Users className="w-3.5 h-3.5 text-[#949BA4]" />
                          {activeDispute.speaker_b || "Speaker B"}
                        </span>
                        {activeDispute.speaker_b_status === "SUPPORTED" ? (
                          <span className="flex items-center gap-1 text-[11px] font-bold text-[#23A55A]">
                            <CheckCircle2 className="w-3.5 h-3.5" /> SUPPORTED
                          </span>
                        ) : (
                          <span className="flex items-center gap-1 text-[11px] font-bold text-[#F23F43]">
                            <XCircle className="w-3.5 h-3.5" /> CONTRADICTED
                          </span>
                        )}
                      </div>
                      <p dir="auto" className="text-sm font-medium text-[#F2F3F5]">
                        "{activeDispute.claim_b}"
                      </p>
                    </div>
                  </div>

                  {/* GROUND TRUTH VERIFIED FACT */}
                  <div className="p-4 rounded-xl bg-[#1e1f22] border border-[#383a40]">
                    <div className="flex items-center justify-between gap-2 mb-1.5">
                      <span className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-[#23A55A]">
                        <CheckCircle2 className="w-4 h-4" />
                        <span>Verified Ground Truth:</span>
                      </span>
                      {activeDispute.evidence_strength && (
                        <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded bg-[#23A55A]/20 text-[#23A55A] border border-[#23A55A]/30">
                          Evidence: {activeDispute.evidence_strength}
                        </span>
                      )}
                    </div>
                    <p className="text-sm md:text-base font-semibold text-[#F2F3F5]">
                      {activeDispute.correct_fact}
                    </p>
                  </div>

                  {/* WHY DID THE AGENT SPEAK? EXPLAINABILITY BLOCK */}
                  <div className="p-4 rounded-xl bg-[#1e1f22] border border-[#383a40] space-y-2">
                    <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-[#5865F2]">
                      <HelpCircle className="w-4 h-4" />
                      <span>Why did the agent speak? (Decision Trace)</span>
                    </div>
                    <div className="space-y-1.5 pl-1">
                      {(activeDispute.why_i_spoke || [
                        "Factual claim detected via FastGate + Groq",
                        "Direct contradiction identified on target entity",
                        "Tier-1 authoritative source located",
                        "Evidence confidence high (99%)",
                        "Spoken intervention triggered via neural voice"
                      ]).map((reason, idx) => (
                        <div key={idx} className="flex items-center gap-2 text-xs text-[#DBDEE1]">
                          <span className="w-4 h-4 rounded-full bg-[#23A55A]/20 border border-[#23A55A]/50 flex items-center justify-center text-[#23A55A] text-[10px]">
                            ✓
                          </span>
                          <span>{reason}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* SPOKEN NEURAL VOICE INTERVENTION */}
                  <div className="p-4 rounded-xl bg-[#5865F2]/10 border border-[#5865F2]/30">
                    <div className="flex items-center justify-between gap-2 mb-2">
                      <span className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-[#DBDEE1]">
                        <Volume2 className="w-4 h-4 text-[#5865F2]" />
                        <span>Referee Spoken Intervention (Template-Based):</span>
                      </span>
                      <span className="text-[10px] text-[#5865F2] font-mono">Edge Neural ar-EG-Shakir</span>
                    </div>
                    <p dir="auto" className="text-sm font-medium text-[#F2F3F5] leading-relaxed bg-[#1e1f22] p-3 rounded-lg border border-[#383a40]">
                      "{activeDispute.spoken_intervention}"
                    </p>
                  </div>

                  {/* CLICKABLE OFFICIAL WEB CITATION */}
                  {activeDispute.source_url && (
                    <div className="flex items-center justify-between gap-3 p-3.5 rounded-xl bg-[#1e1f22] border border-[#383a40]">
                      <div className="flex items-center gap-2 truncate">
                        <Search className="w-4 h-4 text-[#949BA4] flex-shrink-0" />
                        <span className="text-xs text-[#949BA4] font-medium">Source:</span>
                        <span className="text-xs font-semibold text-[#F2F3F5] truncate">
                          {activeDispute.source_title || "Verified Documentation"}
                        </span>
                      </div>
                      <a
                        href={activeDispute.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#5865F2] hover:bg-[#4752C4] text-white text-xs font-semibold transition-all flex-shrink-0"
                      >
                        <span>Open Source</span>
                        <ExternalLink className="w-3.5 h-3.5" />
                      </a>
                    </div>
                  )}
                </div>
              ) : (
                <div className="py-12 px-4 text-center space-y-4">
                  <div className="w-14 h-14 mx-auto rounded-2xl bg-[#1e1f22] border border-[#383a40] flex items-center justify-center text-[#949BA4]">
                    <Scale className="w-7 h-7" />
                  </div>
                  <div className="space-y-1">
                    <h3 className="text-base font-semibold text-[#F2F3F5]">
                      Silent Referee Standing By
                    </h3>
                    <p className="text-xs text-[#949BA4] max-w-md mx-auto">
                      The bot listens silently to multi-speaker conversation in Discord. When an objective factual disagreement is detected, it queries Tavily and intervenes with the verified facts.
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
                    <button
                      onClick={handleTriggerReplay}
                      className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#23A55A] hover:bg-[#1f9450] text-white text-xs font-semibold shadow-lg shadow-[#23A55A]/20 transition-all cursor-pointer"
                    >
                      <Play className="w-4 h-4 fill-current" />
                      <span>Run Demo Replay (RTX 5070 Dispute)</span>
                    </button>
                    <a
                      href={discordInviteUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#5865F2] hover:bg-[#4752C4] text-white text-xs font-semibold shadow-lg shadow-[#5865F2]/25 transition-all cursor-pointer"
                    >
                      <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24">
                        <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994.021-.041.001-.09-.041-.106a13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.929 1.793 8.18 1.793 12.061 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.894.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.028zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/>
                      </svg>
                      <span>Invite Bot to Discord Server</span>
                    </a>
                  </div>
                </div>
              )}
            </div>

            {/* DISPUTES PANEL */}
            <DisputesPanel disputes={disputes} />

            {/* REAL-TIME DISCORD TRANSCRIPT STREAM (STYLED LIKE DISCORD CHAT) */}
            <div className="flex flex-col h-[520px] rounded-2xl bg-[#2b2d31] border border-[#383a40] overflow-hidden">
              <div className="p-3.5 border-b border-[#383a40] bg-[#1e1f22] flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Radio className="w-4 h-4 text-[#F23F43] animate-pulse" />
                  <h2 className="text-sm font-bold text-[#F2F3F5] tracking-wide">
                    DISCORD VOICE TRANSCRIPT STREAM
                  </h2>
                </div>
                <span className="text-[11px] font-mono text-[#949BA4]">
                  {turns.length} utterances
                </span>
              </div>

              {/* Transcript Chat Area */}
              <div
                ref={transcriptScrollRef}
                className="flex-1 p-4 overflow-y-auto space-y-3 bg-[#313338] scroll-smooth"
              >
                {turns.length > 0 ? (
                  turns.map((t, idx) => (
                    <div
                      key={idx}
                      className="p-3 rounded-xl bg-[#2b2d31] border border-[#383a40] space-y-1 hover:border-[#404249] transition-colors"
                    >
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-bold text-[#F2F3F5] flex items-center gap-2">
                          <span className="w-5 h-5 rounded-full bg-[#5865F2] text-white flex items-center justify-center text-[10px] font-bold">
                            {t.speaker_name.charAt(0).toUpperCase()}
                          </span>
                          <span dir="auto">{t.speaker_name}</span>
                        </span>
                        <div className="flex items-center gap-2">
                          {t.stt_ms && (
                            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-cyan-950/60 text-cyan-400 border border-cyan-800/40">
                              {t.stt_ms}ms
                            </span>
                          )}
                          <span className="text-[10px] text-[#949BA4] font-mono">
                            {new Date(t.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                          </span>
                        </div>
                      </div>
                      <p dir="auto" className="text-sm text-[#DBDEE1] leading-relaxed font-normal pl-7">
                        {t.text}
                      </p>
                    </div>
                  ))
                ) : (
                  <div className="h-full flex flex-col items-center justify-center text-center p-6 text-[#949BA4] space-y-3">
                    <Radio className="w-8 h-8 opacity-40 text-[#5865F2]" />
                    <p className="text-xs max-w-xs">
                      Listening for speech in Discord voice channel... Utterances with bilingual code-switching will stream here verbatim.
                    </p>
                  </div>
                )}
              </div>

              {/* Stream Footer Info */}
              <div className="p-2.5 border-t border-[#383a40] bg-[#1e1f22] flex items-center justify-between text-[11px] text-[#949BA4] font-mono">
                <span className="flex items-center gap-1.5">
                  <Cpu className="w-3.5 h-3.5 text-cyan-400" />
                  <span>{speechModel} Code-Switching</span>
                </span>
                <span>Raw Verbatim Evidence</span>
              </div>
            </div>

          </div>

          {/* ======================================================== */}
          {/* RIGHT COLUMN: CALLWRAPPED INTELLIGENCE & STATS (5 COLS) */}
          {/* ======================================================== */}
          <div className="lg:col-span-5 flex flex-col space-y-6">

            {/* 1. CALLWRAPPED BADGES & RECORDS */}
            <div className="rounded-2xl bg-[#2b2d31] border border-[#383a40] p-5 space-y-3 shadow-lg">
              <div className="flex items-center justify-between border-b border-[#383a40] pb-3">
                <div className="flex items-center gap-2">
                  <Award className="w-4 h-4 text-[#F0B232]" />
                  <h3 className="text-sm font-bold text-[#F2F3F5] tracking-wide uppercase">
                    Call Badges & Records
                  </h3>
                </div>
                <button
                  onClick={() => setShowRecapModal(true)}
                  className="text-[11px] font-bold text-[#5865F2] hover:text-[#5865F2]/80 transition-colors cursor-pointer"
                >
                  View Wrapped Card →
                </button>
              </div>

              {analytics.longest_streak && analytics.longest_streak.speaker_name && analytics.longest_streak.streak_seconds > 0 ? (
                <div className="space-y-2.5">
                  {/* The Monologue King */}
                  <div className="p-3 rounded-xl bg-[#1e1f22] border border-[#F0B232]/30 text-center space-y-1">
                    <div className="inline-flex p-1.5 rounded-xl bg-[#F0B232]/20 text-[#F0B232] border border-[#F0B232]/40">
                      <Award className="w-4 h-4" />
                    </div>
                    <div>
                      <div className="text-[10px] uppercase font-bold text-[#F0B232] tracking-wider">
                        The Monologue King
                      </div>
                      <div className="text-sm font-bold text-[#F2F3F5] flex items-center justify-center gap-1.5" dir="auto">
                        <span>👑</span>
                        <span>{analytics.longest_streak.speaker_name}</span>
                      </div>
                      <div className="text-lg font-extrabold font-mono text-[#F0B232]">
                        {formatStreakMMSS(analytics.longest_streak.streak_seconds)}
                      </div>
                      <div className="text-[10px] font-mono text-[#949BA4]">
                        ({formatDurationHuman(analytics.longest_streak.streak_seconds)} uninterrupted)
                      </div>
                    </div>
                  </div>

                  {/* The Silent Observer */}
                  {hasSpeakers && speakerEntries.length >= 2 && (() => {
                    const quietest = speakerEntries[speakerEntries.length - 1];
                    const secondQuietest = speakerEntries[speakerEntries.length - 2];
                    if (secondQuietest.talk_seconds - quietest.talk_seconds >= 1.0) {
                      const qPct = analytics.total_talk_seconds > 0 ? (quietest.talk_seconds / analytics.total_talk_seconds) * 100 : 0;
                      return (
                        <div className="p-2.5 rounded-xl bg-[#1e1f22] border border-[#5865F2]/30 flex items-center justify-between text-xs">
                          <div className="flex items-center gap-2">
                            <span className="text-base">🤫</span>
                            <div>
                              <div className="text-[9px] uppercase font-bold text-[#5865F2] tracking-wider">
                                The Silent Observer
                              </div>
                              <div className="font-bold text-[#F2F3F5] truncate max-w-[120px]" dir="auto">
                                {quietest.speaker_name}
                              </div>
                            </div>
                          </div>
                          <div className="text-right font-mono text-[#5865F2]">
                            <div className="font-bold text-xs">{formatDurationHuman(quietest.talk_seconds)}</div>
                            <div className="text-[9px] text-[#949BA4]">({qPct.toFixed(1)}% airtime)</div>
                          </div>
                        </div>
                      );
                    }
                    return null;
                  })()}

                  {/* The Most Unfiltered */}
                  {hasSpeakers && speakerEntries.length >= 2 && (() => {
                    const withVulgarity = speakerEntries.filter(s => (s.vulgarity_count || 0) > 0);
                    if (withVulgarity.length === 0) return null;
                    const sortedVulgar = [...withVulgarity].sort((a, b) => (b.vulgarity_count || 0) - (a.vulgarity_count || 0));
                    const top = sortedVulgar[0];
                    if (sortedVulgar.length >= 2 && (sortedVulgar[1].vulgarity_count || 0) === (top.vulgarity_count || 0)) {
                      return null;
                    }
                    return (
                      <div className="p-2.5 rounded-xl bg-[#1e1f22] border border-[#F23F43]/30 flex items-center justify-between text-xs">
                        <div className="flex items-center gap-2">
                          <span className="text-base">🌶️</span>
                          <div>
                            <div className="text-[9px] uppercase font-bold text-[#F23F43] tracking-wider">
                              The Most Unfiltered
                            </div>
                            <div className="font-bold text-[#F2F3F5] truncate max-w-[120px]" dir="auto">
                              {top.speaker_name}
                            </div>
                          </div>
                        </div>
                        <div className="text-right font-mono text-[#F23F43]">
                          <div className="font-bold text-xs">{top.vulgarity_count} raw tokens</div>
                          <div className="text-[9px] text-[#949BA4]">
                            {top.vulgarity_terms && top.vulgarity_terms.length > 0 ? top.vulgarity_terms.slice(0, 2).join(", ") : "uncensored"}
                          </div>
                        </div>
                      </div>
                    );
                  })()}

                  {/* The Diplomat */}
                  {hasSpeakers && speakerEntries.length >= 2 && (() => {
                    const diplomatCandidates = speakerEntries.filter(
                      s => (s.vulgarity_count || 0) === 0 && s.angry_episodes === 0 && s.talk_seconds >= 15.0
                    );
                    if (diplomatCandidates.length === 0) return null;
                    const sortedDiplomats = [...diplomatCandidates].sort((a, b) => b.talk_seconds - a.talk_seconds);
                    const topDiplomat = sortedDiplomats[0];
                    if (sortedDiplomats.length >= 2 && (topDiplomat.talk_seconds - sortedDiplomats[1].talk_seconds) < 1.0) {
                      return null;
                    }
                    return (
                      <div className="p-2.5 rounded-xl bg-[#1e1f22] border border-[#23A55A]/30 flex items-center justify-between text-xs">
                        <div className="flex items-center gap-2">
                          <span className="text-base">🕊️</span>
                          <div>
                            <div className="text-[9px] uppercase font-bold text-[#23A55A] tracking-wider">
                              The Diplomat
                            </div>
                            <div className="font-bold text-[#F2F3F5] truncate max-w-[120px]" dir="auto">
                              {topDiplomat.speaker_name}
                            </div>
                          </div>
                        </div>
                        <div className="text-right font-mono text-[#23A55A]">
                          <div className="font-bold text-xs">{formatDurationHuman(topDiplomat.talk_seconds)}</div>
                          <div className="text-[9px] text-[#949BA4]">100% peaceful</div>
                        </div>
                      </div>
                    );
                  })()}

                  {/* The Roast Master */}
                  {hasSpeakers && speakerEntries.length >= 2 && (() => {
                    const withBanter = speakerEntries.filter(s => (s.banter_count || 0) > 0);
                    if (withBanter.length === 0) return null;
                    const sortedBanter = [...withBanter].sort((a, b) => (b.banter_count || 0) - (a.banter_count || 0));
                    const topBanter = sortedBanter[0];
                    if (sortedBanter.length >= 2 && (sortedBanter[1].banter_count || 0) === (topBanter.banter_count || 0)) {
                      return null;
                    }
                    return (
                      <div className="p-2.5 rounded-xl bg-[#1e1f22] border border-purple-500/30 flex items-center justify-between text-xs">
                        <div className="flex items-center gap-2">
                          <span className="text-base">🎭</span>
                          <div>
                            <div className="text-[9px] uppercase font-bold text-purple-400 tracking-wider">
                              The Roast Master
                            </div>
                            <div className="font-bold text-[#F2F3F5] truncate max-w-[120px]" dir="auto">
                              {topBanter.speaker_name}
                            </div>
                          </div>
                        </div>
                        <div className="text-right font-mono text-purple-400">
                          <div className="font-bold text-xs">{topBanter.banter_count} {topBanter.banter_count === 1 ? "roast turn" : "roast turns"}</div>
                          <div className="text-[9px] text-[#949BA4]">
                            {topBanter.banter_terms && topBanter.banter_terms.length > 0 ? topBanter.banter_terms.slice(0, 2).join(", ") : "friendly teasing"}
                          </div>
                        </div>
                      </div>
                    );
                  })()}
                </div>
              ) : (
                <div className="py-6 text-center text-xs text-[#949BA4] italic">
                  waiting for call data…
                </div>
              )}
            </div>

            {/* 2. TALK TIME SHARE */}
            <div className="rounded-2xl bg-[#2b2d31] border border-[#383a40] p-5 space-y-3 shadow-lg">
              <div className="flex items-center justify-between border-b border-[#383a40] pb-3">
                <div className="flex items-center gap-2">
                  <Clock className="w-4 h-4 text-cyan-400" />
                  <h3 className="text-sm font-bold text-[#F2F3F5] tracking-wide uppercase">
                    Talk Time Share
                  </h3>
                </div>
                {analytics.total_talk_seconds > 0 && (
                  <span className="text-[10px] font-mono font-bold text-cyan-400">
                    {formatDurationHuman(analytics.total_talk_seconds)} total
                  </span>
                )}
              </div>

              {hasSpeakers && analytics.total_talk_seconds > 0 ? (
                <div className="space-y-2.5">
                  {speakerEntries.map((s, idx) => {
                    const pct = analytics.total_talk_seconds > 0 ? (s.talk_seconds / analytics.total_talk_seconds) * 100 : 0;
                    return (
                      <div key={s.speaker_name || idx} className="space-y-1">
                        <div className="flex items-center justify-between text-xs font-medium">
                          <span className="text-[#F2F3F5] font-semibold" dir="auto">
                            {s.speaker_name}
                          </span>
                          <span className="font-mono text-cyan-400">
                            {formatDurationHuman(s.talk_seconds)} ({pct.toFixed(1)}%)
                          </span>
                        </div>
                        <div className="w-full bg-[#1e1f22] h-2 rounded-full overflow-hidden border border-[#383a40]">
                          <div
                            className="h-full bg-cyan-500 rounded-full transition-all duration-500"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="py-6 text-center text-xs text-[#949BA4] italic">
                  waiting for call data…
                </div>
              )}
            </div>

            {/* 3. ANGER LEADERBOARD & AUDIO RECEIPTS */}
            <div className="rounded-2xl bg-[#2b2d31] border border-[#383a40] p-5 space-y-3 shadow-lg">
              <div className="flex items-center justify-between border-b border-[#383a40] pb-3">
                <div className="flex items-center gap-2">
                  <Flame className="w-4 h-4 text-[#F23F43]" />
                  <h3 className="text-sm font-bold text-[#F2F3F5] tracking-wide uppercase">
                    Anger Receipts & Audio Evidence
                  </h3>
                </div>
                {analytics.total_angry_episodes > 0 && (
                  <span className="text-[10px] font-mono font-bold text-[#F23F43]">
                    {analytics.total_angry_episodes} {analytics.total_angry_episodes === 1 ? "episode" : "episodes"}
                  </span>
                )}
              </div>

              {!hasSpeakers ? (
                <div className="py-6 text-center text-xs text-[#949BA4] italic">
                  waiting for call data…
                </div>
              ) : analytics.total_angry_episodes === 0 || angrySpeakers.length === 0 ? (
                <div className="py-5 px-3 rounded-lg bg-[#23A55A]/10 border border-[#23A55A]/30 text-center space-y-1">
                  <Smile className="w-5 h-5 text-[#23A55A] mx-auto" />
                  <p className="text-xs text-[#23A55A] font-medium">
                    Nobody got angry this call... suspicious.
                  </p>
                </div>
              ) : (
                <div className="space-y-3 max-h-56 overflow-y-auto pr-1">
                  {angrySpeakers.map((s, idx) => {
                    const fallbackQuote = (s.anger_evidence || s.first_anger_quote || "").trim();
                    const validHistory = (s.anger_episodes_history || []).filter(
                      (ep) => ep.quote && ep.quote.trim() !== "" && ep.quote !== "(no verbal evidence captured)"
                    );
                    const history = validHistory.length > 0
                      ? validHistory
                      : (fallbackQuote && fallbackQuote !== "(no verbal evidence captured)"
                          ? [{ quote: fallbackQuote, episode_number: s.angry_episodes }]
                          : []);

                    if (history.length === 0) return null;

                    return (
                      <div key={s.speaker_name || idx} className="p-3 rounded-xl bg-[#1e1f22] border border-[#F23F43]/30 space-y-2">
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-bold text-[#F2F3F5]" dir="auto">
                            {s.speaker_name}
                          </span>
                          <span className="px-1.5 py-0.5 rounded bg-[#F23F43]/20 text-[#F23F43] font-mono font-bold text-[10px]">
                            {s.angry_episodes} {s.angry_episodes === 1 ? "episode" : "episodes"}
                          </span>
                        </div>
                        {history.map((ep, eIdx) => {
                          const isLoud = Boolean(ep.was_loud || (ep.peak_z && ep.peak_z >= 2.5));
                          const clampedZ = ep.peak_z ? Math.min(10.0, ep.peak_z).toFixed(1) : "2.8";
                          return (
                            <div
                              key={eIdx}
                              className="text-[11px] text-[#DBDEE1] bg-[#313338] border border-[#383a40] rounded-lg p-2 space-y-1.5"
                            >
                              <div className="flex items-center justify-between text-[9px] font-mono text-[#949BA4]">
                                <span className="text-[#F0B232] font-semibold">
                                  {ep.episode_number ? `Ep #${ep.episode_number}` : "Receipt"}
                                </span>
                                {isLoud ? (
                                  <span className="text-[#F23F43] font-bold flex items-center gap-0.5">
                                    <span>🔊</span>
                                    <span>+{clampedZ}σ spike</span>
                                  </span>
                                ) : (
                                  <span className="text-[#949BA4]">vocal friction</span>
                                )}
                              </div>
                              <div className="italic" dir="auto">
                                "{ep.quote}"
                              </div>
                              {ep.audio_clip && (
                                <div className="pt-1 mt-1 border-t border-[#383a40] flex items-center justify-between text-[10px]">
                                  <button
                                    onClick={() => {
                                      const audio = new Audio(`/api/audio-evidence/${ep.audio_clip}`);
                                      audio.play().catch(e => console.error("Playback error:", e));
                                    }}
                                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-[#F23F43]/20 hover:bg-[#F23F43]/30 text-[#F23F43] font-mono border border-[#F23F43]/40 transition-colors cursor-pointer"
                                    title={`Play audio evidence: ${ep.audio_clip}`}
                                  >
                                    <span>▶️</span>
                                    <span>Play Audio Evidence</span>
                                  </button>
                                  <span className="font-mono text-[9px] text-[#949BA4] truncate max-w-[110px]" title={ep.audio_clip}>
                                    {ep.audio_clip}
                                  </span>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* 4. TOPIC DISTRIBUTION */}
            <div className="rounded-2xl bg-[#2b2d31] border border-[#383a40] p-5 space-y-3 shadow-lg">
              <div className="flex items-center justify-between border-b border-[#383a40] pb-3">
                <div className="flex items-center gap-2">
                  <PieChart className="w-4 h-4 text-[#5865F2]" />
                  <h3 className="text-sm font-bold text-[#F2F3F5] tracking-wide uppercase">
                    Topic Distribution
                  </h3>
                </div>
                {totalAllTopics > 0 && (
                  <span className="text-[10px] font-mono text-[#949BA4]">
                    {topicalCoveragePct.toFixed(0)}% coverage
                  </span>
                )}
              </div>

              {totalTopicalCount > 0 ? (
                <div className="space-y-2.5">
                  {sortedTopics.map(([topic, count], idx) => {
                    const pct = (count / totalTopicalCount) * 100;
                    const color = TOPIC_COLORS[idx % TOPIC_COLORS.length];
                    return (
                      <div key={topic} className="space-y-1">
                        <div className="flex items-center justify-between text-xs font-medium">
                          <span className="text-[#DBDEE1] capitalize">
                            {TOPIC_DISPLAY_NAMES[topic.toLowerCase()] ? `${topic} (${TOPIC_DISPLAY_NAMES[topic.toLowerCase()]})` : topic}
                          </span>
                          <span className="font-mono text-[#949BA4]">
                            {count} ({pct.toFixed(1)}%)
                          </span>
                        </div>
                        <div className="w-full bg-[#1e1f22] h-2 rounded-full overflow-hidden border border-[#383a40]">
                          <div
                            className={`h-full ${color} rounded-full transition-all duration-500`}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="py-6 text-center text-xs text-[#949BA4] italic">
                  waiting for call data…
                </div>
              )}
            </div>

            {/* 5. SERVER EVIDENCE & ACCURACY LEADERBOARD */}
            <div className="rounded-2xl bg-[#2b2d31] border border-[#383a40] p-5 space-y-3 shadow-lg">
              <div className="flex items-center justify-between border-b border-[#383a40] pb-3">
                <div className="flex items-center gap-2">
                  <Award className="w-4 h-4 text-[#23A55A]" />
                  <h3 className="text-sm font-bold text-[#F2F3F5] tracking-wide uppercase">
                    Accuracy Leaderboard
                  </h3>
                </div>
                <div className="flex items-center gap-3 text-xs">
                  <span className="text-[#23A55A] font-mono font-bold">
                    {leaderboard["Verified Claims"]} Verified
                  </span>
                  <span className="text-[#949BA4]">•</span>
                  <span className="text-[#F23F43] font-mono font-bold">
                    {leaderboard["Disputed Claims"]} Contradicted
                  </span>
                </div>
              </div>

              {Object.keys(leaderboard.Speakers || {}).length > 0 ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  {Object.entries(leaderboard.Speakers).map(([name, stats]) => (
                    <div key={name} className="p-3 rounded-xl bg-[#1e1f22] border border-[#383a40] space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-[#F2F3F5] flex items-center gap-1.5" dir="auto">
                          <Users className="w-3.5 h-3.5 text-[#5865F2]" />
                          {name}
                        </span>
                        <span className="text-[10px] text-[#949BA4] font-mono">
                          {stats.turns} turns
                        </span>
                      </div>
                      <div className="flex items-center gap-2 text-xs">
                        <span className="px-2 py-0.5 rounded bg-[#23A55A]/20 text-[#23A55A] border border-[#23A55A]/30 text-[11px] font-semibold">
                          ✅ {stats.verified}
                        </span>
                        <span className="px-2 py-0.5 rounded bg-[#F23F43]/20 text-[#F23F43] border border-[#F23F43]/30 text-[11px] font-semibold">
                          ❌ {stats.refuted}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-[#949BA4] italic text-center py-2">
                  Participant statistics will populate automatically as voice activity is recorded.
                </p>
              )}
            </div>

          </div>

        </div>
      </main>

      {/* 4. POST-CALL CALLWRAPPED RECAP MODAL */}
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
