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
    <section className="bg-[#2b2d31] border-b border-[#383a40] px-4 md:px-8 py-3">
      <div className="max-w-7xl mx-auto flex flex-col lg:flex-row items-center justify-between gap-3 text-xs">
        {/* Title & SLA Badge */}
        <div className="flex items-center gap-2.5 flex-shrink-0">
          <div className="p-1.5 rounded-lg bg-[#5865F2]/20 text-[#5865F2] border border-[#5865F2]/30">
            <Zap className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-[#F2F3F5] text-xs uppercase tracking-wider">
                Autonomous Pipeline Latency Flow
              </span>
              <span
                className={`flex items-center gap-1 text-[10px] font-mono font-bold px-2 py-0.5 rounded-full border ${
                  isPassingSla
                    ? "bg-[#23A55A]/15 border-[#23A55A]/30 text-[#23A55A]"
                    : "bg-[#F23F43]/15 border-[#F23F43]/30 text-[#F23F43]"
                }`}
              >
                <CheckCircle2 className="w-3 h-3" />
                <span>SLA &lt; {(targetSlaMs / 1000).toFixed(1)}s: {isPassingSla ? "PASSED" : "EXCEEDED"}</span>
              </span>
            </div>
            <p className="text-[11px] text-[#949BA4]">
              End-to-end multi-speaker arbitration measured live
            </p>
          </div>
        </div>

        {/* Connected Node Flow */}
        <div className="flex flex-wrap items-center gap-1.5 sm:gap-2 justify-center lg:justify-end">
          {/* Node 1: AssemblyAI STT */}
          <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl bg-[#1e1f22] border border-[#383a40] text-cyan-200 shadow-sm">
            <Radio className="w-3.5 h-3.5 text-cyan-400" />
            <div className="text-[11px] leading-tight">
              <span className="text-[9px] text-cyan-400/80 font-mono block">1. ASR STREAM</span>
              <span className="font-bold text-[#F2F3F5]">AssemblyAI {speechModel}</span>
            </div>
            <span className="font-mono font-bold text-cyan-400 ml-1 text-xs">
              {stt}ms
            </span>
          </div>

          <ArrowRight className="w-3.5 h-3.5 text-[#949BA4]/50 hidden sm:block flex-shrink-0" />

          {/* Node 2: FastGate */}
          <div className="flex items-center gap-1.5 px-2 py-1.5 rounded-xl bg-[#1e1f22] border border-[#383a40] text-indigo-200 shadow-sm">
            <ShieldCheck className="w-3.5 h-3.5 text-[#5865F2]" />
            <div className="text-[11px] leading-tight">
              <span className="text-[9px] text-[#5865F2]/80 font-mono block">2. FASTGATE</span>
              <span className="font-bold text-[#F2F3F5]">Epistemic Veto</span>
            </div>
            <span className="font-mono font-bold text-[#5865F2] ml-1 text-xs">
              &lt;10ms
            </span>
          </div>

          <ArrowRight className="w-3.5 h-3.5 text-[#949BA4]/50 hidden sm:block flex-shrink-0" />

          {/* Node 3: Groq LPU */}
          <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl bg-[#1e1f22] border border-[#383a40] text-purple-200 shadow-sm">
            <Cpu className="w-3.5 h-3.5 text-purple-400" />
            <div className="text-[11px] leading-tight">
              <span className="text-[9px] text-purple-400/80 font-mono block">3. LPU REASONING</span>
              <span className="font-bold text-[#F2F3F5]">Groq Llama 3.3</span>
            </div>
            <span className="font-mono font-bold text-purple-400 ml-1 text-xs">
              {llm}ms
            </span>
          </div>

          <ArrowRight className="w-3.5 h-3.5 text-[#949BA4]/50 hidden sm:block flex-shrink-0" />

          {/* Node 4: Tavily Search */}
          <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl bg-[#1e1f22] border border-[#383a40] text-amber-200 shadow-sm">
            <Search className="w-3.5 h-3.5 text-[#F0B232]" />
            <div className="text-[11px] leading-tight">
              <span className="text-[9px] text-[#F0B232]/80 font-mono block">4. TIER-1 SEARCH</span>
              <span className="font-bold text-[#F2F3F5]">Tavily Web</span>
            </div>
            <span className="font-mono font-bold text-[#F0B232] ml-1 text-xs">
              {search}ms
            </span>
          </div>

          <ArrowRight className="w-3.5 h-3.5 text-[#949BA4]/50 hidden sm:block flex-shrink-0" />

          {/* Node 5: Edge Neural TTS */}
          <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl bg-[#1e1f22] border border-[#383a40] text-emerald-200 shadow-sm">
            <Volume2 className="w-3.5 h-3.5 text-[#23A55A]" />
            <div className="text-[11px] leading-tight">
              <span className="text-[9px] text-[#23A55A]/80 font-mono block">5. VOICE OUT</span>
              <span className="font-bold text-[#F2F3F5]">Edge Neural Shakir</span>
            </div>
            <span className="font-mono font-bold text-[#23A55A] ml-1 text-xs">
              {tts}ms
            </span>
          </div>

          {/* Total Badge */}
          <div className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-[#5865F2]/20 border border-[#5865F2]/40 text-white font-mono font-bold text-xs shadow-md">
            <Clock className="w-3.5 h-3.5 text-[#5865F2]" />
            <span>Total: {(total / 1000).toFixed(2)}s</span>
          </div>
        </div>
      </div>
    </section>
  );
}
