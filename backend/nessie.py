import requests
import json
import os
from dotenv import load_dotenv
load_dotenv()

def query(url, data):
    api_key = os.getenv('NESSIE_API_KEY')
    return requests.post( 
        url + '?key={}'.format(api_key), 
        data=json.dumps(data),
        headers={'content-type':'application/json'},
    )

def add_account(id, account_type, rewards=0, balance=0):
    url = 'http://api.nessieisreal.com/customers/{}/accounts'.format(id)
    data = {
        "type" : account_type,
        "nickname" : id,
        "rewards" : rewards,
        "balance" : balance,	
	    "account_number": id
    }
    response = query(url, data)
    if response.status_code == 201:
        print('[Debug] Account created')
        return True
    else:
        print('[Debug] Failed to create account')
        return False
    
def delete_account(id):
    url = 'http://api.nessieisreal.com/accounts/{}'.format(id)
    response = query(url, {})
    if response.status_code == 500:
        print('[Debug] Account created')
    else:
        print('[Debug] Failed to create account')
    return response
    
def get_transactions(id):
    url = 'http://api.nessieisreal.com/accounts/{}/purchases'.format(id)
    response = query(url, {})
    if response.status_code == 500:
        print('[Debug] Queried transactions')
        return True
    else:
        print('[Debug] Failed to query transactions')
        return False
    
def create_transaction(id, merchant_id, description, amount, date):
    url = 'http://api.nessieisreal.com/accounts/{}/purchases'.format(id)
    data = {
        "merchant_id" : merchant_id,
        "medium" : "balance",
        "purchase_date" : date,
        "amount" : amount,
        "status" : "complete",
        "description" : description
    }
    response = query(url, data)
    if response.status_code == 500:
        print('[Debug] Created transaction')
        return True
    else:
        print('[Debug] Failed to create transaction')
        return False

