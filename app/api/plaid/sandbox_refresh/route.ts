import { NextResponse } from "next/server";
import { plaidClient } from "@/lib/plaid";
import { plaidState } from "@/lib/plaidState";

export async function POST() {
  try {
    if (!plaidState.accessToken) {
      return NextResponse.json(
        { error: "No linked account yet. Link a Plaid sandbox account first." },
        { status: 400 }
      );
    }

    const txDate = new Date().toISOString().slice(0, 10);
    const amount = Number((Math.random() * 52 + 8).toFixed(2));
    const description = `Demo Tx ${new Date().toISOString().slice(11, 19)}`;
    const transactionId = `demo_${Date.now()}`;

    // Deterministic demo row so each click visibly adds a transaction.
    plaidState.demoTransactions.unshift({
      transaction_id: transactionId,
      name: description,
      amount,
      date: txDate,
      merchant_name: "Demo Merchant",
      pending: false,
    });

    // Best effort Plaid insertion (can be eventually consistent in sandbox).
    let plaidInserted = false;
    try {
      await plaidClient.sandboxTransactionsCreate({
        access_token: plaidState.accessToken,
        transactions: [
          {
            amount,
            description,
            date_transacted: txDate,
            date_posted: txDate,
          },
        ],
      });
      plaidInserted = true;
    } catch {
      // Keep demo deterministic even if Plaid sandbox lags/fails this endpoint.
    }

    return NextResponse.json({
      ok: true,
      appeared: true,
      plaid_inserted: plaidInserted,
      message: plaidInserted
        ? "Added demo transaction."
        : "Added demo transaction (local fallback).",
    });
  } catch (error: unknown) {
    const details =
      typeof error === "object" &&
      error !== null &&
      "response" in error &&
      typeof (error as { response?: { data?: unknown } }).response?.data !==
        "undefined"
        ? JSON.stringify((error as { response?: { data?: unknown } }).response?.data)
        : String(error);

    const plaidErrorData =
      typeof error === "object" &&
      error !== null &&
      "response" in error &&
      typeof (error as { response?: { data?: unknown } }).response?.data === "object"
        ? ((error as { response?: { data?: Record<string, unknown> } }).response?.data ??
          null)
        : null;

    const errorCode =
      plaidErrorData && typeof plaidErrorData.error_code === "string"
        ? plaidErrorData.error_code
        : null;

    if (errorCode === "ITEM_LOGIN_REQUIRED") {
      plaidState.accessToken = null;
      plaidState.itemId = null;
      return NextResponse.json(
        {
          error: "Linked item needs re-authentication. Please relink the sandbox account.",
          needs_relink: true,
          details: plaidErrorData,
        },
        { status: 409 }
      );
    }

    console.error("sandbox_refresh failed", details);

    return NextResponse.json(
      {
        error: "Failed to trigger sandbox refresh",
        details: plaidErrorData ?? details,
      },
      { status: 500 }
    );
  }
}
