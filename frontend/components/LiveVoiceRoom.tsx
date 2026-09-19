"use client";

import React, { useState, useEffect, useRef } from "react";
import { Mic, MicOff, Volume2, ShieldCheck, Flame, MessageSquare, AlertCircle, ExternalLink, Square, CheckCircle2, XCircle, Zap, Activity } from "lucide-react";
import { AudioStreamer } from "./AudioStreamer";

interface Turn {
  id: string;
  speaker_id: string;
  speaker_name: string;
  start_ms: number;
  end_ms: number;
  text: string;
  language: string;
  analysis?: {
    topic: string;
    intent: string;
    heat_score: number;
    is_claim: boolean;
    is_disagreement: boolean;
  };
  latency_telemetry?: {
    turn_analysis_ms: number;
  };
}

interface FactCheckAlert {
  claim_id: string;
  topic: string;
  dispute: any;
  result: "supported" | "contradicted" | "inconclusive";
  confidence: number;
  evidence: string;
  sources: Array<{ title: string; url: string; snippet?: string }>;
  interrupted: boolean;
  interruption_text?: string;
  audio_data?: string;
  latency_waterfall?: {
    search_retrieval_ms: number;
    fact_verification_ms: number;
    tts_synthesis_ms: number;
    total_end_to_end_ms: number;
  };
}

