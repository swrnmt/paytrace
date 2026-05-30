"use client";

import { useQuery, useMutation } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useState } from "react";
import {
  getIncident,
  getIncidentContext,
  getAISummary,
  sendChatMessage,
} from "@/lib/api";
import {
  Clock,
  Zap,
  TrendingUp,
  Building2,
  Send,
  ArrowLeft,
  RefreshCw,
} from "lucide-react";
import Link from "next/link";

const severityColor = {
  CRITICAL: "text-red-500 border-red-500",
  HIGH: "text-orange-500 border-orange-500",
  MEDIUM: "text-yellow-500 border-yellow-500",
  LOW: "text-green-500 border-green-500",
};

function formatDuration(minutes: number): string {
  if (minutes < 60) return `${minutes}m`;
  if (minutes < 1440) {
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return m > 0 ? `${h}h ${m}m` : `${h}h`;
  }
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  return hours > 0 ? `${days}d ${hours}h` : `${days}d`;
}

const EXAMPLE_QUESTIONS = [
  "Which merchants are most affected?",
  "Who is impacted?",
  "What should we check first?",
];

export default function IncidentPage() {
  const { id } = useParams();
  const [message, setMessage] = useState("");
  const [chatMessages, setChatMessages] = useState<{ role: string; content: string }[]>([]);
  const [summaryRequested, setSummaryRequested] = useState(false);

  const { data: incident } = useQuery({
    queryKey: ["incident", id],
    queryFn: () => getIncident(id as string),
  });

  const { data: context, isLoading: contextLoading } = useQuery({
    queryKey: ["context", id],
    queryFn: () => getIncidentContext(id as string),
  });

  const { data: summary, isLoading: summaryLoading, refetch: fetchSummary } = useQuery({
    queryKey: ["summary", id],
    queryFn: () => getAISummary(id as string),
    enabled: summaryRequested,
  });

  const chatMutation = useMutation({
    mutationFn: (msg: string) => sendChatMessage(id as string, msg),
    onSuccess: (data) => {
      setChatMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.response },
      ]);
    },
  });

  const handleSend = (msg?: string) => {
    const text = msg || message;
    if (!text.trim()) return;
    setChatMessages((prev) => [...prev, { role: "user", content: text }]);
    chatMutation.mutate(text);
    setMessage("");
  };

  if (!incident) return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center text-zinc-500">
      Loading...
    </div>
  );

  const sev = incident.severity as keyof typeof severityColor;

  return (
    <main className="min-h-screen bg-zinc-950 text-white">
      {/* Header */}
      <div className="border-b border-zinc-800 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center gap-4">
          <Link href="/" className="text-zinc-500 hover:text-white transition-colors">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div className="flex-1">
            <div className="flex items-center gap-3">
              <span className={`text-xs font-bold border px-2 py-0.5 rounded ${severityColor[sev]}`}>
                {incident.severity}
              </span>
              <span className="text-xs text-zinc-500">{incident.status}</span>
            </div>
            <h1 className="text-base font-semibold mt-1">{incident.title}</h1>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6 grid grid-cols-3 gap-6">
        {/* LEFT COLUMN */}
        <div className="col-span-2 flex flex-col gap-6">

          {contextLoading && (
            <div className="bg-zinc-900 rounded-lg p-6 text-zinc-500 text-sm">
              Loading context...
            </div>
          )}

          {context && (
            <div className="bg-zinc-900 rounded-lg p-6">
              <h2 className="text-sm font-semibold text-zinc-300 mb-4">Investigation Context</h2>
              <div className="grid grid-cols-2 gap-4">

                <div className="bg-zinc-800 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <Clock className="w-4 h-4 text-blue-400" />
                    <span className="text-xs font-semibold text-zinc-300">Timeline</span>
                  </div>
                  <p className="text-2xl font-bold text-white">{formatDuration(context.timeline.duration_minutes)}</p>
                  <p className="text-xs text-zinc-500 mt-1">Duration</p>
                  {context.timeline.is_worsening && (
                    <span className="text-xs text-red-400 mt-2 block">Worsening</span>
                  )}
                </div>

                <div className="bg-zinc-800 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <Zap className="w-4 h-4 text-orange-400" />
                    <span className="text-xs font-semibold text-zinc-300">Blast Radius</span>
                  </div>
                  <p className="text-2xl font-bold text-white">{context.blast_radius.failure_rate_percent}%</p>
                  <p className="text-xs text-zinc-500 mt-1">Failure rate</p>
                  <p className="text-xs text-zinc-500">{context.blast_radius.affected_merchants} merchants · {context.blast_radius.total_failed_transactions} failed txns</p>
                </div>

                <div className="bg-zinc-800 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <Building2 className="w-4 h-4 text-purple-400" />
                    <span className="text-xs font-semibold text-zinc-300">Failure Location</span>
                  </div>
                  {context.failure_location.psp && (
                    <p className="text-sm text-white">PSP: {context.failure_location.psp}</p>
                  )}
                  {context.failure_location.bank && (
                    <p className="text-sm text-white">Bank: {context.failure_location.bank}</p>
                  )}
                  {context.failure_location.payment_rail && (
                    <p className="text-xs text-zinc-500 mt-1">Rail: {context.failure_location.payment_rail}</p>
                  )}
                </div>

                <div className="bg-zinc-800 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <TrendingUp className="w-4 h-4 text-green-400" />
                    <span className="text-xs font-semibold text-zinc-300">Historical Pattern</span>
                  </div>
                  <p className="text-2xl font-bold text-white">{context.historical_pattern.similar_incidents_last_30d}</p>
                  <p className="text-xs text-zinc-500 mt-1">Similar incidents (30d)</p>
                  {context.historical_pattern.recurring && (
                    <span className="text-xs text-orange-400 mt-2 block">Recurring pattern</span>
                  )}
                </div>

              </div>
            </div>
          )}

          {/* AI Summary */}
          <div className="bg-zinc-900 rounded-lg p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-zinc-300">AI Summary</h2>
              <button
                onClick={() => { setSummaryRequested(true); fetchSummary(); }}
                className="flex items-center gap-2 text-xs bg-zinc-800 hover:bg-zinc-700 px-3 py-1.5 rounded transition-colors"
              >
                <RefreshCw className="w-3 h-3" />
                Generate
              </button>
            </div>

            {summaryLoading && (
              <p className="text-zinc-500 text-sm">Generating AI summary...</p>
            )}

            {!summaryRequested && !summary && (
              <p className="text-zinc-600 text-sm">Click Generate to get an AI summary of this incident.</p>
            )}

            {summary && (
              <div className="flex flex-col gap-4">
                <div>
                  <p className="text-xs text-zinc-500 mb-1">Overview</p>
                  <p className="text-sm text-zinc-200">{summary.incident_overview}</p>
                </div>
                <div>
                  <p className="text-xs text-zinc-500 mb-1">Suspected Root Cause</p>
                  <p className="text-sm text-zinc-200">{summary.suspected_root_cause}</p>
                </div>
                <div>
                  <p className="text-xs text-zinc-500 mb-1">Recommended Actions</p>
                  <ul className="flex flex-col gap-1">
                    {summary.recommended_actions.map((action, i) => (
                      <li key={i} className="text-sm text-zinc-200 flex gap-2">
                        <span className="text-zinc-600">{i + 1}.</span>
                        {action}
                      </li>
                    ))}
                  </ul>
                </div>
                <div className="flex items-center gap-2">
                  <p className="text-xs text-zinc-500">Confidence</p>
                  <div className="flex-1 bg-zinc-800 rounded-full h-1.5">
                    <div
                      className="bg-blue-500 h-1.5 rounded-full"
                      style={{ width: `${summary.confidence_score * 100}%` }}
                    />
                  </div>
                  <p className="text-xs text-zinc-400">{Math.round(summary.confidence_score * 100)}%</p>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* RIGHT COLUMN — Chat */}
        <div className="col-span-1">
          <div className="bg-zinc-900 rounded-lg flex flex-col h-[600px]">
            <div className="p-4 border-b border-zinc-800">
              <h2 className="text-sm font-semibold text-zinc-300">Investigate with AI</h2>
              <p className="text-xs text-zinc-600 mt-0.5">Ask questions about this incident</p>
            </div>

            <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-3">
              {/* Example questions shown when chat is empty */}
              {chatMessages.length === 0 && (
                <div className="flex flex-col gap-2 mt-2">
                  <p className="text-xs text-zinc-600 mb-1">Try asking:</p>
                  {EXAMPLE_QUESTIONS.map((q, i) => (
                    <button
                      key={i}
                      onClick={() => handleSend(q)}
                      className="text-left text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-zinc-200 px-3 py-2 rounded-lg transition-colors"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              )}

              {chatMessages.map((msg, i) => (
                <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                  <div className={`max-w-[85%] rounded-lg px-3 py-2 text-xs ${
                    msg.role === "user"
                      ? "bg-blue-600 text-white"
                      : "bg-zinc-800 text-zinc-200"
                  }`}>
                    {msg.content}
                  </div>
                </div>
              ))}

              {chatMutation.isPending && (
                <div className="flex justify-start">
                  <div className="bg-zinc-800 rounded-lg px-3 py-2 text-xs text-zinc-500">
                    Thinking...
                  </div>
                </div>
              )}
            </div>

            <div className="p-4 border-t border-zinc-800 flex gap-2">
              <input
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSend()}
                placeholder="Ask about this incident..."
                className="flex-1 bg-zinc-800 rounded-lg px-3 py-2 text-xs text-white placeholder-zinc-600 outline-none focus:ring-1 focus:ring-zinc-600"
              />
              <button
                onClick={() => handleSend()}
                disabled={chatMutation.isPending}
                className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded-lg p-2 transition-colors"
              >
                <Send className="w-3 h-3" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}