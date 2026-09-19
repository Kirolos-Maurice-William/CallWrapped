"use client";

import React, { useState } from "react";
import { ArrowLeft, Flame, Search, CheckCircle2, XCircle, AlertCircle, ExternalLink, Clock, User, Volume2, BookOpen, Layers } from "lucide-react";

interface DashboardData {
  call_id: string;
  title: string;
  duration_ms: number;
  formatted_duration: string;
  speakers: Array<{ name: string; duration_ms: number; percentage: number }>;
  topics: Array<{
    topic: string;
    duration_ms: number;
    formatted_duration: string;
    percentage: number;
    turn_count: number;
  }>;
  heated_moments: Array<{
    topic: string;
    start_ms: number;
    end_ms: number;
    formatted_duration: string;
    heat_score: number;
    description: string;
  }>;
  arguments: Array<{
    id: string;
    topic: string;
    start_ms: number;
    end_ms: number;
    participants: string[];
    claim_a?: string;
    claim_b?: string;
    heat_peak: number;
  }>;
  fact_checks: Array<{
    id: string;
    claim_id: string;
    result: string;
    confidence: number;
    sources: Array<{ title: string; url: string; snippet: string }>;
    evidence: string;
    interrupted: boolean;
    interruption_text?: string;
  }>;
  total_claims_checked: number;
  supported_count: number;
  contradicted_count: number;
  inconclusive_count: number;
  summary: string;
  turns: Array<{
    id: string;
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
  }>;
}

