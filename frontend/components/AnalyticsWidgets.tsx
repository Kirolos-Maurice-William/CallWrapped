"use client";

import React from "react";
import {
  PieChart,
  Clock,
  Flame,
  Award,
  AlertTriangle,
  Smile,
  BarChart3
} from "lucide-react";

export interface AngerEpisodeItem {
  episode_number?: number;
  quote: string;
  timestamp?: number;
  anger?: string;
  was_loud?: boolean;
  peak_z?: number;
  context?: string;
}

export interface SpeakerAnalytics {
  speaker_name: string;
  talk_seconds: number;
  longest_streak_seconds: number;
  angry_episodes: number;
  first_anger_quote?: string;
  anger_evidence?: string;
  anger_episodes_history?: AngerEpisodeItem[];
}

export interface AnalyticsState {
  topic_totals: Record<string, number>;
  speakers: Record<string, SpeakerAnalytics>;
  total_talk_seconds: number;
  total_angry_episodes: number;
  longest_streak: {
    speaker_name: string | null;
    streak_seconds: number;
  };
}

export function formatStreakMMSS(seconds: number): string {
  const totalSec = Math.round(seconds);
  const mins = Math.floor(totalSec / 60);
  const secs = totalSec % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

export function formatDurationHuman(seconds: number): string {
  if (!seconds || seconds <= 0 || isNaN(seconds)) return "0s";
  const totalSec = Math.round(seconds);
  if (totalSec < 60) return `${totalSec}s`;
  const mins = Math.floor(totalSec / 60);
  const secs = totalSec % 60;
  if (mins < 60) {
    return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`;
  }
  const hours = Math.floor(mins / 60);
  const remMins = mins % 60;
  return remMins > 0 ? `${hours}h ${remMins}m` : `${hours}h`;
}

const TOPIC_DISPLAY_NAMES: Record<string, string> = {
  food: "أكل",
  travel: "سفر",
  study_work: "دراسة وشغل",
  health: "صحة",
  cars: "عربيات",
  money: "فلوس",
  football: "كورة",
  politics: "سياسة",
  music: "مزيكا",
  movies: "أفلام",
  gaming: "ألعاب",
  tech: "تكنولوجيا",
  personal: "شخصي",
  other: "أخرى",
};

const TOPIC_COLORS = [
  "bg-cyan-500",
  "bg-purple-500",
  "bg-amber-500",
  "bg-emerald-500",
  "bg-rose-500",
  "bg-indigo-500",
  "bg-blue-500",
  "bg-teal-500",
  "bg-orange-500",
  "bg-lime-500",
  "bg-pink-500",
  "bg-violet-500",
  "bg-yellow-500"
];

interface Props {
  analytics: AnalyticsState;
  onOpenRecap?: () => void;
}

export function AnalyticsWidgets({ analytics, onOpenRecap }: Props) {
  const { topic_totals, speakers, total_talk_seconds, total_angry_episodes, longest_streak } = analytics;

  // Topic totals calculations: exclude null_topic from pie, compute coverage
  const topicalEntries = Object.entries(topic_totals || {}).filter(
    ([t]) => t !== "null_topic" && t !== "null" && t !== "بدون موضوع" && t !== "none"
  );
  const nullCount =
    (topic_totals?.["null_topic"] || 0) +
    (topic_totals?.["null"] || 0) +
    (topic_totals?.["بدون موضوع"] || 0);
  const totalTopicalCount = topicalEntries.reduce((acc, [, c]) => acc + c, 0);
  const totalAllTopics = totalTopicalCount + nullCount;
  const topicalCoveragePct = totalAllTopics > 0 ? (totalTopicalCount / totalAllTopics) * 100 : 0;
  const topicEntries = topicalEntries.sort((a, b) => b[1] - a[1]);

  // Speaker entries
  const speakerEntries = Object.values(speakers || {}).sort((a, b) => b.talk_seconds - a.talk_seconds);
  const hasSpeakers = speakerEntries.length > 0;

  // Angry speakers
  const angrySpeakers = speakerEntries.filter((s) => s.angry_episodes > 0);

  return (
    <div id="analytics-widgets" className="rounded-2xl bg-slate-900/80 border border-slate-800 p-5 space-y-4 shadow-xl">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-cyan-400" />
          <h3 className="text-sm font-bold text-white tracking-wide uppercase">
            Call Analytics & Real-Time Intelligence
          </h3>
        </div>
        <div className="flex items-center gap-2 sm:gap-3">
          {onOpenRecap && (
            <button
              onClick={onOpenRecap}
              className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-600 hover:opacity-90 text-white text-[11px] font-bold shadow-md shadow-indigo-600/25 transition-all cursor-pointer"
              title="Open Spotify-style CallWrapped session recap card"
            >
              <Award className="w-3.5 h-3.5" />
              <span>CallWrapped Recap Card</span>
            </button>
          )}
          <span className="text-[11px] font-mono text-slate-400 hidden sm:inline">
            Live Aggregations from /api/analytics
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* WIDGET 1: TOPIC BREAKDOWN */}
        <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800/80 flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-2 mb-3">
              <PieChart className="w-4 h-4 text-indigo-400" />
              <h4 className="text-xs font-bold text-slate-200 tracking-wider uppercase">
                Topic Breakdown
              </h4>
            </div>

            {totalTopicalCount > 0 ? (
              <div className="space-y-2.5">
                {topicEntries.map(([topic, count], idx) => {
                  const pct = (count / totalTopicalCount) * 100;
                  const color = TOPIC_COLORS[idx % TOPIC_COLORS.length];
                  return (
                    <div key={topic} className="space-y-1">
                      <div className="flex items-center justify-between text-xs font-medium">
                        <span className="text-slate-300 capitalize">
                          {TOPIC_DISPLAY_NAMES[topic.toLowerCase()] ? `${topic} (${TOPIC_DISPLAY_NAMES[topic.toLowerCase()]})` : topic}
                        </span>
                        <span className="font-mono text-slate-400">
                          {count} ({pct.toFixed(1)}%)
                        </span>
                      </div>
                      <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                        <div
                          className={`h-full ${color} rounded-full transition-all duration-500`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="py-6 text-center text-xs text-slate-500 italic">
                waiting for call data…
              </div>
            )}
          </div>
          {totalAllTopics > 0 && (
            <div className="mt-3 pt-2 border-t border-slate-800/60 text-[10px] font-mono text-slate-400 flex justify-between">
              <span>Topical Coverage: {topicalCoveragePct.toFixed(1)}%</span>
              <span className="text-slate-500">Excl. {nullCount} null</span>
            </div>
          )}
        </div>

        {/* WIDGET 2: TALK TIME & SHARE */}
        <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800/80 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Clock className="w-4 h-4 text-cyan-400" />
                <h4 className="text-xs font-bold text-slate-200 tracking-wider uppercase">
                  Talk Time Share
                </h4>
              </div>
              {total_talk_seconds > 0 && (
                <span className="text-[10px] font-mono font-bold text-cyan-400">
                  {formatDurationHuman(total_talk_seconds)} total
                </span>
              )}
            </div>

            {hasSpeakers && total_talk_seconds > 0 ? (
              <div className="space-y-2.5">
                {speakerEntries.map((s, idx) => {
                  const pct = total_talk_seconds > 0 ? (s.talk_seconds / total_talk_seconds) * 100 : 0;
                  return (
                    <div key={s.speaker_name || idx} className="space-y-1">
                      <div className="flex items-center justify-between text-xs font-medium">
                        <span className="text-slate-200 font-semibold" dir="auto">
                          {s.speaker_name}
                        </span>
                        <span className="font-mono text-cyan-300">
                          {formatDurationHuman(s.talk_seconds)} ({pct.toFixed(1)}%)
                        </span>
                      </div>
                      <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-cyan-500 rounded-full transition-all duration-500"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="py-6 text-center text-xs text-slate-500 italic">
                waiting for call data…
              </div>
            )}
          </div>
          {hasSpeakers && (
            <div className="mt-3 pt-2 border-t border-slate-800/60 text-[10px] font-mono text-slate-500 text-right">
              {speakerEntries.length} speaker{speakerEntries.length === 1 ? "" : "s"} tracked
            </div>
          )}
        </div>

        {/* WIDGET 3: ANGER LEADERBOARD & RECEIPTS */}
        <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800/80 flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-2 mb-3">
              <Flame className="w-4 h-4 text-rose-400" />
              <h4 className="text-xs font-bold text-slate-200 tracking-wider uppercase">
                Anger Leaderboard
              </h4>
            </div>

            {!hasSpeakers ? (
              <div className="py-6 text-center text-xs text-slate-500 italic">
                waiting for call data…
              </div>
            ) : total_angry_episodes === 0 || angrySpeakers.length === 0 ? (
              <div className="py-5 px-3 rounded-lg bg-emerald-950/20 border border-emerald-500/20 text-center space-y-1">
                <Smile className="w-5 h-5 text-emerald-400 mx-auto" />
                <p className="text-xs text-emerald-300 font-medium">
                  Nobody got angry this call... suspicious.
                </p>
              </div>
            ) : (
              <div className="space-y-3 max-h-48 overflow-y-auto pr-1">
                {angrySpeakers.map((s, idx) => {
                  const fallbackQuote = (s.anger_evidence || s.first_anger_quote || "").trim();
                  // Filter out empty or placeholder quotes
                  const validHistory = (s.anger_episodes_history || []).filter(
                    (ep) => ep.quote && ep.quote.trim() !== "" && ep.quote !== "(no verbal evidence captured)"
                  );
                  const history = validHistory.length > 0
                    ? validHistory
                    : (fallbackQuote && fallbackQuote !== "(no verbal evidence captured)"
                        ? [{ quote: fallbackQuote, episode_number: s.angry_episodes }]
                        : []);

                  if (history.length === 0) return null;

                  return (
                    <div key={s.speaker_name || idx} className="p-2.5 rounded-lg bg-rose-950/20 border border-rose-500/30 space-y-1.5">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-bold text-white" dir="auto">
                          {s.speaker_name}
                        </span>
                        <span className="px-1.5 py-0.5 rounded bg-rose-900/60 text-rose-300 font-mono font-bold text-[10px]">
                          {s.angry_episodes} {s.angry_episodes === 1 ? "episode" : "episodes"}
                        </span>
                      </div>
                      {history.map((ep, eIdx) => {
                        const isLoud = Boolean(ep.was_loud || (ep.peak_z && ep.peak_z >= 2.5));
                        const isArg = ep.context && (ep.context.includes("argument") || ep.context.includes("dispute"));
                        const clampedZ = ep.peak_z ? Math.min(10.0, ep.peak_z).toFixed(1) : "2.8";
                        return (
                          <div
                            key={eIdx}
                            className="text-[11px] text-amber-200/90 bg-slate-950/70 border border-slate-800 rounded px-2 py-1 leading-snug space-y-0.5"
                          >
                            <div className="flex items-center justify-between text-[9px] font-mono text-slate-400">
                              <span className="text-amber-400 font-semibold">
                                {ep.episode_number ? `Ep #${ep.episode_number}` : "Receipt"}
                              </span>
                              {isLoud ? (
                                <span className="text-rose-400 font-bold flex items-center gap-0.5">
                                  <span>🔊</span>
                                  <span>+{clampedZ}σ spike</span>
                                </span>
                              ) : isArg ? (
                                <span className="text-amber-400 flex items-center gap-0.5">
                                  <span>🎙️</span>
                                  <span>heated exchange</span>
                                </span>
                              ) : (
                                <span className="text-slate-500">vocal friction</span>
                              )}
                            </div>
                            <div className="italic" dir="auto">
                              "{ep.quote}"
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
          {total_angry_episodes > 0 && (
            <div className="mt-3 pt-2 border-t border-slate-800/60 text-[10px] font-mono text-rose-400 text-right">
              {total_angry_episodes} total episode{total_angry_episodes === 1 ? "" : "s"}
            </div>
          )}
        </div>

        {/* WIDGET 4: CALL BADGES & HIGHLIGHTS */}
        <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800/80 flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-2 mb-3">
              <Award className="w-4 h-4 text-amber-400" />
              <h4 className="text-xs font-bold text-slate-200 tracking-wider uppercase">
                Call Badges & Records
              </h4>
            </div>

            {longest_streak && longest_streak.speaker_name && longest_streak.streak_seconds > 0 ? (
              <div className="space-y-2.5">
                <div className="p-3 rounded-xl bg-gradient-to-br from-amber-950/30 to-slate-900 border border-amber-500/30 text-center space-y-1.5">
                  <div className="inline-flex p-1.5 rounded-xl bg-amber-500/20 text-amber-400 border border-amber-500/40">
                    <Award className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="text-[10px] uppercase font-bold text-amber-400 tracking-wider">
                      The Monologue King
                    </div>
                    <div className="text-sm font-bold text-white flex items-center justify-center gap-1.5" dir="auto">
                      <span>👑</span>
                      <span>{longest_streak.speaker_name}</span>
                    </div>
                    <div className="text-xl font-extrabold font-mono text-amber-300 mt-0.5">
                      {formatStreakMMSS(longest_streak.streak_seconds)}
                    </div>
                    <div className="text-[10px] font-mono text-slate-400">
                      ({formatDurationHuman(longest_streak.streak_seconds)} uninterrupted)
                    </div>
                  </div>
                </div>

                {/* The Silent Observer (quietest in call, minimum 2 speakers) */}
                {hasSpeakers && speakerEntries.length >= 2 && (() => {
                  const quietest = speakerEntries[speakerEntries.length - 1];
                  const topSpeaker = speakerEntries[0];
                  if (topSpeaker.talk_seconds - quietest.talk_seconds >= 1.0) {
                    const qPct = total_talk_seconds > 0 ? (quietest.talk_seconds / total_talk_seconds) * 100 : 0;
                    return (
                      <div className="p-2.5 rounded-xl bg-gradient-to-br from-indigo-950/30 to-slate-900 border border-indigo-500/30 flex items-center justify-between text-xs">
                        <div className="flex items-center gap-2">
                          <span className="text-base">🤫</span>
                          <div>
                            <div className="text-[9px] uppercase font-bold text-indigo-300 tracking-wider">
                              The Silent Observer
                            </div>
                            <div className="font-bold text-white truncate max-w-[110px]" dir="auto">
                              {quietest.speaker_name}
                            </div>
                          </div>
                        </div>
                        <div className="text-right font-mono text-indigo-300">
                          <div className="font-bold text-xs">{formatDurationHuman(quietest.talk_seconds)}</div>
                          <div className="text-[9px] text-slate-400">({qPct.toFixed(1)}% airtime)</div>
                        </div>
                      </div>
                    );
                  }
                  return null;
                })()}
              </div>
            ) : (
              <div className="py-6 text-center text-xs text-slate-500 italic">
                waiting for call data…
              </div>
            )}
          </div>
          {longest_streak && longest_streak.streak_seconds > 0 && (
            <div className="mt-3 pt-2 border-t border-slate-800/60 text-[10px] font-mono text-amber-400/80 text-right">
              Session Highlights
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
