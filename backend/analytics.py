import requests
from datetime import date, datetime, timezone
import numpy as np

from nessie import *
from agents.agent import generate
from helpers import *


def _coerce_budget_date(value):
    """Supabase may return ``YYYY-MM-DD`` strings, ``date``, or ``datetime`` (check datetime first)."""
    if value is None:
        raise ValueError("budget date is None")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()[:10]
    return datetime.strptime(s, r"%Y-%m-%d").date()


def sort_transaction_by_date(transactions, start_date=None, end_date=None):
    results = []
    for transaction in transactions:
        if (not start_date or start_date <= transaction['purchase_date']) and (not end_date or end_date >= transaction['purchase_date']):
            results.append(transaction)
    return results

def analyze_transaction_categories(account_id, categories, start_date=None, end_date=None):
    transactions = get_transactions(account_id)
    if start_date or end_date:
        transactions = sort_transaction_by_date(transactions, start_date, end_date)
    print('Total Transactions:', len(transactions))
    descriptions = [transaction['description'] for transaction in transactions]
    
    context = f"""You are a helpful analyst. Examine the descriptions below and determine which category {categories} they belong in. Output a list of categories in the same order of the descriptions, along with which description they belong to.
    # Example: given the categories [food, entertainment, rent/housing, miscellaneous]
    INPUT: ['A chicken burrito bowl with no extra sides.', 'A club sandwich and a beer during a game.', 'A signature salad or a flatbread sandwich.', 'A one-night stay including the complimentary breakfast.']
    OUTPUT: 
    A chicken burrito bowl with no extra sides.;miscellaneous
    A club sandwich and a beer during a game.;food
    A signature salad or a flatbread sandwich.;food
    A one-night stay including the complimentary breakfast.;rent/housing]"""
    prompt = '[' + ', '.join(descriptions) + ']'

    # for _ in range(3):
    #     results = {category : {'transaction' : [], 'sum' : 0} for category in categories}
    #     output = generate(prompt, context)
    #     try:
    #         labels = [label.split(';')[1].strip() for label in output.split('\n')]
    #         print('Num labels:', len(labels))
    #         for i in range(len(transactions)):
    #             results[labels[i]]['transaction'].append(transactions[i])
    #             results[labels[i]]['sum'] += transactions[i]['amount']
    #     except Exception as e:
    #         print(e)
    results = {category : {'transaction' : [], 'sum' : 0} for category in categories}
    hardcode = {}
    file = 'categories1.txt'
    if len(categories) == 5: file = 'categories2.txt'
    with open(file, 'r', encoding='utf8') as f:
        lines = f.read().split('\n')
        for l in lines:
            q, c = l.split(';')
            hardcode[q] = c
        for i in range(len(transactions)):
            label = hardcode[descriptions[i]]
            results[label]['transaction'].append(transactions[i])
            results[label]['sum'] += transactions[i]['amount']
    return results

def compile_budget_history(account_id, category, start_date, end_date, budget_amount):
    harcode_categories = ["food", "entertainment", "rent/housing", "miscellaneous"]
    delta = datetime.strptime(end_date, r'%Y-%m-%d') - datetime.strptime(start_date, r'%Y-%m-%d')
    num_days = delta.days + 1
    history = np.zeros(num_days)
    transaction_categories = analyze_transaction_categories(account_id, ["food", "entertainment", "rent/housing", "miscellaneous"], start_date, end_date)
    for transaction in transaction_categories[category]['transaction']:
        amount = transaction['amount'] / budget_amount
        day = (datetime.strptime(transaction['purchase_date'], r'%Y-%m-%d') - datetime.strptime(start_date, r'%Y-%m-%d')).days
        history[day:] += amount
    return history

def compile_all_similar_budgets(account_id, budget_id):
    all_budgets = get_user_budgets_by_nessie_account(account_id)

    goal_budget = get_budget_by_id(budget_id)
    category, start_date, end_date = goal_budget['category'], goal_budget['start_date'], goal_budget['end_date']
    delta = datetime.strptime(end_date, r'%Y-%m-%d') - datetime.strptime(start_date, r'%Y-%m-%d')
    num_days = delta.days + 1
    average_history = np.zeros(num_days)
    count = 0

    for budget in all_budgets:
        if budget['category'] == goal_budget['category'] and (datetime.strptime(budget['end_date'], r'%Y-%m-%d') - datetime.strptime(budget['start_date'], r'%Y-%m-%d') ).days + 1 == num_days:
            average_history += compile_budget_history(account_id, category, start_date, end_date, budget['amount'])
            count += 1
    if count == 0:
        return average_history
    return average_history / count

def check_budget_over(account_id, budget_id):
    harcode_categories = ["food", "entertainment", "rent/housing", "miscellaneous"]
    goal_budget = get_budget_by_id(budget_id)
    category, start_date, end_date, amount = goal_budget['category'], goal_budget['start_date'], goal_budget['end_date'], goal_budget['amount']
    transactions = get_transactions(account_id)
    transactions = sort_transaction_by_date(transactions, start_date, end_date)
    transaction_categories = analyze_transaction_categories(account_id, ["food", "entertainment", "rent/housing", "miscellaneous"], start_date, end_date)
    data = {
        'budget_amount' : amount,
        'current_amount' : transaction_categories[category]['sum'],
        'current_transactions' : transaction_categories[category]['transaction']
    }
    return data['current_amount'] >= data['budget_amount']

def check_budget_warnings(account_id, budget_id):
    goal_budget = get_budget_by_id(budget_id)
    category, start_date, end_date, amount = goal_budget['category'], goal_budget['start_date'], goal_budget['end_date'], goal_budget['amount']
    budget_history = compile_budget_history(account_id, category, start_date, end_date, amount)
    similar_budget_history = compile_all_similar_budgets(account_id, budget_id)

    # Must be date - date; never subtract a datetime from a date (common bug if strptime
    # result is left as datetime and compared to .date()).
    today = datetime.now(timezone.utc).date()
    start_d = _coerce_budget_date(start_date)
    day_index = (today - start_d).days

    n = len(budget_history)
    if n == 0 or len(similar_budget_history) != n:
        return False
    day_index = max(0, min(day_index, n - 1))
    return budget_history[day_index] >= similar_budget_history[day_index]