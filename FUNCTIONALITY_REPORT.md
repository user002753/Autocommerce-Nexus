# AutoCommerce Nexus — Functionality Report

## Purpose

AutoCommerce Nexus is a test-mode agentic-commerce gateway that lets a buyer agent discover products, negotiate safely, reserve stock, and settle or escalate a payment under explicit user authorization.

## Implemented system functions

| Area | Function | Result |
| --- | --- | --- |
| Buyer authorization | Creates a 30-minute Delegated Agent Token (DAT) tied to a simulated UPI Reserve Pay mandate | Active |
| Policy control | Enforces daily and per-order spending caps on every purchase | Active |
| Merchant swarm | Inventory, pricing/margin, settlement, and recovery agents emit structured execution traces | Active |
| Inventory control | Locks each requested SKU for five minutes before settlement | Active |
| Margin Sentinel | Caps discounts and rejects any final price below cost plus the immutable 15% floor | Active |
| Prompt safety | Blocks instructions intended to override margin/policy controls | Active |
| Settlement | Settles policy-compliant transactions with the Reserve Pay test-mode path | Active |
| HITL | Creates a simulated 2FA payment-link path when a user policy would be exceeded | Active |
| Bank recovery | Creates a multi-rail payment-link fallback after simulated issuer downtime | Active |
| Stock recovery | Safely voids the intent and returns a closest in-category alternative with a 5% goodwill offer | Active |
| Non-repudiation | Writes append-only, hash-chained, HMAC-SHA256 signed entries to SQLite | Active |
| Observability | Flight Recorder displays live traces, guardrail state, failure injection, and ledger entries | Active |

## Transaction decision flow

```text
Buyer intent → DAT/policy verification → prompt safety check
→ stock lock (5 min) → deterministic margin validation
→ policy decision
   ├─ inside bounds: UPI Reserve Pay test settlement
   ├─ policy exceeded: HITL 2FA payment link
   ├─ bank timeout: multi-rail fallback payment link
   └─ stock race: intent void + closest alternative
→ HMAC-signed, chained ledger entry
```

## Validation completed

The following paths were exercised against the FastAPI application:

- DAT issuance with token fingerprint and 1,800-second expiry
- In-policy settlement (`settled`)
- Per-order-cap escalation (`hitl_required`)
- Simulated bank-timeout recovery (`fallback_payment_link`)
- Simulated stock-race recovery (`recovered_stock_race`)
- Prompt-injection attempt rejection (HTTP `422`)
- Signed-ledger retrieval (HTTP `200`)

## Technical boundaries

The interface and gateway are fully operational locally, but payment-provider calls use intentional test-mode simulations. No live payment is initiated and no real UPI mandate is created. A production rollout needs Razorpay-approved API access, merchant credentials in a secret manager, verified webhook signatures, durable database hosting, identity/KYC checks, and Razorpay’s applicable product enablement.
