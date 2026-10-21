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
  food: "Food & Dining",
  travel: "Travel",
  study_work: "Work & Study",
  health: "Health",
  cars: "Cars & Automotive",
  money: "Finance",
  football: "Football",
  politics: "Public Affairs",
  music: "Music",
  movies: "Cinema & Movies",
  gaming: "Gaming",
  tech: "Technology",
  personal: "Personal",
  other: "Other",
};

export const TOPIC_COLORS = [
  "bg-[#3b82f6]",
  "bg-[#10b981]",
  "bg-[#6366f1]",
  "bg-[#06b6d4]",
  "bg-[#8b5cf6]",
  "bg-[#f59e0b]",
  "bg-[#f43f5e]",
  "bg-[#14b8a6]",
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
    <div className="border border-[#1c2436] bg-[#0b0e14] divide-y divide-[#1c2436] rounded">
      <div className="px-6 py-4 bg-[#101522] flex items-center justify-between">
        <div>
          <h3 className="font-editorial text-base font-bold text-white tracking-tight">
            Session Analytics & Participation
          </h3>
          <p className="text-xs text-[#8e98ab] mt-0.5">
            Real-time talk distribution, topics, and conversational metrics
          </p>
        </div>
        {onOpenRecap && (
          <button
            onClick={onOpenRecap}
            className="flex items-center gap-2 px-3.5 py-2 bg-[#3b82f6] hover:bg-[#2563eb] text-white text-xs font-semibold rounded transition-colors cursor-pointer"
          >
            <Award className="w-4 h-4" />
            <span>Open CallWrapped Card</span>
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-[#1c2436]">
        {/* Airtime */}
        <div className="p-6 space-y-4">
          <div className="flex items-center justify-between text-xs text-[#8e98ab]">
            <span className="font-semibold uppercase tracking-wider">
              Airtime Share
            </span>
            <span className="font-mono text-white font-bold">
              {formatDurationHuman(total_talk_seconds)}
            </span>
          </div>

          {speakerEntries.length > 0 ? (
            <div className="space-y-3">
              {speakerEntries.map((s) => {
                const pct =
                  total_talk_seconds > 0
                    ? (s.talk_seconds / total_talk_seconds) * 100
                    : 0;
                return (
                  <div key={s.speaker_name} className="space-y-1.5">
                    <div className="flex justify-between text-sm">
                      <span className="font-medium text-white" dir="auto">
                        {s.speaker_name}
                      </span>
                      <span className="font-mono text-xs text-[#8e98ab]">
                        {formatDurationHuman(s.talk_seconds)} ({pct.toFixed(0)}%)
                      </span>
                    </div>
                    <div className="w-full h-2 bg-[#161c2c] rounded-full overflow-hidden">
                      <div
                        className="h-full bg-[#3b82f6] rounded-full transition-all duration-300"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-sm text-[#5e6b7d] py-4">No speech recorded yet.</p>
          )}
        </div>

        {/* Topics */}
        <div className="p-6 space-y-4">
          <div className="flex items-center justify-between text-xs text-[#8e98ab]">
            <span className="font-semibold uppercase tracking-wider">
              Topics Discussed
            </span>
            <span className="font-mono text-white">
              {topicalEntries.length} categories
            </span>
          </div>

          {totalTopicalCount > 0 ? (
            <div className="space-y-3">
              {topicalEntries.map(([topic, count], idx) => {
                const pct = (count / totalTopicalCount) * 100;
                const color = TOPIC_COLORS[idx % TOPIC_COLORS.length];
                return (
                  <div key={topic} className="space-y-1.5">
                    <div className="flex justify-between text-sm">
                      <span className="text-[#e2e8f0] capitalize">
                        {topic}
                        {TOPIC_DISPLAY_NAMES[topic.toLowerCase()]
                          ? ` · ${TOPIC_DISPLAY_NAMES[topic.toLowerCase()]}`
                          : ""}
                      </span>
                      <span className="font-mono text-xs text-[#8e98ab]">
                        {pct.toFixed(0)}%
                      </span>
                    </div>
                    <div className="w-full h-2 bg-[#161c2c] rounded-full overflow-hidden">
                      <div
                        className={`h-full ${color} rounded-full`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-sm text-[#5e6b7d] py-4">
              Waiting for topic classification...
            </p>
          )}
        </div>

        {/* Friction & Streaks */}
        <div className="p-6 space-y-4">
          <div className="flex items-center justify-between text-xs text-[#8e98ab]">
            <span className="font-semibold uppercase tracking-wider">
              Acoustic Moments
            </span>
            <span
              className={
                total_angry_episodes > 0 ? "text-[#f43f5e]" : "text-[#10b981]"
              }
            >
              {total_angry_episodes === 0 ? "0 Heated Spikes" : `${total_angry_episodes} Spikes`}
            </span>
          </div>

          {angrySpeakers.length > 0 ? (
            <div className="space-y-3">
              {angrySpeakers.map((s) => (
                <div
                  key={s.speaker_name}
                  className="border-l-2 border-[#f43f5e] pl-3 py-1 space-y-1 bg-[#101522] rounded-r p-2"
                >
                  <div className="flex items-center justify-between text-sm font-semibold text-white">
                    <span>{s.speaker_name}</span>
                    <span className="font-mono text-xs text-[#f43f5e]">
                      {s.angry_episodes}x Heated
                    </span>
                  </div>
                  {(s.anger_evidence || s.first_anger_quote) && (
                    <p className="text-xs text-[#a0aec0] italic" dir="auto">
                      “{s.anger_evidence || s.first_anger_quote}”
                    </p>
                  )}
                  {s.anger_episodes_history?.[0]?.audio_clip && (
                    <button
                      onClick={() =>
                        handlePlayAudio(s.anger_episodes_history![0].audio_clip!)
                      }
                      className="inline-flex items-center gap-1.5 font-mono text-xs text-[#f43f5e] hover:underline pt-1 cursor-pointer"
                    >
                      <Volume2 className="w-3.5 h-3.5" />
                      <span>{playingClip ? "Playing..." : "Play Audio Clip"}</span>
                    </button>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-[#10b981] py-2">
              Calm discussion with zero anger spikes.
            </p>
          )}

          {longest_streak?.speaker_name && longest_streak.streak_seconds > 0 && (
            <div className="pt-3 border-t border-[#1c2436] flex items-center justify-between text-sm">
              <span className="text-xs uppercase text-[#f59e0b] font-medium">
                Longest Monologue
              </span>
              <span className="font-mono text-white font-semibold">
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
