"use client";

import { useQuery } from "@tanstack/react-query";
import { getIncidents, Incident } from "@/lib/api";
import { useRouter } from "next/navigation";
import { AlertTriangle, CheckCircle, Clock, Activity } from "lucide-react";

const severityConfig = {
  CRITICAL: { color: "bg-red-500", text: "text-red-500", border: "border-red-500" },
  HIGH: { color: "bg-orange-500", text: "text-orange-500", border: "border-orange-500" },
  MEDIUM: { color: "bg-yellow-500", text: "text-yellow-500", border: "border-yellow-500" },
  LOW: { color: "bg-green-500", text: "text-green-500", border: "border-green-500" },
};

const statusIcon = (status: string) => {
  if (status === "RESOLVED") return <CheckCircle className="w-4 h-4 text-green-500" />;
  if (status === "INVESTIGATING") return <Activity className="w-4 h-4 text-orange-500" />;
  return <AlertTriangle className="w-4 h-4 text-red-500" />;
};

function IncidentCard({ incident }: { incident: Incident }) {
  const router = useRouter();
  const config = severityConfig[incident.severity];

  return (
    <div
      onClick={() => router.push(`/incidents/${incident.id}`)}
      className={`bg-zinc-900 border-l-4 ${config.border} rounded-lg p-5 cursor-pointer hover:bg-zinc-800 transition-all`}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <span className={`text-xs font-bold px-2 py-0.5 rounded ${config.color} text-white`}>
              {incident.severity}
            </span>
            <div className="flex items-center gap-1">
              {statusIcon(incident.status)}
              <span className="text-xs text-zinc-400">{incident.status}</span>
            </div>
          </div>
          <h3 className="text-white font-medium text-sm">{incident.title}</h3>
          <div className="flex items-center gap-3 mt-2 text-xs text-zinc-500">
            {incident.psp && <span>PSP: {incident.psp}</span>}
            {incident.bank && <span>Bank: {incident.bank}</span>}
            <div className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              <span>{new Date(incident.started_at).toLocaleString()}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Home() {
  const { data: incidents, isLoading, isError } = useQuery({
    queryKey: ["incidents"],
    queryFn: getIncidents,
    refetchInterval: 30000, // automatically refetch every 30 seconds
  });

  return (
    <main className="min-h-screen bg-zinc-950 text-white">
      <div className="border-b border-zinc-800 px-6 py-4">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-white">PayTrace</h1>
            <p className="text-xs text-zinc-500">Payment Incident Investigation</p>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            <span className="text-xs text-zinc-400">Live</span>
          </div>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-semibold">Active Incidents</h2>
          {incidents && (
            <span className="text-xs text-zinc-500">{incidents.length} total</span>
          )}
        </div>

        {isLoading && (
          <div className="text-center py-20 text-zinc-500">Loading incidents...</div>
        )}

        {isError && (
          <div className="text-center py-20 text-red-400">
            Could not connect to backend. Make sure uvicorn is running.
          </div>
        )}

        {incidents && (
          <div className="flex flex-col gap-3">
            {incidents.map((incident) => (
              <IncidentCard key={incident.id} incident={incident} />
            ))}
          </div>
        )}
      </div>
    </main>
  );
}