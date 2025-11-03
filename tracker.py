import os
import re
import json
import time
import math
import hashlib
import logging
from typing import Dict, Any, List, Tuple

import requests
from bs4 import BeautifulSoup
import yaml

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()

STATE_FILE = os.environ.get("STATE_FILE", "prices_state.json")
CONFIG_FILE = os.environ.get("CONFIG_FILE", "retailers.yaml")
USER_AGENT = os.environ.get("USER_AGENT", "Mozilla/5.0 (compatible; TabS11UltraPriceBot/1.0; +https://example.local)")


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_state(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return {}


def save_state(path: str, data: Dict[str, Any]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


# Require $ or 'USD' and prefer real price shapes
PRICE_RE = re.compile(
    r'(?i)(?:\bUSD\s*)?\$\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?)|'
    r'(?i)\bUSD\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?)'
)

EXCLUDE_NEAR = re.compile(r'(?i)\b(GB|mAh|nit|nits|inch|in\.|ppi|reviews?|ratings?|points?|/mo|per month|%|trade[- ]?in)\b')

def extract_price_candidates(html: str) -> List[float]:
    candidates = []
    # JSON-LD as you already have...
    try:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all("script", type=lambda t: t and "ld+json" in t):
            try:
                import json as _json
                data = _json.loads(tag.string or "")
                def walk(obj):
                    if isinstance(obj, dict):
                        for k, v in obj.items():
                            if k in ("price", "priceAmount", "lowPrice", "highPrice"):
                                try:
                                    candidates.append(float(str(v).replace(",", "")))
                                except Exception:
                                    pass
                            walk(v)
                    elif isinstance(obj, list):
                        for it in obj:
                            walk(it)
                walk(data)
            except Exception:
                pass
    except Exception:
        pass

    # Fallback: only amounts with $ or USD, and ignore unit/finance context nearby
    window = 40  # chars around the match to scan for bad context
    for m in PRICE_RE.finditer(html):
        raw = m.group(1) or m.group(2)
        if not raw:
            continue
        start = max(0, m.start() - window)
        end = min(len(html), m.end() + window)
        context = html[start:end]
        if EXCLUDE_NEAR.search(context):
            continue
        try:
            val = float(raw.replace(",", ""))
            candidates.append(val)
        except Exception:
            continue

    # 1TB S11 Ultra isn’t < $1,100 in reality; tighten floor to kill noise
    candidates = [c for c in candidates if 1100 <= c <= 3000]
    uniq = sorted(set(round(c, 2) for c in candidates))
    return uniq


def fetch(url: str, timeout: int = 25) -> str:
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def post_to_discord(content: str, embeds: List[Dict[str, Any]] = None) -> None:
    if not DISCORD_WEBHOOK_URL:
        logging.warning("DISCORD_WEBHOOK_URL is not set; printing instead of posting.")
        print(content)
        if embeds:
            print(json.dumps(embeds, indent=2))
        return
    payload: Dict[str, Any] = {"content": content}
    if embeds:
        payload["embeds"] = embeds[:10]
    r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=20)
    r.raise_for_status()



def page_matches_required(html: str, pattern: str | None) -> bool:
    if not pattern:
        return True
    import re
    try:
        return re.search(pattern, html, flags=re.I) is not None
    except re.error:
        return True  # fail open if bad regex

def compare_and_alert(store: Dict[str, Any], prev: Dict[str, Any], now_prices: List[float]) -> Tuple[Dict[str, Any], bool]:
    changed = False
    best_now = min(now_prices) if now_prices else None
    desired = store.get("desired_price")

    new_record = {
        "last_checked": int(time.time()),
        "last_prices": now_prices,
        "best_price": best_now,
        "desired_price": desired,
    }

    prev_best = prev.get("best_price") if prev else None

    def fmt(v):
        return f"${v:,.2f}" if isinstance(v, (int, float)) and not math.isnan(v) else str(v)

    # Determine whether to alert
    alert_reasons = []
    if best_now is not None:
        if prev_best is None or best_now != prev_best:
            alert_reasons.append(f"price change {fmt(prev_best)} → {fmt(best_now)}")
        if desired is not None and best_now <= float(desired):
            alert_reasons.append(f"meets desired ≤ {fmt(desired)}")

    if alert_reasons:
        changed = True
        title = f"Galaxy Tab S11 Ultra @ {store['name']}"
        url = store["url"]
        embeds = [{
            "title": title,
            "url": url,
            "description": "\n".join(f"• {r}" for r in alert_reasons),
            "fields": [
                {"name": "Best Price Now", "value": fmt(best_now), "inline": True},
                {"name": "Previous Best", "value": fmt(prev_best), "inline": True},
            ],
        }]
        post_to_discord(f"📣 Deal update for **{store['name']}**", embeds)

    return new_record, changed


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    conf = load_config(CONFIG_FILE)
    state = load_state(STATE_FILE)
    any_alerts = False

    for store in conf.get("retailers", []):
        name = store["name"]
        url = store["url"]
        logging.info("Checking %s", name)
        try:
            html = fetch(url)
            if not page_matches_required(html, store.get('must_match')):
                logging.info('Skipping %s: must_match not found', name)
                continue
            prices = extract_price_candidates(html)
            rec_key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
            prev = state.get(rec_key, {})
            new_record, changed = compare_and_alert(store, prev, prices)
            state[rec_key] = {"name": name, "url": url, **new_record}
            any_alerts = any_alerts or changed
            time.sleep(1.0)  # be polite
        except Exception as e:
            logging.error("Failed to check %s: %s", name, e)

    save_state(STATE_FILE, state)
    return 0 if any_alerts else 0


if __name__ == "__main__":
    raise SystemExit(main())
