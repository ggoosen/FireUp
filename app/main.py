from os import getenv
from datetime import datetime
from flask import Flask, request, Response
from waitress import serve
import emoji, json, requests

webhook_url = getenv('WEBHOOK_URL') + '/webhook'
up_headers = { 'accept': 'application/json','Authorization': 'Bearer ' + getenv('UP_TOKEN') }
firefly_headers = { 'accept': 'application/json', 'Authorization': 'Bearer ' + getenv('FIREFLY_TOKEN') }
up_url = 'https://api.up.com.au/api/v1/'
firefly_url = f'{getenv("FIREFLY_URL")}/api/v1/'

def xstr(s):
	return '' if s is None else str(s)

def existsWebhook(url):
	webhooks = requests.get('{up_url}webhooks', headers=up_headers).json()['data']
	if not webhooks:
		return False
	else:
		for webhook in webhooks:
			if webhook['attributes']['url'] == url:
				return True
		return False

def getFireflyTransaction(up_id):
	url = f'{firefly_url}tags/{up_id}/transactions'
	response = requests.get(url, headers=firefly_headers).json()
	try:
		return response['data'][0]
	except:
		return None

def getFireflyAccountName(account_number):
	url = f'{firefly_url}search/accounts?query={account_number}&field=number'
	try:
		firefly_account = requests.get(url, headers=firefly_headers).json()['data'][0]
		if account_number == firefly_account['attributes']['account_number']:
			return firefly_account['attributes']['name']
		else:
			return None
	except:
		return None

def setup():
	# Check Up API connection
	if requests.get(f'{up_url}util/ping', headers=up_headers).status_code == 200:
		print ('Connected to Up API.')
	else:
		print('Could not connect to the Up API. Please check your Up token and try again.')
		exit()

	# Check Firefly connection
	try:
		firefly_connection = requests.get(f'{firefly_url}about', headers=firefly_headers).status_code
		if firefly_connection == 200:
			print('Connected to Firefly API.')
		else:
			print('Unable to connect to the Firefly API. Please check your Firefly token and try again.')
			exit()
	except:
		print('Unable to find your Firefly instance. Please check your Firefly URL and try again.')
		exit()

	# Create webhook
	if not existsWebhook(webhook_url):
		payload = {
			"data": {
				"attributes": {
					"url": webhook_url,
					"description": "Firefly"
				}
			}
		}
		print('Creating webhook.')
		requests.post(f'{up_url}webhooks', headers=up_headers, json=payload)
	else:
		print('Found webhook.')

	# Get Up accounts
	print('Fetching Up accounts.')
	up_accounts = {}
	these_accounts = requests.get(f'{up_url}accounts', headers=up_headers).json()
	for account in these_accounts['data']:	
		if account['attributes']['accountType'] == "SAVER":
			role = "savingAsset"
		else:
			role = "defaultAsset"
		
		up_accounts[account['id']] = { 
			'name': emoji.replace_emoji(account['attributes']['displayName'], replace='').lstrip(' '),
			'role': role,
			'balance': account['attributes']['balance']['value']
		}

	# Add Up accounts to Firefly if they don't exist
	for account_id in up_accounts:
		this_account_name = getFireflyAccountName(account_id)
		if not this_account_name:
			print(f'Adding account \"{up_accounts[account_id]["name"]}\" to Firefly.')
			payload = {
				"account_number": account_id,
				"name": up_accounts[account_id]['name'],
				"type": "asset",
				"account_role": up_accounts[account_id]['role'],
				"opening_balance": up_accounts[account_id]['balance'],
				"opening_balance_date": datetime.now().strftime('%Y-%m-%d'),
				"currency_code": "AUD"
			}
			request_code = requests.post(f'{firefly_url}accounts', headers=firefly_headers, json=payload).status_code
			if request_code != 200:
				print('Error creating Up account in Firefly. Does a Firefly account already exist with the same name?')
				exit()
			
		# Update account names (if they have changed)
		elif up_accounts[account_id]['name'] != this_account_name:
			print(f'Updating account \"{up_accounts[account_id]["name"]}\".')
			payload = {
				"name": up_accounts[account_id]['name']
			}
			requests.put(f'{firefly_url}accounts/{account}', headers=firefly_headers, json=payload)
	
	# Get Up categories, and add missing categories to Firefly
	up_categories = {}
	firefly_categories = []
	print('Fetching transaction categories.')

	for firefly_category in requests.get(f'{firefly_url}categories', headers=firefly_headers).json()['data']:
		firefly_categories.append(firefly_category['attributes']['name'])

	for up_category in requests.get(f'{up_url}categories', headers=up_headers).json()['data']:
		this_category = up_category['attributes']['name']
		up_categories[up_category['id']] = this_category
		if this_category not in firefly_categories:
			payload = { 'name': this_category }
			requests.post(f'{firefly_url}categories', headers=firefly_headers, json=payload)


