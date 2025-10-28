# Galaxy Tab S11 Ultra — Discord Sale Tracker

This repo checks prices on a few retailer product pages for the **Samsung Galaxy Tab S11 Ultra** and posts to a **Discord channel** via webhook when:
- the price changes, or
- it drops to or below your `desired_price`.

## Quick Start

### 1) Create a Discord Webhook
1. In Discord, right‑click the channel → **Edit Channel** → **Integrations** → **Webhooks** → **New Webhook**.
2. Copy the **Webhook URL** (keep it secret).

### 2) Configure the retailers
Edit `retailers.yaml`. Each entry needs a `name` and `url`. Optionally set `desired_price`.
Starter entries are included for Samsung US and Best Buy. Add or remove as needed.

### 3) Run locally
```bash
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/...."  # set your webhook
python tracker.py
```

The script will print and/or post any detected price change or threshold hit. State is stored in `prices_state.json` to avoid duplicate alerts.

### 4) Run on a schedule with GitHub Actions
1. Create a new GitHub repo and push these files.
2. In the repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**:
   - Name: `DISCORD_WEBHOOK_URL`
   - Value: your webhook URL
3. The included workflow runs **every 3 hours**. You can also trigger it manually via **Actions → Run workflow**.

### Notes / Tips
- Amazon listings vary by region/seller; if they cause noise, delete those entries.
- If you want alerts **only when price <= X**, set `desired_price`. If omitted, **any price change** will alert.
- You can add **Costco, Walmart, Target, B&H,** etc. Just paste the product URL in `retailers.yaml`.
- If a site blocks scraping, consider using that retailer's **deal alerts** or remove it from the list.

### Caveats
- Retailer pages change often; the parser favors JSON‑LD schema prices and falls back to patterns like `$1,199.99`. It’s intentionally conservative (filters outside $300–$3000).
- This is a lightweight checker, not a full scraping framework. It works well for a handful of pages at modest intervals.

---

**Security:** keep your Discord webhook secret. If it leaks, rotate it in Discord and update the secret.