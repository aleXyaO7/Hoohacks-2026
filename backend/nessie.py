import requests
import json
import os
from dotenv import load_dotenv
load_dotenv()

def query(url, data):
    api_key = os.getenv('NESSIE_API_KEY')
    if not data:
        return requests.get( 
            url + '?key={}'.format(api_key),
            headers={'content-type':'application/json'},
        )
    return requests.post( 
        url + '?key={}'.format(api_key), 
        data=json.dumps(data),
        headers={'content-type':'application/json'},
    )

def add_customer(first_name, last_name):
    url = 'http://api.nessieisreal.com/customers'
    data = {
        "first_name" : first_name,
        "last_name" : last_name,
        "address" : {
            "street_number" : "string",
            "street_name" : "string",
            "city" : "string",
            "state" : "VA",
            "zip" : "10000"
        }
    }
    response = query(url, data)
    if response.status_code == 201:
        print(f'[Debug] Customer created: {response.json()['objectCreated']['_id']}')
        return response.json()['objectCreated']['_id']
    else:
        print(f'[Debug] Failed to create customer: {first_name} {last_name} {[r for r in response]}')
        return ''
    
def get_customers():
    url = 'http://api.nessieisreal.com/customers'
    response = query(url, {})
    for i in response:
        print(i)
    return response

def add_account(id, account_type, rewards=0, balance=0):
    url = 'http://api.nessieisreal.com/customers/{}/accounts'.format(id)
    data = {
        "type" : account_type,
        "nickname" : id,
        "rewards" : rewards,
        "balance" : balance
    }
    response = query(url, data)
    if response.status_code == 201:
        print(f'[Debug] Account created: {response.json()['objectCreated']['_id']}')
        return response.json()['objectCreated']['_id']
    else:
        print(f'[Debug] Failed to create account: {id}')
        return ''
    
def delete_account(id):
    url = 'http://api.nessieisreal.com/accounts/{}'.format(id)
    response = query(url, {})
    if response.status_code == 500:
        print(f'[Debug] Account deleted: {id}')
        return True
    else:
        print(f'[Debug] Failed to create account: {id}')
        return False
    
def get_transactions(id):
    url = 'http://api.nessieisreal.com/accounts/{}/purchases'.format(id)
    response = query(url, {})
    if response.status_code == 200:
        print('[Debug] Queried transactions')
    else:
        print(f'[Debug] Failed to query transactions {[r for r in response]}')
    return response.json()
    
def add_transaction(id, merchant_id, description, amount, date):
    url = 'http://api.nessieisreal.com/accounts/{}/purchases'.format(id)
    data = {
        "merchant_id" : merchant_id,
        "medium" : "balance",
        "purchase_date" : date,
        "amount" : amount,
        "status" : "completed",
        "description" : description
    }
    response = query(url, data)
    if response.status_code == 201:
        print('[Debug] Created transaction')
        return True
    else:
        print(f'[Debug] Failed to create transaction {[r for r in response]}')
        return False

