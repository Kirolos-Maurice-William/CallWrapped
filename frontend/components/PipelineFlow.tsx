"use client";

import React from "react";

interface LatencyMetrics {
  stt_ms?: number;
  llm_ms?: number;
  search_ms?: number;
  tts_ms?: number;
  total_ms?: number;
}

export type ActivePipelineStage =
  | "idle"
  | "asr"
  | "claim"
  | "offer"
  | "search"
  | "verdict";

interface Props {
  latency: LatencyMetrics;
  speechModel?: string;
  targetSlaMs?: number;
  activeStage?: ActivePipelineStage;
}

export function PipelineFlow({
  latency,
  speechModel = "Universal-3.5 Pro",
  targetSlaMs = 2000,
  activeStage = "idle",
}: Props) {
  const stt = latency.stt_ms ?? 0;
  const llm = latency.llm_ms ?? 0;
  const search = latency.search_ms ?? 0;
  const tts = latency.tts_ms ?? 0;
  const total = stt + llm + search + tts || latency.total_ms || 0;

  const isArbitration = llm > 0 || search > 0 || tts > 0;
  const isPassingSla = isArbitration ? total <= targetSlaMs : true;

  const stages = [
    {
      id: "asr",
      code: "01",
      name: "ASR",
      detail: speechModel,
      ms: stt > 0 ? `${stt}ms` : "—",
      active: activeStage === "asr" || stt > 0,
      highlight: activeStage === "asr",
    },
    {
      id: "gate",
      code: "02",
      name: "FASTGATE",
      detail: "Epistemic",
      ms: stt > 0 ? "<8ms" : "—",
      active: activeStage === "claim" || stt > 0,
      highlight: activeStage === "claim",
    },
    {
      id: "llm",
      code: "03",
      name: "GROQ LPU",
      detail: "Claim FSM",
      ms: llm > 0 ? `${llm}ms` : "—",
      active: activeStage === "claim" || activeStage === "offer" || llm > 0,
      highlight: activeStage === "claim" || activeStage === "offer",
    },
    {
      id: "search",
      code: "04",
      name: "TAVILY",
      detail: "Pre-fetch",
      ms: search > 0 ? `${search}ms` : "—",
      active: activeStage === "offer" || activeStage === "search" || search > 0,
      highlight: activeStage === "offer" || activeStage === "search",
    },
    {
      id: "tts",
      code: "05",
      name: "EDGE TTS",
      detail: "Voice Out",
      ms: tts > 0 ? `${tts}ms` : "—",
      active: activeStage === "verdict" || tts > 0,
      highlight: activeStage === "verdict",
    },
  ];

  return (
    <div className="border-b border-[#1c2029] bg-[#0b0d12] px-4 md:px-6 py-2 font-mono text-[11px] select-none overflow-x-auto">
      <div className="max-w-[1440px] mx-auto flex items-center justify-between gap-6 min-w-max">
        {/* Left label */}
        <div className="flex items-center gap-2.5 text-[#7e8694]">
          <span
            className={`w-1.5 h-1.5 ${
              activeStage !== "idle"
                ? "bg-[#3b82f6] animate-ping"
                : stt > 0
                ? "bg-[#10b981]"
                : "bg-[#3a404d]"
            }`}
          />
          <span className="uppercase tracking-[0.14em] text-[10px] font-semibold text-[#9aa2b1]">
            PIPELINE TELEMETRY
          </span>
        </div>

        {/* Stage strip */}
        <div className="flex items-center divide-x divide-[#1c2029]">
          {stages.map((s) => (
            <div
              key={s.id}
              className={`px-3 first:pl-0 last:pr-0 flex items-center gap-2 transition-colors ${
                s.highlight
                  ? "text-[#e6e8ee]"
                  : s.active
                  ? "text-[#b4bcc8]"
                  : "text-[#525866]"
              }`}
            >
              <span className="text-[10px] text-[#525866]">{s.code}</span>
              <span
                className={`font-semibold tracking-wider ${
                  s.highlight ? "text-[#3b82f6]" : ""
                }`}
              >
                {s.name}
              </span>
              <span className="hidden xl:inline text-[10px] text-[#68707e]">
                [{s.detail}]
              </span>
              <span
                className={`px-1.5 py-0.5 text-[10px] font-semibold ${
                  s.highlight
                    ? "bg-[#3b82f6]/20 text-[#60a5fa] border border-[#3b82f6]/40"
                    : s.ms !== "—"
                    ? "bg-[#13161c] text-[#e6e8ee] border border-[#1c2029]"
                    : "text-[#525866]"
                }`}
              >
                {s.ms}
              </span>
            </div>
          ))}
        </div>

        {/* Right SLA / Total */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] uppercase tracking-wider text-[#68707e]">
              PERCEIVED
            </span>
            <span className="font-bold text-[#e6e8ee]">
              {total > 0 ? `${(total / 1000).toFixed(2)}s` : "—"}
            </span>
          </div>
          <span
            className={`px-2 py-0.5 text-[10px] font-bold tracking-wider uppercase border ${
              !isArbitration
                ? "border-[#1c2029] bg-[#111319] text-[#7e8694]"
                : isPassingSla
                ? "border-[#10b981]/40 bg-[#10b981]/10 text-[#10b981]"
                : "border-[#ef4444]/40 bg-[#ef4444]/10 text-[#ef4444]"
            }`}
          >
            {isArbitration
              ? isPassingSla
                ? `SLA <${(targetSlaMs / 1000).toFixed(1)}S PASS`
                : "SLA EXCEEDED"
              : "STANDBY"}
          </span>
        </div>
      </div>
    </div>
  );
}
export default PipelineFlow;
