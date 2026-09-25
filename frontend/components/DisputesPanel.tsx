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
    badge: "bg-amber-500/15 text-amber-300 border-amber-500/40",
    label: "Offered",
    border: "border-amber-500/30",
    accent: "text-amber-300",
    Icon: Clock,
  },
  checking: {
    badge: "bg-sky-500/15 text-sky-300 border-sky-500/40",
    label: "Checking a disputed claim…",
    border: "border-sky-500/40",
    accent: "text-sky-300",
    Icon: Search,
  },
  resolved: {
    badge: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40",
    label: "Resolved",
    border: "border-emerald-500/40",
    accent: "text-emerald-300",
    Icon: CheckCircle2,
  },
  refused_private: {
    badge: "bg-slate-600/20 text-slate-300 border-slate-600/50",
    label: "Refused",
    border: "border-slate-700/70",
    accent: "text-slate-400",
    Icon: ShieldOff,
  },
  expired: {
    badge: "bg-slate-800/60 text-slate-500 border-slate-700/60",
    label: "Expired",
    border: "border-slate-800/80",
    accent: "text-slate-500",
    Icon: Clock,
  },
};

const FALLBACK_STYLE: StatusStyle = {
  badge: "bg-slate-800/60 text-slate-400 border-slate-700/60",
  label: "Unknown",
  border: "border-slate-800/80",
  accent: "text-slate-500",
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
    <div dir="auto" className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/70">
      <div className="flex items-center gap-1.5 mb-1.5">
        <Users className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
        <span className="text-xs font-semibold text-slate-300 truncate">
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
      className={`rounded-2xl bg-slate-900/70 border p-4 space-y-3 ${style.border} ${
        isDim ? "opacity-60" : ""
      }`}
    >
      {/* Header: disputed attribute + status badge */}
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <Scale className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
            <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">
              Disputed
            </span>
          </div>
          <p
            dir="auto"
            className="text-sm font-semibold text-slate-100 truncate mt-0.5"
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
        <ClaimBlock speaker={card.speaker_a} claim={card.claim_a} accent="text-slate-200" />
        <ClaimBlock speaker={card.speaker_b} claim={card.claim_b} accent="text-slate-200" />
      </div>

      {/* Resolved: source link + evidence excerpt */}
      {status === "resolved" && (
        <div className="space-y-2 pt-1 border-t border-slate-800/70">
          {card.source_url && (
            <a
              href={card.source_url}
              target="_blank"
              rel="noreferrer"
              dir="auto"
              className="flex items-center gap-1.5 text-xs font-semibold text-indigo-400 hover:text-indigo-300 break-all"
            >
              <ExternalLink className="w-3.5 h-3.5 flex-shrink-0" />
              {card.source_name || card.source_url}
            </a>
          )}
          {card.evidence_excerpt && (
            <blockquote
              dir="auto"
              className="flex gap-2 p-2.5 rounded-lg bg-slate-950/50 border border-slate-800/70"
            >
              <Quote className="w-3.5 h-3.5 text-slate-500 flex-shrink-0 mt-0.5" />
              <span className="text-xs text-slate-300 leading-relaxed break-words">
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
          className="text-xs text-slate-400 pt-1 border-t border-slate-800/70 flex items-center gap-1.5"
        >
          <ShieldOff className="w-3.5 h-3.5 flex-shrink-0" />
          {card.refusal_reason || "Private claim — no lookup performed"}
        </p>
      )}

      {/* Expired / offered: refusal or pending reason */}
      {status !== "refused_private" && card.refusal_reason && status !== "resolved" && (
        <p dir="auto" className="text-xs text-slate-500 pt-1 border-t border-slate-800/70">
          {card.refusal_reason}
        </p>
      )}

      {/* T_perceived, shown only once measured (confirmed verdict) */}
      {typeof card.t_perceived_ms === "number" && (
        <p className="flex items-center gap-1.5 text-xs text-emerald-300 font-semibold pt-1 border-t border-slate-800/70">
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
    <section className="rounded-2xl bg-slate-900/60 border border-slate-800 p-5 space-y-3">
      <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center gap-2">
        <Scale className="w-4 h-4" />
        Disputes
        {cards.length > 0 && (
          <span className="text-slate-500 normal-case font-medium">({cards.length})</span>
        )}
      </h3>

      {cards.length === 0 ? (
        <p className="text-sm text-slate-500 py-6 text-center">No disputes yet this call.</p>
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
