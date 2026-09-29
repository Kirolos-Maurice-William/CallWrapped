"use client";

import React from "react";
import {
  Scale,
  Search,
  CheckCircle2,
  ShieldOff,
  Clock,
  ExternalLink,
  Quote,
  Users,
  Timer,
} from "lucide-react";

/**
 * One card per gate-passed dispute, mirroring the backend dispute card in
 * LIVE_STATE["disputes"] (`backend/app/routes.py`).
 * Lifecycle: offered -> checking -> resolved | expired | refused_private
 */
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

interface StatusStyle {
  badge: string;
  label: string;
  border: string;
  accent: string;
  Icon: React.ComponentType<{ className?: string }>;
}

const STATUS_STYLES: Record<string, StatusStyle> = {
  offered: {
    badge: "bg-[#F0B232]/15 text-[#F0B232] border-[#F0B232]/40",
    label: "Offered",
    border: "border-[#F0B232]/30",
    accent: "text-[#F0B232]",
    Icon: Clock,
  },
  checking: {
    badge: "bg-[#5865F2]/15 text-[#5865F2] border-[#5865F2]/40",
    label: "Checking a disputed claim…",
    border: "border-[#5865F2]/40",
    accent: "text-[#5865F2]",
    Icon: Search,
  },
  resolved: {
    badge: "bg-[#23A55A]/15 text-[#23A55A] border-[#23A55A]/40",
    label: "Resolved",
    border: "border-[#23A55A]/40",
    accent: "text-[#23A55A]",
    Icon: CheckCircle2,
  },
  refused_private: {
    badge: "bg-[#383a40]/60 text-[#949BA4] border-[#383a40]",
    label: "Refused",
    border: "border-[#383a40]",
    accent: "text-[#949BA4]",
    Icon: ShieldOff,
  },
  expired: {
    badge: "bg-[#1e1f22] text-[#949BA4] border-[#383a40]",
    label: "Expired",
    border: "border-[#383a40]",
    accent: "text-[#949BA4]",
    Icon: Clock,
  },
};

const FALLBACK_STYLE: StatusStyle = {
  badge: "bg-[#1e1f22] text-[#949BA4] border-[#383a40]",
  label: "Unknown",
  border: "border-[#383a40]",
  accent: "text-[#949BA4]",
  Icon: Scale,
};

/**
 * Claim text is code-switched Arabic/English per utterance. `dir="auto"` picks
 * direction from the first strong character, so an Arabic claim renders RTL and
 * an English one LTR without either being forced the wrong way.
 */
function ClaimBlock({
  speaker,
  claim,
  accent,
}: {
  speaker?: string | null;
  claim?: string | null;
  accent: string;
}) {
  return (
    <div dir="auto" className="p-3 rounded-xl bg-[#313338] border border-[#383a40]">
      <div className="flex items-center gap-1.5 mb-1.5">
        <Users className="w-3.5 h-3.5 text-[#949BA4] flex-shrink-0" />
        <span className="text-xs font-semibold text-[#DBDEE1] truncate">
          {speaker || "Unknown speaker"}
        </span>
      </div>
      <p className={`text-sm font-medium leading-relaxed break-words ${accent}`}>
        {claim || "—"}
      </p>
    </div>
  );
}

