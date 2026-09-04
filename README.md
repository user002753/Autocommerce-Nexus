# AutoCommerce Nexus Premium

An interactive, demo-ready agentic commerce gateway and Flight Recorder UI. The user interface is connected to a FastAPI server and local SQLite ledger; it is not a static mock-up.

## Included flows

- Delegated Authorization Token (DAT) and simulated UPI Reserve Pay policy controls
- Multi-agent inventory lock, margin-sentinel, and settlement execution traces
- Immutable 15% margin floor and prompt-injection rejection
- Hash-chained, HMAC-SHA256 signed proof-of-intent SQLite ledger
- HITL payment-link downgrade when a delegated spending cap is exceeded
- Interactive bank-timeout and stock-race recovery matrix
- Responsive commerce catalogue, negotiation desk, bag, and payment journey

## Run locally

The simplest option on Windows is to double-click [START_AUTOCOMMERCE.bat](START_AUTOCOMMERCE.bat). It starts the local gateway on port **8010** and opens the AutoCommerce Nexus application automatically.

If Windows asks which app to use, choose Command Prompt. If dependencies are missing, run this once from the project folder:

```powershell
python -m pip install -r requirements.txt
```

Manual launch:

```powershell
cd autocommerce-premium
python -m uvicorn server:app --reload --port 8010
```

Open `http://127.0.0.1:8010`. The ledger file is created automatically on first event.

## Important

The Razorpay-facing actions deliberately run in safe **test-mode simulation**. They model Reserve Pay, Payment Links, Orders and recovery behavior without sending money or using a live merchant credential. Before production use, replace the adapter with Razorpay's approved SDK/API implementation and store credentials in a secrets manager.
