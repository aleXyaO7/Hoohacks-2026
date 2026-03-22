# CLAUDE.md

## Project: Real-Time Financial Decision Assistant

This document provides guidance for Claude (or any LLM agent) working within this codebase.

---

## System Overview

An AI-powered financial copilot that:

* Monitors user financial data via the **Nessie API** (mock banking backend)
* Runs a multi-agent reasoning pipeline to detect risks and opportunities
* Provides conversational financial guidance through a web dashboard chat
* Explains its reasoning transparently — every agent step is traced and displayed
* Evaluates decisions against the user's financial goals
* Suggests tradeoffs and alternatives instead of just saying "no"

---

## Tech Stack (As Built)

### Frontend

* **Static HTML / CSS / JS** — `frontend/` directory
* **Tailwind CSS (CDN)** — styling
* Pages: `index.html` (auth), `goals.html` (onboarding), `dashboard.html` (main app)
* JS: `script.js` (auth/goals), `dashboard.js` (dashboard logic)
* Served by opening HTML files directly or via any static server

### Backend

* **Flask (Python)** — `backend/app.py`, runs on port 5001
* **Flask-CORS** — cross-origin access for frontend
* `python-dotenv` — loads `.env` for API keys

### Database

* **Supabase (Postgres)** — all persistent storage
* Client: `backend/db.py` → `get_supabase()` singleton
* Tables: `users`, `accounts`, `transactions`, `budgets`, `snapshots`, `events`, `alerts`, `messages`

### Financial Data

* **Nessie API** — mock banking data (customers, accounts, purchases, deposits)
* Client: `backend/nessie.py` → `query()`, `add_customer()`, `get_transactions()`, etc.
* API key in `.env` as `NESSIE_API_KEY`

### AI Layer

* **OpenAI API** — `gpt-4o-mini` for all LLM calls
* API key in `.env` as `OPENAI_API_KEY`
* Used by: Goals Agent, Tradeoffs Agent, Messaging Agent, Conversation Agent (Response Synthesis)
* All financial calculations are deterministic — LLM is only used for natural language

### Not Yet Implemented

* **Twilio SMS** (Layers 7–8) — outbound alerts and inbound SMS webhook
* Deployment (Vercel/Render) — currently local development only

---

## Environment Variables (`.env`)

```
NESSIE_API_KEY=<your-nessie-key>
SUPABASE_URL=<your-supabase-url>
SUPABASE_KEY=<your-supabase-anon-key>
OPENAI_API_KEY=<your-openai-key>
```

---

## Running the Project

```bash
# Install dependencies (use the virtual environment)
.venv/bin/pip install -r requirements.txt

# Start the backend (port 5001, reloader disabled for clean restarts)
python backend/app.py

# Open the frontend
open frontend/index.html
```

To restart the server cleanly:
```bash
# Ctrl+C in the terminal, then re-run. If port is stuck:
lsof -ti :5001 | xargs kill -9
python backend/app.py
```

---

## Project Structure

```
Hoohacks-2026/
├── .env                          # API keys (not committed)
├── requirements.txt              # Python dependencies
├── CLAUDE.md                     # This file
├── backend/
│   ├── app.py                    # Flask app entry point (port 5001)
│   ├── db.py                     # Supabase client singleton
│   ├── nessie.py                 # Nessie API client
│   ├── sync.py                   # Nessie → Supabase sync + event detection
│   ├── routes/
│   │   ├── users.py              # User CRUD, login, goals
│   │   ├── accounts.py           # Account linking + management
│   │   ├── transactions.py       # Transaction read/write
│   │   ├── budgets.py            # Budget CRUD
│   │   ├── snapshots.py          # Risk snapshots
│   │   ├── alerts.py             # Events + alerts
│   │   ├── messages.py           # Chat endpoint + message storage
│   │   ├── sync.py               # Sync trigger endpoints
│   │   └── agents.py             # Pipeline trigger endpoints
│   └── agents/
│       ├── risk_agent.py         # Deterministic risk scorer
│       ├── notification_agent.py # Alert decision agent (anti-spam)
│       ├── messaging_agent.py    # LLM message generator
│       ├── goals_agent.py        # LLM goal alignment evaluator
│       ├── tradeoffs_agent.py    # LLM tradeoff/alternative finder
│       ├── conversation_agent.py # Chat pipeline orchestrator
│       └── orchestrator.py       # Event pipeline orchestrator
└── frontend/
    ├── index.html                # Sign in / Create account
    ├── goals.html                # Onboarding goals form
    ├── script.js                 # Auth + goals JS logic
    ├── dashboard.html            # Main dashboard layout
    └── dashboard.js              # Dashboard logic (chat, pipeline, trace)
```

