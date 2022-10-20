# FireUp
	
Python webserver to connect your UP accounts with [Firefly III](https://www.firefly-iii.org). The inspiration came from a [different project by Gustav de Prez](https://github.com/Mugl3/UP_Firefly_API_Connector). This project takes a different approach with the code written from scratch, and adds some useful features.

Expect the occasional bug at this stage. The webserver can be deployed in a Docker container. Pull requests welcome!

## Features

* Listens for new activity on your Up accounts
* Adds, deletes, and settles transactions
* Support for round-ups, transfers and quick saves.
* Supports Up categories
* Supports foreign currencies
* Accounts and balances automatically added to Firefly on first run
* Automatically creates an Up webhook on your specified endpoint if none exists

## Notes

* Up transaction IDs are save as tags in Firefly
* Up account IDs are saved as account numbers in Firefly
* If you rename an Up account, you will need to restart the server for the change to be reflected in Firefly. 
* Foreign currency amounts are appended to the transaction description 
* Does not import your past account activity.

## Setting up the webserver

### Prerequistes

* A running instance of [Firefly III](https://www.firefly-iii.org)
* [Firefly API token](https://docs.firefly-iii.org/firefly-iii/api/)
* [Up API token](https://api.up.com.au/getting_started)
* Endpoint for your webhook

### Building the image

For easy deployment, the webserver runs in a [Docker](https://docs.docker.com/engine/install/) container. To get set up, clone the repository and build the image.

```
git clone https://github.com/lo-decibel/FireUp
cd FireUp
docker build -t fireup .
```

### Configuring the webserver

In `docker-compose.env`, edit following environment variables.

```ini
WEBHOOK_URL=https://webhook.example
FIREFLY_URL=https://firefly.example
UP_TOKEN=up:yeah:ABCDEF123456
FIREFLY_TOKEN=eyABCDEF123456
WEBSERVER_PORT=5001
```

Then, fire up (pun intended) the container with

```
docker compose up -d
```

### Running without Docker

It's also possible to run the webserver without Docker. You will need a working install of Python, and you'll need to install the following packages with

```
pip install emoji requests flask waitress python-dotenv[cli]
```

Load the environment variables and run the script with

```
dotenv run python -u ./app/main.py &
```

LICENSE: CC BY-NC-SA