# INCOMING WEBHOOKS
print('Ready to receive incoming events.')
app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def respond():
	data = request.json['data']
	
	event_type = data['attributes']['eventType']
	url = data['relationships']['transaction']['links']['related']
	up_transaction = requests.get(url, headers=up_headers).json()['data']
	
	if event_type == 'TRANSACTION_DELETED':
		firefly_transaction = getFireflyTransaction(up_transaction['id'])
		requests.delete(f'{firefly_url}transactions/{firefly_transaction["id"]}', headers=firefly_headers)

	if event_type == 'TRANSACTION_SETTLED':
		firefly_transaction = getFireflyTransaction(up_transaction['id'])
		entry = firefly_transaction['attributes']['transactions'][0]['description'].lstrip('[HELD] ')
		payload = {
			"transactions": [
				{
					"description": entry,
					"source_name": firefly_transaction['attributes']['transactions'][0]['source_name']
				}
			]
		}
		requests.put(f'{firefly_url}transactions/' + firefly_transaction['id'], headers=firefly_headers, json=payload)
	
	if event_type == 'TRANSACTION_CREATED':
		# GET TRANSACTION DETAILS
		this_account = up_accounts[up_transaction['relationships']['account']['data']['id']]['name']
		amount = float(up_transaction['attributes']['amount']['value'])
		raw_text = xstr(up_transaction['attributes']['rawText'])
		tags = [up_transaction['id']]
		created_at = up_transaction['attributes']['createdAt']
		descriptor = up_transaction['attributes']['description']
				
		# Deposits and withdrawals
		if not up_transaction['relationships']['transferAccount']['data']:
			if amount > 0:
				kind = 'deposit'
				source = descriptor
				target = this_account
			elif amount < 0:
				kind = 'withdrawal'
				source = this_account
				target = descriptor
		
		# Transfers, quick saves and roundups
		else:
			if descriptor.startswith('Quick save transfer to') or descriptor.startswith('Transfer to'):
				return Response(status=200)
			elif descriptor.startswith('Quick save transfer from'):
				raw_text = 'Quick Save'
			elif descriptor.startswith('Transfer from'):
				raw_text = 'Transfer'
			elif descriptor == 'Round Up':
				raw_text = 'Round Up'
			tags.append(raw_text)
			kind = 'transfer'
			source = up_accounts[up_transaction['relationships']['transferAccount']['data']['id']]['name']
			target = this_account			
		
		# Entry name (e.g. "[HELD] My transaction (message) 40 USD")
		entry = ''
		if up_transaction['attributes']['status'] == 'HELD':
			entry += '[HELD] '
		entry += raw_text
		message = xstr(up_transaction['attributes']['message'])
		if message:
			if raw_text:
				message = f'({message})'
			entry += ' ' + message
		if up_transaction['attributes']['foreignAmount']:
			foreign_amount = f' {up_transaction["attributes"]["foreignAmount"]["value"]} {up_transaction["attributes"]["foreignAmount"]["currencyCode"]}'
			entry += foreign_amount
		
		# Category
		if up_transaction['relationships']['category']['data']:
			category = up_categories[up_transaction['relationships']['category']['data']['id']]
		else:
			category = None

		# ADD TRANSACTION TO FIREFLY
		payload = {
			"transactions": [
				{
					"amount": str(abs(amount)),
					"description": entry,
					"source_name": source,
					"destination_name": target,
					"category_name": category,
					"type": kind,
					"tags": tags,
					"date": created_at
				}
			]
		}
		requests.post(f'{firefly_url}transactions', headers=firefly_headers, json=payload)

	return Response(status=200)

if __name__ == '__main__':
	setup()
	serve(app, host='0.0.0.0', port=5001)