---

## Agent Architecture

There are **two pipelines**, both fully traced for transparency.

### Pipeline 1: Event Pipeline (Sync & Analyze button)

Triggered by `POST /api/users/<id>/pipeline`. Runs automatically when the user clicks "Sync & Analyze."

```
Nessie API → Sync Agent → Risk Agent → Notification Agent → Messaging Agent → Dashboard
```

| Step | Agent | Type | Purpose |
|------|-------|------|---------|
| 1 | **Nessie Sync Agent** | Deterministic | Polls Nessie for accounts/transactions, diffs against Supabase, detects events (new_transaction, large_transaction, paycheck_received, low_balance, budget_exceeded) |
| 2 | **Financial Risk Agent** | Deterministic | Scores financial health (0–100) based on balance runway, budget usage, cash flow, and goal alignment. Outputs risk level, factors, and recommendations |
| 3 | **Notification Agent** | Deterministic | Decides whether to alert the user. Checks risk severity, cooldown periods (anti-spam), and actionability |
| 4 | **Messaging Agent** | LLM (gpt-4o-mini) | Transforms the structured risk assessment into natural language alerts for SMS and dashboard |

Each step is recorded in a `trace` array returned in the API response. The frontend renders this as an animated, expandable timeline.

### Pipeline 2: Chat Pipeline (user sends a message)

Triggered by `POST /api/users/<id>/chat`. Runs every time the user sends a chat message.

```
User Message → Context Gathering → Goals Agent → Tradeoffs Agent → Response Synthesis → Dashboard
```

| Step | Agent | Type | Purpose |
|------|-------|------|---------|
| 1 | **Context Gathering Agent** | Deterministic | Pulls balance, accounts, recent transactions, budgets, latest risk snapshot, and recent alerts from Supabase |
| 2 | **Goals Agent** | LLM (gpt-4o-mini) | Evaluates the user's question/decision against their financial goals. Computes savings capacity, debt pressure, balance runway, spending ratio. LLM generates natural language assessment |
| 3 | **Tradeoffs Agent** | LLM (gpt-4o-mini) | Analyzes spending areas for potential cuts (~40% reduction). Identifies lowest-impact adjustment. LLM generates 3 creative alternatives (what to cut, cheaper options, timing adjustments) |
| 4 | **Response Synthesis Agent** | LLM (gpt-4o-mini) | Combines goals analysis + tradeoff suggestions + full financial context + chat history into a final coherent response |

This trace is also returned and displayed in the "Chat Reasoning Loop" panel on the dashboard.

---

## Agent Details

### Risk Agent (`agents/risk_agent.py`)

Fully deterministic. No LLM calls. Evaluates:
* **Balance score** — runway in months based on spending rate
* **Budget score** — per-category spending vs limits
* **Cash flow score** — income vs expenses ratio
* **Goals score** — savings progress vs target

Outputs: `{ score, risk_level, factors: [{category, severity, detail}], recommendations: [str] }`

### Notification Agent (`agents/notification_agent.py`)

Fully deterministic. Decides whether to alert:
* Critical risk → always alert
* High risk → alert after 1-hour cooldown
* Medium risk → alert after 4-hour cooldown
* Low risk → suppress
* Checks: has actionable recommendations, not redundant with recent alerts