export default function DashboardView({
  data,
  onBackToCall,
}: {
  data: DashboardData;
  onBackToCall?: () => void;
}) {
  const [selectedTopicFilter, setSelectedTopicFilter] = useState<string | null>(null);

  const filteredTurns = selectedTopicFilter
    ? data.turns.filter((t) => t.analysis?.topic.toLowerCase() === selectedTopicFilter.toLowerCase())
    : data.turns;

  return (
    <div className="min-h-screen bg-[#070b13] text-slate-100 p-6 md:p-10">
      <div className="max-w-6xl mx-auto space-y-8">
        {/* Top Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-6">
          <div>
            <div className="flex items-center gap-3 mb-2">
              {onBackToCall && (
                <button
                  onClick={onBackToCall}
                  className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
                  title="Start New Call"
                >
                  <ArrowLeft className="w-4 h-4" />
                </button>
              )}
              <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-blue-400 via-indigo-300 to-emerald-400 bg-clip-text text-transparent">
                Conversation Intelligence Report
              </h1>
            </div>
            <p className="text-sm text-slate-400">
              Session: {data.title} • Completed with Universal-3.5 Pro Realtime & Verified Sources
            </p>
          </div>

          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 px-4 py-2 rounded-xl bg-[#0f172a] border border-slate-800 shadow">
              <Clock className="w-4 h-4 text-blue-400" />
              <span className="text-sm font-semibold text-slate-300">Call Duration:</span>
              <span className="text-sm font-mono font-bold text-white">{data.formatted_duration}</span>
            </div>
          </div>
        </div>

        {/* Executive Summary Card */}
        <div className="p-5 rounded-2xl bg-gradient-to-r from-indigo-950/40 to-slate-900 border border-indigo-800/30 shadow-lg">
          <div className="flex items-center gap-2 mb-2">
            <BookOpen className="w-4 h-4 text-indigo-400" />
            <h2 className="text-sm font-bold uppercase tracking-wider text-indigo-300">Executive Summary</h2>
          </div>
          <p className="text-sm text-slate-300 leading-relaxed">{data.summary}</p>
        </div>

        {/* Row 1: Speaking Time & Topic Distribution */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Speaking Time Card */}
          <div className="p-6 rounded-2xl bg-[#0f172a] border border-slate-800 shadow-md flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <User className="w-4 h-4 text-blue-400" />
                  <h3 className="font-bold text-sm uppercase tracking-wider text-slate-200">Speaking Time Split</h3>
                </div>
                <span className="text-xs text-slate-500 font-mono">Deterministic Turn Math</span>
              </div>

              {/* Progress Bar Split */}
              <div className="h-4 w-full rounded-full overflow-hidden flex bg-slate-800 mb-4 border border-slate-700/60">
                {data.speakers.map((s, idx) => (
                  <div
                    key={s.name}
                    className={`h-full transition-all ${idx === 0 ? "bg-blue-500" : "bg-amber-500"}`}
                    style={{ width: `${s.percentage}%` }}
                  />
                ))}
              </div>

              {/* Speaker Stats */}
              <div className="grid grid-cols-2 gap-4">
                {data.speakers.map((s, idx) => (
                  <div key={s.name} className="p-3 rounded-xl bg-slate-900/60 border border-slate-800/80">
                    <div className="flex items-center gap-2 mb-1">
                      <div className={`w-2.5 h-2.5 rounded-full ${idx === 0 ? "bg-blue-400" : "bg-amber-400"}`} />
                      <span className="text-xs font-semibold text-slate-300">{s.name}</span>
                    </div>
                    <div className="text-2xl font-black text-white">{s.percentage}%</div>
                    <div className="text-[11px] text-slate-500">{Math.round(s.duration_ms / 1000)} seconds spoken</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Topics Breakdown Card */}
          <div className="p-6 rounded-2xl bg-[#0f172a] border border-slate-800 shadow-md">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Layers className="w-4 h-4 text-emerald-400" />
                <h3 className="font-bold text-sm uppercase tracking-wider text-slate-200">Topics Explored</h3>
              </div>
              {selectedTopicFilter && (
                <button
                  onClick={() => setSelectedTopicFilter(null)}
                  className="text-xs text-indigo-400 hover:underline"
                >
                  Clear filter
                </button>
              )}
            </div>

            <div className="space-y-3">
              {data.topics.map((t) => {
                const isSelected = selectedTopicFilter?.toLowerCase() === t.topic.toLowerCase();
                return (
                  <button
                    key={t.topic}
                    onClick={() => setSelectedTopicFilter(isSelected ? null : t.topic)}
                    className={`w-full text-left p-2.5 rounded-xl border transition-all ${
                      isSelected
                        ? "bg-indigo-950/60 border-indigo-600 shadow-sm"
                        : "bg-slate-900/40 border-slate-800 hover:bg-slate-800/50"
                    }`}
                  >
                    <div className="flex justify-between text-xs font-semibold mb-1.5">
                      <span className="text-slate-200">{t.topic}</span>
                      <span className="font-mono text-slate-400">{t.formatted_duration} ({t.percentage}%)</span>
                    </div>
                    <div className="h-2 w-full bg-slate-800 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-blue-500 to-indigo-500 rounded-full"
                        style={{ width: `${Math.max(5, t.percentage)}%` }}
                      />
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Row 2: Heated Moments & Arguments */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Heated Moments */}
          <div className="p-6 rounded-2xl bg-[#0f172a] border border-slate-800 shadow-md">
            <div className="flex items-center gap-2 mb-4">
              <Flame className="w-4 h-4 text-rose-500" />
              <h3 className="font-bold text-sm uppercase tracking-wider text-slate-200">⚡ Heated Moments</h3>
            </div>

            {data.heated_moments.length === 0 ? (
              <p className="text-xs text-slate-500 italic">No heated moments detected during this session.</p>
            ) : (
              <div className="space-y-3">
                {data.heated_moments.map((m, idx) => (
                  <div key={idx} className="p-3 rounded-xl bg-rose-950/20 border border-rose-900/30 flex justify-between items-center">
                    <div>
                      <div className="text-xs font-bold text-rose-400 uppercase">{m.topic}</div>
                      <div className="text-[11px] text-slate-400">{m.description}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-xs font-mono font-bold text-slate-200">{m.formatted_duration}</div>
                      <div className="text-[10px] text-rose-400 font-semibold">{Math.round(m.heat_score * 100)}% Heat</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Direct Arguments Discovered */}
          <div className="p-6 rounded-2xl bg-[#0f172a] border border-slate-800 shadow-md">
            <div className="flex items-center gap-2 mb-4">
              <Search className="w-4 h-4 text-amber-400" />
              <h3 className="font-bold text-sm uppercase tracking-wider text-slate-200">Disagreements & Arguments ({data.arguments.length})</h3>
            </div>

            {data.arguments.length === 0 ? (
              <p className="text-xs text-slate-500 italic">No direct arguments recorded.</p>
            ) : (
              <div className="space-y-3">
                {data.arguments.map((arg) => (
                  <div key={arg.id} className="p-3 rounded-xl bg-slate-900/60 border border-slate-800 text-xs space-y-1.5">
                    <div className="flex justify-between items-center">
                      <span className="font-bold text-amber-400 uppercase">{arg.topic}</span>
                      <span className="text-[10px] text-slate-500">{arg.participants.join(" vs ")}</span>
                    </div>
                    <div className="text-slate-300">
                      <strong>Claim A:</strong> <span dir="auto">"{arg.claim_a}"</span>
                    </div>
                    <div className="text-slate-300">
                      <strong>Claim B:</strong> <span dir="auto">"{arg.claim_b}"</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Row 3: Ground-Truth Fact Checks Ledger */}
        <div className="p-6 rounded-2xl bg-[#0f172a] border border-slate-800 shadow-md space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5 text-emerald-400" />
              <h3 className="font-bold text-base text-slate-100">🔎 Fact-Checked Claims Ledger</h3>
            </div>
            <div className="flex items-center gap-3 text-xs">
              <span className="text-slate-400">{data.total_claims_checked} claims checked</span>
              <span className="px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800/40">
                {data.supported_count} Supported
              </span>
              <span className="px-2 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-800/40">
                {data.contradicted_count} Contradicted
              </span>
              <span className="px-2 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-800/40">
                {data.inconclusive_count} Inconclusive
              </span>
            </div>
          </div>

          {data.fact_checks.length === 0 ? (
            <p className="text-xs text-slate-500 italic py-4">No factual disputes required web verification during this call.</p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {data.fact_checks.map((fc) => (
                <div key={fc.id} className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 flex flex-col justify-between gap-3">
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <span className={`text-xs font-bold px-2 py-0.5 rounded-full uppercase ${
                        fc.result === "supported"
                          ? "bg-emerald-950 text-emerald-400 border border-emerald-800/40"
                          : fc.result === "contradicted"
                          ? "bg-rose-950 text-rose-400 border border-rose-800/40"
                          : "bg-amber-950 text-amber-400 border border-amber-800/40"
                      }`}>
                        {fc.result}
                      </span>
                      <span className="text-xs font-semibold text-slate-400">
                        Confidence: {Math.round(fc.confidence * 100)}%
                      </span>
                    </div>

                    <p className="text-xs text-slate-200 leading-relaxed font-medium mb-2">{fc.evidence}</p>

                    {fc.interrupted && (
                      <div className="p-2 rounded bg-indigo-950/40 border border-indigo-900/40 text-[11px] text-indigo-300 flex items-center gap-1.5 mb-2">
                        <Volume2 className="w-3.5 h-3.5 shrink-0" />
                        <span>AI Interrupted: <em>"{fc.interruption_text}"</em></span>
                      </div>
                    )}
                  </div>

                  {fc.sources && fc.sources.length > 0 && (
                    <div className="pt-2 border-t border-slate-800 flex flex-wrap gap-1.5">
                      {fc.sources.map((s, idx) => (
                        <a
                          key={idx}
                          href={s.url}
                          target="_blank"
                          rel="noreferrer"
                          className="flex items-center gap-1 text-[10px] text-blue-400 hover:text-blue-300 bg-blue-950/30 hover:bg-blue-900/40 px-2 py-1 rounded border border-blue-900/30 transition-colors"
                        >
                          <span>{s.title.slice(0, 25)}...</span>
                          <ExternalLink className="w-2.5 h-2.5" />
                        </a>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Row 4: Full Synchronized Transcript Viewer */}
        <div className="p-6 rounded-2xl bg-[#0f172a] border border-slate-800 shadow-md space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <h3 className="font-bold text-base text-slate-100">
              Synchronized Transcript {selectedTopicFilter && `(Filtered: ${selectedTopicFilter})`}
            </h3>
            <span className="text-xs text-slate-500">{filteredTurns.length} turns</span>
          </div>

          <div className="max-h-96 overflow-y-auto space-y-3 pr-2">
            {filteredTurns.map((turn) => {
              const isYou = turn.speaker_name === "You";
              return (
                <div
                  key={turn.id}
                  className={`p-3 rounded-xl border ${
                    isYou ? "bg-blue-950/20 border-blue-900/30" : "bg-amber-950/20 border-amber-900/30"
                  }`}
                >
                  <div className="flex justify-between items-center text-xs mb-1">
                    <div className="flex items-center gap-2">
                      <span className={`font-bold ${isYou ? "text-blue-400" : "text-amber-400"}`}>
                        {turn.speaker_name}
                      </span>
                      <span className="text-[10px] text-slate-500">{Math.floor(turn.start_ms / 1000)}s</span>
                      <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-400 uppercase">
                        {turn.language}
                      </span>
                    </div>
                    {turn.analysis && (
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 text-slate-300">
                        {turn.analysis.topic}
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-slate-100" dir="auto">
                    {turn.text}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
