# Shopify import/export tool

Simple Flask app for:

- updating prices in Shopify
- updating stock in Shopify
- exporting products as JSON
- exporting products as CSV
- using everything through a local browser GUI

## Local GUI

The main way to use the app is through the local browser interface.

Open:

```text
http://localhost:8000/
```

Preview:

![Shopify import/export tool preview](Preview.png)

## What you need

- Python `3.11+`
- a `Shopify Admin API access token`
- a `.env` file

Recommended Shopify scopes:

- `read_products`
- `write_products`
- `read_inventory`
- `write_inventory`

## Configuration

1. Create `.env` from `.env.example`
2. Fill in your real values

Example:

```env
SHOP_DOMAIN=survivalprep-2.myshopify.com
SHOPIFY_ACCESS_TOKEN=shpat_xxx
DEFAULT_LOCATION_ID=1234567890
PORT=8000
```

## Quick start

### Windows

Start:

```powershell
.\start_app.ps1
```

Stop:

```powershell
.\stop_app.ps1
```

Or double-click:

- `launch_app.bat`
- `stop_app.bat`

### macOS

First time only:

```bash
chmod +x start_app.sh stop_app.sh launch_app.command stop_app.command
```

Start:

```bash
./start_app.sh
```

Stop:

```bash
./stop_app.sh
```

Or double-click:

- `launch_app.command`
- `stop_app.command`

## Manual start

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

### Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python app.py
```

## What the start scripts do

- create `.venv` if it is missing
- install dependencies
- stop any old app instance on the app port
- start the app
- save the PID in `logs/app.pid`
- open the browser automatically

On macOS the scripts use:

- `python3`
- `lsof`
- `curl`
- `open`

## What you can do in the app

- use the tool from the GUI without sending manual requests if you do not want to
- check configuration status through `Health`
- run `Update Price`
- run `Update Stock`
- preview product exports inside the UI
- download CSV
- filter, sort, and paginate the table

## Telegram Bot

You can control the app remotely through a Telegram bot using polling.

The Telegram bot is optional. The app still works normally from the browser UI even if you do not configure Telegram.

### What the bot can do

- update stock with `/stock SKU CANTITATE`
- update price with `/price SKU PRET`
- check basic status with `/health`
- list exported products in chat with `/products`
- open product pages directly from the product names in `/products`

### How it works

- the Flask app starts a background Telegram polling worker automatically
- the bot starts only when both `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALLOWED_CHAT_IDS` are set
- only the listed chat IDs are allowed to execute commands
- no public webhook or public domain is required

### Step 1: Create the bot in Telegram

1. Open Telegram
2. Search for `@BotFather`
3. Send:

```text
/newbot
```

4. Choose a bot name
5. Choose a username that ends in `bot`
6. Copy the token BotFather gives you

The token looks similar to:

```text
1234567890:ABCDEF_your_real_token_here
```

### Step 2: Start a chat with your bot

Open your bot in Telegram and send:

```text
/start
```

This is important because Telegram usually does not create message updates for your private chat until you send the bot a first message.

### Step 3: Find your chat ID

After you have sent `/start`, open this URL in your browser, replacing the token with your real one:

```text
https://api.telegram.org/botYOUR_TELEGRAM_BOT_TOKEN/getUpdates
```

Look for a section similar to:

```json
{
  "message": {
    "chat": {
      "id": 123456789,
      "type": "private"
    }
  }
}
```

Use that `chat.id` value as `TELEGRAM_ALLOWED_CHAT_IDS`.

Notes:

- for a private chat, the chat ID is usually a positive number
- for a group, the chat ID is often a negative number
- if `getUpdates` returns an empty list, send `/start` again and retry
- if the app is already running with Telegram polling enabled, it may consume updates immediately; in that case stop the app first, send `/start`, then call `getUpdates`

### Step 4: Add Telegram values to `.env`

Add these values to your real `.env` file:

```env
TELEGRAM_BOT_TOKEN=1234567890:your_telegram_bot_token
TELEGRAM_ALLOWED_CHAT_IDS=123456789
```

If you want to allow multiple chats:

```env
TELEGRAM_ALLOWED_CHAT_IDS=123456789,-1009876543210
```

The environment variables available in `.env.example` are:

```env
SHOP_DOMAIN=your-store.myshopify.com
SHOPIFY_ACCESS_TOKEN=shpat_your_admin_api_access_token
DEFAULT_LOCATION_ID=1234567890
PORT=8000
TELEGRAM_BOT_TOKEN=1234567890:your_telegram_bot_token
TELEGRAM_ALLOWED_CHAT_IDS=123456789
```

### Step 5: Restart the app

After updating `.env`, restart the app:

```bash
./stop_app.sh
./start_app.sh
```

When the bot starts correctly, the app logs will include a line similar to:

```text
Telegram bot polling started.
```

### Supported commands

- `/stock SKU CANTITATE`
- `/price SKU PRET`
- `/products` for product list directly in chat
- `/health`
- `/help`

### Telegram examples

```text
/stock ABC-123 25
/price ABC-123 149.99
/products
/health
```

Expected behavior:

- `/stock ABC-123 25` updates available stock for SKU `ABC-123`
- `/price ABC-123 149.99` updates the Shopify variant price
- `/products` sends the product list directly in Telegram chat
- product names inside `/products` are clickable links to the product pages
- `/health` confirms that the bot can see the configured store and default location

### Troubleshooting

If the bot does not respond:

- verify that `TELEGRAM_BOT_TOKEN` is correct
- verify that `TELEGRAM_ALLOWED_CHAT_IDS` matches your actual chat ID
- make sure you sent `/start` to the bot at least once
- restart the app after changing `.env`
- check the terminal or `logs/flask.err.log` for Telegram polling errors

If `getUpdates` returns no messages:

- stop the app first
- send `/start` again to the bot
- call `getUpdates` again

If the bot replies with `Chat neautorizat pentru acest bot.`:

- your `TELEGRAM_ALLOWED_CHAT_IDS` value is missing or incorrect
- update `.env` and restart the app

Typical flow:

- start the app
- open the GUI in the browser
- update prices or stock directly from the interface
- use the endpoints only if you want external integrations or Postman testing

## Endpoints

- `GET /health`
- `POST /incoming/update-price`
- `POST /incoming/update-stock`
- `GET /outgoing/products.json`
- `GET /outgoing/products.csv`

## Quick examples

### Update price by SKU

```bash
curl -X POST http://localhost:8000/incoming/update-price \
  -H "Content-Type: application/json" \
  -d '{"sku":"ABC-123","price":"149.99"}'
```

### Update stock by SKU

```bash
curl -X POST http://localhost:8000/incoming/update-stock \
  -H "Content-Type: application/json" \
  -d '{"sku":"ABC-123","available":25}'
```

### Export JSON

```bash
curl http://localhost:8000/outgoing/products.json
```

### Export CSV

```bash
curl http://localhost:8000/outgoing/products.csv -o products.csv
```

## Notes

- SKU lookup matches exactly on `variant.sku`
- `manufacturer = vendor`
- `category = product_type`
- `product_url = https://{SHOP_DOMAIN}/products/{handle}`
- `image_url = first available image`
- if `location_id` is missing, the app uses `DEFAULT_LOCATION_ID`
