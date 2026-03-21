from backend.nessie import *
from backend.agents.agent import generate

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