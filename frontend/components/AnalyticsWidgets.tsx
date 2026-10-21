"use client";

import React, { useState } from "react";
import { Award, Volume2 } from "lucide-react";

export interface AngerEpisodeItem {
  episode_number?: number;
  quote: string;
  timestamp?: number;
  anger?: string;
  intensity?: string;
  loudness?: number;
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
  "bg-[#3b82f6]",
  "bg-[#10b981]",
  "bg-[#f59e0b]",
  "bg-[#8b5cf6]",
  "bg-[#ec4899]",
  "bg-[#06b6d4]",
  "bg-[#ef4444]",
  "bg-[#84cc16]",
];

interface Props {
  analytics: AnalyticsState;
  onOpenRecap?: () => void;
}

export function AnalyticsWidgets({ analytics, onOpenRecap }: Props) {
  const {
    topic_totals,
    speakers,
    total_talk_seconds,
    total_angry_episodes,
    longest_streak,
  } = analytics;
  const [playingClip, setPlayingClip] = useState<string | null>(null);

  const getAudioUrl = (clip: string) => {
    if (typeof window !== "undefined") {
      const hostname = window.location.hostname || "localhost";
      const isLocal = hostname === "localhost" || hostname === "127.0.0.1";
      const port = isLocal ? "8000" : window.location.port;
      const hostPart = port ? `${hostname}:${port}` : hostname;
      return `${window.location.protocol}//${hostPart}/api/audio-evidence/${clip}`;
    }
    return `/api/audio-evidence/${clip}`;
  };

  const handlePlayAudio = (clip: string) => {
    try {
      const url = getAudioUrl(clip);
      const audio = new Audio(url);
      setPlayingClip(clip);
      audio.onended = () => setPlayingClip(null);
      audio.onerror = () => setPlayingClip(null);
      audio.play().catch(() => setPlayingClip(null));
    } catch {
      setPlayingClip(null);
    }
  };

  const topicalEntries = Object.entries(topic_totals || {})
    .filter(
      ([t]) =>
        t !== "null_topic" &&
        t !== "null" &&
        t !== "بدون موضوع" &&
        t !== "none"
    )
    .sort((a, b) => b[1] - a[1]);

  const totalTopicalCount = topicalEntries.reduce((acc, [, c]) => acc + c, 0);
  const speakerEntries = Object.values(speakers || {}).sort(
    (a, b) => b.talk_seconds - a.talk_seconds
  );
  const angrySpeakers = speakerEntries.filter((s) => s.angry_episodes > 0);

  return (
    <div className="border border-[#1c2029] bg-[#090a0d] divide-y divide-[#1c2029]">
      <div className="px-5 py-3 bg-[#0e1015] flex items-center justify-between">
        <span className="font-mono text-xs font-bold uppercase tracking-[0.14em] text-[#e6e8ee]">
          SESSION TELEMETRY & ANALYTICS
        </span>
        {onOpenRecap && (
          <button
            onClick={onOpenRecap}
            className="flex items-center gap-1.5 px-3 py-1 bg-[#3b82f6] hover:bg-[#2563eb] text-white font-mono text-[11px] font-bold uppercase tracking-wider transition-colors cursor-pointer"
          >
            <Award className="w-3.5 h-3.5" />
            <span>Open Recap Card</span>
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-[#1c2029]">
        {/* Talk Share */}
        <div className="p-5 space-y-3">
          <div className="flex items-center justify-between font-mono text-[11px] text-[#7e8694] uppercase">
            <span>AIRTIME SHARE</span>
            <span className="text-[#e6e8ee] font-bold">
              {formatDurationHuman(total_talk_seconds)}
            </span>
          </div>
          {speakerEntries.length > 0 ? (
            <div className="space-y-2.5">
              {speakerEntries.map((s) => {
                const pct =
                  total_talk_seconds > 0
                    ? (s.talk_seconds / total_talk_seconds) * 100
                    : 0;
                return (
                  <div key={s.speaker_name} className="space-y-1">
                    <div className="flex justify-between text-xs">
                      <span className="font-semibold text-[#e6e8ee]" dir="auto">
                        {s.speaker_name}
                      </span>
                      <span className="font-mono text-[#7e8694]">
                        {formatDurationHuman(s.talk_seconds)} ({pct.toFixed(0)}%)
                      </span>
                    </div>
                    <div className="w-full h-1.5 bg-[#151821]">
                      <div
                        className="h-full bg-[#3b82f6]"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="font-mono text-xs text-[#525866] py-4">
              No voice activity recorded yet.
            </p>
          )}
        </div>

        {/* Topics */}
        <div className="p-5 space-y-3">
          <div className="flex items-center justify-between font-mono text-[11px] text-[#7e8694] uppercase">
            <span>TOPICS DETECTED</span>
            <span>{topicalEntries.length} CATEGORIES</span>
          </div>
          {totalTopicalCount > 0 ? (
            <div className="space-y-2.5">
              {topicalEntries.map(([topic, count], idx) => {
                const pct = (count / totalTopicalCount) * 100;
                const color = TOPIC_COLORS[idx % TOPIC_COLORS.length];
                return (
                  <div key={topic} className="space-y-1">
                    <div className="flex justify-between text-xs">
                      <span className="text-[#e6e8ee] capitalize">
                        {topic}
                        {TOPIC_DISPLAY_NAMES[topic.toLowerCase()]
                          ? ` · ${TOPIC_DISPLAY_NAMES[topic.toLowerCase()]}`
                          : ""}
                      </span>
                      <span className="font-mono text-[#7e8694]">
                        {pct.toFixed(0)}%
                      </span>
                    </div>
                    <div className="w-full h-1.5 bg-[#151821]">
                      <div
                        className={`h-full ${color}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="font-mono text-xs text-[#525866] py-4">
              No topic data yet.
            </p>
          )}
        </div>

        {/* Acoustic Friction & Streaks */}
        <div className="p-5 space-y-3">
          <div className="flex items-center justify-between font-mono text-[11px] text-[#7e8694] uppercase">
            <span>ACOUSTIC FRICTION</span>
            <span
              className={
                total_angry_episodes > 0 ? "text-[#ef4444]" : "text-[#10b981]"
              }
            >
              {total_angry_episodes} SPIKES
            </span>
          </div>
          {angrySpeakers.length > 0 ? (
            <div className="space-y-2">
              {angrySpeakers.map((s) => (
                <div
                  key={s.speaker_name}
                  className="border-l-2 border-[#ef4444] pl-3 py-1 space-y-1"
                >
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-bold text-[#e6e8ee]">
                      {s.speaker_name}
                    </span>
                    <span className="font-mono text-[10px] text-[#ef4444]">
                      {s.angry_episodes}x HEATED
                    </span>
                  </div>
                  {(s.anger_evidence || s.first_anger_quote) && (
                    <p className="text-xs text-[#9aa2b1] italic" dir="auto">
                      “{s.anger_evidence || s.first_anger_quote}”
                    </p>
                  )}
                  {s.anger_episodes_history?.[0]?.audio_clip && (
                    <button
                      onClick={() =>
                        handlePlayAudio(
                          s.anger_episodes_history![0].audio_clip!
                        )
                      }
                      className="inline-flex items-center gap-1 font-mono text-[10px] text-[#ef4444] hover:underline"
                    >
                      <Volume2 className="w-3 h-3" />
                      <span>
                        {playingClip ? "PLAYING..." : "PLAY AUDIO RECEIPT"}
                      </span>
                    </button>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="font-mono text-xs text-[#10b981] py-2">
              0 acoustic anger spikes detected.
            </p>
          )}

          {longest_streak?.speaker_name && longest_streak.streak_seconds > 0 && (
            <div className="pt-3 border-t border-[#1c2029] flex items-center justify-between text-xs">
              <span className="font-mono text-[10px] uppercase text-[#f59e0b]">
                LONGEST MONOLOGUE
              </span>
              <span className="font-mono font-bold text-[#e6e8ee]">
                {longest_streak.speaker_name} (
                {formatStreakMMSS(longest_streak.streak_seconds)})
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
export default AnalyticsWidgets;
