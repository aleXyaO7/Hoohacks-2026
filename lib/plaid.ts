import {
  Configuration,
  PlaidApi,
  PlaidEnvironments,
  Products,
  CountryCode,
} from "plaid";

const PLAID_CLIENT_ID = process.env.PLAID_CLIENT_ID;
const PLAID_SECRET = process.env.PLAID_SECRET;
const PLAID_ENV = process.env.PLAID_ENV ?? "sandbox";

if (!PLAID_CLIENT_ID || !PLAID_SECRET) {
  // This intentionally throws at startup so the app fails fast
  // when required Plaid credentials are missing.
  console.warn("PLAID_CLIENT_ID or PLAID_SECRET is missing.");
}

const environmentMap: Record<string, string> = {
  sandbox: PlaidEnvironments.sandbox,
  development: PlaidEnvironments.development,
  production: PlaidEnvironments.production,
};

const configuration = new Configuration({
  basePath: environmentMap[PLAID_ENV] ?? PlaidEnvironments.sandbox,
  baseOptions: {
    headers: {
      "PLAID-CLIENT-ID": PLAID_CLIENT_ID ?? "",
      "PLAID-SECRET": PLAID_SECRET ?? "",
      "Plaid-Version": "2020-09-14",
    },
  },
});

export const plaidClient = new PlaidApi(configuration);

export const plaidDefaults = {
  clientName: "Plaid Sandbox Dashboard",
  language: "en",
  countryCodes: [CountryCode.Us],
  products: [Products.Transactions],
};
