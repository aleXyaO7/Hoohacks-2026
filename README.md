# Plaid Sandbox Dashboard (No DB)

Minimal Next.js app that lets you:

- Link a Plaid Sandbox account
- View recent transactions
- Add demo transactions on demand for demos

## Prerequisites

- Node.js 20+ (Node 22 recommended)
- A Plaid Sandbox account with `client_id` and `secret`

## 1) Install

```bash
npm install
```

## 2) Configure environment variables

```bash
cp .env.example .env.local
```

Then set these values in `.env.local`:

```env
PLAID_CLIENT_ID=your_plaid_client_id
PLAID_SECRET=your_plaid_sandbox_secret
PLAID_ENV=sandbox
```

## 3) Start the app

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## 4) Use the dashboard

1. Click **Link Sandbox Account**
2. Complete Plaid Link with sandbox credentials
3. Click **Refresh Transactions** to load baseline data
4. Click **Add Demo Transaction** to insert a new transaction row

Each click on **Add Demo Transaction** creates a new visible demo transaction.

## Helpful commands

```bash
npm run lint
npm run build
```

## Troubleshooting

- **`ITEM_LOGIN_REQUIRED` error**
  - Relink the sandbox account. The app will clear stale access-token state automatically.
- **No DB behavior**
  - This project has no database yet.
  - Access token and demo transactions are stored in server memory (`lib/plaidState.ts`).
  - Restarting the dev server clears that state.
