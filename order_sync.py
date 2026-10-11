"""
Order Sync Engine
------------------
Receives a "new order" webhook from your store (Shopify or any platform that
sends JSON), matches the ordered SKU against products_map.json, and forwards
the order to the correct supplier's API (CJ Dropshipping / AliExpress) so it
gets fulfilled automatically — no manual copy-pasting of orders.

Run locally for testing:
    pip install -r requirements.txt
    python order_sync.py

Then point your Shopify webhook (Settings > Notifications > Webhooks,
event "Order creation") at:
    https://<your-server>/webhook/order

Deploy anywhere that runs Python (Render, Railway, PythonAnywhere, a small
VPS with gunicorn, etc.) — see README.md.
"""

import hashlib
import hmac
import json
import logging
import os
from base64 import b64encode

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("order_sync")

app = Flask(__name__)

SHOPIFY_WEBHOOK_SECRET = os.getenv("SHOPIFY_WEBHOOK_SECRET", "")
CJ_API_BASE = os.getenv("CJ_API_BASE", "https://api.cjdropshipping.com/v1")
CJ_API_KEY = os.getenv("CJ_API_KEY", "")
ORDERS_LOG_FILE = os.path.join(os.path.dirname(__file__), "orders_log.jsonl")

with open(os.path.join(os.path.dirname(__file__), "products_map.json"), encoding="utf-8") as f:
    PRODUCTS_MAP = json.load(f)


def verify_shopify_signature(raw_body: bytes, received_hmac: str) -> bool:
    """Confirms the webhook really came from Shopify (prevents fake fulfilment
    requests from being forwarded to your supplier and billed to you)."""
    if not SHOPIFY_WEBHOOK_SECRET:
        # No secret configured yet (e.g. first local test) — skip verification.
        return True
    digest = hmac.new(SHOPIFY_WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256).digest()
    computed_hmac = b64encode(digest).decode()
    return hmac.compare_digest(computed_hmac, received_hmac or "")


def log_order(order_id, sku, status, detail=""):
    entry = {"order_id": order_id, "sku": sku, "status": status, "detail": detail}
    with open(ORDERS_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def forward_to_supplier(sku: str, quantity: int, shipping_address: dict) -> dict:
    """Sends the order to the supplier's API. Currently wired for CJ
    Dropshipping's order-creation endpoint; swap the URL/payload shape if a
    product's supplier is AliExpress instead (see products_map.json)."""
    product = PRODUCTS_MAP.get(sku)
    if not product:
        raise ValueError(f"SKU '{sku}' not found in products_map.json")

    payload = {
        "supplierProductId": product["supplier_id"],
        "quantity": quantity,
        "shippingAddress": {
            "name": shipping_address.get("name"),
            "address1": shipping_address.get("address1"),
            "address2": shipping_address.get("address2"),
            "city": shipping_address.get("city"),
            "province": shipping_address.get("province"),
            "zip": shipping_address.get("zip"),
            "country": shipping_address.get("country"),
            "phone": shipping_address.get("phone"),
        },
    }

    headers = {"CJ-Access-Token": CJ_API_KEY, "Content-Type": "application/json"}
    response = requests.post(f"{CJ_API_BASE}/orders", json=payload, headers=headers, timeout=20)
    response.raise_for_status()
    return response.json()


@app.route("/webhook/order", methods=["POST"])
def handle_order_webhook():
    raw_body = request.get_data()
    received_hmac = request.headers.get("X-Shopify-Hmac-Sha256", "")

    if not verify_shopify_signature(raw_body, received_hmac):
        log.warning("Rejected webhook with invalid signature")
        return jsonify({"error": "invalid signature"}), 401

    order_data = request.get_json(force=True, silent=True) or {}
    order_id = order_data.get("id", "unknown")
    line_items = order_data.get("line_items", [])
    shipping_address = order_data.get("shipping_address", {})

    if not line_items:
        return jsonify({"error": "no line_items in order payload"}), 400

    results = []
    for item in line_items:
        sku = item.get("sku")
        quantity = item.get("quantity", 1)
        try:
            supplier_response = forward_to_supplier(sku, quantity, shipping_address)
            log_order(order_id, sku, "forwarded", json.dumps(supplier_response, ensure_ascii=False)[:500])
            results.append({"sku": sku, "status": "forwarded", "supplier_response": supplier_response})
            log.info("Order %s / SKU %s forwarded to supplier successfully", order_id, sku)
        except Exception as exc:  # noqa: BLE001 — we want to log & continue with other line items
            log_order(order_id, sku, "failed", str(exc))
            results.append({"sku": sku, "status": "failed", "error": str(exc)})
            log.error("Order %s / SKU %s failed to forward: %s", order_id, sku, exc)

    return jsonify({"order_id": order_id, "results": results}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
