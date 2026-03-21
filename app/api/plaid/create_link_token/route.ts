import { NextResponse } from "next/server";
import { plaidClient, plaidDefaults } from "@/lib/plaid";

export async function POST() {
  try {
    const response = await plaidClient.linkTokenCreate({
      user: { client_user_id: "demo-user" },
      client_name: plaidDefaults.clientName,
      products: plaidDefaults.products,
      country_codes: plaidDefaults.countryCodes,
      language: plaidDefaults.language,
    });

    return NextResponse.json({ link_token: response.data.link_token });
  } catch (error: unknown) {
    return NextResponse.json(
      { error: "Failed to create link token", details: String(error) },
      { status: 500 }
    );
  }
}
