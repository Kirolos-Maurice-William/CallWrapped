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
  RefreshCw,
  Play,
  Users,
  ShieldCheck,
  Search,
  Cpu,
  MessageSquare,
  AlertTriangle,
  Award,
  HelpCircle,
  RotateCcw,
  Check
} from "lucide-react";

import {
  AnalyticsWidgets,
  AnalyticsState,
  SpeakerAnalytics
} from "../components/AnalyticsWidgets";

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

export default function VoiceArbitratorDashboard() {
  const [isConnected, setIsConnected] = useState(false);
  const [connectionType, setConnectionType] = useState<"ws" | "poll">("poll");
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
    longest_streak: {
      speaker_name: null,
      streak_seconds: 0,
    },
  });
  const [turns, setTurns] = useState<Turn[]>([]);
  const [activeDispute, setActiveDispute] = useState<DisputeInfo | null>(null);
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

      // If an event carries anger_evidence or first_anger_quote, cache it
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
            anger_evidence: spk.anger_evidence || spk.first_anger_quote || cache[name] || undefined
          };
        }
      }

      setAnalytics({
        topic_totals: rawAnalytics.topic_totals || {},
        speakers: mergedSpeakers,
        total_talk_seconds: Number(rawAnalytics.total_talk_seconds || 0),
        total_angry_episodes: Number(rawAnalytics.total_angry_episodes || 0),
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
          const data = await resLive.json();
          if (isMounted) {
            setIsConnected(true);
            if (data.latency) setLatency(data.latency);
            if (data.turns) setTurns(data.turns);
            if (data.active_dispute) setActiveDispute(data.active_dispute);
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
        if (isMounted) setIsConnected(false);
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
              if (d.latency) setLatency(d.latency);
              if (d.turns) setTurns(d.turns);
              if (d.active_dispute) setActiveDispute(d.active_dispute);
              if (d.disputes_history) setDisputesHistory(d.disputes_history);
              if (d.leaderboard) setLeaderboard(d.leaderboard);
              if (d.analytics) applyAnalytics(d.analytics);
            } else if (msg.live_state) {
              const d = msg.live_state;
              if (d.latency) setLatency(d.latency);
              if (d.turns) setTurns(d.turns);
              if (d.active_dispute) setActiveDispute(d.active_dispute);
              if (d.disputes_history) setDisputesHistory(d.disputes_history);
              if (d.leaderboard) setLeaderboard(d.leaderboard);
              if (d.analytics) applyAnalytics(d.analytics, msg.event);
            }

            if (msg.analytics) {
              applyAnalytics(msg.analytics, msg.event);
            }

            if (msg.type === "analytics_update" && msg.event) {
              // Direct analytics update event
              applyAnalytics(msg.analytics || analytics, msg.event);
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

  const totalCalculatedLatency =
    (latency.stt_ms || 0) + (latency.llm_ms || 0) + (latency.search_ms || 0) + (latency.tts_ms || 0);

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

  // Simulate Casual Banter (ignored by Silent Referee)
  const handleSimulateCasual = async () => {
    const { http } = getBackendBase();
    try {
      await fetch(`${http}/api/events`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          event_id: `evt_casual_${Date.now()}`,
          session_id: "hackathon_live_session",
          timestamp: Date.now() / 1000,
          type: "transcript",
          speaker_name: "Ahmed",
          text: "My ping is a bit high on this game server, going to restart the router and reconnect.",
          latency: { stt_ms: 245 }
        })
      });
    } catch (e) {
      console.error("Casual simulation failed:", e);
    }
  };

  return (
    <div className="min-h-screen bg-[#070b13] text-slate-100 flex flex-col font-sans selection:bg-indigo-600 selection:text-white">
      {/* 1. TOP HEADER & STATUS BAR */}
      <header className="border-b border-slate-800/80 bg-[#0b1120]/90 backdrop-blur sticky top-0 z-50 px-4 md:px-8 py-3.5 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-gradient-to-tr from-indigo-600 to-cyan-500 text-white shadow-lg shadow-indigo-500/20">
            <Scale className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg md:text-xl font-bold tracking-tight bg-gradient-to-r from-white via-slate-100 to-slate-400 bg-clip-text text-transparent">
                VOICE ARBITRATOR
              </h1>
              <span className="text-[11px] font-semibold tracking-wider uppercase px-2 py-0.5 rounded-md bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                AssemblyAI Voice Agent Hackathon
              </span>
            </div>
            <p className="text-xs text-slate-400 hidden sm:block">
              Multi-Speaker Discord E2EE • Universal-3.5 Pro Code-Switching • Groq LPU • Tavily Ground-Truth
            </p>
          </div>
        </div>

        {/* Live Indicator & Controls */}
        <div className="flex items-center gap-2 sm:gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-900/90 border border-slate-800 text-xs">
            <span className={`w-2.5 h-2.5 rounded-full ${isConnected ? "bg-emerald-400 animate-pulse" : "bg-rose-500"}`} />
            <span className="font-medium text-slate-300">
              {isConnected ? (connectionType === "ws" ? "LIVE STREAMING" : "POLLING ACTIVE") : "DISCONNECTED"}
            </span>
          </div>

          <button
            onClick={handleTriggerReplay}
            disabled={isSimulating}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-semibold shadow-md shadow-emerald-600/20 transition-all cursor-pointer"
            title="Replay RTX 5070 Golden Demo Session"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
            <span>{isSimulating ? "Replaying Demo..." : "Demo Replay (RTX 5070)"}</span>
          </button>

          <button
            onClick={handleSimulateCasual}
            className="hidden md:flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs transition-colors"
            title="Inject casual banter to show referee ignores it"
          >
            <MessageSquare className="w-3.5 h-3.5" />
            <span>Send Banter</span>
          </button>

          <button
            onClick={handleReset}
            className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-200 transition-colors"
            title="Reset Session Data"
          >
            <RotateCcw className="w-4 h-4" />
          </button>
        </div>
      </header>

      {/* 2. REAL-TIME LATENCY PIPELINE TICKER */}
      <section className="bg-slate-900/60 border-b border-slate-800/80 px-4 md:px-8 py-2.5">
        <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-2 text-slate-400 font-semibold tracking-wider uppercase text-[11px]">
            <Zap className="w-3.5 h-3.5 text-amber-400" />
            <span>Realtime Pipeline Latency:</span>
          </div>

          <div className="flex flex-wrap items-center gap-2 sm:gap-4">
            {/* Stage 1: STT */}
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-cyan-950/40 border border-cyan-800/40 text-cyan-300">
              <span className="text-[10px] text-cyan-500 font-mono">1. STT</span>
              <span className="font-semibold">AssemblyAI Universal-3.5:</span>
              <span className="font-mono font-bold text-white">{latency.stt_ms ?? 0}ms</span>
            </div>

            {/* Stage 2: Groq LLM */}
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-purple-950/40 border border-purple-800/40 text-purple-300">
              <span className="text-[10px] text-purple-500 font-mono">2. LPU</span>
              <span className="font-semibold">Groq Epistemic Engine:</span>
              <span className="font-mono font-bold text-white">{latency.llm_ms ?? 0}ms</span>
            </div>

            {/* Stage 3: Tavily Search */}
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-amber-950/40 border border-amber-800/40 text-amber-300">
              <span className="text-[10px] text-amber-500 font-mono">3. WEB</span>
              <span className="font-semibold">Tavily Tier-1 Search:</span>
              <span className="font-mono font-bold text-white">{latency.search_ms ?? 0}ms</span>
            </div>

            {/* Stage 4: Neural TTS */}
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-950/40 border border-emerald-800/40 text-emerald-300">
              <span className="text-[10px] text-emerald-500 font-mono">4. VOICE</span>
              <span className="font-semibold">Edge Neural Shakir:</span>
              <span className="font-mono font-bold text-white">{latency.tts_ms ?? 0}ms</span>
            </div>

            {/* Total */}
            <div className="px-2.5 py-1 rounded-md bg-indigo-900/40 border border-indigo-700/50 text-indigo-200 font-mono font-bold">
              Total: ~{(totalCalculatedLatency / 1000).toFixed(2)}s
            </div>
          </div>
        </div>
      </section>

      {/* 3. MAIN DASHBOARD CONTENT */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 md:p-6 flex flex-col space-y-6">
        {/* REAL-TIME CALL ANALYTICS WIDGETS */}
        <AnalyticsWidgets analytics={analytics} />

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* LEFT/CENTER: HERO ACTIVE DISPUTE CARD & PAST DISPUTES (7 COLS) */}
          <div className="lg:col-span-7 flex flex-col space-y-6">

          {/* ACTIVE DISPUTE CARD */}
          <div className="relative rounded-2xl bg-gradient-to-b from-slate-900/90 to-slate-950/90 border-2 border-emerald-500/40 shadow-2xl shadow-emerald-500/10 p-5 md:p-6 overflow-hidden">
            {/* Header Badge */}
            <div className="flex items-center justify-between gap-3 border-b border-slate-800 pb-4 mb-5">
              <div className="flex items-center gap-2">
                <span className="p-2 rounded-xl bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                  <ShieldCheck className="w-5 h-5" />
                </span>
                <div>
                  <h2 className="text-base font-bold text-white tracking-wide flex items-center gap-2">
                    EVIDENCE-BASED ARBITRATION
                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 animate-pulse">
                      VERIFIED
                    </span>
                  </h2>
                  <p className="text-xs text-slate-400">
                    Contradiction caught, verified against authoritative sources, and settled via voice intervention.
                  </p>
                </div>
              </div>

              {activeDispute?.confidence && (
                <div className="text-right">
                  <span className="text-[10px] text-slate-400 uppercase font-mono block">Confidence</span>
                  <span className="text-sm font-bold text-emerald-400 font-mono">{activeDispute.confidence}%</span>
                </div>
              )}
            </div>

            {activeDispute ? (
              <div className="space-y-5">
                {/* OPPOSING CLAIMS COMPARISON */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {/* Claim A */}
                  <div className={`p-4 rounded-xl border transition-all ${
                    activeDispute.speaker_a_status === "SUPPORTED"
                      ? "bg-emerald-950/20 border-emerald-500/50"
                      : "bg-rose-950/20 border-rose-500/40"
                  }`}>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                        <Users className="w-3.5 h-3.5 text-slate-400" />
                        {activeDispute.speaker_a || "Speaker A"}
                      </span>
                      {activeDispute.speaker_a_status === "SUPPORTED" ? (
                        <span className="flex items-center gap-1 text-[11px] font-bold text-emerald-400">
                          <CheckCircle2 className="w-3.5 h-3.5" /> SUPPORTED
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 text-[11px] font-bold text-rose-400">
                          <XCircle className="w-3.5 h-3.5" /> CONTRADICTED
                        </span>
                      )}
                    </div>
                    <p className="text-sm font-medium text-slate-200 dir-rtl text-right">
                      "{activeDispute.claim_a}"
                    </p>
                  </div>

                  {/* Claim B */}
                  <div className={`p-4 rounded-xl border transition-all ${
                    activeDispute.speaker_b_status === "SUPPORTED"
                      ? "bg-emerald-950/20 border-emerald-500/50"
                      : "bg-rose-950/20 border-rose-500/40"
                  }`}>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                        <Users className="w-3.5 h-3.5 text-slate-400" />
                        {activeDispute.speaker_b || "Speaker B"}
                      </span>
                      {activeDispute.speaker_b_status === "SUPPORTED" ? (
                        <span className="flex items-center gap-1 text-[11px] font-bold text-emerald-400">
                          <CheckCircle2 className="w-3.5 h-3.5" /> SUPPORTED
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 text-[11px] font-bold text-rose-400">
                          <XCircle className="w-3.5 h-3.5" /> CONTRADICTED
                        </span>
                      )}
                    </div>
                    <p className="text-sm font-medium text-slate-200 dir-rtl text-right">
                      "{activeDispute.claim_b}"
                    </p>
                  </div>
                </div>

                {/* GROUND TRUTH VERIFIED FACT */}
                <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-700/80">
                  <div className="flex items-center justify-between gap-2 mb-1.5">
                    <span className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-emerald-400">
                      <CheckCircle2 className="w-4 h-4" />
                      <span>Verified Ground Truth:</span>
                    </span>
                    {activeDispute.evidence_strength && (
                      <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded bg-emerald-900/50 text-emerald-300 border border-emerald-700/40">
                        Evidence: {activeDispute.evidence_strength}
                      </span>
                    )}
                  </div>
                  <p className="text-sm md:text-base font-semibold text-white">
                    {activeDispute.correct_fact}
                  </p>
                </div>

                {/* WHY DID THE AGENT SPEAK? EXPLAINABILITY BLOCK */}
                <div className="p-4 rounded-xl bg-slate-950/70 border border-slate-800 space-y-2">
                  <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-cyan-400">
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
                      <div key={idx} className="flex items-center gap-2 text-xs text-slate-300">
                        <span className="w-4 h-4 rounded-full bg-emerald-950 border border-emerald-500/50 flex items-center justify-center text-emerald-400 text-[10px]">
                          ✓
                        </span>
                        <span>{reason}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* SPOKEN NEURAL VOICE INTERVENTION */}
                <div className="p-4 rounded-xl bg-indigo-950/30 border border-indigo-500/30">
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <span className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-indigo-300">
                      <Volume2 className="w-4 h-4 text-indigo-400" />
                      <span>Referee Spoken Intervention (Template-Based):</span>
                    </span>
                    <span className="text-[10px] text-indigo-400 font-mono">Edge Neural ar-EG-Shakir</span>
                  </div>
                  <p className="text-sm font-medium text-slate-200 dir-rtl text-right leading-relaxed bg-slate-950/40 p-3 rounded-lg border border-slate-800">
                    "{activeDispute.spoken_intervention}"
                  </p>
                </div>

                {/* CLICKABLE OFFICIAL WEB CITATION */}
                {activeDispute.source_url && (
                  <div className="flex items-center justify-between gap-3 p-3.5 rounded-xl bg-slate-950/60 border border-slate-800">
                    <div className="flex items-center gap-2 truncate">
                      <Search className="w-4 h-4 text-slate-400 flex-shrink-0" />
                      <span className="text-xs text-slate-400 font-medium">Source:</span>
                      <span className="text-xs font-semibold text-slate-200 truncate">
                        {activeDispute.source_title || "Verified Documentation"}
                      </span>
                    </div>
                    <a
                      href={activeDispute.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600/30 hover:bg-indigo-600/50 text-indigo-300 border border-indigo-500/30 text-xs font-semibold transition-all flex-shrink-0"
                    >
                      <span>Open Source</span>
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  </div>
                )}
              </div>
            ) : (
              <div className="py-12 px-4 text-center space-y-4">
                <div className="w-14 h-14 mx-auto rounded-2xl bg-slate-800/80 border border-slate-700 flex items-center justify-center text-slate-400">
                  <Scale className="w-7 h-7" />
                </div>
                <div className="space-y-1">
                  <h3 className="text-base font-semibold text-slate-200">
                    Silent Referee Standing By
                  </h3>
                  <p className="text-xs text-slate-400 max-w-md mx-auto">
                    The bot listens silently to multi-speaker conversation in Discord. When an objective factual disagreement is detected, it queries Tavily and intervenes with the verified facts.
                  </p>
                </div>
                <button
                  onClick={handleTriggerReplay}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow-lg shadow-emerald-600/20 transition-all cursor-pointer"
                >
                  <Play className="w-4 h-4 fill-current" />
                  <span>Run Demo Replay (RTX 5070 Dispute)</span>
                </button>
              </div>
            )}
          </div>

          {/* EVIDENCE LEADERBOARD & SERVER INSIGHTS */}
          <div className="rounded-2xl bg-slate-900/80 border border-slate-800 p-5 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <Award className="w-4 h-4 text-amber-400" />
                <h3 className="text-sm font-bold text-white tracking-wide">
                  SERVER EVIDENCE & ACCURACY LEADERBOARD
                </h3>
              </div>
              <div className="flex items-center gap-3 text-xs">
                <span className="text-emerald-400 font-mono font-bold">
                  {leaderboard["Verified Claims"]} Verified
                </span>
                <span className="text-slate-600">•</span>
                <span className="text-rose-400 font-mono font-bold">
                  {leaderboard["Disputed Claims"]} Contradicted
                </span>
              </div>
            </div>

            {Object.keys(leaderboard.Speakers || {}).length > 0 ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
                {Object.entries(leaderboard.Speakers).map(([name, stats]) => (
                  <div key={name} className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/80 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-white flex items-center gap-1.5">
                        <Users className="w-3.5 h-3.5 text-indigo-400" />
                        {name}
                      </span>
                      <span className="text-[10px] text-slate-400 font-mono">
                        {stats.turns} turns
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-xs">
                      <span className="px-2 py-0.5 rounded bg-emerald-950/50 text-emerald-400 border border-emerald-800/30 text-[11px] font-semibold">
                        ✅ {stats.verified}
                      </span>
                      <span className="px-2 py-0.5 rounded bg-rose-950/50 text-rose-400 border border-rose-800/30 text-[11px] font-semibold">
                        ❌ {stats.refuted}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-500 italic text-center py-2">
                Participant statistics will populate automatically as voice activity is recorded.
              </p>
            )}
          </div>

          {/* HISTORICAL DISPUTES LIST */}
          {disputesHistory.length > 1 && (
            <div className="rounded-2xl bg-slate-900/60 border border-slate-800 p-5 space-y-3">
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                Previous Arbitrated Disputes ({disputesHistory.length})
              </h3>
              <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                {disputesHistory.slice(0, -1).reverse().map((d, i) => (
                  <div key={i} className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/70 text-xs flex items-center justify-between gap-3">
                    <div className="truncate space-y-0.5">
                      <p className="font-semibold text-slate-200 truncate">
                        {d.correct_fact}
                      </p>
                      <p className="text-[11px] text-slate-400 truncate">
                        {d.speaker_a}: <span className={d.speaker_a_status === "SUPPORTED" ? "text-emerald-400" : "text-rose-400"}>{d.speaker_a_status}</span> | {d.speaker_b}: <span className={d.speaker_b_status === "SUPPORTED" ? "text-emerald-400" : "text-rose-400"}>{d.speaker_b_status}</span>
                      </p>
                    </div>
                    {d.source_url && (
                      <a
                        href={d.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-indigo-400 hover:text-indigo-300 p-1 flex-shrink-0"
                      >
                        <ExternalLink className="w-3.5 h-3.5" />
                      </a>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

        </div>

        {/* RIGHT: REAL-TIME VERBATIM TRANSCRIPT STREAM (5 COLS) */}
        <div className="lg:col-span-5 flex flex-col h-[700px] rounded-2xl bg-slate-900/80 border border-slate-800 overflow-hidden">
          {/* Stream Header */}
          <div className="p-4 border-b border-slate-800 bg-slate-900 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Radio className="w-4 h-4 text-rose-500 animate-pulse" />
              <h2 className="text-sm font-bold text-white tracking-wide">
                DISCORD VOICE TRANSCRIPT STREAM
              </h2>
            </div>
            <span className="text-[11px] font-mono text-slate-400">
              {turns.length} utterances
            </span>
          </div>

          {/* Transcript Feed */}
          <div
            ref={transcriptScrollRef}
            className="flex-1 p-4 overflow-y-auto space-y-3 scroll-smooth"
          >
            {turns.length > 0 ? (
              turns.map((t, idx) => (
                <div
                  key={idx}
                  className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800/80 space-y-1.5 hover:border-slate-700 transition-colors"
                >
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-bold text-indigo-300 flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-indigo-500" />
                      {t.speaker_name}
                    </span>
                    <div className="flex items-center gap-2">
                      {t.stt_ms && (
                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-400 border border-cyan-800/40">
                          {t.stt_ms}ms
                        </span>
                      )}
                      <span className="text-[10px] text-slate-500 font-mono">
                        {new Date(t.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                      </span>
                    </div>
                  </div>
                  <p className="text-sm text-slate-200 leading-relaxed dir-rtl text-right font-normal">
                    {t.text}
                  </p>
                </div>
              ))
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-center p-6 text-slate-500 space-y-3">
                <MessageSquare className="w-8 h-8 opacity-40" />
                <p className="text-xs max-w-xs">
                  Listening for speech in Discord voice channel... Utterances with bilingual code-switching will stream here verbatim.
                </p>
              </div>
            )}
          </div>

          {/* Stream Footer Info */}
          <div className="p-3 border-t border-slate-800/80 bg-slate-950/50 flex items-center justify-between text-[11px] text-slate-400 font-mono">
            <span className="flex items-center gap-1">
              <Cpu className="w-3 h-3 text-cyan-400" />
              <span>Universal-3.5 Pro Code-Switching</span>
            </span>
            <span>Raw Verbatim Evidence</span>
          </div>
        </div>

        </div>
      </main>
    </div>
  );
}
