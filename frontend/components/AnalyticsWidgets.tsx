"use client";

import React, { useState } from "react";
import {
  PieChart,
  Clock,
  Flame,
  Award,
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
  audio_clip?: string;
}

export interface SpeakerAnalytics {
  speaker_name: string;
  talk_seconds: number;
  longest_streak_seconds: number;
  angry_episodes: number;
  first_anger_quote?: string;
  anger_evidence?: string;
  anger_episodes_history?: AngerEpisodeItem[];
  vulgarity_count?: number;
  vulgarity_terms?: string[];
  banter_count?: number;
  banter_terms?: string[];
}

export interface AnalyticsState {
  topic_totals: Record<string, number>;
  speakers: Record<string, SpeakerAnalytics>;
  total_talk_seconds: number;
  total_angry_episodes: number;
  total_vulgarity_count?: number;
  total_banter_count?: number;
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

export const TOPIC_DISPLAY_NAMES: Record<string, string> = {
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

export const TOPIC_COLORS = [
  "bg-cyan-500",
  "bg-purple-500",
  "bg-amber-500",
  "bg-[#23A55A]",
  "bg-[#F23F43]",
  "bg-[#5865F2]",
  "bg-blue-500",
  "bg-teal-500",
  "bg-orange-500",
  "bg-lime-500",
  "bg-pink-500",
  "bg-violet-500",
  "bg-[#F0B232]"
];

interface Props {
  analytics: AnalyticsState;
  onOpenRecap?: () => void;
}

export function AnalyticsWidgets({ analytics, onOpenRecap }: Props) {
  const { topic_totals, speakers, total_talk_seconds, total_angry_episodes, longest_streak } = analytics;
  const [playingClip, setPlayingClip] = useState<string | null>(null);

  const getAudioUrl = (clip: string) => {
    if (typeof window !== "undefined") {
      const hostname = window.location.hostname || "localhost";
      const port = window.location.port === "3000" ? "8000" : (window.location.port || "8000");
      return `${window.location.protocol}//${hostname}:${port}/api/audio-evidence/${clip}`;
    }
    return `/api/audio-evidence/${clip}`;
  };

  const handlePlayAudio = (clip: string) => {
    try {
      const url = getAudioUrl(clip);
      const audio = new Audio(url);
      setPlayingClip(clip);
      audio.onended = () => setPlayingClip(null);
      audio.onerror = (e) => {
        console.error("Audio playback error for", url, e);
        setPlayingClip(null);
      };
      audio.play().catch(e => {
        console.error("Audio play promise error:", e);
        setPlayingClip(null);
      });
    } catch (err) {
      console.error("Audio error:", err);
      setPlayingClip(null);
    }
  };

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
    <div id="analytics-widgets" className="rounded-2xl bg-[#2b2d31] border border-[#383a40] p-5 space-y-4 shadow-xl">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#383a40] pb-3">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-[#5865F2]" />
          <h3 className="text-sm font-bold text-[#F2F3F5] tracking-wide uppercase">
            Call Analytics & Real-Time Intelligence
          </h3>
        </div>
        <div className="flex items-center gap-2 sm:gap-3">
          {onOpenRecap && (
            <button
              onClick={onOpenRecap}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#5865F2] hover:bg-[#4752C4] text-white text-[11px] font-bold shadow-md shadow-[#5865F2]/25 transition-all cursor-pointer"
              title="Open Spotify-style CallWrapped session recap card"
            >
              <Award className="w-3.5 h-3.5" />
              <span>CallWrapped Recap Card</span>
            </button>
          )}
          <span className="text-[11px] font-mono text-[#949BA4] hidden sm:inline">
            Live Aggregations from /api/analytics
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* WIDGET 1: TOPIC BREAKDOWN */}
        <div className="p-4 rounded-xl bg-[#1e1f22] border border-[#383a40] flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-2 mb-3">
              <PieChart className="w-4 h-4 text-[#5865F2]" />
              <h4 className="text-xs font-bold text-[#DBDEE1] tracking-wider uppercase">
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
                        <span className="text-[#DBDEE1] capitalize">
                          {TOPIC_DISPLAY_NAMES[topic.toLowerCase()] ? `${topic} (${TOPIC_DISPLAY_NAMES[topic.toLowerCase()]})` : topic}
                        </span>
                        <span className="font-mono text-[#949BA4]">
                          {count} ({pct.toFixed(1)}%)
                        </span>
                      </div>
                      <div className="w-full bg-[#313338] h-2 rounded-full overflow-hidden">
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
              <div className="py-6 text-center text-xs text-[#949BA4] italic">
                waiting for call data…
              </div>
            )}
          </div>
          {totalAllTopics > 0 && (
            <div className="mt-3 pt-2 border-t border-[#383a40] text-[10px] font-mono text-[#949BA4] flex justify-between">
              <span>Topical Coverage: {topicalCoveragePct.toFixed(1)}%</span>
              <span className="text-[#949BA4]">Excl. {nullCount} null</span>
            </div>
          )}
        </div>

        {/* WIDGET 2: TALK TIME & SHARE */}
        <div className="p-4 rounded-xl bg-[#1e1f22] border border-[#383a40] flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Clock className="w-4 h-4 text-cyan-400" />
                <h4 className="text-xs font-bold text-[#DBDEE1] tracking-wider uppercase">
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
                        <span className="text-[#F2F3F5] font-semibold" dir="auto">
                          {s.speaker_name}
                        </span>
                        <span className="font-mono text-cyan-400">
                          {formatDurationHuman(s.talk_seconds)} ({pct.toFixed(1)}%)
                        </span>
                      </div>
                      <div className="w-full bg-[#313338] h-2 rounded-full overflow-hidden">
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
              <div className="py-6 text-center text-xs text-[#949BA4] italic">
                waiting for call data…
              </div>
            )}
          </div>
          {hasSpeakers && (
            <div className="mt-3 pt-2 border-t border-[#383a40] text-[10px] font-mono text-[#949BA4] text-right">
              {speakerEntries.length} speaker{speakerEntries.length === 1 ? "" : "s"} tracked
            </div>
          )}
        </div>

        {/* WIDGET 3: ANGER LEADERBOARD & RECEIPTS */}
        <div className="p-4 rounded-xl bg-[#1e1f22] border border-[#383a40] flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-2 mb-3">
              <Flame className="w-4 h-4 text-[#F23F43]" />
              <h4 className="text-xs font-bold text-[#DBDEE1] tracking-wider uppercase">
                Anger Leaderboard
              </h4>
            </div>

            {!hasSpeakers ? (
              <div className="py-6 text-center text-xs text-[#949BA4] italic">
                waiting for call data…
              </div>
            ) : total_angry_episodes === 0 || angrySpeakers.length === 0 ? (
              <div className="py-5 px-3 rounded-lg bg-[#23A55A]/10 border border-[#23A55A]/30 text-center space-y-1">
                <Smile className="w-5 h-5 text-[#23A55A] mx-auto" />
                <p className="text-xs text-[#23A55A] font-medium">
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
                    <div key={s.speaker_name || idx} className="p-2.5 rounded-lg bg-[#F23F43]/10 border border-[#F23F43]/30 space-y-1.5">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-bold text-[#F2F3F5]" dir="auto">
                          {s.speaker_name}
                        </span>
                        <span className="px-1.5 py-0.5 rounded bg-[#F23F43]/20 text-[#F23F43] font-mono font-bold text-[10px]">
                          {s.angry_episodes} {s.angry_episodes === 1 ? "episode" : "episodes"}
                        </span>
                      </div>
                      {history.map((ep, eIdx) => {
                        const isLoud = Boolean(ep.was_loud || (ep.peak_z && ep.peak_z >= 2.5));
                        const isHostile = ep.context && ep.context.includes("escalation");
                        const isRant = ep.context && (ep.context.includes("rant") || ep.context.includes("monologue"));
                        const isArg = ep.context && (ep.context.includes("argument") || ep.context.includes("dispute"));
                        const clampedZ = ep.peak_z ? Math.min(10.0, ep.peak_z).toFixed(1) : "2.8";
                        return (
                          <div
                            key={eIdx}
                            className="text-[11px] text-[#DBDEE1] bg-[#313338] border border-[#383a40] rounded px-2 py-1 leading-snug space-y-0.5"
                          >
                            <div className="flex items-center justify-between text-[9px] font-mono text-[#949BA4]">
                              <span className="text-[#F0B232] font-semibold">
                                {ep.episode_number ? `Ep #${ep.episode_number}` : "Receipt"}
                              </span>
                              {isHostile ? (
                                <span className="text-[#F23F43] font-bold flex items-center gap-0.5">
                                  <span>🔥</span>
                                  <span>hostile escalation</span>
                                </span>
                              ) : isRant ? (
                                <span className="text-orange-400 font-bold flex items-center gap-0.5">
                                  <span>📢</span>
                                  <span>monologue rant</span>
                                </span>
                              ) : isLoud ? (
                                <span className="text-[#F23F43] font-bold flex items-center gap-0.5">
                                  <span>🔊</span>
                                  <span>+{clampedZ}σ spike</span>
                                </span>
                              ) : isArg ? (
                                <span className="text-[#F0B232] flex items-center gap-0.5">
                                  <span>🎙️</span>
                                  <span>heated exchange</span>
                                </span>
                              ) : (
                                <span className="text-[#949BA4]">vocal friction</span>
                              )}
                            </div>
                            <div className="italic" dir="auto">
                              "{ep.quote}"
                            </div>
                            {ep.audio_clip && (
                              <div className="pt-1 mt-1 border-t border-[#383a40] flex items-center justify-between text-[10px]">
                                <button
                                  onClick={() => handlePlayAudio(ep.audio_clip!)}
                                  className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded font-mono border transition-all cursor-pointer ${
                                    playingClip === ep.audio_clip
                                      ? "bg-[#23A55A]/20 border-[#23A55A]/50 text-[#23A55A] animate-pulse"
                                      : "bg-[#F23F43]/20 hover:bg-[#F23F43]/30 text-[#F23F43] border-[#F23F43]/40"
                                  }`}
                                  title={`Play audio evidence: ${ep.audio_clip}`}
                                >
                                  <span>{playingClip === ep.audio_clip ? "🔊" : "▶️"}</span>
                                  <span>{playingClip === ep.audio_clip ? "Playing..." : "Play Audio Evidence"}</span>
                                </button>
                                <span className="font-mono text-[9px] text-[#949BA4] truncate max-w-[110px]" title={ep.audio_clip}>
                                  {ep.audio_clip}
                                </span>
                              </div>
                            )}
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
            <div className="mt-3 pt-2 border-t border-[#383a40] text-[10px] font-mono text-[#F23F43] text-right">
              {total_angry_episodes} total episode{total_angry_episodes === 1 ? "" : "s"}
            </div>
          )}
        </div>

        {/* WIDGET 4: CALL BADGES & HIGHLIGHTS */}
        <div className="p-4 rounded-xl bg-[#1e1f22] border border-[#383a40] flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-2 mb-3">
              <Award className="w-4 h-4 text-[#F0B232]" />
              <h4 className="text-xs font-bold text-[#DBDEE1] tracking-wider uppercase">
                Call Badges & Records
              </h4>
            </div>

            {(longest_streak?.streak_seconds > 0) || hasSpeakers ? (
              <div className="space-y-2.5">
                {longest_streak && longest_streak.speaker_name && longest_streak.streak_seconds > 0 && (
                  <div className="p-3 rounded-xl bg-[#313338] border border-[#F0B232]/30 text-center space-y-1.5">
                    <div className="inline-flex p-1.5 rounded-xl bg-[#F0B232]/20 text-[#F0B232] border border-[#F0B232]/40">
                      <Award className="w-5 h-5" />
                    </div>
                    <div>
                      <div className="text-[10px] uppercase font-bold text-[#F0B232] tracking-wider">
                        The Monologue King
                      </div>
                      <div className="text-sm font-bold text-white flex items-center justify-center gap-1.5" dir="auto">
                        <span>👑</span>
                        <span>{longest_streak.speaker_name}</span>
                      </div>
                      <div className="text-xl font-extrabold font-mono text-[#F0B232] mt-0.5">
                        {formatStreakMMSS(longest_streak.streak_seconds)}
                      </div>
                      <div className="text-[10px] font-mono text-[#949BA4]">
                        ({formatDurationHuman(longest_streak.streak_seconds)} uninterrupted)
                      </div>
                    </div>
                  </div>
                )}

                {/* The Silent Observer (quietest in call, minimum 2 speakers) */}
                {hasSpeakers && speakerEntries.length >= 2 && (() => {
                  const quietest = speakerEntries[speakerEntries.length - 1];
                  const secondQuietest = speakerEntries[speakerEntries.length - 2];
                  if (secondQuietest.talk_seconds - quietest.talk_seconds >= 1.0) {
                    const qPct = total_talk_seconds > 0 ? (quietest.talk_seconds / total_talk_seconds) * 100 : 0;
                    return (
                      <div className="p-2.5 rounded-xl bg-[#313338] border border-[#5865F2]/30 flex items-center justify-between text-xs">
                        <div className="flex items-center gap-2">
                          <span className="text-base">🤫</span>
                          <div>
                            <div className="text-[9px] uppercase font-bold text-[#5865F2] tracking-wider">
                              The Silent Observer
                            </div>
                            <div className="font-bold text-white truncate max-w-[110px]" dir="auto">
                              {quietest.speaker_name || "Speaker"}
                            </div>
                          </div>
                        </div>
                        <div className="text-right font-mono text-[#5865F2]">
                          <div className="font-bold text-xs">{formatDurationHuman(quietest.talk_seconds)}</div>
                          <div className="text-[9px] text-[#949BA4]">({qPct.toFixed(1)}% airtime)</div>
                        </div>
                      </div>
                    );
                  }
                  return null;
                })()}

                {/* The Most Unfiltered / Spicy Tongue (minimum 2 speakers) */}
                {hasSpeakers && speakerEntries.length >= 2 && (() => {
                  const withVulgarity = speakerEntries.filter(s => (s.vulgarity_count || 0) > 0);
                  if (withVulgarity.length === 0) return null;
                  const sortedVulgar = [...withVulgarity].sort((a, b) => (b.vulgarity_count || 0) - (a.vulgarity_count || 0));
                  const top = sortedVulgar[0];
                  if (sortedVulgar.length >= 2 && (sortedVulgar[1].vulgarity_count || 0) === (top.vulgarity_count || 0)) {
                    return null;
                  }
                  return (
                    <div className="p-2.5 rounded-xl bg-[#313338] border border-[#F23F43]/30 flex items-center justify-between text-xs">
                      <div className="flex items-center gap-2">
                        <span className="text-base">🌶️</span>
                        <div>
                          <div className="text-[9px] uppercase font-bold text-[#F23F43] tracking-wider">
                            The Most Unfiltered
                          </div>
                          <div className="font-bold text-white truncate max-w-[110px]" dir="auto">
                            {top.speaker_name}
                          </div>
                        </div>
                      </div>
                      <div className="text-right font-mono text-[#F23F43]">
                        <div className="font-bold text-xs">{top.vulgarity_count} raw tokens</div>
                        <div className="text-[9px] text-[#949BA4]">
                          {top.vulgarity_terms && top.vulgarity_terms.length > 0 ? top.vulgarity_terms.slice(0, 2).join(", ") : "uncensored"}
                        </div>
                      </div>
                    </div>
                  );
                })()}

                {/* The Diplomat (0 anger, 0 vulgarity, >= 15s talk time, min 2 speakers) */}
                {hasSpeakers && speakerEntries.length >= 2 && (() => {
                  const diplomatCandidates = speakerEntries.filter(
                    s => (s.vulgarity_count || 0) === 0 && s.angry_episodes === 0 && s.talk_seconds >= 15.0
                  );
                  if (diplomatCandidates.length === 0) return null;
                  const sortedDiplomats = [...diplomatCandidates].sort((a, b) => b.talk_seconds - a.talk_seconds);
                  const topDiplomat = sortedDiplomats[0];
                  if (sortedDiplomats.length >= 2 && (topDiplomat.talk_seconds - sortedDiplomats[1].talk_seconds) < 1.0) {
                    return null;
                  }
                  return (
                    <div className="p-2.5 rounded-xl bg-[#313338] border border-[#23A55A]/30 flex items-center justify-between text-xs">
                      <div className="flex items-center gap-2">
                        <span className="text-base">🕊️</span>
                        <div>
                          <div className="text-[9px] uppercase font-bold text-[#23A55A] tracking-wider">
                            The Diplomat
                          </div>
                          <div className="font-bold text-white truncate max-w-[110px]" dir="auto">
                            {topDiplomat.speaker_name}
                          </div>
                        </div>
                      </div>
                      <div className="text-right font-mono text-[#23A55A]">
                        <div className="font-bold text-xs">{formatDurationHuman(topDiplomat.talk_seconds)}</div>
                        <div className="text-[9px] text-[#949BA4]">100% peaceful</div>
                      </div>
                    </div>
                  );
                })()}

                {/* The Roast Master (The Banter King / ملك الضحك والمناوشات, min 2 speakers) */}
                {hasSpeakers && speakerEntries.length >= 2 && (() => {
                  const withBanter = speakerEntries.filter(s => (s.banter_count || 0) > 0);
                  if (withBanter.length === 0) return null;
                  const sortedBanter = [...withBanter].sort((a, b) => (b.banter_count || 0) - (a.banter_count || 0));
                  const topBanter = sortedBanter[0];
                  if (sortedBanter.length >= 2 && (sortedBanter[1].banter_count || 0) === (topBanter.banter_count || 0)) {
                    return null;
                  }
                  return (
                    <div className="p-2.5 rounded-xl bg-[#313338] border border-purple-500/30 flex items-center justify-between text-xs">
                      <div className="flex items-center gap-2">
                        <span className="text-base">🎭</span>
                        <div>
                          <div className="text-[9px] uppercase font-bold text-purple-400 tracking-wider">
                            The Roast Master
                          </div>
                          <div className="font-bold text-white truncate max-w-[110px]" dir="auto">
                            {topBanter.speaker_name}
                          </div>
                        </div>
                      </div>
                      <div className="text-right font-mono text-purple-400">
                        <div className="font-bold text-xs">{topBanter.banter_count} {topBanter.banter_count === 1 ? "banter turn" : "banter turns"}</div>
                        <div className="text-[9px] text-[#949BA4]">
                          {topBanter.banter_terms && topBanter.banter_terms.length > 0 ? topBanter.banter_terms.slice(0, 2).join(", ") : "friendly teasing"}
                        </div>
                      </div>
                    </div>
                  );
                })()}
              </div>
            ) : (
              <div className="py-6 text-center text-xs text-[#949BA4] italic">
                waiting for call data…
              </div>
            )}
          </div>
          {longest_streak && longest_streak.streak_seconds > 0 && (
            <div className="mt-3 pt-2 border-t border-[#383a40] text-[10px] font-mono text-[#F0B232] text-right">
              Session Highlights
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
