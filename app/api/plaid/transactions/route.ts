import { NextResponse } from "next/server";
import { plaidClient } from "@/lib/plaid";
import { plaidState } from "@/lib/plaidState";

export async function GET() {
  try {
    if (!plaidState.accessToken) {
      return NextResponse.json(
        { error: "No linked account yet. Link a Plaid sandbox account first." },
        { status: 400 }
      );
    }

    const endDate = new Date();
    const startDate = new Date();
    startDate.setDate(endDate.getDate() - 30);

    const response = await plaidClient.transactionsGet({
      access_token: plaidState.accessToken,
      start_date: startDate.toISOString().slice(0, 10),
      end_date: endDate.toISOString().slice(0, 10),
      options: {
        count: 50,
      },
    });

    const mergedTransactions = [
      ...plaidState.demoTransactions,
      ...response.data.transactions,
    ].sort((a, b) => b.date.localeCompare(a.date));

    return NextResponse.json({
      accounts: response.data.accounts,
      transactions: mergedTransactions,
      total_transactions:
        response.data.total_transactions + plaidState.demoTransactions.length,
    });
  } catch (error: unknown) {
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
          transactions: plaidState.demoTransactions,
        },
        { status: 409 }
      );
    }

    return NextResponse.json(
      {
        error: "Failed to fetch transactions",
        details: plaidErrorData ?? String(error),
      },
      { status: 500 }
    );
  }
}