### Messaging Agent (`agents/messaging_agent.py`)

Uses `gpt-4o-mini`. Generates:
* SMS-style messages (2–3 sentences)
* Dashboard-style messages (more detail)
* Falls back to templated messages if no API key

### Goals Agent (`agents/goals_agent.py`)

Hybrid (deterministic math + LLM summary). Evaluates:
* Monthly savings capacity (income − expenses)
* Months to savings goal at current rate
* Debt pressure
* Balance runway (months of expenses covered)
* Spending-to-income ratio

Returns: `{ aligned: bool, goal_impacts: [...], analysis: str, summary: str }`

### Tradeoffs Agent (`agents/tradeoffs_agent.py`)

Hybrid (deterministic spending analysis + LLM alternatives). Provides:
* Top 5 spending areas ranked by amount
* Suggested 40% cut for each area with dollar amounts
* Lowest-impact adjustment (smallest meaningful cut)
* 3 LLM-generated alternatives: what to cut, cheaper options, timing changes

Returns: `{ cuts: [...], lowest_impact: str, alternatives: [str], summary: str }`

### Conversation Agent (`agents/conversation_agent.py`)

Orchestrates the chat pipeline. For each user message:
1. Builds full financial context from Supabase
2. Runs Goals Agent with the context + user message
3. Runs Tradeoffs Agent with the context + user message
4. Synthesizes a final response using all agent outputs + chat history
5. Stores both user message and assistant response in Supabase
6. Returns response + full trace array

### Orchestrator (`agents/orchestrator.py`)

Orchestrates the event pipeline. For each sync trigger:
1. Runs Nessie Sync to detect new events
2. Runs Risk Agent for full assessment
3. Runs Notification Agent to decide on alerting
4. If alert-worthy, runs Messaging Agent for natural language
5. Stores snapshot + alert records in Supabase
6. Returns all results + full trace array

---

## API Endpoints

### Users
* `POST /api/users` — Create user (creates Nessie customer + default account + Supabase record)
* `POST /api/users/login` — Login by first + last name
* `GET /api/users/<id>` — Get user
* `PUT /api/users/<id>/goals` — Set financial goals

### Accounts
* `POST /api/users/<id>/accounts` — Link new account (creates in Nessie + Supabase)
* `GET /api/users/<id>/accounts` — List accounts

### Transactions
* `GET /api/accounts/<id>/transactions` — List transactions for account
* `POST /api/accounts/<id>/transactions` — Upsert transactions
* `GET /api/users/<id>/transactions` — All transactions for user

### Budgets
* `POST /api/users/<id>/budgets` — Create/upsert budget
* `GET /api/users/<id>/budgets` — List budgets
* `DELETE /api/users/<id>/budgets/<category>` — Delete budget

### Snapshots
* `POST /api/users/<id>/snapshots` — Create snapshot
* `GET /api/users/<id>/snapshots/latest` — Latest snapshot
* `GET /api/users/<id>/snapshots` — List snapshots

### Events & Alerts
* `POST /api/users/<id>/events` — Create event
* `GET /api/users/<id>/events` — List events
* `POST /api/users/<id>/alerts` — Create alert
* `GET /api/users/<id>/alerts` — List alerts

### Chat & Messages
* `POST /api/users/<id>/chat` — Send message → runs chat pipeline → returns `{ response, trace }`
* `POST /api/users/<id>/messages` — Store raw message
* `GET /api/users/<id>/messages` — List messages

### Sync & Pipeline
* `POST /api/users/<id>/sync` — Sync one user from Nessie
* `POST /api/sync` — Sync all users
* `POST /api/users/<id>/pipeline` — Run full event pipeline → returns `{ sync, risk, notification, alert, trace }`
* `POST /api/pipeline` — Run pipeline for all users
* `GET /api/users/<id>/risk` — Risk assessment only

