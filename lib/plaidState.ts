type PlaidSessionState = {
  accessToken: string | null;
  itemId: string | null;
  demoTransactions: Array<{
    transaction_id: string;
    name: string;
    amount: number;
    date: string;
    merchant_name: string | null;
    pending: boolean;
  }>;
};

const globalForPlaid = globalThis as typeof globalThis & {
  __plaidState?: PlaidSessionState;
};

if (!globalForPlaid.__plaidState) {
  globalForPlaid.__plaidState = {
    accessToken: null,
    itemId: null,
    demoTransactions: [],
  };
}

export const plaidState = globalForPlaid.__plaidState;
