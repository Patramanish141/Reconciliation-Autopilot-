"""
Central configuration for Reconciliation Autopilot.
Import from here instead of hardcoding paths/model names in every file.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Data file paths ---
DATA_DIR = os.getenv("DATA_DIR", "data")
os.makedirs(DATA_DIR, exist_ok=True)

TRANSACTIONS_FILE = os.path.join(DATA_DIR, "transactions.json")
SETTLEMENTS_FILE = os.path.join(DATA_DIR, "settlements.json")
ORDERS_FILE = os.path.join(DATA_DIR, "merchant_orders.csv")

RAW_REPORT_FILE = os.path.join(DATA_DIR, "reconciliation_report.json")
ENHANCED_REPORT_FILE = os.path.join(DATA_DIR, "enhanced_report.json")

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- Gemini settings ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
GEMINI_TIMEOUT_SECONDS = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "20"))
GEMINI_MAX_RETRIES = int(os.getenv("GEMINI_MAX_RETRIES", "2"))

# --- Razorpay settings ---
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
RAZORPAY_TEST_MODE = os.getenv("RAZORPAY_TEST_MODE", "true").lower() == "true"

# --- Fallback explanations (used when Gemini fails / times out) ---
# Keeps the dashboard from ever showing a broken/blank message during a live demo.
FALLBACK_EXPLANATIONS = {
    "ORPHAN_ORDER": {
        "explanation": "This order exists in your internal records but has no matching Razorpay payment. This usually means the payment failed silently, was never initiated, or was recorded manually without going through checkout.",
        "action": "Check with the customer whether payment was completed elsewhere, or correct the order record if it was entered in error."
    },
    "PAYMENT_NOT_SETTLED": {
        "explanation": "This payment was successfully captured by Razorpay but hasn't appeared in any settlement batch yet. Settlements can take T+1 to T+3 business days depending on your account type.",
        "action": "Wait for the next settlement cycle. If it's been more than 3 business days, raise a ticket with Razorpay support."
    },
    "DUPLICATE_SETTLEMENT": {
        "explanation": "The same payment appears in more than one settlement batch, which could mean you were credited twice for the same transaction, or there's a data sync issue.",
        "action": "Verify your bank statement for a duplicate credit before assuming it's a reporting glitch — if duplicated, expect Razorpay to reverse the extra credit."
    },
    "AMOUNT_MISMATCH": {
        "explanation": "The settled amount differs from the original payment amount. This is most commonly explained by Razorpay's transaction fees and applicable taxes being deducted before settlement.",
        "action": "Cross-check the difference against your current Razorpay fee schedule. If it doesn't match expected fees, flag it to Razorpay support."
    },
    "PAYMENT_WITHOUT_ORDER": {
        "explanation": "Razorpay shows a successful payment that has no corresponding order in your internal system. This can happen with test transactions, manually created payment links, or a sync delay between systems.",
        "action": "Search your system by customer email/date for a matching order. If none exists, confirm this wasn't a test or duplicate payment link."
    },
    "UNKNOWN_SETTLEMENT_TRANSACTION": {
        "explanation": "A settlement references a transaction ID that doesn't appear in your payment records. This is unusual and may indicate a data export gap or a transaction from outside the selected date range.",
        "action": "Re-fetch transaction data for a wider date range before treating this as an anomaly."
    },
}

DEFAULT_FALLBACK = {
    "explanation": "Automated explanation is temporarily unavailable.",
    "action": "Please review this flag manually."
}
