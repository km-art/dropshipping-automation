"""
Inventory & Price Sync
-----------------------
Reads the "Product Research & Niche" sheet of your master-plan Excel file
and pushes the selling prices to your Shopify store via the Admin API — so
you keep managing prices/margins in Excel, and this script keeps the live
store in sync automatically.

Usage:
    python inventory_sync.py path/to/Dropshipping_Cloud_Automation_Masterplan.xlsx

Requires in .env (see .env.example):
    SHOPIFY_STORE_URL       e.g. your-store.myshopify.com
    SHOPIFY_ACCESS_TOKEN    Admin API access token with write_products scope
"""

import json
import logging
import os
import sys

import openpyxl
import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("inventory_sync")

SHOPIFY_STORE_URL = os.getenv("SHOPIFY_STORE_URL", "")
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
API_VERSION = "2024-10"


def read_products_from_excel(excel_path: str) -> list[dict]:
    """Pulls product rows from the 'Product Research & Niche' sheet."""
    wb = openpyxl.load_workbook(excel_path, data_only=True)
    sheet = wb["Product Research & Niche"]

    products = []
    for row in sheet.iter_rows(min_row=4, max_col=8, values_only=True):
        prod_id, name, category, buy_price, sell_price, margin, supplier, supplier_id = row
        if not prod_id or not str(prod_id).startswith("PROD"):
            continue  # skip the totals row / blank rows
        products.append(
            {
                "sku": prod_id,
                "name": name,
                "category": category,
                "buy_price": buy_price,
                "sell_price": sell_price,
                "margin": margin,
                "supplier": supplier,
                "supplier_id": supplier_id,
            }
        )
    wb.close()
    return products


def find_shopify_variant_id_by_sku(sku: str) -> str | None:
    """Looks up the Shopify variant ID that matches a given SKU."""
    url = f"https://{SHOPIFY_STORE_URL}/admin/api/{API_VERSION}/variants.json"
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN}
    resp = requests.get(url, headers=headers, params={"sku": sku}, timeout=20)
    resp.raise_for_status()
    variants = resp.json().get("variants", [])
    return str(variants[0]["id"]) if variants else None


def update_shopify_price(variant_id: str, price: float) -> None:
    url = f"https://{SHOPIFY_STORE_URL}/admin/api/{API_VERSION}/variants/{variant_id}.json"
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN, "Content-Type": "application/json"}
    payload = {"variant": {"id": variant_id, "price": str(price)}}
    resp = requests.put(url, headers=headers, json=payload, timeout=20)
    resp.raise_for_status()


def sync_excel_inventory(excel_path: str, push_to_shopify: bool = True) -> None:
    products = read_products_from_excel(excel_path)
    log.info("Loaded %d products from %s", len(products), excel_path)

    # Always write a fresh products_map.json so order_sync.py stays in sync too.
    products_map = {p["sku"]: {
        "name": p["name"], "category": p["category"], "buy_price": p["buy_price"],
        "sell_price": p["sell_price"], "margin": p["margin"],
        "supplier": p["supplier"], "supplier_id": p["supplier_id"],
    } for p in products}
    map_path = os.path.join(os.path.dirname(__file__), "products_map.json")
    with open(map_path, "w", encoding="utf-8") as f:
        json.dump(products_map, f, ensure_ascii=False, indent=2)
    log.info("products_map.json updated (%s)", map_path)

    if not push_to_shopify:
        return

    if not SHOPIFY_STORE_URL or not SHOPIFY_ACCESS_TOKEN:
        log.warning("SHOPIFY_STORE_URL / SHOPIFY_ACCESS_TOKEN not set — skipping live store push. "
                    "Set them in .env to push prices automatically.")
        return

    for p in products:
        try:
            variant_id = find_shopify_variant_id_by_sku(p["sku"])
            if not variant_id:
                log.warning("No Shopify variant found for SKU %s (%s) — add the product to Shopify "
                            "with this SKU first.", p["sku"], p["name"])
                continue
            update_shopify_price(variant_id, p["sell_price"])
            log.info("Synced %s -> $%.2f on Shopify", p["sku"], p["sell_price"])
        except Exception as exc:  # noqa: BLE001
            log.error("Failed to sync %s: %s", p["sku"], exc)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python inventory_sync.py <path-to-excel-file>")
        sys.exit(1)
    sync_excel_inventory(sys.argv[1])
