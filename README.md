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
http://localhost:5000/
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
PORT=5000
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
curl -X POST http://localhost:5000/incoming/update-price \
  -H "Content-Type: application/json" \
  -d '{"sku":"ABC-123","price":"149.99"}'
```

### Update stock by SKU

```bash
curl -X POST http://localhost:5000/incoming/update-stock \
  -H "Content-Type: application/json" \
  -d '{"sku":"ABC-123","available":25}'
```

### Export JSON

```bash
curl http://localhost:5000/outgoing/products.json
```

### Export CSV

```bash
curl http://localhost:5000/outgoing/products.csv -o products.csv
```

## Notes

- SKU lookup matches exactly on `variant.sku`
- `manufacturer = vendor`
- `category = product_type`
- `product_url = https://{SHOP_DOMAIN}/products/{handle}`
- `image_url = first available image`
- if `location_id` is missing, the app uses `DEFAULT_LOCATION_ID`
