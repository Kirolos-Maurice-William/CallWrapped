"use client";

import React, { useState } from "react";
import { X, Copy, Check } from "lucide-react";
import { AnalyticsState, formatDurationHuman } from "./AnalyticsWidgets";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  analytics: AnalyticsState;
  verifiedCount?: number;
  disputedCount?: number;
}

export function CallWrappedModal({
  isOpen,
  onClose,
  analytics,
  verifiedCount = 3,
  disputedCount = 1,
}: Props) {
  const [copied, setCopied] = useState(false);

  if (!isOpen) return null;

  const {
    speakers,
    topic_totals,
    total_talk_seconds,
    total_angry_episodes,
    longest_streak,
  } = analytics;

  const speakerList = Object.values(speakers || {}).sort(
    (a, b) => b.talk_seconds - a.talk_seconds
  );
  const silentObserver =
    speakerList.length >= 2 ? speakerList[speakerList.length - 1] : null;
  const secondSilent =
    speakerList.length >= 2 ? speakerList[speakerList.length - 2] : null;
  const isObserverEligible = Boolean(
    silentObserver &&
      secondSilent &&
      secondSilent.talk_seconds - silentObserver.talk_seconds >= 1.0
  );

  const spicySpeakers = speakerList
    .filter((s) => (s.vulgarity_count || 0) > 0)
    .sort((a, b) => (b.vulgarity_count || 0) - (a.vulgarity_count || 0));
  const topSpicy = spicySpeakers[0];
  const isSpicyEligible = Boolean(
    speakerList.length >= 2 &&
      topSpicy &&
      (spicySpeakers.length < 2 ||
        (topSpicy.vulgarity_count || 0) >
          (spicySpeakers[1].vulgarity_count || 0))
  );

  const diplomatCandidates = speakerList
    .filter(
      (s) =>
        (s.vulgarity_count || 0) === 0 &&
        s.angry_episodes === 0 &&
        (s.banter_count || 0) === 0 &&
        s.talk_seconds >= 15.0
    )
    .sort((a, b) => b.talk_seconds - a.talk_seconds);
  const secondaryDiplomatCandidates = diplomatCandidates.filter(
    (s) =>
      !longest_streak?.speaker_name ||
      s.speaker_name !== longest_streak.speaker_name
  );
  const topDiplomat =
    secondaryDiplomatCandidates.length > 0
      ? secondaryDiplomatCandidates[0]
      : diplomatCandidates[0];
  const isDiplomatEligible = Boolean(
    speakerList.length >= 2 &&
      topDiplomat &&
      (diplomatCandidates.length < 2 || topDiplomat.talk_seconds >= 15.0)
  );

  const banterSpeakers = speakerList
    .filter((s) => (s.banter_count || 0) > 0)
    .sort((a, b) => (b.banter_count || 0) - (a.banter_count || 0));
  const topBanter = banterSpeakers[0];
  const isBanterEligible = Boolean(
    speakerList.length >= 2 &&
      topBanter &&
      (banterSpeakers.length < 2 ||
        (topBanter.banter_count || 0) > (banterSpeakers[1].banter_count || 0))
  );

  const topicalEntries = Object.entries(topic_totals || {})
    .filter(
      ([t]) =>
        t !== "null_topic" &&
        t !== "null" &&
        t !== "بدون موضوع" &&
        t !== "none"
    )
    .sort((a, b) => b[1] - a[1]);

  const topTopic = topicalEntries[0];
  const topTopicName = topTopic ? topTopic[0].toUpperCase() : "GENERAL";

  const handleCopy = () => {
    const observerLine =
      isObserverEligible && silentObserver
        ? `• **Silent Observer:** ${silentObserver.speaker_name} (${formatDurationHuman(silentObserver.talk_seconds)})\n`
        : "";
    const spicyLine =
      isSpicyEligible && topSpicy
        ? `• **Most Unfiltered:** ${topSpicy.speaker_name} (${topSpicy.vulgarity_count} raw tokens)\n`
        : "";
    const diplomatLine =
      isDiplomatEligible && topDiplomat
        ? `• **The Diplomat:** ${topDiplomat.speaker_name} (${formatDurationHuman(topDiplomat.talk_seconds)} peaceful)\n`
        : "";
    const roastLine =
      isBanterEligible && topBanter
        ? `• **Roast Master:** ${topBanter.speaker_name} (${topBanter.banter_count} roasts)\n`
        : "";
    const vibeText =
      total_angry_episodes === 0
        ? (analytics.total_banter_count || 0) > 0
          ? `Friendly Banter (${analytics.total_banter_count} roasts, 0 anger spikes)`
          : "Civilized (0 anger spikes)"
        : `${total_angry_episodes} heated episodes`;

    const summaryText =
      `**CALLWRAPPED // SESSION DOSSIER**\n` +
      `• **Monologue King:** ${longest_streak?.speaker_name || "N/A"} (${formatDurationHuman(longest_streak?.streak_seconds || 0)})\n` +
      observerLine +
      spicyLine +
      diplomatLine +
      roastLine +
      `• **Fact Record:** ${verifiedCount} verified, ${disputedCount} contradicted\n` +
      `• **Primary Topic:** ${topTopicName}\n` +
      `• **Call Vibe:** ${vibeText}`;

    navigator.clipboard.writeText(summaryText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-sm">
      <div className="relative w-full max-w-3xl bg-[#090a0d] border border-[#2a303c] shadow-2xl flex flex-col overflow-hidden text-[#e6e8ee]">
        {/* Top Bar */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[#1c2029] bg-[#0e1015]">
          <div className="flex items-center gap-3">
            <span className="w-2 h-2 bg-[#3b82f6]" />
            <span className="font-mono text-xs font-bold uppercase tracking-[0.16em] text-[#e6e8ee]">
              CALLWRAPPED // POST-CALL DOSSIER
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-[#7e8694] hover:text-white transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="divide-y divide-[#1c2029] overflow-y-auto max-h-[82vh]">
          {/* 4-Metric Strip */}
          <div className="grid grid-cols-2 md:grid-cols-4 divide-y md:divide-y-0 divide-x divide-[#1c2029]">
            <div className="p-5">
              <span className="font-mono text-[10px] uppercase tracking-wider text-[#7e8694] block">
                TOTAL AIRTIME
              </span>
              <span className="text-2xl font-bold text-white font-display mt-1 block">
                {formatDurationHuman(total_talk_seconds)}
              </span>
              <span className="font-mono text-[11px] text-[#3b82f6] mt-0.5 block">
                {speakerList.length} speakers
              </span>
            </div>

            <div className="p-5">
              <span className="font-mono text-[10px] uppercase tracking-wider text-[#7e8694] block">
                MONOLOGUE KING
              </span>
              <span
                className="text-xl font-bold text-white font-display mt-1 block truncate"
                dir="auto"
              >
                {longest_streak?.speaker_name || "—"}
              </span>
              <span className="font-mono text-[11px] text-[#f59e0b] mt-0.5 block">
                {formatDurationHuman(longest_streak?.streak_seconds || 0)} unbroken
              </span>
            </div>

            <div className="p-5">
              <span className="font-mono text-[10px] uppercase tracking-wider text-[#7e8694] block">
                TRUTH RECORD
              </span>
              <span className="text-2xl font-bold text-white font-display mt-1 block">
                {verifiedCount} / {verifiedCount + disputedCount}
              </span>
              <span className="font-mono text-[11px] text-[#10b981] mt-0.5 block">
                {verifiedCount} verified · {disputedCount} refuted
              </span>
            </div>

            <div className="p-5">
              <span className="font-mono text-[10px] uppercase tracking-wider text-[#7e8694] block">
                DOMINANT TOPIC
              </span>
              <span className="text-xl font-bold text-white font-display mt-1 block truncate">
                {topTopicName}
              </span>
              <span className="font-mono text-[11px] text-[#9aa2b1] mt-0.5 block">
                {total_angry_episodes === 0
                  ? "0 anger spikes"
                  : `${total_angry_episodes} heated moment(s)`}
              </span>
            </div>
          </div>

          {/* Titles & Awards */}
          <div className="p-6 space-y-3">
            <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-[#7e8694]">
              EARNED TITLES
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-px bg-[#1c2029] border border-[#1c2029]">
              {isDiplomatEligible && topDiplomat && (
                <div className="p-4 bg-[#090a0d] flex items-center justify-between">
                  <div>
                    <span className="font-mono text-[10px] uppercase tracking-wider text-[#10b981] block">
                      THE DIPLOMAT
                    </span>
                    <span className="text-sm font-bold text-white" dir="auto">
                      {topDiplomat.speaker_name}
                    </span>
                  </div>
                  <span className="font-mono text-xs text-[#7e8694]">
                    {formatDurationHuman(topDiplomat.talk_seconds)} · 0 friction
                  </span>
                </div>
              )}

              {isObserverEligible && silentObserver && (
                <div className="p-4 bg-[#090a0d] flex items-center justify-between">
                  <div>
                    <span className="font-mono text-[10px] uppercase tracking-wider text-[#3b82f6] block">
                      SILENT OBSERVER
                    </span>
                    <span className="text-sm font-bold text-white" dir="auto">
                      {silentObserver.speaker_name}
                    </span>
                  </div>
                  <span className="font-mono text-xs text-[#7e8694]">
                    {formatDurationHuman(silentObserver.talk_seconds)} airtime
                  </span>
                </div>
              )}

              {isSpicyEligible && topSpicy && (
                <div className="p-4 bg-[#090a0d] flex items-center justify-between">
                  <div>
                    <span className="font-mono text-[10px] uppercase tracking-wider text-[#ef4444] block">
                      MOST UNFILTERED
                    </span>
                    <span className="text-sm font-bold text-white" dir="auto">
                      {topSpicy.speaker_name}
                    </span>
                  </div>
                  <span className="font-mono text-xs text-[#7e8694]">
                    {topSpicy.vulgarity_count} raw tokens
                  </span>
                </div>
              )}

              {isBanterEligible && topBanter && (
                <div className="p-4 bg-[#090a0d] flex items-center justify-between">
                  <div>
                    <span className="font-mono text-[10px] uppercase tracking-wider text-[#f59e0b] block">
                      ROAST MASTER
                    </span>
                    <span className="text-sm font-bold text-white" dir="auto">
                      {topBanter.speaker_name}
                    </span>
                  </div>
                  <span className="font-mono text-xs text-[#7e8694]">
                    {topBanter.banter_count} roasts
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Talk Share Breakdown */}
          {speakerList.length > 0 && (
            <div className="p-6 space-y-3">
              <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-[#7e8694]">
                SPEAKER SHARE
              </div>
              <div className="space-y-2.5">
                {speakerList.map((spk) => {
                  const pct =
                    total_talk_seconds > 0
                      ? (spk.talk_seconds / total_talk_seconds) * 100
                      : 0;
                  return (
                    <div key={spk.speaker_name} className="space-y-1">
                      <div className="flex justify-between text-xs">
                        <span className="font-semibold text-white" dir="auto">
                          {spk.speaker_name}
                        </span>
                        <span className="font-mono text-[#7e8694]">
                          {formatDurationHuman(spk.talk_seconds)} (
                          {pct.toFixed(0)}%)
                        </span>
                      </div>
                      <div className="h-1.5 w-full bg-[#151821]">
                        <div
                          className="h-full bg-[#3b82f6]"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-[#1c2029] bg-[#0e1015] flex items-center justify-between">
          <span className="font-mono text-[11px] text-[#7e8694]">
            ASSEMBLYAI + GROQ LPU + TAVILY
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={handleCopy}
              className="flex items-center gap-1.5 px-4 py-2 bg-[#3b82f6] hover:bg-[#2563eb] text-white font-mono text-xs font-bold uppercase tracking-wider transition-colors cursor-pointer"
            >
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5" />
                  <span>COPIED TO CLIPBOARD</span>
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" />
                  <span>COPY DISCORD SUMMARY</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
export default CallWrappedModal;
