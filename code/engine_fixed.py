from pathlib import Path
import sys
import re
import pandas as pd

from flask import Flask, request, jsonify
from flask_cors import CORS

ROOT = Path(__file__).resolve().parent
CODE_DIR = ROOT / "code"
DATASET = ROOT / "dataset"

sys.path.insert(0, str(CODE_DIR))

from engine import BuyOrWaitEngine


app = Flask(__name__)
CORS(app)


def load_csv(name):
    return pd.read_csv(DATASET / name)


print("Loading financial datasets...")

requests_df = load_csv("requests.csv")
profiles_df = load_csv("financial_profiles.csv")
events_df = load_csv("financial_events.csv")
rates_df = load_csv("exchange_rates.csv")
messages_df = load_csv("messages.csv")
images_df = load_csv("images.csv")
payment_options_df = load_csv("request_payment_options.csv")

# Normalize IDs so matching is reliable.
for df in (requests_df, profiles_df, events_df, messages_df, images_df):
    if "user_id" in df.columns:
        df["user_id"] = df["user_id"].astype(str).str.strip()

# Find users that really exist in BOTH requests and profiles.
request_users = set(requests_df["user_id"].dropna().astype(str).str.strip())
profile_users = set(profiles_df["user_id"].dropna().astype(str).str.strip())
common_users = sorted(request_users & profile_users)

if not common_users:
    raise RuntimeError(
        "No user_id exists in both requests.csv and financial_profiles.csv"
    )

DEMO_USER = common_users[0]

# Use a REAL request belonging to the REAL common user.
demo_requests = requests_df[requests_df["user_id"] == DEMO_USER].copy()

if demo_requests.empty:
    raise RuntimeError(f"No request found for {DEMO_USER}")

DEMO_TEMPLATE = demo_requests.iloc[0].copy()

print(f"Financial agent ready.")
print(f"Demo user: {DEMO_USER}")
print(f"Demo request: {DEMO_TEMPLATE['request_id']}")


engine = BuyOrWaitEngine(
    requests_df,
    profiles_df,
    events_df,
    rates_df,
    messages_df,
    images_df,
    payment_options_df,
    ROOT,
)


def extract_amount(text):
    if not text:
        return None

    cleaned = str(text).replace(",", "")

    patterns = [
        r"₹\s*(\d+(?:\.\d+)?)",
        r"(?:rs\.?|inr)\s*(\d+(?:\.\d+)?)",
    ]

    for pattern in patterns:
        matches = re.findall(pattern, cleaned, flags=re.IGNORECASE)
        if matches:
            return float(matches[-1])

    numbers = re.findall(r"\d+(?:\.\d+)?", cleaned)
    return float(numbers[-1]) if numbers else None


def clean(value):
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass

    return value


@app.get("/api/health")
def health():
    return jsonify({
        "status": "online",
        "agent": "Buy or Wait Financial Agent",
        "dataset": "connected",
        "financial_engine": "connected",
        "demo_user": DEMO_USER,
        "demo_request": str(DEMO_TEMPLATE["request_id"]),
    })


@app.post("/api/analyze")
def analyze():
    try:
        data = request.get_json(silent=True) or {}

        text = str(data.get("text", "")).strip()

        if not text:
            return jsonify({
                "success": False,
                "error": "Please enter a purchase request."
            }), 400

        amount = data.get("amount")

        if amount is None:
            amount = extract_amount(text)

        if amount is None:
            return jsonify({
                "success": False,
                "error": "Please include an amount, for example ₹35000."
            }), 400

        amount = float(amount)

        if amount <= 0:
            return jsonify({
                "success": False,
                "error": "Amount must be greater than zero."
            }), 400

        # Copy a REAL request so all required date/user fields exist.
        simulated_request = DEMO_TEMPLATE.copy()

        simulated_request["request_id"] = "WEB_DEMO"
        simulated_request["user_id"] = DEMO_USER
        simulated_request["requested_amount"] = amount
        simulated_request["request_text"] = text
        simulated_request["allows_partial_payment"] = True

        result = engine.decide(simulated_request)

        decision = {
            "request_id": clean(result.get("request_id")),
            "amount_safe_to_pay": clean(result.get("amount_safe_to_pay")),
            "affordability_status": clean(result.get("affordability_status")),
            "recommended_payment_method": clean(
                result.get("recommended_payment_method")
            ),
            "payment_plan": clean(result.get("payment_plan")),
            "earliest_date_for_full_payment": clean(
                result.get("earliest_date_for_full_payment")
            ),
            "spending_changes_needed": clean(
                result.get("spending_changes_needed")
            ),
            "decision_explanation": clean(
                result.get("decision_explanation")
            ),
        }

        return jsonify({
            "success": True,
            "request": {
                "text": text,
                "amount": amount,
                "user_id": DEMO_USER,
            },
            "decision": decision,
        })

    except Exception as error:
        print(f"API ERROR: {repr(error)}")
        return jsonify({
            "success": False,
            "error": str(error)
        }), 500


if __name__ == "__main__":
    print()
    print("=" * 60)
    print("BUY OR WAIT — AI FINANCIAL AGENT")
    print("=" * 60)
    print("Dataset: CONNECTED")
    print("Financial engine: CONNECTED")
    print(f"Demo user: {DEMO_USER}")
    print(f"Demo request: {DEMO_TEMPLATE['request_id']}")
    print("API: http://127.0.0.1:5000")
    print("=" * 60)
    print()

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False
    )
