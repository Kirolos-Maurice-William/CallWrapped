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

  const isArbitration = (llm > 0 || search > 0 || tts > 0);
  const isPassingSla = isArbitration ? total <= targetSlaMs : true;

  return (
    <section className="bg-[#2b2d31] border-b border-[#383a40] px-4 md:px-8 py-3">
      <div className="max-w-7xl mx-auto flex flex-col xl:flex-row items-start xl:items-center justify-between gap-3 text-xs">
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
                  isArbitration
                    ? isPassingSla
                      ? "bg-[#23A55A]/15 border-[#23A55A]/30 text-[#23A55A]"
                      : "bg-[#F23F43]/15 border-[#F23F43]/30 text-[#F23F43]"
                    : "bg-[#5865F2]/15 border-[#5865F2]/30 text-[#DBDEE1]"
                }`}
              >
                <CheckCircle2 className="w-3 h-3" />
                <span>
                  {isArbitration
                    ? `SLA < ${(targetSlaMs / 1000).toFixed(1)}s: ${isPassingSla ? "PASSED" : "EXCEEDED"}`
                    : "PIPELINE ACTIVE"}
                </span>
              </span>
            </div>
            <p className="text-[11px] text-[#949BA4]">
              End-to-end multi-speaker arbitration measured live
            </p>
          </div>
        </div>

        {/* Connected Node Flow (Compact Vertically-Stacked Cards with Bottom-Centered Latency) */}
        <div className="w-full xl:w-auto flex items-center justify-between xl:justify-end gap-1 sm:gap-1.5 flex-nowrap py-1">
          {/* Node 1: AssemblyAI STT */}
          <div className="flex flex-col items-center justify-between p-2 rounded-xl bg-[#1e1f22] border border-[#383a40] text-center shadow-sm w-[110px] sm:w-[124px] flex-shrink-0">
            <div className="flex items-center gap-1 text-[9px] font-mono uppercase text-cyan-400 font-bold mb-0.5">
              <Radio className="w-3 h-3 text-cyan-400" />
              <span>1. ASR</span>
            </div>
            <div className="text-[11px] font-bold text-[#F2F3F5] truncate w-full" title={`AssemblyAI ${speechModel}`}>
              AssemblyAI
            </div>
            <div className="mt-1 px-1.5 py-0.5 rounded bg-cyan-950/70 border border-cyan-800/40 text-cyan-300 font-mono text-[10px] font-bold">
              {stt}ms
            </div>
          </div>

          <ArrowRight className="w-3 h-3 text-[#949BA4]/40 flex-shrink-0" />

          {/* Node 2: FastGate */}
          <div className="flex flex-col items-center justify-between p-2 rounded-xl bg-[#1e1f22] border border-[#383a40] text-center shadow-sm w-[110px] sm:w-[124px] flex-shrink-0">
            <div className="flex items-center gap-1 text-[9px] font-mono uppercase text-[#5865F2] font-bold mb-0.5">
              <ShieldCheck className="w-3 h-3 text-[#5865F2]" />
              <span>2. FASTGATE</span>
            </div>
            <div className="text-[11px] font-bold text-[#F2F3F5] truncate w-full" title="FastGate Epistemic Veto">
              Epistemic Veto
            </div>
            <div className="mt-1 px-1.5 py-0.5 rounded bg-[#5865F2]/20 border border-[#5865F2]/40 text-[#5865F2] font-mono text-[10px] font-bold">
              &lt;10ms
            </div>
          </div>

          <ArrowRight className="w-3 h-3 text-[#949BA4]/40 flex-shrink-0" />

          {/* Node 3: Groq LPU */}
          <div className="flex flex-col items-center justify-between p-2 rounded-xl bg-[#1e1f22] border border-[#383a40] text-center shadow-sm w-[110px] sm:w-[124px] flex-shrink-0">
            <div className="flex items-center gap-1 text-[9px] font-mono uppercase text-purple-400 font-bold mb-0.5">
              <Cpu className="w-3 h-3 text-purple-400" />
              <span>3. REASONING</span>
            </div>
            <div className="text-[11px] font-bold text-[#F2F3F5] truncate w-full" title="Groq Qwen 3.8 27B">
              Groq Qwen 27B
            </div>
            <div className="mt-1 px-1.5 py-0.5 rounded bg-purple-950/70 border border-purple-800/40 text-purple-300 font-mono text-[10px] font-bold">
              {llm}ms
            </div>
          </div>

          <ArrowRight className="w-3 h-3 text-[#949BA4]/40 flex-shrink-0" />

          {/* Node 4: Tavily Search */}
          <div className="flex flex-col items-center justify-between p-2 rounded-xl bg-[#1e1f22] border border-[#383a40] text-center shadow-sm w-[110px] sm:w-[124px] flex-shrink-0">
            <div className="flex items-center gap-1 text-[9px] font-mono uppercase text-[#F0B232] font-bold mb-0.5">
              <Search className="w-3 h-3 text-[#F0B232]" />
              <span>4. SEARCH</span>
            </div>
            <div className="text-[11px] font-bold text-[#F2F3F5] truncate w-full" title="Tavily Tier-1 Ground Truth Search">
              Tavily Web
            </div>
            <div className="mt-1 px-1.5 py-0.5 rounded bg-amber-950/70 border border-amber-800/40 text-amber-300 font-mono text-[10px] font-bold">
              {search}ms
            </div>
          </div>

          <ArrowRight className="w-3 h-3 text-[#949BA4]/40 flex-shrink-0" />

          {/* Node 5: Edge Neural TTS */}
          <div className="flex flex-col items-center justify-between p-2 rounded-xl bg-[#1e1f22] border border-[#383a40] text-center shadow-sm w-[110px] sm:w-[124px] flex-shrink-0">
            <div className="flex items-center gap-1 text-[9px] font-mono uppercase text-[#23A55A] font-bold mb-0.5">
              <Volume2 className="w-3 h-3 text-[#23A55A]" />
              <span>5. VOICE OUT</span>
            </div>
            <div className="text-[11px] font-bold text-[#F2F3F5] truncate w-full" title="Edge Neural TTS (Shakir Arabic / Christopher English)">
              Edge Neural
            </div>
            <div className="mt-1 px-1.5 py-0.5 rounded bg-emerald-950/70 border border-emerald-800/40 text-emerald-300 font-mono text-[10px] font-bold">
              {tts}ms
            </div>
          </div>

          {/* Total Badge */}
          <div className="flex flex-col items-center justify-between p-2 rounded-xl bg-[#5865F2]/20 border border-[#5865F2]/40 text-center shadow-md w-[90px] sm:w-[100px] flex-shrink-0">
            <div className="flex items-center gap-1 text-[9px] font-mono uppercase text-[#5865F2] font-bold mb-0.5">
              <Clock className="w-3 h-3" />
              <span>TOTAL</span>
            </div>
            <div className="text-xs font-black font-mono text-white mt-1">
              {(total / 1000).toFixed(2)}s
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
