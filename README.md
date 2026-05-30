# PayTrace

AI-assisted payment incident investigation for fintech operations teams.

**Live Demo:** https://paytrace-three.vercel.app  
**GitHub:** https://github.com/swrnmt/paytrace

---

## The Problem

Payment ops teams spend critical incident time toggling between dashboards, databases, and Slack threads just to answer basic questions — what broke, who's affected, has this happened before. During a live outage, every minute of context-switching is revenue lost.

While exploring fintech pain points, I noticed this gap: there was no single surface where an ops engineer could open an incident and immediately get blast radius, failure location, historical patterns, and AI-powered answers to follow-up questions — all scoped to that specific incident's data.

PayTrace is that surface.

---

## What It Does

An ops user opens an incident and immediately sees:

- **Timeline** — when it started, how long it's been running, whether it's worsening
- **Blast Radius** — how many merchants affected, total failed transactions, failure rate
- **Failure Location** — which PSP, bank, and payment rail is the culprit
- **Historical Pattern** — has this happened before in the last 30 days, is it recurring

They can then generate an AI summary or ask follow-up questions in plain English. The AI answers using only the scoped incident data — it will never hallucinate or pull in information from outside the incident context.

### Simulate Incident

The dashboard includes a **Simulate Incident** button that creates a brand new OPEN incident in real time — complete with a random PSP or bank culprit, realistic title, and CRITICAL or HIGH severity. This demonstrates the full investigation flow live: the incident appears in the list immediately, the context panel populates, the AI generates a summary, and the chat is ready for questions. It shows exactly how PayTrace would behave when a real payment degradation is detected.

---

## Architecture

The core design principle: **the system computes, the LLM explains.**

All deterministic logic — blast radius calculation, failure location detection, historical pattern matching — is handled by SQL queries in the backend. The LLM only receives the pre-computed results and explains them in plain English.

This separation means:
- AI answers are grounded in real data, not general knowledge
- The investigation surface works even if the AI is down
- Accuracy is enforced at the data layer, not the prompt layer

```
Incident opened
      ↓
Backend computes 4-context bundle (SQL queries)
      ↓
Context injected into LLM prompt
      ↓
LLM explains — never computes
      ↓
Ops user asks follow-up → same scoped context passed to LLM
```

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Frontend | Next.js + TypeScript | App router, fast rendering, easy Vercel deployment |
| Styling | TailwindCSS + shadcn/ui | Utility-first, consistent dark theme for ops tooling |
| Data fetching | TanStack Query | Built-in caching, polling, and mutation handling |
| Backend | FastAPI | Fast, async, automatic OpenAPI docs |
| Database | PostgreSQL (Neon) | Relational model fits incident investigation queries perfectly |
| ORM | SQLAlchemy | Type-safe models, clean relationship handling |
| AI | Groq (Llama 3.1) | Fast inference, free tier |
| Deployment | Render + Vercel | Auto-deploy from GitHub |

---

## Data Model

8 tables designed around three query patterns:

- **What's happening right now** — `incidents` indexed on `(severity, status)`
- **What was the blast radius** — `transactions` indexed on `(incident_id, status)`
- **Has this happened before** — `incidents` filtered by `psp_id` or `bank_id` in a 30-day window

- merchants → transactions
- psps → transactions → incident_transactions → incidents
- banks → transactions                               ↓
- rails → transactions                     incident_chat_history


Key design decision: `psp_id` and `bank_id` are denormalized onto the `incidents` table. This makes historical pattern queries a simple WHERE clause instead of an expensive aggregation through transactions.

---

## Synthetic Dataset

The database is seeded with a realistic simulation of Indian payment traffic:

- **30,000 transactions** over 30 days
- **5 PSPs** weighted by real market share (Razorpay 35%, PayU 25%, Cashfree 20%, Juspay 12%, Paytm PG 8%)
- **5 banks** (HDFC, SBI, ICICI, Axis, Kotak)
- **4 payment rails** (UPI 55%, Cards 25%, IMPS 12%, NEFT 8%)
- **Evening peak** — 6pm-10pm is 2.5x normal traffic volume
- **12 injected incidents** — PSP timeout storms, bank outages, webhook retry storms, latency surges
- **Recurring clusters** — HDFC UPI degradation occurs 3 times, Razorpay timeouts occur twice, enabling historical pattern detection to return meaningful data

---

## Grounded Chat

Every user question goes through this flow:

1. Fetch the incident record
2. Fetch top 20 affected transactions
3. Fetch affected merchants and failure rates
4. Build a structured context packet
5. Inject only this context into the LLM prompt
6. Return grounded response

System prompt enforces: *"Answer ONLY using the provided operational context. If information is not in the context, say so."*

The AI will never make up merchant names, transaction counts, or root causes. If the data doesn't support an answer, it says so.

---

## API

| Method | Endpoint | Description |
|---|---|---|
| GET | `/incidents` | List all incidents |
| GET | `/incidents/{id}` | Single incident detail |
| GET | `/incidents/{id}/context` | 4-context investigation bundle |
| POST | `/incidents/{id}/summary` | Generate AI summary |
| POST | `/incidents/{id}/chat` | Grounded chat message |
| GET | `/incidents/{id}/chat/history` | Full chat history |
| POST | `/incidents/simulate` | Create a new synthetic incident |

---

## Future Extensions

- Settlement anomaly investigation
- Reconciliation exception analysis
- Merchant health monitoring
- UPI success-rate monitoring
- PSP degradation detection

---
## Running Locally

**Backend:**
```bash
cd backend
pip install -r requirements.txt

# Create .env with:
# DATABASE_URL=your_neon_connection_string
# GROQ_API_KEY=your_groq_key

uvicorn main:app --reload
```

**Seed the database (first time only):**
```bash
python scripts/run_all.py
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```