### Health
* `GET /api/health` — Returns `{ "status": "ok" }`

---

## Frontend Pages

### `index.html` — Sign In / Create Account

Two-tab form. Sign In looks up user by name (`POST /api/users/login`). Create Account creates a Nessie customer + Supabase user (`POST /api/users`), then redirects to `goals.html`. Auto-redirects to dashboard if `userId` exists in `localStorage`.

### `goals.html` — Financial Goals Onboarding

Form for: monthly income, required expenditures, savings goal, total debt, current savings. Saves via `PUT /api/users/<id>/goals`.

### `dashboard.html` + `dashboard.js` — Main Dashboard

Layout (two-column grid):
* **Left column:** Transaction list with total balance pill
* **Right column:** Risk gauge (animated SVG arc + score) and Agent Reasoning Loop timeline

Below the grid (split 2/5 + 3/5):
* **Chat panel:** Message bubbles + input form
* **Chat Reasoning Loop:** Animated timeline showing Goals Agent, Tradeoffs Agent, and Response Synthesis steps for each message

Key interactions:
* **"Sync & Analyze"** — triggers event pipeline, animates each trace step into the timeline, then animates the risk gauge
* **Chat** — sends message, shows typing indicator, renders response + reasoning trace
* Each trace step is expandable to show full details (goal impacts, spending cuts, alternatives, risk factors, etc.)

---

## Supabase Schema

| Table | Key Columns |
|-------|-------------|
| `users` | id, first_name, last_name, nessie_customer_id, phone, monthly_income, monthly_expenses, savings_goal, current_savings, debt |
| `accounts` | id, user_id, nessie_account_id, type, balance |
| `transactions` | id, account_id, nessie_transaction_id, type, amount, description, transaction_date |
| `budgets` | id, user_id, account_id (FK), category, amount, start_date, end_date |
| `snapshots` | id, user_id, data (JSONB), created_at |
| `events` | id, user_id, event_type, data (JSONB), processed, created_at |
| `alerts` | id, user_id, message, risk_level, channel, sent_at |
| `messages` | id, user_id, role (user/assistant), channel (web/sms), content, created_at |

---

## Design Principles

* **Deterministic logic for calculations** — risk scores, budget math, goal projections are all code, not LLM
* **LLM only for natural language** — explanation, message generation, creative alternatives
* **Full transparency** — every agent step is traced with timing, input/output summaries, and expandable details
* **Two pipelines, same trace format** — event pipeline and chat pipeline both produce trace arrays rendered identically
* **Anti-spam** — notification agent enforces cooldown periods and checks for redundancy
* **Graceful fallbacks** — all LLM agents have deterministic fallbacks if `OPENAI_API_KEY` is not set
* **Nessie as source of truth** — sync service diffs Nessie data against Supabase to detect changes

---

## Testing

### Test the event pipeline:
```bash
curl -X POST http://127.0.0.1:5001/api/users/<USER_ID>/pipeline
```

### Test the chat pipeline:
```bash
curl -X POST http://127.0.0.1:5001/api/users/<USER_ID>/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Can I afford dinner tonight?"}'
```

### Test risk assessment only:
```bash
curl http://127.0.0.1:5001/api/users/<USER_ID>/risk
```

---

## Core Responsibilities of the LLM Assistant

When generating responses, the LLM should:

1. Help users make better financial decisions in real time
2. Explain reasoning clearly and concisely
3. Provide actionable recommendations — never vague advice
4. Align decisions with user goals
5. Suggest tradeoffs and alternatives, not just "no"
6. Reference actual numbers from the financial context
7. Never fabricate data or give investment advice

### Response Structure

1. **Situation** — what's happening financially
2. **Impact** — why it matters for their goals
3. **Recommendation** — specific action to take, with alternatives

### Tone

* Supportive, not judgmental
* Clear and confident
* Practical, not theoretical
* Concise for SMS (2–3 sentences), slightly more detail for web (3–5 sentences)