function DisputeCardView({ card }: { card: DisputeCard }) {
  const status = card.status || "unknown";
  const style = STATUS_STYLES[status] || FALLBACK_STYLE;
  const { Icon } = style;
  const isDim = status === "expired";

  return (
    <article
      className={`rounded-2xl bg-[#1e1f22] border p-4 space-y-3 ${style.border} ${
        isDim ? "opacity-60" : ""
      }`}
    >
      {/* Header: disputed attribute + status badge */}
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <Scale className="w-3.5 h-3.5 text-[#949BA4] flex-shrink-0" />
            <span className="text-[11px] font-bold text-[#949BA4] uppercase tracking-wider">
              Disputed
            </span>
          </div>
          <p
            dir="auto"
            className="text-sm font-semibold text-[#F2F3F5] truncate mt-0.5"
            title={card.disputed_attribute || undefined}
          >
            {card.disputed_attribute || "Unspecified attribute"}
          </p>
        </div>
        <span
          className={`flex items-center gap-1.5 text-[11px] font-bold px-2 py-1 rounded-lg border flex-shrink-0 ${style.badge}`}
        >
          <Icon className={`w-3.5 h-3.5 ${status === "checking" ? "animate-pulse" : ""}`} />
          {style.label}
        </span>
      </header>

      {/* Claims side by side */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <ClaimBlock speaker={card.speaker_a} claim={card.claim_a} accent="text-[#F2F3F5]" />
        <ClaimBlock speaker={card.speaker_b} claim={card.claim_b} accent="text-[#F2F3F5]" />
      </div>

      {/* Resolved: source link + evidence excerpt */}
      {status === "resolved" && (
        <div className="space-y-2 pt-1 border-t border-[#383a40]">
          {card.source_url && (
            <a
              href={card.source_url}
              target="_blank"
              rel="noreferrer"
              dir="auto"
              className="flex items-center gap-1.5 text-xs font-semibold text-[#5865F2] hover:text-[#5865F2]/80 break-all"
            >
              <ExternalLink className="w-3.5 h-3.5 flex-shrink-0" />
              {card.source_name || card.source_url}
            </a>
          )}
          {card.evidence_excerpt && (
            <blockquote
              dir="auto"
              className="flex gap-2 p-2.5 rounded-lg bg-[#313338] border border-[#383a40]"
            >
              <Quote className="w-3.5 h-3.5 text-[#949BA4] flex-shrink-0 mt-0.5" />
              <span className="text-xs text-[#DBDEE1] leading-relaxed break-words">
                {card.evidence_excerpt}
              </span>
            </blockquote>
          )}
        </div>
      )}

      {/* Refused: reason, and no looked-up evidence exists to show */}
      {status === "refused_private" && (
        <p
          dir="auto"
          className="text-xs text-[#949BA4] pt-1 border-t border-[#383a40] flex items-center gap-1.5"
        >
          <ShieldOff className="w-3.5 h-3.5 flex-shrink-0" />
          {card.refusal_reason || "Private claim — no lookup performed"}
        </p>
      )}

      {/* Expired / offered: refusal or pending reason */}
      {status !== "refused_private" && card.refusal_reason && status !== "resolved" && (
        <p dir="auto" className="text-xs text-[#949BA4] pt-1 border-t border-[#383a40]">
          {card.refusal_reason}
        </p>
      )}

      {/* T_perceived, shown only once measured (confirmed verdict) */}
      {typeof card.t_perceived_ms === "number" && (
        <p className="flex items-center gap-1.5 text-xs text-[#23A55A] font-semibold pt-1 border-t border-[#383a40]">
          <Timer className="w-3.5 h-3.5" />
          T_perceived: {card.t_perceived_ms} ms
        </p>
      )}
    </article>
  );
}

export function DisputesPanel({ disputes }: { disputes: DisputeCard[] }) {
  const cards = disputes || [];

  return (
    <section className="rounded-2xl bg-[#2b2d31] border border-[#383a40] p-5 space-y-3">
      <h3 className="text-xs font-bold text-[#949BA4] uppercase tracking-wider flex items-center gap-2">
        <Scale className="w-4 h-4 text-[#5865F2]" />
        Disputes
        {cards.length > 0 && (
          <span className="text-[#949BA4] normal-case font-medium">({cards.length})</span>
        )}
      </h3>

      {cards.length === 0 ? (
        <p className="text-sm text-[#949BA4] py-6 text-center">No disputes yet this call.</p>
      ) : (
        <div className="space-y-3">
          {cards.map((card) => (
            <DisputeCardView key={card.dispute_id} card={card} />
          ))}
        </div>
      )}
    </section>
  );
}

export default DisputesPanel;
