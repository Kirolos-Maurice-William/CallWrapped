"use client";

import React from "react";
import { ExternalLink, ShieldOff, Check, Clock, Search } from "lucide-react";

export interface DisputeCard {
  dispute_id: string;
  speaker_a?: string | null;
  claim_a?: string | null;
  speaker_b?: string | null;
  claim_b?: string | null;
  disputed_attribute?: string | null;
  status?: string | null;
  refusal_reason?: string | null;
  source_name?: string | null;
  source_url?: string | null;
  evidence_excerpt?: string | null;
  checked_timestamp?: number | null;
  t_perceived_ms?: number | null;
  created_at?: number;
  last_updated?: number;
}

const STATUS_META: Record<
  string,
  { label: string; badgeClass: string; borderClass: string }
> = {
  offered: {
    label: "Awaiting Consent",
    badgeClass: "text-[#f59e0b] border-[#f59e0b]/30 bg-[#f59e0b]/10",
    borderClass: "border-l-[#f59e0b]",
  },
  checking: {
    label: "Searching Web",
    badgeClass: "text-[#3b82f6] border-[#3b82f6]/30 bg-[#3b82f6]/10",
    borderClass: "border-l-[#3b82f6]",
  },
  resolved: {
    label: "Verified",
    badgeClass: "text-[#10b981] border-[#10b981]/30 bg-[#10b981]/10",
    borderClass: "border-l-[#10b981]",
  },
  refused_private: {
    label: "Privacy Refusal",
    badgeClass: "text-[#8e98ab] border-[#1e2638] bg-[#161c2c]",
    borderClass: "border-l-[#5e6b7d]",
  },
  expired: {
    label: "Expired",
    badgeClass: "text-[#5e6b7d] border-[#1c2436] bg-[#101522]",
    borderClass: "border-l-[#2b364e]",
  },
};

export function DisputesPanel({
  disputes,
  onSelectDispute,
}: {
  disputes: DisputeCard[];
  onSelectDispute?: (card: DisputeCard) => void;
}) {
  const cards = disputes || [];
  if (cards.length === 0) return null;

  return (
    <div className="border-t border-[#1c2436] bg-[#0b0e14]">
      <div className="px-6 py-3 bg-[#101522] border-b border-[#1c2436] flex items-center justify-between">
        <span className="font-mono text-xs font-semibold uppercase tracking-wider text-[#8e98ab]">
          Session Dispute History ({cards.length})
        </span>
        <span className="font-mono text-xs text-[#5e6b7d]">
          Consensual Voice Referee Log
        </span>
      </div>

      <div className="divide-y divide-[#1c2436]">
        {cards.map((card) => {
          const status = card.status || "unknown";
          const meta = STATUS_META[status] || {
            label: status,
            badgeClass: "text-[#8e98ab] border-[#1c2436] bg-[#101522]",
            borderClass: "border-l-[#2b364e]",
          };

          return (
            <div
              key={card.dispute_id}
              onClick={() => onSelectDispute?.(card)}
              className={`p-5 bg-[#0b0e14] hover:bg-[#101522] transition-colors border-l-2 ${
                meta.borderClass
              } ${onSelectDispute ? "cursor-pointer" : ""}`}
            >
              <div className="flex items-center justify-between gap-3 mb-2">
                <span className="font-editorial text-sm font-bold text-white tracking-tight">
                  {card.disputed_attribute || "Factual Disagreement"}
                </span>
                <span
                  className={`font-mono text-xs font-semibold px-2 py-0.5 rounded border ${meta.badgeClass}`}
                >
                  {meta.label}
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm mt-3 pt-3 border-t border-[#161c2c]">
                <div dir="auto" className="space-y-1">
                  <span className="font-mono text-xs text-[#7d8b9e] block">
                    {card.speaker_a || "Speaker A"}
                  </span>
                  <p className="text-[#d8e0ec] leading-relaxed">
                    “{card.claim_a || "—"}”
                  </p>
                </div>
                <div
                  dir="auto"
                  className="space-y-1 sm:border-l sm:border-[#1c2436] sm:pl-4"
                >
                  <span className="font-mono text-xs text-[#7d8b9e] block">
                    {card.speaker_b || "Speaker B"}
                  </span>
                  <p className="text-[#d8e0ec] leading-relaxed">
                    “{card.claim_b || "—"}”
                  </p>
                </div>
              </div>

              {status === "resolved" && (card.evidence_excerpt || card.source_url) && (
                <div className="mt-3 pt-3 border-t border-[#161c2c] flex flex-wrap items-center justify-between gap-3 text-sm">
                  {card.evidence_excerpt && (
                    <p dir="auto" className="text-[#10b981] font-medium flex-1">
                      <Check className="w-4 h-4 inline mr-1.5 -mt-0.5" />
                      {card.evidence_excerpt}
                    </p>
                  )}
                  {card.source_url && (
                    <a
                      href={card.source_url}
                      target="_blank"
                      rel="noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="font-mono text-xs text-[#3b82f6] hover:underline inline-flex items-center gap-1.5 shrink-0"
                    >
                      <span>{card.source_name || "Official Source"}</span>
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  )}
                </div>
              )}

              {status === "refused_private" && (
                <div className="mt-3 pt-3 border-t border-[#161c2c] flex items-center gap-2 text-xs text-[#8e98ab]">
                  <ShieldOff className="w-4 h-4 text-[#f59e0b]" />
                  <span>
                    {card.refusal_reason ||
                      "Private claim — web search skipped by privacy policy."}
                  </span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default DisputesPanel;
