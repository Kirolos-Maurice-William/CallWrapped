"use client";

import React from "react";
import {
  Zap,
  ArrowRight,
  ShieldCheck,
  CheckCircle2,
  Clock,
  Radio,
  Cpu,
  Search,
  Volume2
} from "lucide-react";

interface LatencyMetrics {
  stt_ms?: number;
  llm_ms?: number;
  search_ms?: number;
  tts_ms?: number;
  total_ms?: number;
}

interface Props {
  latency: LatencyMetrics;
  speechModel?: string;
  targetSlaMs?: number;
}

export function PipelineFlow({
  latency,
  speechModel = "Universal-3.5 Pro",
  targetSlaMs = 2000
}: Props) {
  const stt = latency.stt_ms ?? 0;
  const llm = latency.llm_ms ?? 0;
  const search = latency.search_ms ?? 0;
  const tts = latency.tts_ms ?? 0;
  const total = (stt + llm + search + tts) || latency.total_ms || 0;

  const isPassingSla = total > 0 ? total <= targetSlaMs : true;

  return (
    <section className="bg-slate-900/80 border-b border-slate-800/80 px-4 md:px-8 py-3">
      <div className="max-w-7xl mx-auto flex flex-col lg:flex-row items-center justify-between gap-3 text-xs">
        {/* Title & SLA Badge */}
        <div className="flex items-center gap-2.5 flex-shrink-0">
          <div className="p-1.5 rounded-lg bg-amber-500/20 text-amber-400 border border-amber-500/30">
            <Zap className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-white text-xs uppercase tracking-wider">
                Autonomous Pipeline Latency Flow
              </span>
              <span
                className={`flex items-center gap-1 text-[10px] font-mono font-bold px-2 py-0.5 rounded-full border ${
                  isPassingSla
                    ? "bg-emerald-500/15 border-emerald-500/30 text-emerald-400"
                    : "bg-rose-500/15 border-rose-500/30 text-rose-400"
                }`}
              >
                <CheckCircle2 className="w-3 h-3" />
                <span>SLA &lt; {(targetSlaMs / 1000).toFixed(1)}s: {isPassingSla ? "PASSED" : "EXCEEDED"}</span>
              </span>
            </div>
            <p className="text-[11px] text-slate-400">
              End-to-end multi-speaker arbitration measured live
            </p>
          </div>
        </div>

        {/* Connected Node Flow */}
        <div className="flex flex-wrap items-center gap-1.5 sm:gap-2 justify-center lg:justify-end">
          {/* Node 1: AssemblyAI STT */}
          <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl bg-cyan-950/40 border border-cyan-800/50 text-cyan-200 shadow-sm">
            <Radio className="w-3.5 h-3.5 text-cyan-400" />
            <div className="text-[11px] leading-tight">
              <span className="text-[9px] text-cyan-400/80 font-mono block">1. ASR STREAM</span>
              <span className="font-bold text-white">AssemblyAI {speechModel}</span>
            </div>
            <span className="font-mono font-bold text-cyan-300 ml-1 text-xs">
              {stt}ms
            </span>
          </div>

          <ArrowRight className="w-3.5 h-3.5 text-slate-600 hidden sm:block flex-shrink-0" />

          {/* Node 2: FastGate */}
          <div className="flex items-center gap-1.5 px-2 py-1.5 rounded-xl bg-indigo-950/40 border border-indigo-800/50 text-indigo-200 shadow-sm">
            <ShieldCheck className="w-3.5 h-3.5 text-indigo-400" />
            <div className="text-[11px] leading-tight">
              <span className="text-[9px] text-indigo-400/80 font-mono block">2. FASTGATE</span>
              <span className="font-bold text-white">Epistemic Veto</span>
            </div>
            <span className="font-mono font-bold text-indigo-300 ml-1 text-xs">
              &lt;10ms
            </span>
          </div>

          <ArrowRight className="w-3.5 h-3.5 text-slate-600 hidden sm:block flex-shrink-0" />

          {/* Node 3: Groq LPU */}
          <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl bg-purple-950/40 border border-purple-800/50 text-purple-200 shadow-sm">
            <Cpu className="w-3.5 h-3.5 text-purple-400" />
            <div className="text-[11px] leading-tight">
              <span className="text-[9px] text-purple-400/80 font-mono block">3. LPU REASONING</span>
              <span className="font-bold text-white">Groq Llama 3.3</span>
            </div>
            <span className="font-mono font-bold text-purple-300 ml-1 text-xs">
              {llm}ms
            </span>
          </div>

          <ArrowRight className="w-3.5 h-3.5 text-slate-600 hidden sm:block flex-shrink-0" />

          {/* Node 4: Tavily Search */}
          <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl bg-amber-950/40 border border-amber-800/50 text-amber-200 shadow-sm">
            <Search className="w-3.5 h-3.5 text-amber-400" />
            <div className="text-[11px] leading-tight">
              <span className="text-[9px] text-amber-400/80 font-mono block">4. TIER-1 SEARCH</span>
              <span className="font-bold text-white">Tavily Web</span>
            </div>
            <span className="font-mono font-bold text-amber-300 ml-1 text-xs">
              {search}ms
            </span>
          </div>

          <ArrowRight className="w-3.5 h-3.5 text-slate-600 hidden sm:block flex-shrink-0" />

          {/* Node 5: Edge Neural TTS */}
          <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl bg-emerald-950/40 border border-emerald-800/50 text-emerald-200 shadow-sm">
            <Volume2 className="w-3.5 h-3.5 text-emerald-400" />
            <div className="text-[11px] leading-tight">
              <span className="text-[9px] text-emerald-400/80 font-mono block">5. VOICE OUT</span>
              <span className="font-bold text-white">Edge Neural Shakir</span>
            </div>
            <span className="font-mono font-bold text-emerald-300 ml-1 text-xs">
              {tts}ms
            </span>
          </div>

          {/* Total Badge */}
          <div className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-gradient-to-r from-indigo-900/60 to-purple-900/60 border border-indigo-500/40 text-white font-mono font-bold text-xs shadow-md">
            <Clock className="w-3.5 h-3.5 text-indigo-300" />
            <span>Total: {(total / 1000).toFixed(2)}s</span>
          </div>
        </div>
      </div>
    </section>
  );
}
