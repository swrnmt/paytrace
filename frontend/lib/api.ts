import axios from "axios";

// All API calls go through this base URL
// We'll change this to the deployed URL later
const api = axios.create({
  baseURL: "https://paytrace-backend.onrender.com",
});

export interface Incident {
  id: string;
  title: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  status: "OPEN" | "INVESTIGATING" | "RESOLVED";
  started_at: string;
  resolved_at: string | null;
  psp: string | null;
  bank: string | null;
}

export interface IncidentContext {
  timeline: {
    started_at: string;
    duration_minutes: number;
    is_worsening: boolean;
  };
  blast_radius: {
    affected_merchants: number;
    total_failed_transactions: number;
    failure_rate_percent: number;
  };
  failure_location: {
    psp: string | null;
    bank: string | null;
    payment_rail: string | null;
  };
  historical_pattern: {
    similar_incidents_last_30d: number;
    last_occurrence: string | null;
    recurring: boolean;
  };
}

export interface AISummary {
  incident_overview: string;
  suspected_root_cause: string;
  blast_radius: {
    affected_merchants: number;
    affected_psp: string | null;
    affected_bank: string | null;
  };
  severity_assessment: string;
  recommended_actions: string[];
  confidence_score: number;
}

export const getIncidents = async (): Promise<Incident[]> => {
  const res = await api.get("/incidents");
  return res.data;
};

export const getIncident = async (id: string): Promise<Incident> => {
  const res = await api.get(`/incidents/${id}`);
  return res.data;
};

export const getIncidentContext = async (id: string): Promise<IncidentContext> => {
  const res = await api.get(`/incidents/${id}/context`);
  return res.data;
};

export const getAISummary = async (id: string): Promise<AISummary> => {
  const res = await api.post(`/incidents/${id}/summary`);
  return res.data;
};

export const sendChatMessage = async (id: string, message: string) => {
  const res = await api.post(`/incidents/${id}/chat`, { message });
  return res.data;
};

export const getChatHistory = async (id: string) => {
  const res = await api.get(`/incidents/${id}/chat/history`);
  return res.data;
};