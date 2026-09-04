"""AutoCommerce Nexus — Universal Agentic Gateway for Shopify, WooCommerce, Custom & Social E-Commerce.

All Razorpay interactions are safe test-mode simulations. Add real credentials and
replace the adapter methods only after completing Razorpay's production onboarding.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, List

from fastapi import FastAPI, HTTPException, Header, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).parent
DB_PATH = ROOT / "nexus_ledger.sqlite3"
SECRET = os.getenv("NEXUS_AUDIT_SECRET", "demo-only-change-me").encode()
MARGIN_FLOOR = 15.0
LOCK_TTL_SECONDS = 300
EOF_MARKER = None

# ... (middle lines)
app = FastAPI(title="AutoCommerce Nexus Universal Gateway", version="3.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=ROOT), name="static")

CATALOG = [
    {"sku":"PHONE-X1","name":"Nexus Phone X1","category":"Electronics","price":29999,"cost":24000,"stock":50,"icon":"▣","color":"#b2b2b2","merchant":"Nexus Verified Store","platform":"Shopify"},
    {"sku":"WRLSS-BUD","name":"BassCore Wireless Buds","category":"Audio","price":4999,"cost":2800,"stock":200,"icon":"◉","color":"#e0c2b5","merchant":"BassCore Audio Store","platform":"Shopify"},
    {"sku":"CHRG-65W","name":"TurboCharge 65W Adapter","category":"Accessories","price":1999,"cost":1100,"stock":500,"icon":"ϟ","color":"#e7d49a","merchant":"Nexus Verified Store","platform":"Shopify"},
    {"sku":"CASE-X1","name":"ArmorCase for Phone X1","category":"Accessories","price":1499,"cost":450,"stock":300,"icon":"▤","color":"#c1d2c3","merchant":"Nexus Verified Store","platform":"Custom"},
    {"sku":"SCRN-GLS","name":"Tempered Glass Shield","category":"Accessories","price":899,"cost":250,"stock":400,"icon":"◇","color":"#a9c4cc","merchant":"Nexus Verified Store","platform":"Custom"},
    {"sku":"LAP-PRO14","name":"ProBook Laptop 14","category":"Electronics","price":74999,"cost":62000,"stock":20,"icon":"▱","color":"#c8bfd6","merchant":"Nexus Verified Store","platform":"Custom"},
    {"sku":"MOUSE-RGB","name":"GripMaster RGB Mouse","category":"Accessories","price":2999,"cost":1400,"stock":150,"icon":"◒","color":"#d3b9b3","merchant":"Nexus Verified Store","platform":"WooCommerce"},
    {"sku":"HDMI-2M","name":"HDMI 2.1 Cable","category":"Accessories","price":1299,"cost":350,"stock":250,"icon":"⌇","color":"#b8c7e1","merchant":"Nexus Verified Store","platform":"WooCommerce"},
    {"sku":"WARR-1Y","name":"Extended Warranty","category":"Services","price":2499,"cost":500,"stock":9999,"icon":"✦","color":"#dac79c","merchant":"Nexus Verified Store","platform":"Custom"},
    {"sku":"SNEAK-R1","name":"FlexRun Sneakers R1","category":"Footwear","price":4999,"cost":2200,"stock":80,"icon":"◒","color":"#d1bdb0","merchant":"FlexFit Apparel","platform":"Shopify"},
    {"sku":"SOCKS-BLU","name":"Blue Running Socks (2-pack)","category":"Apparel","price":299,"cost":120,"stock":100,"icon":"🧦","color":"#93c5fd","merchant":"FlexFit Apparel","platform":"WooCommerce"},
    {"sku":"JACKET-LTHR","name":"Vintage Leather Jacket","category":"Apparel","price":4200,"cost":2800,"stock":15,"icon":"🧥","color":"#78350f","merchant":"LeatherCraft Co (Shopify)","platform":"Shopify"},
    {"sku":"POLISH-SHOE","name":"Premium Shoe Polish","category":"Accessories","price":499,"cost":200,"stock":50,"icon":"🧴","color":"#f59e0b","merchant":"ShoeCare Store (WooCommerce)","platform":"WooCommerce"},
    {"sku":"JACKET-SUEDE","name":"Suede Leather Jacket","category":"Apparel","price":3999,"cost":2600,"stock":25,"icon":"🧥","color":"#b45309","merchant":"AltStyle Store (WooCommerce)","platform":"WooCommerce"},
    {"sku":"RICE-BAS","name":"Basmati Rice 1kg","category":"Groceries","price":180,"cost":120,"stock":150,"icon":"🌾","color":"#fef08a","merchant":"FreshMart Organics","platform":"Custom"},
    {"sku":"SALT-TATA","name":"Tata Salt 1kg","category":"Groceries","price":28,"cost":18,"stock":300,"icon":"🧂","color":"#e2e8f0","merchant":"FreshMart Organics","platform":"Custom"},
    {"sku":"DAL-TUR","name":"Premium Toor Dal 1kg","category":"Groceries","price":160,"cost":110,"stock":200,"icon":"🫘","color":"#fde047","merchant":"FreshMart Organics","platform":"Custom"},
    {"sku":"KEYBD-MECH","name":"MechType RGB Keyboard","category":"Electronics","price":4499,"cost":2800,"stock":60,"icon":"⌨","color":"#cbd5e1","merchant":"Nexus Verified Store","platform":"Shopify"},
]
PRODUCTS = {p["sku"]: p for p in CATALOG}
locks: dict[str, dict[str, Any]] = {}
policies: dict[str, dict[str, Any]] = {}
holds: dict[str, dict[str, Any]] = {}
orders: dict[str, dict[str, Any]] = {}
family_wallets: dict[str, dict[str, Any]] = {}
concierge: dict[str, dict[str, Any]] = {}
group_buying_pools: dict[str, dict[str, Any]] = {}
vouchers: dict[str, dict[str, Any]] = {}
acp_states: dict[str, dict[str, Any]] = {}
failures = {"bank_timeout": False, "stock_race": False, "pincode_rto": False, "unsafe_prompt": False, "dark_pattern": False}
pii_settings = {"mode": "ZERO_KNOWLEDGE_ANONYMOUS", "released_for_sessions": set()}


def now() -> str: return datetime.now(timezone.utc).isoformat()
def amount(n: float) -> float: return round(n, 2)
def margin_percent(product: dict[str, Any]) -> float: return (product["price"] - product["cost"]) / product["price"] * 100
def signed(value: dict[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(SECRET, raw, hashlib.sha256).hexdigest()


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS ledger (
      sequence INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
      session_id TEXT NOT NULL, event_type TEXT NOT NULL, payload TEXT NOT NULL,
      previous_hash TEXT NOT NULL, entry_hash TEXT NOT NULL, signature TEXT NOT NULL)""")
    return conn


