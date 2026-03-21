"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePlaidLink } from "react-plaid-link";

type PlaidTransaction = {
  transaction_id: string;
  name: string;
  amount: number;
  date: string;
  merchant_name: string | null;
  pending: boolean;
};

export default function PlaidDashboard() {
  const [linkToken, setLinkToken] = useState<string | null>(null);
  const [linked, setLinked] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string>("");
  const [transactions, setTransactions] = useState<PlaidTransaction[]>([]);

  const fetchLinkToken = useCallback(async () => {
    const res = await fetch("/api/plaid/create_link_token", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error ?? "Failed to create link token");
    setLinkToken(data.link_token);
  }, []);

  const fetchTransactions = useCallback(async () => {
    setLoading(true);
    setMessage("");
    try {
      const res = await fetch("/api/plaid/transactions");
      const data = await res.json();
      if (!res.ok) {
        if (data.needs_relink) {
          setLinked(false);
          await fetchLinkToken();
        }
        throw new Error(data.error ?? "Failed to fetch transactions");
      }
      const sorted = [...(data.transactions ?? [])].sort((a, b) =>
        b.date.localeCompare(a.date)
      );
      setTransactions(sorted);
      setMessage(`Loaded ${data.transactions?.length ?? 0} transactions.`);
    } catch (error: unknown) {
      setMessage(String(error));
    } finally {
      setLoading(false);
    }
  }, [fetchLinkToken]);

  const onSuccess = useCallback(
    async (publicToken: string) => {
      setLoading(true);
      setMessage("");
      try {
        const res = await fetch("/api/plaid/exchange_public_token", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ public_token: publicToken }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error ?? "Token exchange failed");
        setLinked(true);
        setMessage("Account linked. Fetching transactions...");
        await fetchTransactions();
      } catch (error: unknown) {
        setMessage(String(error));
      } finally {
        setLoading(false);
      }
    },
    [fetchTransactions]
  );

  const { open, ready } = usePlaidLink({
    token: linkToken ?? "",
    onSuccess,
  });

  useEffect(() => {
    fetchLinkToken().catch((err) => setMessage(String(err)));
  }, [fetchLinkToken]);

  const canLink = useMemo(() => Boolean(linkToken && ready && !loading), [linkToken, ready, loading]);

  const triggerRefresh = useCallback(async () => {
    setLoading(true);
    setMessage("");
    try {
      const res = await fetch("/api/plaid/sandbox_refresh", { method: "POST" });
      const data = await res.json();
      if (!res.ok) {
        if (data.needs_relink) {
          setLinked(false);
          await fetchLinkToken();
        }
        const detailText =
          typeof data.details === "string"
            ? data.details
            : data.details
            ? JSON.stringify(data.details)
            : "";
        const details = detailText ? ` (${detailText})` : "";
        throw new Error((data.error ?? "Failed sandbox refresh") + details);
      }
      setMessage(
        data.plaid_inserted
          ? data.message ?? "Added demo transaction."
          : data.message ?? "Added demo transaction (local fallback)."
      );
      await fetchTransactions();
    } catch (error: unknown) {
      setMessage(String(error));
    } finally {
      setLoading(false);
    }
  }, [fetchLinkToken, fetchTransactions]);

  return (
    <main className="container">
      <h1>Plaid Sandbox Dashboard</h1>
      <p>Link a Sandbox account, view recent transactions, and add demo transactions on demand.</p>

      <div className="actions">
        <button disabled={!canLink} onClick={() => open()}>
          {linked ? "Relink Sandbox Account" : "Link Sandbox Account"}
        </button>
        <button disabled={!linked || loading} onClick={fetchTransactions}>
          Refresh Transactions
        </button>
        <button disabled={!linked || loading} onClick={triggerRefresh}>
          Add Demo Transaction
        </button>
      </div>

      {message ? <p className="message">{message}</p> : null}

      <section>
        <h2>Recent Transactions</h2>
        {transactions.length === 0 ? (
          <p>No transactions loaded yet.</p>
        ) : (
          <ul className="tx-list">
            {transactions.map((tx) => (
              <li key={tx.transaction_id} className="tx-item">
                <div>
                  <strong>{tx.merchant_name ?? tx.name}</strong>
                  <span>{tx.date}</span>
                </div>
                <div>
                  <strong>${tx.amount.toFixed(2)}</strong>
                  {tx.pending ? <span>Pending</span> : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
