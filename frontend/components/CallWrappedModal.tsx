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

  const spicySpeakers = speakerList.filter(s => (s.vulgarity_count || 0) > 0).sort((a, b) => (b.vulgarity_count || 0) - (a.vulgarity_count || 0));
  const topSpicy = spicySpeakers[0];
  const isSpicyEligible = Boolean(
    speakerList.length >= 2 && topSpicy && (spicySpeakers.length < 2 || (topSpicy.vulgarity_count || 0) > (spicySpeakers[1].vulgarity_count || 0))
  );

  const diplomatCandidates = speakerList.filter(
    s => (s.vulgarity_count || 0) === 0 && s.angry_episodes === 0 && s.talk_seconds >= 15.0
  ).sort((a, b) => b.talk_seconds - a.talk_seconds);
  const topDiplomat = diplomatCandidates[0];
  const isDiplomatEligible = Boolean(
    speakerList.length >= 2 && topDiplomat && (diplomatCandidates.length < 2 || (topDiplomat.talk_seconds - diplomatCandidates[1].talk_seconds >= 1.0))
  );

  const banterSpeakers = speakerList.filter(s => (s.banter_count || 0) > 0).sort((a, b) => (b.banter_count || 0) - (a.banter_count || 0));
  const topBanter = banterSpeakers[0];
  const isBanterEligible = Boolean(
    speakerList.length >= 2 && topBanter && (banterSpeakers.length < 2 || (topBanter.banter_count || 0) > (banterSpeakers[1].banter_count || 0))
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
    const spicyLine = isSpicyEligible && topSpicy
      ? `🌶️ **The Most Unfiltered:** ${topSpicy.speaker_name} (${topSpicy.vulgarity_count} raw tokens)\n`
      : "";
    const diplomatLine = isDiplomatEligible && topDiplomat
      ? `🕊️ **The Diplomat:** ${topDiplomat.speaker_name} (${formatDurationHuman(topDiplomat.talk_seconds)} peaceful)\n`
      : "";
    const roastLine = isBanterEligible && topBanter
      ? `🎭 **The Roast Master:** ${topBanter.speaker_name} (${topBanter.banter_count} mutual roasts)\n`
      : "";
    const vibeText = total_angry_episodes === 0
      ? ((analytics.total_banter_count || 0) > 0 ? `Friendly banter (${analytics.total_banter_count} roasts, 0 anger spikes)` : "Civilized discussion (0 anger spikes)")
      : `${total_angry_episodes} heated episodes`;
    const summaryText = `🎙️ **CALLWRAPPED SESSION SUMMARY**\n` +
      `👑 **Monologue King:** ${longest_streak?.speaker_name || "N/A"} (${formatDurationHuman(longest_streak?.streak_seconds || 0)})\n` +
      observerLine +
      spicyLine +
      diplomatLine +
      roastLine +
      `🎯 **Ground Truth:** ${verifiedCount} verified, ${disputedCount} refuted\n` +
      `📊 **Top Topic:** ${topTopicName}\n` +
      `🎭 **Call Vibe:** ${vibeText}\n` +
      `⚡ *Arbitrated live by CallWrapped AI Referee (AssemblyAI + Groq)*`;

    navigator.clipboard.writeText(summaryText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-200">
      <div className="relative w-full max-w-lg bg-[#2b2d31] border border-[#383a40] rounded-3xl shadow-2xl shadow-black/50 flex flex-col overflow-hidden text-[#F2F3F5]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[#383a40] bg-[#1e1f22]">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-[#5865F2]/20 text-[#5865F2]">
              <Award className="w-4 h-4" />
            </div>
            <span className="font-mono text-xs font-bold uppercase tracking-wider text-[#DBDEE1]">
              Your Call Wrapped • Live Edition
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg bg-[#313338] hover:bg-[#383a40] text-[#949BA4] hover:text-white transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Card Body (Spotify Wrapped Aesthetic) */}
        <div className="p-6 space-y-4">
          {/* Hero Banner */}
          <div className="relative rounded-2xl bg-[#1e1f22] border border-[#383a40] p-5 overflow-hidden text-center space-y-2">
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#5865F2]/20 border border-[#5865F2]/40 text-[#DBDEE1] text-xs font-bold">
              <Sparkles className="w-3.5 h-3.5 text-[#F0B232]" />
              <span>POST-CALL MEMORY RECAP</span>
            </div>
            <h3 className="text-xl font-black text-white tracking-tight">
              CALLWRAPPED #1
            </h3>
            <p className="text-xs text-[#949BA4]">
              Total airtime: {formatDurationHuman(total_talk_seconds)} • {topicalEntries.length} topics explored
            </p>
          </div>

          {/* Cards Grid */}
          <div className="grid grid-cols-2 gap-3">
            {/* Monologue King */}
            <div className="p-3.5 rounded-xl bg-[#1e1f22] border border-[#F0B232]/30 space-y-1">
              <div className="flex items-center gap-1.5 text-[#F0B232] text-xs font-bold">
                <Crown className="w-4 h-4" />
                <span>Monologue King</span>
              </div>
              <p className="text-base font-bold text-white truncate" dir="auto">
                {longest_streak?.speaker_name || "N/A"}
              </p>
              <p className="text-[11px] font-mono text-[#F0B232] font-semibold">
                {formatDurationHuman(longest_streak?.streak_seconds || 0)} unbroken
              </p>
            </div>

            {/* Fact Check Score */}
            <div className="p-3.5 rounded-xl bg-[#1e1f22] border border-[#23A55A]/30 space-y-1">
              <div className="flex items-center gap-1.5 text-[#23A55A] text-xs font-bold">
                <ShieldCheck className="w-4 h-4" />
                <span>Truth Meter</span>
              </div>
              <p className="text-base font-bold text-white">
                {verifiedCount} Verified
              </p>
              <p className="text-[11px] font-mono text-[#23A55A] font-semibold">
                {disputedCount} Disputed claims
              </p>
            </div>

            {/* Top Topic */}
            <div className="p-3.5 rounded-xl bg-[#1e1f22] border border-cyan-500/30 space-y-1">
              <div className="flex items-center gap-1.5 text-cyan-400 text-xs font-bold">
                <PieChart className="w-4 h-4" />
                <span>Dominant Topic</span>
              </div>
              <p className="text-base font-bold text-white truncate">
                {topTopicName}
              </p>
              <p className="text-[11px] font-mono text-cyan-400 font-semibold">
                {topTopic ? `${topTopic[1]} mentions` : "Diverse"}
              </p>
            </div>

            {/* Call Vibe */}
            <div className="p-3.5 rounded-xl bg-[#1e1f22] border border-pink-500/30 space-y-1">
              <div className="flex items-center gap-1.5 text-pink-400 text-xs font-bold">
                <Smile className="w-4 h-4" />
                <span>Call Vibe</span>
              </div>
              <p className="text-base font-bold text-white">
                {total_angry_episodes === 0 ? ((analytics.total_banter_count || 0) > 0 ? "Friendly Banter 😂" : "Civilized 🕊️") : "Spicy 🌶️"}
              </p>
              <p className="text-[11px] font-mono text-pink-300 font-semibold">
                {total_angry_episodes === 0 ? ((analytics.total_banter_count || 0) > 0 ? `${analytics.total_banter_count} mutual roasts (0 anger)` : "0 anger spikes") : `${total_angry_episodes} heated receipts`}
              </p>
            </div>
          </div>

          {/* The Silent Observer Award */}
          {isObserverEligible && silentObserver && (
            <div className="p-3 rounded-xl bg-[#1e1f22] border border-[#5865F2]/30 flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <div className="p-1 rounded-lg bg-[#5865F2]/20 text-[#5865F2] font-bold text-xs">🤫</div>
                <div>
                  <div className="text-[10px] uppercase font-bold text-[#5865F2] tracking-wider">The Silent Observer</div>
                  <div className="font-bold text-white truncate max-w-[140px]" dir="auto">{silentObserver.speaker_name}</div>
                </div>
              </div>
              <div className="text-right font-mono text-[#5865F2]">
                <div className="font-bold text-xs">{formatDurationHuman(silentObserver.talk_seconds)}</div>
                <div className="text-[10px] text-[#949BA4]">
                  ({total_talk_seconds > 0 ? ((silentObserver.talk_seconds / total_talk_seconds) * 100).toFixed(0) : 0}% airtime)
                </div>
              </div>
            </div>
          )}

          {/* The Most Unfiltered Award */}
          {isSpicyEligible && topSpicy && (
            <div className="p-3 rounded-xl bg-[#1e1f22] border border-[#F23F43]/30 flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <div className="p-1 rounded-lg bg-[#F23F43]/20 text-[#F23F43] font-bold text-xs">🌶️</div>
                <div>
                  <div className="text-[10px] uppercase font-bold text-[#F23F43] tracking-wider">The Most Unfiltered</div>
                  <div className="font-bold text-white truncate max-w-[140px]" dir="auto">{topSpicy.speaker_name}</div>
                </div>
              </div>
              <div className="text-right font-mono text-[#F23F43]">
                <div className="font-bold text-xs">{topSpicy.vulgarity_count} raw tokens</div>
                <div className="text-[10px] text-[#949BA4]">uncensored banter</div>
              </div>
            </div>
          )}

          {/* The Diplomat Award */}
          {isDiplomatEligible && topDiplomat && (
            <div className="p-3 rounded-xl bg-[#1e1f22] border border-[#23A55A]/30 flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <div className="p-1 rounded-lg bg-[#23A55A]/20 text-[#23A55A] font-bold text-xs">🕊️</div>
                <div>
                  <div className="text-[10px] uppercase font-bold text-[#23A55A] tracking-wider">The Diplomat</div>
                  <div className="font-bold text-white truncate max-w-[140px]" dir="auto">{topDiplomat.speaker_name}</div>
                </div>
              </div>
              <div className="text-right font-mono text-[#23A55A]">
                <div className="font-bold text-xs">{formatDurationHuman(topDiplomat.talk_seconds)}</div>
                <div className="text-[10px] text-[#949BA4]">100% peaceful</div>
              </div>
            </div>
          )}

          {/* The Roast Master Award */}
          {isBanterEligible && topBanter && (
            <div className="p-3 rounded-xl bg-[#1e1f22] border border-purple-500/30 flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <div className="p-1 rounded-lg bg-purple-500/20 text-purple-400 font-bold text-xs">🎭</div>
                <div>
                  <div className="text-[10px] uppercase font-bold text-purple-400 tracking-wider">The Roast Master</div>
                  <div className="font-bold text-white truncate max-w-[140px]" dir="auto">{topBanter.speaker_name}</div>
                </div>
              </div>
              <div className="text-right font-mono text-purple-400">
                <div className="font-bold text-xs">{topBanter.banter_count} {topBanter.banter_count === 1 ? "roast turn" : "roast turns"}</div>
                <div className="text-[10px] text-[#949BA4]">friendly teasing</div>
              </div>
            </div>
          )}

          {/* Talk Time Breakdown Bar */}
          {speakerList.length > 0 && (
            <div className="p-3.5 rounded-xl bg-[#1e1f22] border border-[#383a40] space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-bold text-[#DBDEE1]">Talk Time Share</span>
                <span className="text-[11px] text-[#949BA4] font-mono">
                  {speakerList.length} participant{speakerList.length === 1 ? "" : "s"}
                </span>
              </div>
              <div className="space-y-1.5">
                {speakerList.slice(0, 3).map((spk, idx) => {
                  const pct = total_talk_seconds > 0 ? (spk.talk_seconds / total_talk_seconds) * 100 : 0;
                  return (
                    <div key={idx} className="space-y-0.5 text-xs">
                      <div className="flex justify-between text-[11px]">
                        <span className="font-semibold text-[#F2F3F5]" dir="auto">{spk.speaker_name}</span>
                        <span className="font-mono text-[#949BA4]">{formatDurationHuman(spk.talk_seconds)} ({pct.toFixed(0)}%)</span>
                      </div>
                      <div className="h-1.5 w-full bg-[#313338] rounded-full overflow-hidden">
                        <div
                          className="h-full bg-gradient-to-r from-[#5865F2] to-pink-500 rounded-full"
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
        <div className="px-6 py-4 border-t border-[#383a40] bg-[#1e1f22] flex items-center justify-between gap-3">
          <button
            onClick={handleCopy}
            className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-[#5865F2] hover:bg-[#4752C4] text-white font-bold text-xs shadow-lg shadow-[#5865F2]/25 transition-all cursor-pointer"
          >
            {copied ? <Check className="w-4 h-4 text-[#23A55A]" /> : <Copy className="w-4 h-4" />}
            <span>{copied ? "Copied Discord Markdown!" : "Copy Summary to Discord"}</span>
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2.5 rounded-xl bg-[#313338] hover:bg-[#383a40] text-[#DBDEE1] text-xs font-semibold transition-colors"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
