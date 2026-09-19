"use client";

import React, { useState } from "react";
import { PhoneCall, Sparkles, Activity, ShieldCheck, FileText, Play } from "lucide-react";
import LiveVoiceRoom from "@/components/LiveVoiceRoom";
import DashboardView from "@/components/DashboardView";

export default function HomePage() {
  const [currentCallId, setCurrentCallId] = useState<string | null>(null);
  const [speakerRole, setSpeakerRole] = useState<"you" | "friend">("you");
  const [callState, setCallState] = useState<"idle" | "live" | "dashboard">("idle");
  const [dashboardData, setDashboardData] = useState<any | null>(null);
  const [isStarting, setIsStarting] = useState(false);

  const getApiBaseUrl = () => {
    if (process.env.NEXT_PUBLIC_API_URL) return process.env.NEXT_PUBLIC_API_URL;
    if (typeof window !== "undefined") {
      if (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") {
        return `${window.location.protocol}//${window.location.hostname}:8000`;
      }
      return window.location.origin;
    }
    return "http://localhost:8000";
  };

  // Check for invite link parameters (?callId=...&role=friend)
  React.useEffect(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const inviteCallId = params.get("callId");
      const roleParam = params.get("role");
      if (inviteCallId) {
        setCurrentCallId(inviteCallId);
        setSpeakerRole(roleParam === "friend" ? "friend" : "you");
        setCallState("live");
      }
    }
  }, []);

  // Start new call session
  const handleStartCall = async (title: string = "Friday Voice Discussion") => {
    setIsStarting(true);
    setSpeakerRole("you");
    try {
      const apiBase = getApiBaseUrl();
      const resp = await fetch(`${apiBase}/api/calls`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          participant_a_name: "You",
          participant_b_name: "Friend",
        }),
      });
      const data = await resp.json();
      setCurrentCallId(data.id);
      setCallState("live");
    } catch (e) {
      console.error("Failed to start call:", e);
      alert(`Failed to connect to backend server at ${getApiBaseUrl()}. Ensure backend is running.`);
    } finally {
      setIsStarting(false);
    }
  };

  // End call and load conversation report
  const handleEndCall = async () => {
    if (!currentCallId) return;
    try {
      const apiBase = getApiBaseUrl();
      // 1. End call
      await fetch(`${apiBase}/api/calls/${currentCallId}/end`, {
        method: "POST",
      });

      // 2. Fetch dashboard analytics
      const resp = await fetch(`${apiBase}/api/calls/${currentCallId}/dashboard`);
      const data = await resp.json();
      setDashboardData(data);
      setCallState("dashboard");
    } catch (e) {
      console.error("Failed to end call and load dashboard:", e);
    }
  };

  if (callState === "live" && currentCallId) {
    return <LiveVoiceRoom callId={currentCallId} role={speakerRole} onEndCall={handleEndCall} />;
  }

  if (callState === "dashboard" && dashboardData) {
    return (
      <DashboardView
        data={dashboardData}
        onBackToCall={() => {
          setCallState("idle");
          setCurrentCallId(null);
          setDashboardData(null);
        }}
      />
    );
  }

  return (
    <div className="min-h-screen flex flex-col justify-between p-6 md:p-12 bg-[#070b13]">
      <div className="max-w-4xl mx-auto w-full my-auto space-y-12">
        {/* Brand & Hero */}
        <div className="text-center space-y-4">
          <div className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-indigo-950/60 border border-indigo-700/50 text-indigo-300 text-xs font-semibold mb-2">
            <Sparkles className="w-3.5 h-3.5" />
            Universal-3.5 Pro Realtime • Egyptian Arabic & English Intelligence
          </div>
          <h1 className="text-4xl md:text-6xl font-extrabold tracking-tight bg-gradient-to-r from-blue-400 via-indigo-200 to-emerald-300 bg-clip-text text-transparent">
            AI Third Participant
          </h1>
          <p className="text-base md:text-lg text-slate-400 max-w-2xl mx-auto leading-relaxed">
            Joins two-person voice calls as an intelligent co-listener. Understands who is talking, tracks topics,
            detects factual claims, verifies disputes via web evidence, and generates deterministic reports.
          </p>
        </div>

        {/* Feature Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="p-6 rounded-2xl bg-[#0f172a] border border-slate-800 shadow-md flex flex-col gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-600/20 border border-blue-500/40 flex items-center justify-center text-blue-400">
              <PhoneCall className="w-5 h-5" />
            </div>
            <h3 className="font-bold text-slate-200 text-sm">Realtime Voice Stream</h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              AssemblyAI Universal-3.5 Pro handles low-latency (~285ms) live audio with native Arabic/English code-switching.
            </p>
          </div>

          <div className="p-6 rounded-2xl bg-[#0f172a] border border-slate-800 shadow-md flex flex-col gap-3">
            <div className="w-10 h-10 rounded-xl bg-indigo-600/20 border border-indigo-500/40 flex items-center justify-center text-indigo-400">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <h3 className="font-bold text-slate-200 text-sm">Grounded Fact Checks</h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Disagreements trigger external web search. Intervenes only on high-confidence disputes with official sources.
            </p>
          </div>

          <div className="p-6 rounded-2xl bg-[#0f172a] border border-slate-800 shadow-md flex flex-col gap-3">
            <div className="w-10 h-10 rounded-xl bg-emerald-600/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400">
              <FileText className="w-5 h-5" />
            </div>
            <h3 className="font-bold text-slate-200 text-sm">Deterministic Analytics</h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Exact speaking percentages, topic durations, heat scores, and full interactive transcripts.
            </p>
          </div>
        </div>

        {/* Start Action */}
        <div className="flex flex-col items-center justify-center gap-4 pt-4">
          <button
            onClick={() => handleStartCall("Egyptian Arabic & English Discussion")}
            disabled={isStarting}
            className="flex items-center gap-3 px-8 py-4 rounded-2xl font-bold text-base bg-gradient-to-r from-blue-600 via-indigo-600 to-indigo-700 hover:from-blue-500 hover:to-indigo-600 text-white shadow-xl shadow-indigo-950/60 transition-all transform hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50"
          >
            <Play className="w-5 h-5 fill-white" />
            {isStarting ? "Initializing Call Room..." : "Enter Voice Room"}
          </button>
          <span className="text-xs text-slate-500">
            Works with microphone streaming or simulated one-click scenarios
          </span>
        </div>
      </div>

      <footer className="text-center text-xs text-slate-600 py-4">
        AI Third Participant • AssemblyAI Universal-3.5 Pro • Next.js & FastAPI
      </footer>
    </div>
  );
}
