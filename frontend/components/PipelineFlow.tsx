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
      code: "01",
      name: "ASR",
      ms: stt > 0 ? `${stt}ms` : "—",
      active: activeStage === "asr",
    },
    {
      code: "02",
      name: "FastGate",
      ms: stt > 0 ? "<8ms" : "—",
      active: activeStage === "claim",
    },
    {
      code: "03",
      name: "Groq LPU",
      ms: llm > 0 ? `${llm}ms` : "—",
      active: activeStage === "claim" || activeStage === "offer",
    },
    {
      code: "04",
      name: "Tavily Search",
      ms: search > 0 ? `${search}ms` : "—",
      active: activeStage === "offer" || activeStage === "search",
    },
    {
      code: "05",
      name: "Edge-TTS",
      ms: tts > 0 ? `${tts}ms` : "—",
      active: activeStage === "verdict",
    },
  ];

  return (
    <div className="border-b border-[#1c2436] bg-[#0d121c] px-4 md:px-6 py-1.5 font-mono text-xs select-none">
      <div className="max-w-[1440px] mx-auto flex items-center justify-between gap-4">
        {/* Stages */}
        <div className="flex items-center gap-3 overflow-x-auto text-[11px] text-[#7d8b9e]">
          <span className="text-[10px] uppercase font-semibold text-[#546275] tracking-wider shrink-0">
            Pipeline:
          </span>
          <div className="flex items-center gap-2">
            {stages.map((s, idx) => (
              <React.Fragment key={s.code}>
                {idx > 0 && <span className="text-[#2b364e]">→</span>}
                <div
                  className={`flex items-center gap-1.5 px-2 py-0.5 rounded transition-colors ${
                    s.active
                      ? "bg-[#3b82f6]/20 text-[#60a5fa] font-bold"
                      : "text-[#8e98ab]"
                  }`}
                >
                  <span>{s.name}</span>
                  {s.ms !== "—" && (
                    <span className="text-[10px] text-[#5e6b7d]">({s.ms})</span>
                  )}
                </div>
              </React.Fragment>
            ))}
          </div>
        </div>

        {/* SLA Status */}
        <div className="flex items-center gap-3 text-xs shrink-0 font-mono">
          <span className="text-[#8e98ab]">
            Perceived:{" "}
            <strong className="text-white">
              {total > 0 ? `${(total / 1000).toFixed(2)}s` : "—"}
            </strong>
          </span>
          <span
            className={`px-2 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase border ${
              !isArbitration
                ? "border-[#1c2436] bg-[#101522] text-[#626d80]"
                : isPassingSla
                ? "border-[#10b981]/30 bg-[#10b981]/10 text-[#10b981]"
                : "border-[#f43f5e]/30 bg-[#f43f5e]/10 text-[#f43f5e]"
            }`}
          >
            {isArbitration
              ? isPassingSla
                ? "SLA PASS"
                : "SLA EXCEEDED"
              : "IDLE"}
          </span>
        </div>
      </div>
    </div>
  );
}

export default PipelineFlow;
