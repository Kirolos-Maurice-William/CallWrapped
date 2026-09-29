"use client";

import React, { useState } from "react";
import {
  X,
  Award,
  Crown,
  Flame,
  PieChart,
  Smile,
  Volume2,
  Copy,
  Check,
  Share2,
  ShieldCheck,
  Sparkles
} from "lucide-react";
import { AnalyticsState, formatStreakMMSS, formatDurationHuman } from "./AnalyticsWidgets";

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
  disputedCount = 1
}: Props) {
  const [copied, setCopied] = useState(false);

  if (!isOpen) return null;

  const { speakers, topic_totals, total_talk_seconds, total_angry_episodes, longest_streak } = analytics;

  // Speaker calculations
  const speakerList = Object.values(speakers || {}).sort((a, b) => b.talk_seconds - a.talk_seconds);
  const topTalker = speakerList[0];
  const silentObserver = speakerList.length >= 2 ? speakerList[speakerList.length - 1] : null;
  const secondSilent = speakerList.length >= 2 ? speakerList[speakerList.length - 2] : null;
  const isObserverEligible = Boolean(
    silentObserver && secondSilent && (secondSilent.talk_seconds - silentObserver.talk_seconds >= 1.0)
  );

  // Topics
  const topicalEntries = Object.entries(topic_totals || {})
    .filter(([t]) => t !== "null_topic" && t !== "null" && t !== "بدون موضوع" && t !== "none")
    .sort((a, b) => b[1] - a[1]);

  const topTopic = topicalEntries[0];
  const topTopicName = topTopic ? topTopic[0].toUpperCase() : "GENERAL BANTER";

  const handleCopy = () => {
    const observerLine = isObserverEligible && silentObserver
      ? `🤫 **The Silent Observer:** ${silentObserver.speaker_name} (${formatDurationHuman(silentObserver.talk_seconds)})\n`
      : "";
    const summaryText = `🎙️ **CALLWRAPPED SESSION SUMMARY**\n` +
      `👑 **Monologue King:** ${longest_streak?.speaker_name || "N/A"} (${formatDurationHuman(longest_streak?.streak_seconds || 0)})\n` +
      observerLine +
      `🎯 **Ground Truth:** ${verifiedCount} verified, ${disputedCount} refuted\n` +
      `📊 **Top Topic:** ${topTopicName}\n` +
      `🕊️ **Call Vibe:** ${total_angry_episodes === 0 ? "Civilized discussion (0 anger spikes)" : `${total_angry_episodes} heated episodes`}\n` +
      `⚡ *Arbitrated live by CallWrapped AI Referee (AssemblyAI + Groq)*`;

    navigator.clipboard.writeText(summaryText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-md animate-in fade-in duration-200">
      <div className="relative w-full max-w-lg bg-gradient-to-b from-[#131b2e] via-[#0d1322] to-[#070b13] border-2 border-purple-500/40 rounded-3xl shadow-2xl shadow-purple-500/20 flex flex-col overflow-hidden text-slate-100">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-[#0f172a]/90">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-gradient-to-tr from-purple-600 to-pink-500 text-white">
              <Award className="w-4 h-4" />
            </div>
            <span className="font-mono text-xs font-bold uppercase tracking-wider text-purple-300">
              Your Call Wrapped • Live Edition
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Card Body (Spotify Wrapped Aesthetic) */}
        <div className="p-6 space-y-5">
          {/* Hero Banner */}
          <div className="relative rounded-2xl bg-gradient-to-r from-purple-900/40 via-indigo-900/40 to-pink-900/30 border border-purple-500/30 p-5 overflow-hidden text-center space-y-2">
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-purple-500/20 border border-purple-500/40 text-purple-200 text-xs font-bold">
              <Sparkles className="w-3.5 h-3.5 text-amber-400" />
              <span>POST-CALL MEMORY RECAP</span>
            </div>
            <h3 className="text-xl font-black text-white tracking-tight">
              CALLWRAPPED #1
            </h3>
            <p className="text-xs text-slate-300">
              Total airtime: {formatDurationHuman(total_talk_seconds)} • {topicalEntries.length} topics explored
            </p>
          </div>

          {/* Cards Grid */}
          <div className="grid grid-cols-2 gap-3">
            {/* Monologue King */}
            <div className="p-3.5 rounded-xl bg-slate-900/80 border border-amber-500/30 space-y-1">
              <div className="flex items-center gap-1.5 text-amber-400 text-xs font-bold">
                <Crown className="w-4 h-4" />
                <span>Monologue King</span>
              </div>
              <p className="text-base font-bold text-white truncate" dir="auto">
                {longest_streak?.speaker_name || "N/A"}
              </p>
              <p className="text-[11px] font-mono text-amber-300 font-semibold">
                {formatDurationHuman(longest_streak?.streak_seconds || 0)} unbroken
              </p>
            </div>

            {/* Fact Check Score */}
            <div className="p-3.5 rounded-xl bg-slate-900/80 border border-emerald-500/30 space-y-1">
              <div className="flex items-center gap-1.5 text-emerald-400 text-xs font-bold">
                <ShieldCheck className="w-4 h-4" />
                <span>Truth Meter</span>
              </div>
              <p className="text-base font-bold text-white">
                {verifiedCount} Verified
              </p>
              <p className="text-[11px] font-mono text-emerald-300 font-semibold">
                {disputedCount} Disputed claims
              </p>
            </div>

            {/* Top Topic */}
            <div className="p-3.5 rounded-xl bg-slate-900/80 border border-cyan-500/30 space-y-1">
              <div className="flex items-center gap-1.5 text-cyan-400 text-xs font-bold">
                <PieChart className="w-4 h-4" />
                <span>Dominant Topic</span>
              </div>
              <p className="text-base font-bold text-white truncate">
                {topTopicName}
              </p>
              <p className="text-[11px] font-mono text-cyan-300 font-semibold">
                {topTopic ? `${topTopic[1]} mentions` : "Diverse"}
              </p>
            </div>

            {/* Call Vibe */}
            <div className="p-3.5 rounded-xl bg-slate-900/80 border border-pink-500/30 space-y-1">
              <div className="flex items-center gap-1.5 text-pink-400 text-xs font-bold">
                <Smile className="w-4 h-4" />
                <span>Call Vibe</span>
              </div>
              <p className="text-base font-bold text-white">
                {total_angry_episodes === 0 ? "Civilized 🕊️" : "Spicy 🌶️"}
              </p>
              <p className="text-[11px] font-mono text-pink-300 font-semibold">
                {total_angry_episodes === 0 ? "0 anger spikes" : `${total_angry_episodes} heated receipts`}
              </p>
            </div>
          </div>

          {/* The Silent Observer Award */}
          {isObserverEligible && silentObserver && (
            <div className="p-3 rounded-xl bg-slate-900/80 border border-indigo-500/30 flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <div className="p-1 rounded-lg bg-indigo-500/20 text-indigo-300 font-bold text-xs">🤫</div>
                <div>
                  <div className="text-[10px] uppercase font-bold text-indigo-300 tracking-wider">The Silent Observer</div>
                  <div className="font-bold text-white truncate max-w-[140px]" dir="auto">{silentObserver.speaker_name}</div>
                </div>
              </div>
              <div className="text-right font-mono text-indigo-300">
                <div className="font-bold text-xs">{formatDurationHuman(silentObserver.talk_seconds)}</div>
                <div className="text-[10px] text-slate-400">
                  ({total_talk_seconds > 0 ? ((silentObserver.talk_seconds / total_talk_seconds) * 100).toFixed(0) : 0}% airtime)
                </div>
              </div>
            </div>
          )}

          {/* Talk Time Breakdown Bar */}
          {speakerList.length > 0 && (
            <div className="p-3.5 rounded-xl bg-slate-900/80 border border-slate-800 space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-bold text-slate-300">Talk Time Share</span>
                <span className="text-[11px] text-slate-400 font-mono">
                  {speakerList.length} participant{speakerList.length === 1 ? "" : "s"}
                </span>
              </div>
              <div className="space-y-1.5">
                {speakerList.slice(0, 3).map((spk, idx) => {
                  const pct = total_talk_seconds > 0 ? (spk.talk_seconds / total_talk_seconds) * 100 : 0;
                  return (
                    <div key={idx} className="space-y-0.5 text-xs">
                      <div className="flex justify-between text-[11px]">
                        <span className="font-semibold text-slate-200" dir="auto">{spk.speaker_name}</span>
                        <span className="font-mono text-slate-400">{formatDurationHuman(spk.talk_seconds)} ({pct.toFixed(0)}%)</span>
                      </div>
                      <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-gradient-to-r from-purple-500 to-pink-500 rounded-full"
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

        {/* Footer Actions */}
        <div className="px-6 py-4 border-t border-slate-800 bg-[#0f172a] flex items-center justify-between gap-3">
          <button
            onClick={handleCopy}
            className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-gradient-to-r from-purple-600 via-pink-600 to-indigo-600 hover:opacity-90 text-white font-bold text-xs shadow-lg shadow-purple-600/25 transition-all cursor-pointer"
          >
            {copied ? <Check className="w-4 h-4 text-emerald-300" /> : <Copy className="w-4 h-4" />}
            <span>{copied ? "Copied Discord Markdown!" : "Copy Summary to Discord"}</span>
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold transition-colors"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
