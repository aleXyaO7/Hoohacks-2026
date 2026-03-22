import requests, datetime
from datetime import timezone
import numpy as np

from backend.nessie import *
from backend.agents.agent import generate
from backend.helpers import *

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

    for _ in range(3):
        results = {category : {'transaction' : [], 'sum' : 0} for category in categories}
        output = generate(prompt, context)
        try:
            labels = [label.split(';')[1].strip() for label in output.split('\n')]
            for i in range(len(transactions)):
                results[labels[i]]['transaction'].append(transactions[i])
                results[labels[i]]['sum'] += transactions[i]['amount']
        except Exception as e:
            print(e)
    return results

def compile_budget_history(account_id, category, start_date, end_date, budget_amount):
    delta = datetime.datetime.strptime(end_date, r'%Y-%m-%d') - datetime.datetime.strptime(start_date, r'%Y-%m-%d')
    num_days = delta.days + 1
    history = np.zeros(num_days)
    transaction_categories = analyze_transaction_categories(account_id, [category, 'not ' + category], start_date, end_date)
    for transaction in transaction_categories[category]['transaction']:
        amount = transaction['amount'] / budget_amount
        day = (datetime.datetime.strptime(transaction['purchase_date'], r'%Y-%m-%d') - datetime.datetime.strptime(start_date, r'%Y-%m-%d')).days
        history[day:] += amount
    return history

def compile_all_similar_budgets(account_id, budget_id):
    all_budgets = get_user_budgets_by_nessie_account(account_id)

    goal_budget = get_budget_by_id(budget_id)
    category, start_date, end_date = goal_budget['category'], goal_budget['start_date'], goal_budget['end_date']
    delta = datetime.datetime.strptime(end_date, r'%Y-%m-%d') - datetime.datetime.strptime(start_date, r'%Y-%m-%d')
    num_days = delta.days + 1
    average_history = np.zeros(num_days)
    count = 0

    for budget in all_budgets:
        if budget['category'] == goal_budget['category'] and (datetime.datetime.strptime(budget['end_date'], r'%Y-%m-%d') - datetime.datetime.strptime(budget['start_date'], r'%Y-%m-%d') ).days + 1 == num_days:
            average_history += compile_budget_history(account_id, category, start_date, end_date, budget['amount'])
            count += 1
    return average_history / count

def check_budget_over(account_id, budget_id):
    goal_budget = get_budget_by_id(budget_id)
    category, start_date, end_date, amount = goal_budget['category'], goal_budget['start_date'], goal_budget['end_date'], goal_budget['amount']
    transactions = get_transactions(account_id)
    transactions = sort_transaction_by_date(transactions, start_date, end_date)
    transaction_categories = analyze_transaction_categories(account_id, [category, 'not ' + category], start_date, end_date)
    return {
        'budget_amount' : amount,
        'current_amount' : transaction_categories[category]['sum'],
        'current_transactions' : transaction_categories[category]['transaction']
    }

def check_budget_warnings(account_id, budget_id):
    goal_budget = get_budget_by_id(budget_id)
    category, start_date, end_date, amount = goal_budget['category'], goal_budget['start_date'], goal_budget['end_date'], goal_budget['amount']
    budget_history = compile_budget_history(account_id, category, start_date, end_date, amount)
    similar_budget_history = compile_all_similar_budgets(account_id, budget_id)

    delta = datetime.datetime.now(timezone.utc) - start_date
    return budget_history[delta.days] <= similar_budget_history[delta.days]
