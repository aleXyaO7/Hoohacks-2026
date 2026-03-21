import { NextResponse } from "next/server";
import { plaidClient } from "@/lib/plaid";
import { plaidState } from "@/lib/plaidState";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const publicToken = body?.public_token as string | undefined;

    if (!publicToken) {
      return NextResponse.json(
        { error: "public_token is required" },
        { status: 400 }
      );
    }

    const exchangeResponse = await plaidClient.itemPublicTokenExchange({
      public_token: publicToken,
    });

    plaidState.accessToken = exchangeResponse.data.access_token;
    plaidState.itemId = exchangeResponse.data.item_id;

    return NextResponse.json({
      ok: true,
      item_id: plaidState.itemId,
    });
  } catch (error: unknown) {
    return NextResponse.json(
      { error: "Failed to exchange public token", details: String(error) },
      { status: 500 }
    );
  }
}
