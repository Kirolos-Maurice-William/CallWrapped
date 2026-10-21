"use client";

import React, { useState } from "react";
import { X, Copy, Check, Sparkles } from "lucide-react";
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
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
      <div className="relative w-full max-w-3xl bg-[#0b0e14] border border-[#1e2638] rounded shadow-2xl flex flex-col overflow-hidden text-[#f0f3f8]">
        {/* Top Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[#1c2436] bg-[#101522]">
          <div className="flex items-center gap-2.5">
            <Sparkles className="w-4 h-4 text-[#3b82f6]" />
            <span className="font-editorial text-base font-bold text-white tracking-tight">
              CallWrapped Session Dossier
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-[#8e98ab] hover:text-white transition-colors cursor-pointer rounded hover:bg-[#161c2c]"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="divide-y divide-[#1c2436] overflow-y-auto max-h-[80vh]">
          {/* Key Metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 divide-y md:divide-y-0 md:divide-x divide-[#1c2436] bg-[#0e131f]">
            <div className="p-5">
              <span className="text-xs uppercase font-medium text-[#7d8b9e] block">
                Total Airtime
              </span>
              <span className="text-2xl font-bold text-white font-editorial mt-1 block">
                {formatDurationHuman(total_talk_seconds)}
              </span>
              <span className="font-mono text-xs text-[#3b82f6] mt-0.5 block">
                {speakerList.length} speakers
              </span>
            </div>

            <div className="p-5">
              <span className="text-xs uppercase font-medium text-[#7d8b9e] block">
                Monologue King
              </span>
              <span
                className="text-xl font-bold text-white font-editorial mt-1 block truncate"
                dir="auto"
              >
                {longest_streak?.speaker_name || "—"}
              </span>
              <span className="font-mono text-xs text-[#f59e0b] mt-0.5 block">
                {formatDurationHuman(longest_streak?.streak_seconds || 0)} unbroken
              </span>
            </div>

            <div className="p-5">
              <span className="text-xs uppercase font-medium text-[#7d8b9e] block">
                Fact Accuracy
              </span>
              <span className="text-2xl font-bold text-white font-editorial mt-1 block">
                {verifiedCount} / {verifiedCount + disputedCount}
              </span>
              <span className="font-mono text-xs text-[#10b981] mt-0.5 block">
                {verifiedCount} verified · {disputedCount} refuted
              </span>
            </div>

            <div className="p-5">
              <span className="text-xs uppercase font-medium text-[#7d8b9e] block">
                Dominant Topic
              </span>
              <span className="text-xl font-bold text-white font-editorial mt-1 block truncate">
                {topTopicName}
              </span>
              <span className="font-mono text-xs text-[#8e98ab] mt-0.5 block">
                {total_angry_episodes === 0
                  ? "0 anger spikes"
                  : `${total_angry_episodes} heated moment(s)`}
              </span>
            </div>
          </div>

          {/* Titles & Awards */}
          <div className="p-6 space-y-3">
            <h4 className="text-xs uppercase font-bold tracking-wider text-[#7d8b9e]">
              Earned Badges
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {isDiplomatEligible && topDiplomat && (
                <div className="p-4 bg-[#101522] border border-[#1c2436] rounded flex items-center justify-between">
                  <div>
                    <span className="font-editorial text-sm font-bold text-[#10b981] block">
                      The Diplomat
                    </span>
                    <span className="text-sm font-medium text-white" dir="auto">
                      {topDiplomat.speaker_name}
                    </span>
                  </div>
                  <span className="font-mono text-xs text-[#8e98ab]">
                    {formatDurationHuman(topDiplomat.talk_seconds)} peaceful
                  </span>
                </div>
              )}

              {isObserverEligible && silentObserver && (
                <div className="p-4 bg-[#101522] border border-[#1c2436] rounded flex items-center justify-between">
                  <div>
                    <span className="font-editorial text-sm font-bold text-[#3b82f6] block">
                      Silent Observer
                    </span>
                    <span className="text-sm font-medium text-white" dir="auto">
                      {silentObserver.speaker_name}
                    </span>
                  </div>
                  <span className="font-mono text-xs text-[#8e98ab]">
                    {formatDurationHuman(silentObserver.talk_seconds)} airtime
                  </span>
                </div>
              )}

              {isSpicyEligible && topSpicy && (
                <div className="p-4 bg-[#101522] border border-[#1c2436] rounded flex items-center justify-between">
                  <div>
                    <span className="font-editorial text-sm font-bold text-[#f43f5e] block">
                      Most Unfiltered
                    </span>
                    <span className="text-sm font-medium text-white" dir="auto">
                      {topSpicy.speaker_name}
                    </span>
                  </div>
                  <span className="font-mono text-xs text-[#8e98ab]">
                    {topSpicy.vulgarity_count} raw tokens
                  </span>
                </div>
              )}

              {isBanterEligible && topBanter && (
                <div className="p-4 bg-[#101522] border border-[#1c2436] rounded flex items-center justify-between">
                  <div>
                    <span className="font-editorial text-sm font-bold text-[#f59e0b] block">
                      Roast Master
                    </span>
                    <span className="text-sm font-medium text-white" dir="auto">
                      {topBanter.speaker_name}
                    </span>
                  </div>
                  <span className="font-mono text-xs text-[#8e98ab]">
                    {topBanter.banter_count} friendly roasts
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Talk Time Breakdown */}
          {speakerList.length > 0 && (
            <div className="p-6 space-y-3">
              <h4 className="text-xs uppercase font-bold tracking-wider text-[#7d8b9e]">
                Speaker Share
              </h4>
              <div className="space-y-3">
                {speakerList.map((spk) => {
                  const pct =
                    total_talk_seconds > 0
                      ? (spk.talk_seconds / total_talk_seconds) * 100
                      : 0;
                  return (
                    <div key={spk.speaker_name} className="space-y-1.5">
                      <div className="flex justify-between text-sm">
                        <span className="font-medium text-white" dir="auto">
                          {spk.speaker_name}
                        </span>
                        <span className="font-mono text-xs text-[#8e98ab]">
                          {formatDurationHuman(spk.talk_seconds)} ({pct.toFixed(0)}%)
                        </span>
                      </div>
                      <div className="h-2 w-full bg-[#161c2c] rounded-full overflow-hidden">
                        <div
                          className="h-full bg-[#3b82f6] rounded-full"
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

        {/* Modal Footer */}
        <div className="px-6 py-4 border-t border-[#1c2436] bg-[#101522] flex items-center justify-between">
          <span className="text-xs text-[#7d8b9e]">
            AssemblyAI + Groq LPU + Tavily Ground-Truth
          </span>
          <button
            onClick={handleCopy}
            className="flex items-center gap-2 px-4 py-2 bg-[#3b82f6] hover:bg-[#2563eb] text-white text-xs font-semibold rounded transition-colors cursor-pointer"
          >
            {copied ? (
              <>
                <Check className="w-4 h-4" />
                <span>Copied to Clipboard</span>
              </>
            ) : (
              <>
                <Copy className="w-4 h-4" />
                <span>Copy Summary for Discord</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

export default CallWrappedModal;