export default function LiveVoiceRoom({
  callId,
  role = "you",
  onEndCall,
}: {
  callId: string;
  role?: "you" | "friend";
  onEndCall: () => void;
}) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [partialTurn, setPartialTurn] = useState<string>("");
  const [partialSpeaker, setPartialSpeaker] = useState<string>("");
  const [currentTopic, setCurrentTopic] = useState<string>("general");
  const [heatScore, setHeatScore] = useState<number>(0.1);
  const [isMicActive, setIsMicActive] = useState<boolean>(false);
  const [micAudioLevel, setMicAudioLevel] = useState<number>(0);
  const [copiedInvite, setCopiedInvite] = useState<boolean>(false);
  const [factCheckAlert, setFactCheckAlert] = useState<FactCheckAlert | null>(null);
  const [latestLatency, setLatestLatency] = useState<{
    turnMs?: number;
    searchMs?: number;
    verifyMs?: number;
    ttsMs?: number;
    totalMs?: number;
  }>({});
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0);

  const streamerRef = useRef<AudioStreamer | null>(null);
  const roomWsRef = useRef<WebSocket | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const audioPlayerRef = useRef<HTMLAudioElement | null>(null);

  const getWsBaseUrl = () => {
    if (process.env.NEXT_PUBLIC_WS_URL) return process.env.NEXT_PUBLIC_WS_URL;
    if (typeof window !== "undefined") {
      const isHttps = window.location.protocol === "https:";
      // If deployed or tunneled on same host or port 8000
      return `${isHttps ? "wss" : "ws"}://${window.location.hostname}:8000`;
    }
    return "ws://localhost:8000";
  };

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [turns, partialTurn]);

  useEffect(() => {
    const timer = setInterval(() => {
      setElapsedSeconds((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    const wsBase = getWsBaseUrl();
    const ws = new WebSocket(`${wsBase}/ws/room/${callId}`);
    roomWsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        const { type, data } = msg;

        if (type === "transcript_partial") {
          setPartialSpeaker(data.speaker_name);
          setPartialTurn(data.text);
        } else if (type === "transcript_final") {
          setPartialTurn("");
          setPartialSpeaker("");
          setTurns((prev) => [
            ...prev,
            {
              id: data.turn_id || Math.random().toString(),
              speaker_id: data.speaker_id,
              speaker_name: data.speaker_name,
              start_ms: data.start_ms,
              end_ms: data.end_ms,
              text: data.text,
              language: data.language,
              analysis: data.analysis,
              latency_telemetry: data.latency_telemetry,
            },
          ]);

          if (data.analysis) {
            setCurrentTopic(data.analysis.topic);
            setHeatScore(data.analysis.heat_score);
          }
          if (data.latency_telemetry) {
            setLatestLatency((prev) => ({ ...prev, turnMs: data.latency_telemetry.turn_analysis_ms }));
          }
        } else if (type === "fact_check_result") {
          setFactCheckAlert(data);
          if (data.latency_waterfall) {
            setLatestLatency({
              searchMs: data.latency_waterfall.search_retrieval_ms,
              verifyMs: data.latency_waterfall.fact_verification_ms,
              ttsMs: data.latency_waterfall.tts_synthesis_ms,
              totalMs: data.latency_waterfall.total_end_to_end_ms,
            });
          }
          if (data.audio_data && audioPlayerRef.current) {
            audioPlayerRef.current.src = data.audio_data;
            audioPlayerRef.current.play().catch((e) => console.log("Audio autoplay prevented:", e));
          }
        }
      } catch (e) {
        console.error("Error handling room ws message:", e);
      }
    };

    return () => {
      ws.close();
    };
  }, [callId]);

  const handleCopyInviteLink = () => {
    if (typeof window === "undefined") return;
    const url = `${window.location.origin}/?callId=${callId}&role=friend`;
    navigator.clipboard.writeText(url);
    setCopiedInvite(true);
    setTimeout(() => setCopiedInvite(false), 3000);
  };

  const toggleMicrophone = async () => {
    if (isMicActive) {
      streamerRef.current?.stop();
      streamerRef.current = null;
      setIsMicActive(false);
      setMicAudioLevel(0);
    } else {
      try {
        const streamId = role === "friend" ? "stream_b" : "stream_a";
        const streamer = new AudioStreamer(callId, streamId, getWsBaseUrl());
        await streamer.start((level) => setMicAudioLevel(level));
        streamerRef.current = streamer;
        setIsMicActive(true);
      } catch (err) {
        console.error("Microphone access error:", err);
        alert("Could not access microphone. Ensure mic permissions are granted.");
      }
    }
  };

  const sendSimulatedTurn = (speakerName: string, text: string, lang: string = "mixed") => {
    if (roomWsRef.current && roomWsRef.current.readyState === WebSocket.OPEN) {
      const now = elapsedSeconds * 1000;
      roomWsRef.current.send(
        JSON.stringify({
          action: "simulate_turn",
          turn: {
            call_id: callId,
            speaker_name: speakerName,
            start_ms: now,
            end_ms: now + 3000,
            text,
            language: lang,
          },
        })
      );
    }
  };

  const formatTimer = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const s = sec % 60;
    return `${mins.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  return (
    <div className="flex flex-col h-screen bg-[#070b13] text-slate-100">
      <audio ref={audioPlayerRef} className="hidden" />

      {/* Top Header */}
      <header className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-[#0d1322]/90 backdrop-blur-md">
        <div className="flex items-center gap-4">
          <div className="w-3 h-3 rounded-full bg-emerald-500 animate-pulse" />
          <h1 className="text-xl font-bold tracking-tight bg-gradient-to-r from-blue-400 via-indigo-300 to-emerald-300 bg-clip-text text-transparent">
            AI Third Participant Call
          </h1>
          <span className="px-2.5 py-0.5 rounded-full text-xs font-mono bg-slate-800 text-slate-300 border border-slate-700">
            {formatTimer(elapsedSeconds)}
          </span>
          <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-950 text-indigo-300 border border-indigo-700/50 uppercase">
            Role: {role === "friend" ? "Speaker B (Friend)" : "Speaker A (You)"}
          </span>
        </div>

        {/* Intelligence Status Indicators */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400">Topic:</span>
            <span className="px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wider bg-indigo-950/80 text-indigo-300 border border-indigo-700/50">
              {currentTopic}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <Flame className={`w-4 h-4 ${heatScore > 0.6 ? "text-rose-500 animate-bounce" : heatScore > 0.3 ? "text-amber-400" : "text-slate-400"}`} />
            <div className="flex flex-col">
              <div className="flex justify-between text-[10px] text-slate-400 mb-0.5">
                <span>Heat</span>
                <span>{Math.round(heatScore * 100)}%</span>
              </div>
              <div className="w-24 h-2 bg-slate-800 rounded-full overflow-hidden border border-slate-700">
                <div
                  className={`h-full transition-all duration-300 rounded-full ${
                    heatScore > 0.6
                      ? "bg-gradient-to-r from-amber-500 to-rose-600"
                      : heatScore > 0.3
                      ? "bg-gradient-to-r from-blue-500 to-amber-500"
                      : "bg-emerald-500"
                  }`}
                  style={{ width: `${Math.max(10, heatScore * 100)}%` }}
                />
              </div>
            </div>
          </div>

          {/* Copy Invite Link Button */}
          <button
            onClick={handleCopyInviteLink}
            className={`flex items-center gap-2 px-3.5 py-2 text-xs font-semibold rounded-lg border transition-all ${
              copiedInvite
                ? "bg-emerald-950 border-emerald-500 text-emerald-300"
                : "bg-slate-800 hover:bg-slate-700 border-slate-700 text-slate-200"
            }`}
            title="Copy link to send to your friend"
          >
            <span>{copiedInvite ? "✓ Invite Copied!" : "🔗 Invite Friend"}</span>
          </button>

          <button
            onClick={onEndCall}
            className="flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg bg-rose-600 hover:bg-rose-500 text-white shadow-lg shadow-rose-950/40 transition-colors"
          >
            <Square className="w-4 h-4 fill-white" />
            End Call
          </button>
        </div>
      </header>

      {/* Production Telemetry Bar */}
      <div className="px-6 py-2 bg-[#0b101c] border-b border-slate-800/80 flex items-center justify-between text-xs text-slate-400 font-mono">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5 text-indigo-400">
            <Zap className="w-3.5 h-3.5" />
            <span className="font-semibold">Latency Watermarks:</span>
          </div>
          {latestLatency.totalMs ? (
            <div className="flex items-center gap-4">
              <span>Total Intervention: <strong className="text-emerald-400">{latestLatency.totalMs}ms</strong></span>
              <span>Search: <strong className="text-blue-400">{latestLatency.searchMs}ms</strong></span>
              <span>Verification: <strong className="text-purple-400">{latestLatency.verifyMs}ms</strong></span>
              {latestLatency.ttsMs ? (
                <span>TTS Voice: <strong className="text-amber-400">{latestLatency.ttsMs}ms</strong></span>
              ) : null}
            </div>
          ) : (
            <span className="text-slate-500 italic">V3 Global Edge Active • Sub-second Engine Ready</span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1 text-slate-400">
            <Activity className="w-3 h-3 text-emerald-400" /> AudioWorklet PCM16
          </span>
          <span className="text-slate-600">•</span>
          <span className="text-indigo-400">AssemblyAI Universal-3.5 Pro</span>
        </div>
      </div>

      {/* Main Call Room Grid */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-4 gap-4 p-6 overflow-hidden">
        {/* Left Column: Participants & Mic Controls */}
        <div className="lg:col-span-1 flex flex-col gap-4">
          {/* Participant A (You) */}
          <div className="p-4 rounded-xl bg-[#0f172a] border border-slate-800 shadow-md">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-blue-600/30 border border-blue-500 flex items-center justify-center font-bold text-blue-400">
                  YOU
                </div>
                <div>
                  <h3 className="font-semibold text-sm">Speaker A (You)</h3>
                  <p className="text-[11px] text-slate-400">AudioWorklet Stream A</p>
                </div>
              </div>
              <button
                onClick={toggleMicrophone}
                className={`p-2.5 rounded-full transition-colors ${
                  isMicActive
                    ? "bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-950/40"
                    : "bg-slate-800 hover:bg-slate-700 text-slate-300"
                }`}
                title={isMicActive ? "Mute Microphone" : "Start Microphone"}
              >
                {isMicActive ? <Mic className="w-4 h-4" /> : <MicOff className="w-4 h-4" />}
              </button>
            </div>
            <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-500 transition-all duration-75"
                style={{ width: isMicActive ? `${Math.max(5, micAudioLevel * 100)}%` : "0%" }}
              />
            </div>
          </div>

          {/* Participant B (Friend) */}
          <div className="p-4 rounded-xl bg-[#0f172a] border border-slate-800 shadow-md">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-amber-600/30 border border-amber-500 flex items-center justify-center font-bold text-amber-400">
                  FR
                </div>
                <div>
                  <h3 className="font-semibold text-sm">Speaker B (Friend)</h3>
                  <p className="text-[11px] text-slate-400">Stream B</p>
                </div>
              </div>
              <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/80" />
            </div>
            <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
              <div className="h-full bg-amber-500/40 w-1/4" />
            </div>
          </div>

          {/* AI Co-Participant Card */}
          <div className="p-4 rounded-xl bg-gradient-to-br from-[#131b2e] to-[#0f172a] border border-indigo-900/40 shadow-md flex flex-col gap-2">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-indigo-600/30 border border-indigo-500 flex items-center justify-center text-indigo-400">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-semibold text-sm text-indigo-200">AI Co-Participant</h3>
                <p className="text-xs text-slate-400">Speculative Fact-Check Engine</p>
              </div>
            </div>
            <p className="text-xs text-slate-400 leading-relaxed mt-1">
              Listens for Egyptian Arabic & English code-switching. Intervenes only on verifiable factual disputes with sub-second evidence.
            </p>
          </div>

          {/* Simulation Playground */}
          <div className="p-4 rounded-xl bg-[#0f172a]/70 border border-slate-800 flex flex-col gap-2.5">
            <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
              Simulation Playground
            </h4>
            <button
              onClick={() => {
                sendSimulatedTurn("You", "بص يا عم أنا متأكد فيلم Inception نزل في 2015");
                setTimeout(() => {
                  sendSimulatedTurn("Friend", "لا يا عم أنت فاهم غلط الفيلم نزل في 2010");
                }, 1200);
              }}
              className="px-3 py-2 text-xs text-left rounded-lg bg-slate-800/80 hover:bg-slate-700 text-slate-200 border border-slate-700/60 transition-colors"
            >
              🎬 <strong>Dispute: Inception Release</strong>
              <div className="text-[11px] text-slate-400">2015 vs 2010 (Triggers Speculative Check)</div>
            </button>

            <button
              onClick={() => {
                sendSimulatedTurn("You", "Messi joined Inter Miami back in 2022");
                setTimeout(() => {
                  sendSimulatedTurn("Friend", "No bro, Messi signed with Miami in 2023");
                }, 1200);
              }}
              className="px-3 py-2 text-xs text-left rounded-lg bg-slate-800/80 hover:bg-slate-700 text-slate-200 border border-slate-700/60 transition-colors"
            >
              ⚽ <strong>Dispute: Messi Inter Miami</strong>
              <div className="text-[11px] text-slate-400">2022 vs 2023 (Triggers Speculative Check)</div>
            </button>

            <button
              onClick={() => {
                sendSimulatedTurn("You", "بص يا عم basically أنا شايف الذكاء الاصطناعي هيغير كل حاجة السنة دي");
              }}
              className="px-3 py-2 text-xs text-left rounded-lg bg-slate-800/80 hover:bg-slate-700 text-slate-200 border border-slate-700/60 transition-colors"
            >
              💬 <strong>Egyptian Code-Switching</strong>
              <div className="text-[11px] text-slate-400">Casual tech turn without dispute</div>
            </button>
          </div>
        </div>

        {/* Center & Right Columns: Live Transcript & Alerts */}
        <div className="lg:col-span-3 flex flex-col gap-4 h-full overflow-hidden">
          {/* Active Fact-Check & AI Interruption Alert Toast */}
          {factCheckAlert && (
            <div className={`p-4 rounded-xl border backdrop-blur-md transition-all animate-in fade-in slide-in-from-top-4 ${
              factCheckAlert.result === "supported"
                ? "bg-emerald-950/40 border-emerald-700/60 text-emerald-200"
                : factCheckAlert.result === "contradicted"
                ? "bg-rose-950/40 border-rose-700/60 text-rose-200"
                : "bg-slate-900/80 border-slate-700 text-slate-200"
            }`}>
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2.5">
                  {factCheckAlert.result === "supported" ? (
                    <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                  ) : factCheckAlert.result === "contradicted" ? (
                    <XCircle className="w-5 h-5 text-rose-400" />
                  ) : (
                    <AlertCircle className="w-5 h-5 text-amber-400" />
                  )}
                  <span className="text-xs font-bold uppercase tracking-wider">
                    Fact Check: {factCheckAlert.topic} ({factCheckAlert.result})
                  </span>
                  <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-slate-800 text-slate-300">
                    Confidence: {Math.round(factCheckAlert.confidence * 100)}%
                  </span>
                </div>
                {factCheckAlert.interrupted && (
                  <span className="flex items-center gap-1.5 text-xs font-semibold text-indigo-300 bg-indigo-950/60 px-2.5 py-1 rounded-full border border-indigo-700/50">
                    <Volume2 className="w-3.5 h-3.5" /> AI Interrupted
                  </span>
                )}
              </div>

              {factCheckAlert.interruption_text && (
                <div className="mt-2 text-sm font-medium text-white bg-slate-950/40 p-2.5 rounded-lg border border-slate-800">
                  🗣️ <em>"{factCheckAlert.interruption_text}"</em>
                </div>
              )}

              <p className="mt-2 text-xs text-slate-300">{factCheckAlert.evidence}</p>

              {factCheckAlert.sources && factCheckAlert.sources.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {factCheckAlert.sources.map((s, idx) => (
                    <a
                      key={idx}
                      href={s.url}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center gap-1 text-[11px] text-blue-400 hover:text-blue-300 bg-blue-950/40 hover:bg-blue-900/50 px-2 py-1 rounded border border-blue-800/40 transition-colors"
                    >
                      <span>{s.title.slice(0, 30)}...</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Transcript Feed Box */}
          <div className="flex-1 rounded-xl bg-[#0f172a] border border-slate-800 p-4 flex flex-col overflow-hidden shadow-inner">
            <div className="flex items-center justify-between pb-3 mb-3 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <MessageSquare className="w-4 h-4 text-slate-400" />
                <h3 className="text-sm font-semibold text-slate-200">Live Transcript Feed</h3>
              </div>
              <span className="text-xs text-slate-500 font-mono">Zero-Jank Stream</span>
            </div>

            <div ref={scrollRef} className="flex-1 overflow-y-auto space-y-3 pr-2">
              {turns.length === 0 && !partialTurn && (
                <div className="h-full flex flex-col items-center justify-center text-slate-500 gap-2">
                  <Mic className="w-8 h-8 opacity-40 animate-pulse" />
                  <p className="text-sm">Speak into your mic or click a simulation scenario to begin...</p>
                </div>
              )}

              {turns.map((turn) => {
                const isYou = turn.speaker_name === "You";
                return (
                  <div
                    key={turn.id}
                    className={`flex flex-col p-3 rounded-lg border transition-all ${
                      isYou
                        ? "bg-blue-950/20 border-blue-900/30 self-start"
                        : "bg-amber-950/20 border-amber-900/30 self-start"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        <span className={`text-xs font-bold ${isYou ? "text-blue-400" : "text-amber-400"}`}>
                          {turn.speaker_name}
                        </span>
                        <span className="text-[10px] text-slate-500">
                          {Math.floor(turn.start_ms / 1000)}s
                        </span>
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 uppercase">
                          {turn.language}
                        </span>
                      </div>

                      {turn.analysis && (
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800/80 text-slate-300 font-medium">
                            {turn.analysis.topic}
                          </span>
                          {turn.analysis.is_disagreement && (
                            <span className="text-[10px] px-2 py-0.5 rounded-full bg-rose-950 text-rose-300 font-semibold border border-rose-800/40">
                              Disagreement
                            </span>
                          )}
                          {turn.analysis.is_claim && (
                            <span className="text-[10px] px-2 py-0.5 rounded-full bg-indigo-950 text-indigo-300 font-semibold border border-indigo-800/40">
                              Claim
                            </span>
                          )}
                        </div>
                      )}
                    </div>

                    <p className="text-sm text-slate-100 font-normal leading-relaxed" dir="auto">
                      {turn.text}
                    </p>
                  </div>
                );
              })}

              {partialTurn && (
                <div className="flex flex-col p-3 rounded-lg border border-indigo-800/40 bg-indigo-950/20 animate-pulse">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-bold text-indigo-400">{partialSpeaker || "Listening"}</span>
                    <span className="text-[10px] text-indigo-300">Streaming live...</span>
                  </div>
                  <p className="text-sm text-slate-300 font-light" dir="auto">
                    {partialTurn}
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
