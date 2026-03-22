"""Import all Nessie customers and their accounts into Supabase.

Usage:
    cd Hoohacks-2026
    .venv/bin/python backend/import_nessie.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

import requests
from dotenv import load_dotenv
from db import get_supabase

load_dotenv()

NESSIE_BASE = "http://api.nessieisreal.com"
API_KEY = os.getenv("NESSIE_API_KEY")


def get_nessie(path):
    resp = requests.get(f"{NESSIE_BASE}{path}?key={API_KEY}")
    resp.raise_for_status()
    return resp.json()


def main():
    sb = get_supabase()

    # 1) Fetch all Nessie customers
    customers = get_nessie("/customers")
    print(f"Found {len(customers)} Nessie customer(s)\n")

    for cust in customers:
        nessie_id = cust["_id"]
        first = cust.get("first_name", "")
        last = cust.get("last_name", "")
        print(f"  Customer: {first} {last} (nessie_id={nessie_id})")

        # Check if already in Supabase
        existing = (
            sb.table("users")
            .select("id")
            .eq("nessie_customer_id", nessie_id)
            .execute()
        )
        if existing.data:
            user_id = existing.data[0]["id"]
            print(f"    Already in Supabase (user_id={user_id}), skipping user insert")
        else:
            # Insert user
            user_row = {
                "first_name": first,
                "last_name": last,
                "nessie_customer_id": nessie_id,
            }
            result = sb.table("users").insert(user_row).execute()
            user_id = result.data[0]["id"]
            print(f"    Created Supabase user (user_id={user_id})")

        # 2) Fetch Nessie accounts for this customer
        accounts = get_nessie(f"/customers/{nessie_id}/accounts")
        print(f"    Found {len(accounts)} account(s)")

        for acct in accounts:
            nessie_acct_id = acct["_id"]

            # Check if already in Supabase
            existing_acct = (
                sb.table("accounts")
                .select("id")
                .eq("nessie_account_id", nessie_acct_id)
                .execute()
            )
            if existing_acct.data:
                print(f"      Account {acct['type']} ({nessie_acct_id}) already exists, skipping")
                continue

            acct_row = {
                "user_id": user_id,
                "nessie_account_id": nessie_acct_id,
                "type": acct.get("type", "Checking"),
                "balance": acct.get("balance", 0),
            }
            sb.table("accounts").insert(acct_row).execute()
            print(f"      Imported account: {acct['type']} — ${acct.get('balance', 0):,.2f} ({nessie_acct_id})")

    print("\nDone!")


if __name__ == "__main__":
    main()