def record(session_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Append hash-chained, HMAC-signed proof of intent to the local ledger."""
    with db() as conn:
        prior = conn.execute("SELECT entry_hash FROM ledger ORDER BY sequence DESC LIMIT 1").fetchone()
        previous_hash = prior["entry_hash"] if prior else "GENESIS"
        core = {"created_at": now(), "session_id": session_id, "event_type": event_type, "payload": payload, "previous_hash": previous_hash}
        entry_hash = hashlib.sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()
        signature = signed({**core, "entry_hash": entry_hash})
        cursor = conn.execute("INSERT INTO ledger (created_at,session_id,event_type,payload,previous_hash,entry_hash,signature) VALUES (?,?,?,?,?,?,?)", (core["created_at"],session_id,event_type,json.dumps(payload),previous_hash,entry_hash,signature))
        return {"sequence": cursor.lastrowid, **core, "entry_hash": entry_hash, "signature": signature}


def trace(name: str, detail: str, status: str = "ok") -> dict[str, str]:
    return {"at": now(), "agent": name, "detail": detail, "status": status}


def sanitize_prompt(prompt: str) -> None:
    hostile = ("ignore previous", "margin floor", "system prompt", "negative margin", "override policy", "disable guardrail", "sell for 1", "sell for 0")
    if any(term in prompt.lower() for term in hostile):
        raise HTTPException(422, "ERR_MARGIN_BREACH: Unsafe prompt instruction detected! Bounded policy sentinel rejected attempt to bypass margin floor.")

def scan_dark_patterns(text: str, stock_count: int = 50) -> None:
    predatory_scarcity = ("only 1 left", "only 2 left", "hurry stock running out", "1 item remaining", "last chance")
    if stock_count > 10 and any(phrase in text.lower() for phrase in predatory_scarcity):
        raise HTTPException(422, f"ERR_DARK_PATTERN_DETECTED: False scarcity claim ('Only 1 left in stock!') violates India 2023 Consumer Protection Guidelines. Actual merchant inventory count is {stock_count}.")


def clean_locks() -> None:
    expired = [k for k, v in locks.items() if v["expires"] <= time.time()]
    for key in expired: del locks[key]


def product_for(sku: str) -> dict[str, Any]:
    p = PRODUCTS.get(sku)
    if not p: raise HTTPException(404, f"Unknown SKU: {sku}")
    return p


class PolicyInput(BaseModel):
    session_id: str = Field(default_factory=lambda: f"buyer_{uuid.uuid4().hex[:10]}")
    daily_limit: float = Field(5000, gt=0, le=500000)
    item_limit: float = Field(2500, gt=0, le=500000)
    auto_categories: list[str] = Field(default_factory=lambda: ["Accessories", "Electronics", "Groceries", "Apparel"])
    merchant_whitelist: list[str] = Field(default_factory=lambda: ["Razorpay Verified Stores", "Nexus Verified Store", "BassCore Audio Store", "FlexFit Apparel", "LeatherCraft Co (Shopify)", "ShoeCare Store (WooCommerce)"])

class Line(BaseModel): sku: str; quantity: int = Field(1, ge=1, le=10); requested_discount: float = Field(0, ge=0, le=50)
class Purchase(BaseModel): session_id: str; prompt: str = Field("Purchase selected products", max_length=500); items: list[Line]; merchant: str = "Nexus Verified Store"; pincode: str = Field("560037", pattern=r"^\d{6}$")
class FailureInput(BaseModel): bank_timeout: bool = False; stock_race: bool = False; pincode_rto: bool = False; unsafe_prompt: bool = False; dark_pattern: bool = False
class FamilyInput(BaseModel): primary_session_id: str; member_name: str = Field(min_length=2,max_length=40); weekly_limit: float = Field(gt=0,le=500000); categories: list[str] = Field(default_factory=list)
class UndoInput(BaseModel): session_id: str
class AgentPromptInput(BaseModel): session_id: str; prompt: str; max_budget_inr: Optional[float] = None
class VoiceInput(BaseModel): session_id: str; speech_text: str; auto_checkout: bool = True
class GroupBuyInput(BaseModel): action: str = "pool_intent"; sku: str = "KEYBD-MECH"; buyers_count: int = 3; session_id: str = "group_session_01"
class ComplianceCheckInput(BaseModel): message: str; sku: str = "PHONE-X1"
class ProofCertInput(BaseModel): session_id: str; prompt: str; cart_item_ids: list[str]; max_approved_price: float
class PriceLockInput(BaseModel): sku: str; requested_discount: float = 10.0
class MultiMerchantInput(BaseModel): session_id: str; items: list[dict[str, Any]]
class WhatsAppDMInput(BaseModel): phone_number: str; message_text: str; session_id: Optional[str] = "wa_session_01"
class CrossPlatformCartInput(BaseModel): session_id: str; prompt: str = "Buy leather jacket from Merchant A (Shopify) and matching polish from Merchant B (WooCommerce) under 5000 total"


app = FastAPI(title="AutoCommerce Nexus Universal Gateway", version="3.0.0")
app.mount("/static", StaticFiles(directory=ROOT), name="static")

@app.get("/")
def home(): return FileResponse(ROOT / "index.html")

@app.get("/app.js")
def get_app_js(): return FileResponse(ROOT / "app.js")

@app.get("/gateway.js")
def get_gateway_js(): return FileResponse(ROOT / "gateway.js")

@app.get("/styles.css")
def get_styles_css(): return FileResponse(ROOT / "styles.css")

@app.get("/recorder.css")
def get_recorder_css(): return FileResponse(ROOT / "recorder.css")

@app.get("/api/catalog")
def catalog():
    clean_locks()
    return {"products": [{**p, "available_stock": p["stock"] - sum(x["quantity"] for x in locks.values() if x["sku"] == p["sku"]), "margin_pct": round(margin_percent(p), 1)} for p in CATALOG]}

@app.get("/.well-known/agentic-catalog.json")
def agentic_catalog():
    """UAP-style discovery manifest for external agent clients (NPCI UAP compliance)."""
    return {
        "protocol": "Universal Agentic Protocol (UAP v1.0) & HTTP 402 Micro-Payment Proxy",
        "version": "1.0.0",
        "merchant": "Razorpay Universal Agentic Gateway",
        "connectors": ["Shopify Admin API", "WooCommerce REST API", "Custom Headless OpenAPI", "WhatsApp Business API"],
        "tools": ["discover_catalog", "check_inventory_lock", "negotiate_tier_discount", "generate_settlement_manifest"],
        "catalog_url": "/api/catalog",
        "intent_url": "/api/purchase",
        "agent_prompt_url": "/api/agent-prompt",
        "acp_handshake_url": "/api/acp/{order_id}",
        "products": [{"id": p["sku"], "name": p["name"], "category": p["category"], "price_inr": p["price"], "merchant": p["merchant"], "platform": p["platform"]} for p in CATALOG]
    }

@app.get("/.well-known/mcp-plugin-manifest.json")
def mcp_plugin_manifest():
    """Universal Storefront Plugin Manifest (Shopify App & WordPress/WooCommerce plugin shell)."""
    return {
        "plugin_name": "AutoCommerce Nexus Universal MCP Adapter",
        "version": "1.0.0",
        "supported_platforms": ["Shopify", "WooCommerce", "Magento", "Custom REST"],
        "description": "Instantly turns any Shopify or WooCommerce store into an MCP/UAP-compliant AI-transactable storefront settling via Razorpay.",
        "capabilities": {
            "mcp_tools": ["discover_catalog", "check_stock_hold", "negotiate_bundle", "create_razorpay_settlement"],
            "razorpay_features": ["UPI Reserve Pay", "Razorpay Route Split Settlement", "Smart Payment Links"],
            "anti_dark_pattern_enabled": True,
            "margin_floor_protected": True
        },
        "setup_guide_url": "/api/plugin/download"
    }

@app.get("/api/plugin/download")
def plugin_download():
    return {
        "status": "ready",
        "plugin_package": "autocommerce-nexus-universal-mcp-plugin-v1.0.zip",
        "instructions": "1. Upload ZIP to WordPress / WooCommerce or install Shopify App shell. 2. Enter Razorpay Key ID and Secret. 3. AI Buyer Agents can now interact and negotiate directly with your store!"
    }

# ---------------------------------------------------------------- E-Commerce Platform Adapters (Shopify, WooCommerce, Custom, WhatsApp)
@app.get("/api/connectors/shopify")
def shopify_adapter():
    """Shopify Admin GraphQL/REST API connector adapter."""
    shopify_products = [p for p in CATALOG if p["platform"] == "Shopify"]
    return {
        "connector": "Shopify Admin REST/GraphQL API v2026-01",
        "status": "CONNECTED_ACTIVE",
        "store_domain": "nexus-verified-merchant.myshopify.com",
        "products_count": len(shopify_products),
        "inventory_sync": "REALTIME_GRAPHQL_WEBHOOKS",
        "products": shopify_products
    }

@app.get("/api/connectors/woocommerce")
def woocommerce_adapter():
    """WooCommerce REST API connector adapter (/wp-json/wc/v3/products)."""
    wc_products = [p for p in CATALOG if p["platform"] == "WooCommerce"]
    return {
        "connector": "WooCommerce REST API (/wp-json/wc/v3/products)",
        "status": "CONNECTED_ACTIVE",
        "wp_version": "6.7.1",
        "wc_version": "9.4.2",
        "products_count": len(wc_products),
        "inventory_sync": "WEBHOOK_REST_LOCK",
        "products": wc_products
    }

@app.get("/api/connectors/custom")
def custom_adapter():
    """Custom/Headless OpenAPI & MCP Catalog Spec adapter."""
    custom_products = [p for p in CATALOG if p["platform"] == "Custom"]
    return {
        "connector": "Custom/Headless OpenAPI 3.1 & MCP Protocol Adapter",
        "status": "CONNECTED_ACTIVE",
        "schema_format": "OPENAPI_MCP_CATALOG",
        "products_count": len(custom_products),
        "products": custom_products
    }

@app.post("/api/connectors/whatsapp")
def whatsapp_dm_adapter(req: WhatsAppDMInput):
    """WhatsApp Business API & Instagram DMs converter to Razorpay Intent."""
    text = req.message_text.strip()
    traces = [
        trace("WhatsApp Business Connector", f"Received DM from {req.phone_number}: '{text}'"),
        trace("Social Intent Parser", "Extracted product intent: Basmati Rice 1kg (₹180)."),
        trace("Razorpay Intent Builder", "Generated dynamic UPI QR sheet & Payment Link for instant DM checkout.")
    ]
    
    amount_inr = 180.0
    payment_link = f"https://rzp.io/i/wa-{uuid.uuid4().hex[:8]}"
    qr_payload = f"upi://pay?pa=autocommerce@razorpay&pn=WhatsAppOrder&am={amount_inr}&tn=WADM_{uuid.uuid4().hex[:6]}"
    
    event = record(req.session_id, "whatsapp_dm_converted_to_intent", {
        "phone": req.phone_number,
        "text": text,
        "amount_inr": amount_inr,
        "link": payment_link
    })
    
    return {
        "status": "whatsapp_intent_generated",
        "phone": req.phone_number,
        "parsed_intent": "1kg Basmati Rice",
        "amount_inr": amount_inr,
        "payment_link": payment_link,
        "qr_payload": qr_payload,
        "auto_reply_message": f"Hi! Here is your instant checkout link for 1kg Basmati Rice (₹180): {payment_link}",
        "traces": traces,
        "audit": event
    }

# ---------------------------------------------------------------- Cross-Platform Multi-Merchant Shopping Cart
@app.post("/api/cross-platform-cart")
def cross_platform_cart(req: CrossPlatformCartInput):
    session_id = req.session_id
    prompt = req.prompt.strip()
    
    # Item 1: Leather Jacket from Shopify (LeatherCraft Co)
    p1 = PRODUCTS["JACKET-LTHR"]
    # Item 2: Shoe Polish from WooCommerce (ShoeCare Store)
    p2 = PRODUCTS["POLISH-SHOE"]
    
    subtotal = amount(p1["price"] + p2["price"])
    order_id = f"order_cross_{uuid.uuid4().hex[:10]}"
    payment_link = f"https://rzp.io/i/cross-platform-{order_id[:8]}"
    
    splits = [
        {
            "platform": "Shopify",
            "merchant": p1["merchant"],
            "sku": p1["sku"],
            "product_name": p1["name"],
            "amount_inr": p1["price"],
            "razorpay_route_account": "acc_shopify_leathercraft_901"
        },
        {
            "platform": "WooCommerce",
            "merchant": p2["merchant"],
            "sku": p2["sku"],
            "product_name": p2["name"],
            "amount_inr": p2["price"],
            "razorpay_route_account": "acc_wc_shoecare_402"
        }
    ]
    
    traces = [
        trace("Universal Gateway Router", f"Ingested cross-platform buyer prompt: '{prompt}'"),
        trace("Shopify Adapter", f"Queried {p1['merchant']} via Shopify Admin API. Locked {p1['name']} (₹{p1['price']})."),
        trace("WooCommerce Adapter", f"Queried {p2['merchant']} via WooCommerce REST API. Locked {p2['name']} (₹{p2['price']})."),
        trace("Razorpay Route Engine", f"Generated unified payment link ({payment_link}). Auto-splits ₹{p1['price']} to Shopify & ₹{p2['price']} to WooCommerce.")
    ]
    
    event = record(session_id, "cross_platform_multi_merchant_cart_settled", {
        "order_id": order_id,
        "prompt": prompt,
        "subtotal": subtotal,
        "splits": splits
    })
    
    return {
        "status": "cross_platform_cart_settled",
        "order_id": order_id,
        "prompt": prompt,
        "subtotal": subtotal,
        "items": [p1, p2],
        "split_settlement_route": splits,
        "razorpay_payment_link": payment_link,
        "traces": traces,
        "audit": event
    }

# ---------------------------------------------------------------- Omnichannel Inventory Lock & Flash Vendor Shift
@app.post("/api/omnichannel-stock-shift")
def omnichannel_stock_shift(session_id: str = "omni_session_01"):
    primary_item = PRODUCTS["JACKET-LTHR"] # Shopify item sells out
    alt_item = PRODUCTS["JACKET-SUEDE"] # WooCommerce item shift
    
    traces = [
        trace("Shopify Webhook Listener", f"Stock lock error: {primary_item['name']} on Shopify store sold out mid-negotiation!", "failed"),
        trace("Razorpay Pre-Auth Engine", "Released open UPI Reserve Pay pre-authorization hold to prevent invalid charge.", "recovered"),
        trace("Omnichannel Vendor Router", f"Shifted order automatically to WooCommerce vendor ({alt_item['merchant']}). Selected {alt_item['name']} (₹{alt_item['price']}) + applied ₹100 inconvenience waiver credit.", "recovered")
    ]
    
    event = record(session_id, "omnichannel_vendor_shift_executed", {
        "failed_sku": primary_item["sku"],
        "failed_platform": "Shopify",
        "recovered_sku": alt_item["sku"],
        "recovered_platform": "WooCommerce",
        "inconvenience_waiver_inr": 100.0
    })
    
    return {
        "status": "omnichannel_vendor_shift_success",
        "failed_item": primary_item,
        "recovered_alternative": alt_item,
        "pre_auth_released": True,
        "inconvenience_waiver_inr": 100.0,
        "final_price_inr": amount(alt_item["price"] - 100.0),
        "traces": traces,
        "audit": event
    }

# ---------------------------------------------------------------- ACP State Handshake
@app.get("/api/acp/{order_id}")
def acp_state(order_id: str):
    state_obj = acp_states.get(order_id, {
        "order_id": order_id,
        "state": "INTENT_SUBMITTED",
        "history": [{"state": "INTENT_SUBMITTED", "at": now(), "note": "Buyer agent initiated UAP handshake"}]
    })
    return {"protocol": "Agentic Commerce Protocol (ACP v1.0)", "order_id": order_id, "state": state_obj["state"], "history": state_obj["history"]}

@app.post("/api/acp/transition")
def acp_transition(order_id: str, new_state: str):
    allowed_states = ("INTENT_SUBMITTED", "OFFER_PROPOSED", "SETTLEMENT_GATED", "ORDER_SETTLED", "ORDER_VOIDED")
    if new_state not in allowed_states: raise HTTPException(400, f"Invalid ACP state: {new_state}")
    state_obj = acp_states.setdefault(order_id, {"order_id": order_id, "state": "INTENT_SUBMITTED", "history": []})
    state_obj["state"] = new_state
    state_obj["history"].append({"state": new_state, "at": now(), "note": f"Handshake state transitioned to {new_state}"})
    record("acp_engine", "acp_state_transition", {"order_id": order_id, "new_state": new_state})
    return state_obj

# ---------------------------------------------------------------- x402 Micro-Payment Protocol Header Endpoint
@app.post("/api/stock-hold/{sku}")
def quoted_stock_hold(sku: str, quantity: int = 1, x_verification_token: Optional[str] = Header(None)):
    product_for(sku)
    if not x_verification_token:
        return Response(
            content=json.dumps({"error": "HTTP 402 Payment Required", "detail": "x402 micro-payment verification token missing for real-time stock hold."}),
            status_code=402,
            headers={
                "X-Payment-Required": "zero-value-preauth",
                "X-Verification-URL": "/api/policy",
                "Content-Type": "application/json"
            }
        )
    return {"status": "verified_hold_quote", "sku": sku, "quantity": quantity, "ttl_seconds": LOCK_TTL_SECONDS, "token": x_verification_token}

# ---------------------------------------------------------------- Anti-Dark Pattern Compliance Endpoint
@app.post("/api/compliance/scan")
def compliance_scan(req: ComplianceCheckInput):
    p = PRODUCTS.get(req.sku, PRODUCTS["PHONE-X1"])
    if failures["dark_pattern"] or "only 1 left" in req.message.lower():
        failures["dark_pattern"] = False
        scan_dark_patterns("Only 1 left in stock! Order now before stock runs out!", stock_count=p["stock"])
    scan_dark_patterns(req.message, stock_count=p["stock"])
    event = record("compliance_gate", "dark_pattern_scan_passed", {"message": req.message, "sku": req.sku})
    return {"status": "COMPLIANT_ZERO_DARK_PATTERNS", "message": req.message, "actual_stock": p["stock"], "audit": event}

# ---------------------------------------------------------------- Cryptographic Proof of Intent Certificate
@app.post("/api/proof-certificate")
def generate_proof_certificate(req: ProofCertInput):
    prompt_hash = hashlib.sha256(req.prompt.encode()).hexdigest()
    timestamp = now()
    cert_id = f"cert_{uuid.uuid4().hex[:12]}"
    core_payload = {
        "certificate_id": cert_id,
        "session_id": req.session_id,
        "prompt_hash": prompt_hash,
        "cart_item_ids": req.cart_item_ids,
        "max_approved_price_inr": req.max_approved_price,
        "timestamp": timestamp
    }
    signature = signed(core_payload)
    cert = {**core_payload, "signature": signature, "issuer": "AutoCommerce Nexus Consent Sentinel"}
    record(req.session_id, "proof_of_intent_certificate_issued", cert)
    return cert

# ---------------------------------------------------------------- 300s Price-Lock Ephemeral Voucher
@app.post("/api/price-lock")
def issue_price_lock_voucher(req: PriceLockInput):
    p = product_for(req.sku)
    max_discount = max(0, margin_percent(p) - MARGIN_FLOOR)
    discount = min(req.requested_discount, max_discount)
    locked_price = amount(p["price"] * (1 - discount / 100))
    voucher_id = f"voucher_lock_{uuid.uuid4().hex[:10]}"
    expires_at = time.time() + 300
    
    voucher = {
        "voucher_id": voucher_id,
        "sku": req.sku,
        "product_name": p["name"],
        "list_price": p["price"],
        "locked_price": locked_price,
        "discount_pct": discount,
        "ttl_seconds": 300,
        "expires_at": expires_at,
        "status": "ACTIVE_LOCKED"
    }
    vouchers[voucher_id] = voucher
    record("merchant_gate", "price_lock_voucher_issued", voucher)
    return voucher

# ---------------------------------------------------------------- Multi-Merchant Split-Order Cart
@app.post("/api/multi-merchant-cart")
def multi_merchant_cart(req: MultiMerchantInput):
    subtotal = 0.0
    split_breakdown = []
    
    for item in req.items:
        p = product_for(item["sku"])
        line_total = amount(p["price"] * item.get("quantity", 1))
        subtotal += line_total
        split_breakdown.append({
            "merchant": p["merchant"],
            "sku": p["sku"],
            "product_name": p["name"],
            "amount_inr": line_total,
            "razorpay_account_id": f"acc_{hashlib.sha256(p['merchant'].encode()).hexdigest()[:10]}"
        })
    
    order_id = f"order_split_{uuid.uuid4().hex[:10]}"
    payment_link = f"https://rzp.io/i/split-{order_id[:8]}"
    
    event = record(req.session_id, "multi_merchant_split_cart_created", {
        "order_id": order_id,
        "subtotal": subtotal,
        "splits": split_breakdown
    })
    
    return {
        "status": "multi_merchant_cart_ready",
        "order_id": order_id,
        "subtotal": subtotal,
        "merchant_count": len(set(s["merchant"] for s in split_breakdown)),
        "split_settlement_route": split_breakdown,
        "razorpay_payment_link": payment_link,
        "audit": event
    }

# ---------------------------------------------------------------- Policy & Failure endpoints
@app.post("/api/policy")
def set_policy(input: PolicyInput):
    token = "dat_" + secrets.token_urlsafe(22)
    expires_at = time.time() + 30 * 60
    policy = {
        "session_id": input.session_id,
        "daily_limit": input.daily_limit,
        "item_limit": input.item_limit,
        "auto_categories": input.auto_categories,
        "merchant_whitelist": input.merchant_whitelist,
        "token": token,
        "mandate": "UPI-RESERVE-" + uuid.uuid4().hex[:10].upper(),
        "issued_at": now(),
        "expires_at": expires_at,
        "spent_today": 0.0,
        "attempts": 0
    }
    policies[input.session_id] = policy
    record(input.session_id, "delegated_authorization_issued", {k: v for k, v in policy.items() if k != "token"})
    return {
        **policy,
        "token": token[:13] + "…",
        "token_fingerprint": hashlib.sha256(token.encode()).hexdigest()[:16],
        "expires_in_seconds": 30 * 60,
        "mode": "RAZORPAY_UPI_RESERVE_PAY_SIMULATION"
    }

@app.post("/api/failure")
def inject_failure(input: FailureInput):
    failures.update(input.model_dump())
    record("control-panel", "failure_injection", failures.copy())
    return {"active": failures, "message": "Fault matrix updated live on Agent Flight Recorder."}

@app.post("/api/family-wallet")
def create_family_wallet(input: FamilyInput):
    if input.primary_session_id not in policies: raise HTTPException(401, "Primary account needs an active DAT wallet mandate first.")
    wallet_id = "circle_" + uuid.uuid4().hex[:10]
    wallet = {
        "wallet_id": wallet_id,
        "primary_session_id": input.primary_session_id,
        "member_name": input.member_name,
        "weekly_limit": input.weekly_limit,
        "categories": input.categories or ["Textbooks", "Stationery", "Groceries"],
        "spent": 0.0,
        "approval_channel": "WhatsApp / UPI App Instant Route",
        "status": "active"
    }
    family_wallets[wallet_id] = wallet
    record(input.primary_session_id, "upi_circle_wallet_created", wallet)
    return wallet

@app.post("/api/family-escalation")
def trigger_family_escalation(wallet_id: str, amount_inr: float, category: str, sku: str):
    wallet = family_wallets.get(wallet_id)
    if not wallet: raise HTTPException(404, "Family wallet not found.")
    p = PRODUCTS.get(sku, {"name": sku})
    exceeds = amount_inr > wallet["weekly_limit"]
    reason = "Weekly budget exceeded" if exceeds else f"Category '{category}' requires parent approval"
    payload = {
        "wallet_id": wallet_id,
        "member_name": wallet["member_name"],
        "amount_inr": amount_inr,
        "item_name": p.get("name"),
        "category": category,
        "reason": reason,
        "whatsapp_preview": f"🚨 *UPI Circle Escalation Alert*\n{wallet['member_name']} is trying to purchase {p.get('name')} for ₹{amount_inr}.\nReason: {reason}.\nTap [Approve] or [Reject] in your UPI app.",
        "status": "PENDING_PRIMARY_APPROVAL"
    }
    record(wallet["primary_session_id"], "family_circle_escalation_routed", payload)
    return payload

@app.post("/api/undo/{order_id}")
def undo_order(order_id: str, input: UndoInput):
    order = orders.get(order_id)
    if not order or order["session_id"] != input.session_id: raise HTTPException(404, "Order not found for this buyer session.")
    if order["state"] != "ORDER_SETTLED" or time.time() > order["undo_until"]:
        raise HTTPException(409, "The 60-second one-tap reversal window has expired.")
    order["state"] = "ORDER_VOIDED"
    order["history"].append({"state":"ORDER_VOIDED","at":now(),"reason":"BUYER_ONE_TAP_REVERSAL_60S"})
    if order.get("hold_id") in holds: holds[order["hold_id"]]["status"] = "released"
    event = record(input.session_id, "buyer_undo_release_hold", {
        "order_id": order_id,
        "hold_id": order.get("hold_id"),
        "amount_refunded_inr": order["subtotal"],
        "upi_mandate_released": True
    })
    return {"status": "voided_and_hold_released", "order_id": order_id, "amount_released": order["subtotal"], "audit": event}

@app.get("/api/explainability/{order_id}")
def get_explainability(order_id: str):
    order = orders.get(order_id)
    if not order: raise HTTPException(404, "Order not found")
    remaining_undo = max(0, int(order.get("undo_until", 0) - time.time()))
    return {
        "order_id": order_id,
        "reasoning_trace": order.get("reasoning_trace", "Matched user request and negotiated within protected margin."),
        "diff": order.get("diff", {"retail_price": order["subtotal"], "negotiated_price": order["subtotal"], "savings_inr": 0}),
        "undo_seconds_remaining": remaining_undo,
        "can_undo": order["state"] == "ORDER_SETTLED" and remaining_undo > 0,
        "upi_hold_id": order.get("hold_id")
    }

@app.get("/api/concierge/{order_id}")
def concierge_status(order_id: str):
    item = concierge.get(order_id)
    if not item:
        order = orders.get(order_id)
        if not order: raise HTTPException(404, "No post-purchase concierge record exists.")
        item = {
            "order_id": order_id,
            "session_id": order["session_id"],
            "sku": order["lines"][0]["sku"] if order.get("lines") else "PHONE-X1",
            "product_name": order["lines"][0]["name"] if order.get("lines") else "Purchased Item",
            "dispatch_status": "DISPATCH_ON_SCHEDULE",
            "tracking_number": f"TRK-{uuid.uuid4().hex[:8].upper()}",
            "invoice_pdf": f"Razorpay_Invoice_{order_id}.pdf",
            "warranty_months": 12,
            "warranty_expires": "2027-09-03",
            "calendar_reminder_set": True,
            "inquiry": "none",
            "refund_action": "AVAILABLE"
        }
        concierge[order_id] = item
    return item

@app.post("/api/concierge/{order_id}/miss-sla")
def miss_dispatch_sla(order_id: str):
    item = concierge_status(order_id)
    item.update({
        "dispatch_status": "SLA_MISSED_OVER_48H",
        "inquiry": "automated_merchant_inquiry_opened",
        "refund_action": "ONE_TAP_REFUND_READY",
        "concierge_note": "Merchant missed fulfillment SLA by >48 hours. Autonomous concierge initiated razorpay refund claim."
    })
    record(item["session_id"], "concierge_sla_breach", {"order_id": order_id, "action": "INQUIRY_AND_REFUND_READY"})
    return item

@app.post("/api/concierge/{order_id}/refund")
def trigger_instant_refund(order_id: str):
    item = concierge_status(order_id)
    item["dispatch_status"] = "ORDER_REFUNDED_VIA_RAZORPAY"
    item["refund_action"] = "REFUNDED"
    event = record(item["session_id"], "razorpay_instant_refund_executed", {"order_id": order_id, "status": "REFUNDED_TO_UPI"})
    return {"status": "refund_completed", "order_id": order_id, "refund_id": f"rfnd_{uuid.uuid4().hex[:10]}", "audit": event}

@app.get("/api/ledger")
def ledger():
    with db() as conn:
        rows = conn.execute("SELECT sequence,created_at,session_id,event_type,payload,entry_hash,signature FROM ledger ORDER BY sequence DESC LIMIT 30").fetchall()
    return {"entries": [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]}

# ---------------------------------------------------------------- Concept 1 Endpoint: AgentPay Protocol (x402 & UAP)
@app.post("/api/agent-prompt")
def agent_pay_prompt(req: AgentPromptInput):
    session_id = req.session_id
    prompt = req.prompt.strip()
    
    # Prompt injection check
    if failures["unsafe_prompt"] or "ignore previous" in prompt.lower() or "sell for 1" in prompt.lower():
        failures["unsafe_prompt"] = False
        record(session_id, "bounded_safety_intercept", {"prompt": prompt, "reason": "ERR_MARGIN_BREACH"})
        raise HTTPException(422, "ERR_MARGIN_BREACH: Deterministic policy interceptor rejected prompt injection! Price cannot be forced below margin floor.")

    policy = policies.get(session_id)
    if not policy:
        raise HTTPException(401, "Buyer Intent & Allowance Cockpit token missing. Please issue a DAT token first.")

    traces = [
        trace("Buyer Agent (UAP Protocol)", f"Ingested natural language intent: '{prompt}'"),
        trace("x402 Reverse-Proxy", f"Queries merchant MCP catalog via HTTP 402 discovery manifest."),
    ]

    target = None
    if "sock" in prompt.lower(): target = PRODUCTS["SOCKS-BLU"]
    elif "bud" in prompt.lower() or "headphone" in prompt.lower(): target = PRODUCTS["WRLSS-BUD"]
    elif "phone" in prompt.lower(): target = PRODUCTS["PHONE-X1"]
    elif "mouse" in prompt.lower(): target = PRODUCTS["MOUSE-RGB"]
    elif "jacket" in prompt.lower(): target = PRODUCTS["JACKET-LTHR"]
    else: target = PRODUCTS["CHRG-65W"]

    qty = 2 if "2" in prompt or "two" in prompt.lower() else 1
    requested_discount = 10.0
    max_discount = max(0, margin_percent(target) - MARGIN_FLOOR)
    discount = min(requested_discount, max_discount)
    unit_price = amount(target["price"] * (1 - discount / 100))
    subtotal = amount(unit_price * qty)

    traces.append(trace(f"{target['merchant']} ({target['platform']} Adapter)", f"Matched SKU {target['sku']} ({target['name']}). List ₹{target['price']} → Negotiated ₹{unit_price} (-{discount:.0f}%) within {MARGIN_FLOOR}% margin floor."))

    # Stock race check
    if failures["stock_race"]:
        failures["stock_race"] = False
        alt = PRODUCTS["CHRG-65W"]
        event = record(session_id, "stock_race_trapped", {"primary_sku": target["sku"], "alternative_sku": alt["sku"], "inconvenience_waiver_inr": 100.0})
        traces.extend([
            trace("Inventory Sentinel", f"Trapped stock lock error for {target['sku']} mid-negotiation.", "recovered"),
            trace("Recovery Matrix", f"Open Razorpay Order cancelled, UPI Reserve Pay hold released. Recommended alternative: {alt['name']} + ₹100 inconvenience waiver credit.", "recovered")
        ])
        return {
            "status": "recovered_stock_race",
            "prompt": prompt,
            "alternative": alt,
            "inconvenience_waiver_inr": 100.0,
            "goodwill_discount": 5,
            "traces": traces,
            "audit": event
        }

    # Bank failure check
    if failures["bank_timeout"]:
        failures["bank_timeout"] = False
        link = {"id": "plink_" + uuid.uuid4().hex[:10], "short_url": "https://rzp.io/i/test-fallback", "channels": ["WhatsApp", "SMS"], "methods": ["Cards", "Netbanking", "UPI"]}
        event = record(session_id, "bank_outage_fallback", {"prompt": prompt, "subtotal": subtotal, "link": link})
        traces.extend([
            trace("Razorpay Order Engine", "Primary UPI bank issuer returned 500 error.", "failed"),
            trace("Recovery Orchestrator", "Agent generated multi-rail smart payment link and dispatched via WhatsApp.", "recovered")
        ])
        return {
            "status": "bank_fallback_link",
            "prompt": prompt,
            "subtotal": subtotal,
            "payment_link": link,
            "traces": traces,
            "audit": event
        }

    hold_id = "hold_" + uuid.uuid4().hex[:10]
    holds[hold_id] = {"amount": subtotal, "status": "active", "created_at": time.time()}
    order_id = "order_agent_" + uuid.uuid4().hex[:10]
    undo_until = time.time() + 60

    acp_states[order_id] = {
        "order_id": order_id,
        "state": "ORDER_SETTLED",
        "history": [
            {"state": "INTENT_SUBMITTED", "at": now(), "note": "Intent ingested from agent prompt"},
            {"state": "OFFER_PROPOSED", "at": now(), "note": f"Merchant proposed ₹{unit_price}/unit"},
            {"state": "ORDER_SETTLED", "at": now(), "note": "Zero-click settlement confirmed via UPI Reserve Pay"}
        ]
    }

    order_obj = {
        "order_id": order_id,
        "session_id": session_id,
        "state": "ORDER_SETTLED",
        "subtotal": subtotal,
        "hold_id": hold_id,
        "undo_until": undo_until,
        "lines": [{"sku": target["sku"], "name": target["name"], "quantity": qty, "unit_price": target["price"], "line_total": subtotal}],
        "reasoning_trace": f"Selected {target['name']} matching query '{prompt}'. Negotiated {discount:.0f}% volume discount with Merchant MCP Server under the ₹{policy['item_limit']} per-order cap.",
        "diff": {"retail_price": target["price"] * qty, "negotiated_price": subtotal, "savings_inr": amount((target["price"] * qty) - subtotal)},
        "history": [{"state": "ORDER_SETTLED", "at": now(), "via": "AgentPay_x402"}]
    }
    orders[order_id] = order_obj
    policy["spent_today"] = amount(policy["spent_today"] + subtotal)

    traces.append(trace("Settlement Engine", f"Zero-click settlement executed via UPI Reserve Pay token. Order {order_id} recorded in ledger."))
    event = record(session_id, "agentpay_zero_click_settlement", {"order_id": order_id, "subtotal": subtotal, "prompt": prompt})

    return {
        "status": "settled",
        "order_id": order_id,
        "subtotal": subtotal,
        "lines": order_obj["lines"],
        "acp_state": "ORDER_SETTLED",
        "explainability": {
            "reasoning_trace": order_obj["reasoning_trace"],
            "diff": order_obj["diff"],
            "undo_seconds_remaining": 60
        },
        "traces": traces,
        "audit": event
    }

# ---------------------------------------------------------------- Concept 2 Endpoint: VoiceCommerce Mesh (Hinglish)
@app.post("/api/voice-commerce")
def voice_commerce_mesh(req: VoiceInput):
    session_id = req.session_id
    text = req.speech_text.strip()
    
    traces = [
        trace("VoiceCommerce Mesh", f"Captured audio transcript (Hinglish): '{text}'"),
        trace("NLP Intent Extractor", f"Parsed items: 1kg Basmati Rice (₹180) + 1 packet Tata Salt (₹28)."),
        trace("Combo Discount Engine", f"Cross-category opportunity detected: Suggested ₹30 combo discount on Premium Toor Dal.")
    ]

    subtotal = 208.0
    final_subtotal = subtotal

    if failures["bank_timeout"]:
        failures["bank_timeout"] = False
        fallback_link = f"https://rzp.io/i/voice-fallback-{uuid.uuid4().hex[:6]}"
        voice_nudge = "Aapke bank server mein issue aa raha hai. Maine aapke WhatsApp pe ek fallback card payment link bhej diya hai."
        event = record(session_id, "voice_bank_fallback", {"text": text, "fallback_link": fallback_link})
        traces.extend([
            trace("Razorpay Payment Gateway", "Primary bank handle down (payment.failed webhook).", "failed"),
            trace("Voice Agent Recovery", f"Voice nudge delivered to buyer: '{voice_nudge}'", "recovered")
        ])
        return {
            "status": "bank_outage_fallback",
            "voice_response": voice_nudge,
            "fallback_link": fallback_link,
            "traces": traces,
            "audit": event
        }

    qr_payload = f"upi://pay?pa=autocommerce@razorpay&pn=NexusCommerce&am={final_subtotal:.2f}&tn=VoiceOrder_{uuid.uuid4().hex[:6]}"
    voice_response = f"Ji bhaiya! 1kg Basmati Rice aur Tata Salt aapke cart mein add kar diya. Dal pe ₹30 combo discount offer unlocked hai! Checkout amount ₹{final_subtotal:.0f} ke liye UPI QR screen pe ready hai."

    event = record(session_id, "voice_intent_checkout_rendered", {"transcript": text, "amount_inr": final_subtotal, "qr": qr_payload})
    traces.append(trace("Razorpay Dynamic QR", f"Rendered zero-reload UPI intent sheet for ₹{final_subtotal:.0f}."))

    return {
        "status": "voice_checkout_ready",
        "transcript": text,
        "voice_response": voice_response,
        "subtotal": final_subtotal,
        "suggested_combo": {"sku": "DAL-TUR", "name": "Premium Toor Dal 1kg", "combo_discount_inr": 30.0},
        "qr_payload": qr_payload,
        "traces": traces,
        "audit": event
    }

# ---------------------------------------------------------------- Concept 3 Endpoint: A2A Group-Buying Coordinator
@app.post("/api/group-buying")
def group_buying_coordinator(req: GroupBuyInput):
    pool_id = "pool_mech_keyboard"
    sku = req.sku
    product = PRODUCTS.get(sku, PRODUCTS["KEYBD-MECH"])

    if req.action == "pool_intent":
        pool = {
            "pool_id": pool_id,
            "sku": sku,
            "product_name": product["name"],
            "unit_retail_price": product["price"],
            "buyers": [
                {"agent_id": "Buyer_Alpha_Agent", "qty": 1, "status": "LOCKED"},
                {"agent_id": "Buyer_Beta_Agent", "qty": 1, "status": "LOCKED"},
                {"agent_id": "Buyer_Gamma_Agent", "qty": 1, "status": "LOCKED"}
            ],
            "total_units": 3,
            "tier_unlocked": "Tier 3 (3+ units)",
            "wholesale_unit_price": 3599.0,
            "individual_savings_inr": 900.0,
            "ttl_seconds": 300,
            "status": "TIER_3_UNLOCKED"
        }
        group_buying_pools[pool_id] = pool
        traces = [
            trace("A2A Coordinator", f"Pooled intent from 3 distinct buyer agents for {product['name']}."),
            trace("Merchant Swarm Tool", f"Unlocked Tier-3 Wholesale Rate: ₹3,599/unit (20% off retail price ₹4,499)."),
            trace("Razorpay Smart Links", f"Auto-dispatched 3 split payment links with 300s escrow holds to Buyer Alpha, Beta, Gamma.")
        ]
        event = record("group_coord", "a2a_group_buying_tier_unlocked", pool)
        return {"status": "pooled_successfully", "pool": pool, "traces": traces, "audit": event}

    elif req.action == "simulate_dropout":
        pool = group_buying_pools.get(pool_id)
        if not pool:
            return group_buying_coordinator(GroupBuyInput(action="pool_intent"))
        
        pool["buyers"] = [b for b in pool["buyers"] if b["agent_id"] != "Buyer_Gamma_Agent"]
        pool["buyers"].append({"agent_id": "Buyer_Gamma_Agent", "qty": 0, "status": "TIMED_OUT"})
        pool["total_units"] = 2
        pool["tier_unlocked"] = "Tier 2 (2 units)"
        pool["wholesale_unit_price"] = 3999.0
        pool["individual_savings_inr"] = 500.0
        pool["status"] = "RE_EVALUATED_TIER_2"

        traces = [
            trace("A2A Coordinator", "Trapped Buyer_Gamma timeout event.", "recovered"),
            trace("Dynamic Tier Engine", "Re-evaluated volume pricing in real-time: Tier 2 rate (₹3,999/unit) applied without breaking remaining orders.", "recovered"),
            trace("Razorpay Link Refresher", "Updated open Payment Links for Alpha & Beta with explainable pricing adjustments.", "recovered")
        ]
        event = record("group_coord", "a2a_group_buying_dropout_adjusted", pool)
        return {"status": "re_evaluated_after_dropout", "pool": pool, "traces": traces, "audit": event}

    raise HTTPException(400, "Unknown group buying action.")

# ---------------------------------------------------------------- General Purchase Endpoint
@app.post("/api/purchase")
def purchase(req: Purchase):
    if not req.items: raise HTTPException(400, "Cart cannot be empty.")
    sanitize_prompt(req.prompt)
    policy = policies.get(req.session_id)
    if not policy: raise HTTPException(401, "Create a delegated wallet policy before purchase.")
    if policy["expires_at"] <= time.time():
        record(req.session_id, "delegated_token_expired", {"mandate": policy["mandate"]})
        raise HTTPException(401, "Delegated agent token expired. Issue a new authorization token to continue.")

    # High RTO Pincode check
    if req.pincode == "841301" or failures["pincode_rto"]:
        failures["pincode_rto"] = False
        rto_qr = f"upi://pay?pa=rto-prepaid@razorpay&am=4849.00&tn=Prepaid3PctCashback"
        event = record(req.session_id, "rto_blacklist_recovery", {"pincode": req.pincode, "action": "DISABLE_COD_PREPAID_INCENTIVE"})
        traces = [
            trace("RTO Sentinel", f"Pincode '{req.pincode}' flagged for high Return-To-Origin risk.", "failed"),
            trace("Recovery Orchestrator", "Disabled Cash-on-Delivery (COD); generated prepaid Razorpay UPI QR offering 3% instant cashback.", "recovered")
        ]
        return {
            "status": "rto_prepaid_cashback",
            "pincode": req.pincode,
            "cashback_pct": 3.0,
            "qr_payload": rto_qr,
            "traces": traces,
            "audit": event
        }
    
    traces = [trace("Buyer Agent", "Proof of intent captured and policy token attached."), trace("Pricing & Margin Sentinel", "Prompt safety and price-floor validation started.")]
    record(req.session_id, "user_intent", {"prompt": req.prompt, "items": [i.model_dump() for i in req.items]})
    clean_locks()
    lines, subtotal = [], 0.0
    for line in req.items:
        p = product_for(line.sku)
        max_discount = max(0, margin_percent(p) - MARGIN_FLOOR)
        discount = min(line.requested_discount, max_discount)
        final_price = amount(p["price"] * (1 - discount / 100))
        if final_price < p["cost"] * 1.15: raise HTTPException(422, "ERR_MARGIN_BREACH: Margin sentinel rejected an unsafe price.")
        if failures["stock_race"] or p["stock"] - sum(x["quantity"] for x in locks.values() if x["sku"] == p["sku"]) < line.quantity:
            failures["stock_race"] = False
            alternative = next((x for x in CATALOG if x["category"] == p["category"] and x["sku"] != p["sku"] and x["stock"] > 0), None)
            event = record(req.session_id, "stock_race_recovery", {"sku":p["sku"],"alternative":alternative["sku"] if alternative else None,"inconvenience_waiver_inr":100.0})
            traces.extend([trace("Inventory & Fulfillment Agent", f"Stock race trapped for {p['sku']}", "recovered"), trace("Recovery Orchestrator", "Reserved intent voided; closest alternative issued with ₹100 inconvenience waiver credit.", "recovered")])
            return {"status":"recovered_stock_race","requires_hitl":False,"alternative":alternative,"inconvenience_waiver_inr":100.0,"traces":traces,"audit":event}
        lock_id = "lock_" + uuid.uuid4().hex[:10]
        locks[lock_id] = {"sku":p["sku"],"quantity":line.quantity,"expires":time.time()+LOCK_TTL_SECONDS}
        lines.append({"sku":p["sku"],"name":p["name"],"quantity":line.quantity,"unit_price":p["price"],"discount_pct":round(discount,2),"line_total":amount(final_price*line.quantity),"lock_id":lock_id})
        subtotal += final_price * line.quantity
    subtotal = amount(subtotal)
    traces.append(trace("Inventory & Fulfillment Agent", f"{len(lines)} SKU lock(s) secured for {LOCK_TTL_SECONDS // 60} minutes."))
    record(req.session_id, "margin_check", {"subtotal":subtotal,"margin_floor":MARGIN_FLOOR,"lines":lines})
    over_policy = subtotal > policy["item_limit"] or subtotal + policy["spent_today"] > policy["daily_limit"]
    order_id = "order_test_" + uuid.uuid4().hex[:12]
    if failures["bank_timeout"]:
        failures["bank_timeout"] = False
        link = {"id":"plink_test_"+uuid.uuid4().hex[:10],"short_url":"https://rzp.io/i/test-fallback","channels":["WhatsApp","SMS"],"methods":["Cards","Netbanking","UPI"]}
        event = record(req.session_id,"payment_fallback",{"order_id":order_id,"reason":"ISSUER_DOWNTIME","payment_link":link})
        traces.extend([trace("Settlement Engine", "UPI issuer timeout received.", "failed"),trace("Recovery Orchestrator", "Dynamic payment link sent with Cards, Netbanking and UPI alternatives.", "recovered")])
        return {"status":"fallback_payment_link","order_id":order_id,"payment_link":link,"subtotal":subtotal,"traces":traces,"audit":event}
    if over_policy:
        reason = "single-order cap" if subtotal > policy["item_limit"] else "daily delegated budget"
        link = {"id":"plink_test_"+uuid.uuid4().hex[:10],"short_url":"https://rzp.io/i/hitl-demo","requires_2fa":True}
        event = record(req.session_id,"hitl_payment_link",{"order_id":order_id,"subtotal":subtotal,"reason":reason,"limits":{"item":policy["item_limit"],"daily":policy["daily_limit"]}})
        traces.append(trace("Settlement Engine", f"Delegated limit exceeded ({reason}); HITL 2FA link created.", "needs_approval"))
        return {"status":"hitl_required","order_id":order_id,"subtotal":subtotal,"reason":reason,"payment_link":link,"traces":traces,"audit":event}
    
    hold_id = "hold_" + uuid.uuid4().hex[:10]
    undo_until = time.time() + 60
    order_obj = {
        "order_id": order_id,
        "session_id": req.session_id,
        "state": "ORDER_SETTLED",
        "subtotal": subtotal,
        "hold_id": hold_id,
        "undo_until": undo_until,
        "lines": lines,
        "reasoning_trace": f"Negotiated {lines[0]['discount_pct']}% discount for {lines[0]['name']}. Protected margin floor above {MARGIN_FLOOR}%.",
        "diff": {"retail_price": sum(l["unit_price"] * l["quantity"] for l in lines), "negotiated_price": subtotal, "savings_inr": amount(sum(l["unit_price"] * l["quantity"] for l in lines) - subtotal)},
        "history": [{"state": "ORDER_SETTLED", "at": now(), "via": "Visual_Checkout"}]
    }
    orders[order_id] = order_obj

    policy["spent_today"] = amount(policy["spent_today"] + subtotal)
    event = record(req.session_id,"reserve_pay_settlement",{"order_id":order_id,"subtotal":subtotal,"mandate":policy["mandate"],"lines":lines})
    traces.append(trace("Settlement Engine", "UPI Reserve Pay authorization valid. Test-mode settlement confirmed."))
    return {"status":"settled","order_id":order_id,"subtotal":subtotal,"lines":lines,"dat":"active","traces":traces,"audit":event}
