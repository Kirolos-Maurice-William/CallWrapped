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

export interface SpeakerAnalytics {
  speaker_name: string;
  talk_seconds: number;
  longest_streak_seconds: number;
  angry_episodes: number;
  first_anger_quote?: string;
  anger_evidence?: string;
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

const TOPIC_COLORS = [
  "bg-cyan-500",
  "bg-purple-500",
  "bg-amber-500",
  "bg-emerald-500",
  "bg-rose-500",
  "bg-indigo-500",
  "bg-blue-500"
];

interface Props {
  analytics: AnalyticsState;
}

export function AnalyticsWidgets({ analytics }: Props) {
  const { topic_totals, speakers, total_talk_seconds, total_angry_episodes, longest_streak } = analytics;

  // Topic totals calculations
  const totalTopicCount = Object.values(topic_totals || {}).reduce((acc, c) => acc + c, 0);
  const topicEntries = Object.entries(topic_totals || {}).sort((a, b) => b[1] - a[1]);

  // Speaker entries
  const speakerEntries = Object.values(speakers || {}).sort((a, b) => b.talk_seconds - a.talk_seconds);
  const hasSpeakers = speakerEntries.length > 0;

  // Angry speakers
  const angrySpeakers = speakerEntries.filter((s) => s.angry_episodes > 0);

  return (
    <div id="analytics-widgets" className="rounded-2xl bg-slate-900/80 border border-slate-800 p-5 space-y-4">
      <div className="flex items-center justify-between border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-cyan-400" />
          <h3 className="text-sm font-bold text-white tracking-wide uppercase">
            Call Analytics & Real-Time Intelligence
          </h3>
        </div>
        <span className="text-[11px] font-mono text-slate-400">
          Live Aggregations from /api/analytics
        </span>
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

            {totalTopicCount > 0 ? (
              <div className="space-y-2.5">
                {topicEntries.map(([topic, count], idx) => {
                  const pct = (count / totalTopicCount) * 100;
                  const color = TOPIC_COLORS[idx % TOPIC_COLORS.length];
                  return (
                    <div key={topic} className="space-y-1">
                      <div className="flex items-center justify-between text-xs font-medium">
                        <span className="text-slate-300 capitalize">{topic}</span>
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
          {totalTopicCount > 0 && (
            <div className="mt-3 pt-2 border-t border-slate-800/60 text-[10px] font-mono text-slate-500 text-right">
              Total mentions: {totalTopicCount}
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
                  {total_talk_seconds.toFixed(1)}s total
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
                          {s.talk_seconds.toFixed(1)}s ({pct.toFixed(1)}%)
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
              <div className="space-y-3 max-h-40 overflow-y-auto pr-1">
                {angrySpeakers.map((s, idx) => {
                  const quote = s.anger_evidence || s.first_anger_quote;
                  return (
                    <div key={s.speaker_name || idx} className="p-2.5 rounded-lg bg-rose-950/20 border border-rose-500/30 space-y-1">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-bold text-white" dir="auto">
                          {s.speaker_name}
                        </span>
                        <span className="px-1.5 py-0.5 rounded bg-rose-900/60 text-rose-300 font-mono font-bold text-[10px]">
                          {s.angry_episodes} {s.angry_episodes === 1 ? "episode" : "episodes"}
                        </span>
                      </div>
                      {quote && (
                        <div
                          className="text-[11px] text-amber-200/90 italic bg-slate-950/60 border border-slate-800 rounded px-2 py-1 leading-snug"
                          dir="auto"
                        >
                          Receipt: "{quote}"
                        </div>
                      )}
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

        {/* WIDGET 4: STREAK RECORD CARD */}
        <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800/80 flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-2 mb-3">
              <Award className="w-4 h-4 text-amber-400" />
              <h4 className="text-xs font-bold text-slate-200 tracking-wider uppercase">
                Longest Streak Record
              </h4>
            </div>

            {longest_streak && longest_streak.speaker_name && longest_streak.streak_seconds > 0 ? (
              <div className="p-4 rounded-xl bg-gradient-to-br from-amber-950/30 to-slate-900 border border-amber-500/30 text-center space-y-2">
                <div className="inline-flex p-2 rounded-xl bg-amber-500/20 text-amber-400 border border-amber-500/40">
                  <Award className="w-6 h-6" />
                </div>
                <div>
                  <div className="text-sm font-bold text-white flex items-center justify-center gap-1.5" dir="auto">
                    <span>👑</span>
                    <span>{longest_streak.speaker_name}</span>
                  </div>
                  <div className="text-2xl font-extrabold font-mono text-amber-300 mt-1">
                    {formatStreakMMSS(longest_streak.streak_seconds)}
                  </div>
                  <div className="text-[10px] font-mono text-slate-400 mt-0.5">
                    ({longest_streak.streak_seconds.toFixed(1)}s uninterrupted)
                  </div>
                </div>
              </div>
            ) : (
              <div className="py-6 text-center text-xs text-slate-500 italic">
                waiting for call data…
              </div>
            )}
          </div>
          {longest_streak && longest_streak.streak_seconds > 0 && (
            <div className="mt-3 pt-2 border-t border-slate-800/60 text-[10px] font-mono text-amber-400/80 text-right">
              Session Record
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
