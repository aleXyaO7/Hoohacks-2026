"""Seed transactions for a Nessie account.

Usage:
    cd Hoohacks-2026
    .venv/bin/python backend/seed_transactions.py
"""

import sys
import os
import random

sys.path.insert(0, os.path.dirname(__file__))

from nessie import add_transaction, query
from dotenv import load_dotenv

load_dotenv()

ACCOUNT_ID = "69bf074695150878ea0006d3"
NESSIE_BASE = "http://api.nessieisreal.com"

# First, get or create a merchant
def get_or_create_merchant():
    resp = query(f"{NESSIE_BASE}/merchants", None)
    merchants = resp.json()
    if merchants:
        return merchants[0]["_id"]

    # Create one if none exist
    resp = query(f"{NESSIE_BASE}/merchants", {
        "name": "General Store",
        "category": "food",
        "address": {
            "street_number": "1",
            "street_name": "Main St",
            "city": "Charlottesville",
            "state": "VA",
            "zip": "22903",
        },
        "geocode": {"lat": 0, "lng": 0},
    })
    if resp.status_code == 201:
        return resp.json()["objectCreated"]["_id"]
    print(f"Failed to create merchant: {resp.text}")
    return None


transactions = [
    ("Chipotle", 12.50, "2024-01-15"),
    ("Walmart Groceries", 67.23, "2024-01-22"),
    ("Starbucks", 6.75, "2024-02-03"),
    ("Uber Eats", 34.99, "2024-02-14"),
    ("Trader Joes", 52.10, "2024-02-28"),
    ("McDonalds", 9.80, "2024-03-05"),
    ("Whole Foods", 88.42, "2024-03-18"),
    ("Dominos Pizza", 22.99, "2024-04-01"),
    ("Costco", 145.30, "2024-04-12"),
    ("Panera Bread", 15.60, "2024-04-25"),
    ("Target Groceries", 43.15, "2024-05-08"),
    ("Chick-fil-A", 11.25, "2024-05-19"),
    ("Amazon Fresh", 76.80, "2024-06-02"),
    ("Subway", 8.99, "2024-06-15"),
    ("Kroger", 61.44, "2024-07-01"),
    ("Taco Bell", 14.30, "2024-07-20"),
    ("Aldi", 38.90, "2024-08-05"),
    ("Five Guys", 18.75, "2024-08-22"),
    ("Safeway", 55.60, "2024-09-10"),
    ("Popeyes", 13.20, "2024-09-28"),
    ("Whole Foods", 92.15, "2024-10-05"),
    ("Chipotle", 13.75, "2024-10-18"),
    ("Walmart Groceries", 71.00, "2024-11-02"),
    ("Starbucks", 7.25, "2024-11-15"),
    ("Costco", 132.50, "2024-12-01"),
    ("Uber Eats", 28.99, "2024-12-14"),
    ("Trader Joes", 48.30, "2024-12-28"),
]


def main():
    merchant_id = get_or_create_merchant()
    if not merchant_id:
        print("No merchant available, aborting.")
        return

    print(f"Using merchant_id: {merchant_id}")
    print(f"Adding {len(transactions)} transactions to account {ACCOUNT_ID}\n")

    success = 0
    for desc, amount, date in transactions:
        ok = add_transaction(ACCOUNT_ID, merchant_id, desc, amount, date)
        if ok:
            success += 1
            print(f"  ${amount:>7.2f}  {date}  {desc}")
        else:
            print(f"  FAILED: {desc} ({date})")

    print(f"\nDone — {success}/{len(transactions)} transactions created.")


if __name__ == "__main__":
    main()
