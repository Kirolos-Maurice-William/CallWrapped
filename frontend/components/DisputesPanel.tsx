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
  { label: string; color: string; borderLeft: string }
> = {
  offered: {
    label: "AWAITING CONSENT",
    color: "text-[#f59e0b] border-[#f59e0b]/40 bg-[#f59e0b]/10",
    borderLeft: "border-l-[#f59e0b]",
  },
  checking: {
    label: "VERIFYING",
    color: "text-[#3b82f6] border-[#3b82f6]/40 bg-[#3b82f6]/10",
    borderLeft: "border-l-[#3b82f6]",
  },
  resolved: {
    label: "VERIFIED",
    color: "text-[#10b981] border-[#10b981]/40 bg-[#10b981]/10",
    borderLeft: "border-l-[#10b981]",
  },
  refused_private: {
    label: "PRIVACY REFUSAL",
    color: "text-[#9aa2b1] border-[#2a303c] bg-[#13161c]",
    borderLeft: "border-l-[#68707e]",
  },
  expired: {
    label: "EXPIRED (NO CONSENT)",
    color: "text-[#68707e] border-[#1c2029] bg-[#0e1015]",
    borderLeft: "border-l-[#2a303c]",
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
    <div className="border-t border-[#1c2029]">
      <div className="px-5 py-2.5 bg-[#0c0e13] border-b border-[#1c2029] flex items-center justify-between">
        <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-[#7e8694]">
          SESSION DISPUTE LOG ({cards.length})
        </span>
        <span className="font-mono text-[10px] text-[#525866]">
          GATE-PASSED CLAIMS
        </span>
      </div>

      <div className="divide-y divide-[#1c2029]">
        {cards.map((card) => {
          const status = card.status || "unknown";
          const meta = STATUS_META[status] || {
            label: status.toUpperCase(),
            color: "text-[#7e8694] border-[#1c2029] bg-[#0e1015]",
            borderLeft: "border-l-[#2a303c]",
          };

          return (
            <div
              key={card.dispute_id}
              onClick={() => onSelectDispute?.(card)}
              className={`p-4 bg-[#090a0d] hover:bg-[#0e1015] transition-colors border-l-2 ${
                meta.borderLeft
              } ${onSelectDispute ? "cursor-pointer" : ""} ${
                status === "expired" ? "opacity-60" : ""
              }`}
            >
              <div className="flex items-center justify-between gap-3 mb-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="font-mono text-xs font-bold text-[#e6e8ee] truncate">
                    {card.disputed_attribute || "Factual Dispute"}
                  </span>
                  {typeof card.t_perceived_ms === "number" && (
                    <span className="font-mono text-[10px] text-[#10b981]">
                      • {card.t_perceived_ms}ms
                    </span>
                  )}
                </div>
                <span
                  className={`font-mono text-[10px] font-bold px-2 py-0.5 border shrink-0 ${meta.color}`}
                >
                  {meta.label}
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs border-t border-[#151821] pt-2.5">
                <div dir="auto" className="space-y-0.5">
                  <span className="font-mono text-[10px] uppercase text-[#7e8694] block">
                    {card.speaker_a || "Speaker A"}
                  </span>
                  <p className="text-[#c8ceda] line-clamp-2">
                    “{card.claim_a || "—"}”
                  </p>
                </div>
                <div dir="auto" className="space-y-0.5 sm:border-l sm:border-[#1c2029] sm:pl-3">
                  <span className="font-mono text-[10px] uppercase text-[#7e8694] block">
                    {card.speaker_b || "Speaker B"}
                  </span>
                  <p className="text-[#c8ceda] line-clamp-2">
                    “{card.claim_b || "—"}”
                  </p>
                </div>
              </div>

              {status === "resolved" && (card.evidence_excerpt || card.source_url) && (
                <div className="mt-2.5 pt-2 border-t border-[#151821] flex flex-wrap items-center justify-between gap-2 text-xs">
                  {card.evidence_excerpt && (
                    <p
                      dir="auto"
                      className="text-[#10b981] font-medium text-xs flex-1 min-w-[200px]"
                    >
                      <Check className="w-3.5 h-3.5 inline mr-1 -mt-0.5" />
                      {card.evidence_excerpt}
                    </p>
                  )}
                  {card.source_url && (
                    <a
                      href={card.source_url}
                      target="_blank"
                      rel="noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="font-mono text-[11px] text-[#3b82f6] hover:underline inline-flex items-center gap-1 shrink-0"
                    >
                      <span>{card.source_name || "Source"}</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  )}
                </div>
              )}

              {status === "refused_private" && (
                <div className="mt-2 pt-2 border-t border-[#151821] flex items-center gap-1.5 text-[11px] font-mono text-[#7e8694]">
                  <ShieldOff className="w-3.5 h-3.5 text-[#f59e0b]" />
                  <span>
                    {card.refusal_reason ||
                      "Private individual claim — web lookup refused by privacy policy."}
                  </span>
                </div>
              )}

              {status === "checking" && (
                <div className="mt-2 pt-2 border-t border-[#151821] flex items-center gap-1.5 text-[11px] font-mono text-[#3b82f6]">
                  <Search className="w-3.5 h-3.5 animate-pulse" />
                  <span>Querying authoritative sources via Tavily...</span>
                </div>
              )}

              {status === "offered" && (
                <div className="mt-2 pt-2 border-t border-[#151821] flex items-center gap-1.5 text-[11px] font-mono text-[#f59e0b]">
                  <Clock className="w-3.5 h-3.5" />
                  <span>Offered in voice («أشوفها؟» / &quot;Do I check?&quot;) — awaiting confirmation</span>
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
