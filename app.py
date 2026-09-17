from pathlib import Path
import sys
import re
import pandas as pd

from flask import Flask, jsonify, request
from flask_cors import CORS

ROOT = Path(__file__).resolve().parent
CODE_DIR = ROOT / "code"
DATASET_DIR = ROOT / "dataset"

sys.path.insert(0, str(CODE_DIR))

from engine import BuyOrWaitEngine, norm_date


def load_csv(name):
    path = DATASET_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")
    df = pd.read_csv(path)
    if "user_id" in df.columns:
        df["user_id"] = df["user_id"].astype(str).str.strip()
    return df


print("Loading financial datasets...")

requests_df = load_csv("requests.csv")
profiles_df = load_csv("financial_profiles.csv")
events_df = load_csv("financial_events.csv")
rates_df = load_csv("exchange_rates.csv")
messages_df = load_csv("messages.csv")
images_df = load_csv("images.csv")
payment_options_df = load_csv("request_payment_options.csv")

request_users = set(requests_df["user_id"].astype(str).str.strip())
profile_users = set(profiles_df["user_id"].astype(str).str.strip())
common_users = sorted(request_users.intersection(profile_users))

if not common_users:
    raise RuntimeError("No user_id exists in both requests.csv and financial_profiles.csv")

DEMO_USER = common_users[0]

demo_requests = requests_df[
    requests_df["user_id"].astype(str).str.strip() == DEMO_USER
].copy()

if demo_requests.empty:
    raise RuntimeError(f"No request found for demo user {DEMO_USER}")

DEMO_TEMPLATE = demo_requests.iloc[0].copy()


def parse_profile_number(value, default):
    try:
        return float(str(value).replace(",", "").replace("₹", "").strip())
    except (TypeError, ValueError):
        return float(default)


def active_profile_values(raw_profile):
    base = engine.profile(DEMO_USER)
    raw_profile = raw_profile if isinstance(raw_profile, dict) else {}
    income = parse_profile_number(raw_profile.get("monthly_income"), 0)
    other_income = parse_profile_number(raw_profile.get("other_regular_income"), 0)
    rent = parse_profile_number(raw_profile.get("monthly_rent"), 0)
    home_emi = parse_profile_number(raw_profile.get("home_emi"), 0)
    maintenance = parse_profile_number(raw_profile.get("maintenance"), 0)
    household = parse_profile_number(raw_profile.get("household_contribution"), 0)
    essential = parse_profile_number(raw_profile.get("essential_expenses"), 0)
    utilities = parse_profile_number(raw_profile.get("utilities"), 0)
    emi = parse_profile_number(raw_profile.get("loan_emi"), 0)
    housing_label = str(raw_profile.get("housing") or "Rent")
    housing_key = housing_label.lower()
    return {
        "current_available_balance": parse_profile_number(raw_profile.get("current_balance"), base["current_available_balance"]),
        "minimum_balance_to_keep": parse_profile_number(raw_profile.get("minimum_reserve"), base["minimum_balance_to_keep"]),
        "monthly_income": income,
        "other_regular_income": other_income,
        "next_income_date": raw_profile.get("next_income_date") or str(DEMO_TEMPLATE["request_date"]),
        "housing": housing_label,
        "monthly_rent": rent,
        "home_emi": home_emi,
        "maintenance": maintenance,
        "household_contribution": household,
        "essential_expenses": essential,
        "utilities": utilities,
        "loan_emi": emi,
        "total_income": income + other_income,
        "housing_cost": rent if housing_key == "rent" else home_emi + maintenance if housing_key == "own home" else household,
        "payment_methods": str(raw_profile.get("payment_methods") or "full_payment|installments"),
        "max_installment_months": parse_profile_number(raw_profile.get("max_installment_months"), base.get("max_installment_months") or 0),
        "financial_priorities": str(raw_profile.get("financial_priority") or base.get("financial_priorities", "")),
    }


def build_profile_engine(raw_profile):
    values = active_profile_values(raw_profile)
    scoped_profiles = profiles_df.copy()
    scoped_events = events_df.copy()
    profile_mask = scoped_profiles["user_id"].astype(str).eq(DEMO_USER)
    scoped_profiles.loc[profile_mask, "current_available_balance"] = values["current_available_balance"]
    scoped_profiles.loc[profile_mask, "minimum_balance_to_keep"] = values["minimum_balance_to_keep"]
    scoped_profiles.loc[profile_mask, "max_installment_months"] = values["max_installment_months"]
    # Full payment is always a safe fallback when the requested amount fits;
    # installment preference still participates when an installment is viable.
    methods = set(values["payment_methods"].lower().replace(",", "|").split("|"))
    methods.add("full_payment")
    scoped_profiles.loc[profile_mask, "payment_methods_user_will_consider"] = "|".join(sorted(methods))
    scoped_profiles.loc[profile_mask, "financial_priorities"] = values["financial_priorities"]

    user_events = scoped_events[scoped_events["user_id"].astype(str).eq(DEMO_USER)]
    event_dates = pd.to_datetime(user_events["event_date"], errors="coerce")
    before_request = event_dates < norm_date(DEMO_TEMPLATE["request_date"])
    salary_mask = scoped_events["user_id"].astype(str).eq(DEMO_USER) & scoped_events["category"].astype(str).str.lower().eq("salary")
    if values["total_income"] > 0:
        scoped_events.loc[salary_mask, "amount"] = values["total_income"]
    future_salary = salary_mask & (pd.to_datetime(scoped_events["event_date"], errors="coerce") >= norm_date(DEMO_TEMPLATE["request_date"]))
    if future_salary.any():
        first_salary = scoped_events.index[future_salary][0]
        scoped_events.loc[first_salary, "event_date"] = values["next_income_date"]

    def update_series(category, amount):
        if amount <= 0:
            return
        mask = scoped_events["user_id"].astype(str).eq(DEMO_USER) & scoped_events["category"].astype(str).str.lower().eq(category)
        scoped_events.loc[mask & before_request.reindex(scoped_events.index, fill_value=False), "amount"] = amount

    housing = values["housing"].lower()
    housing_mask = scoped_events["user_id"].astype(str).eq(DEMO_USER) & scoped_events["category"].astype(str).str.lower().eq("rent")
    if housing == "rent":
        scoped_events.loc[housing_mask, "amount"] = values["housing_cost"]
    else:
        scoped_events.loc[housing_mask, "amount"] = 0
        source_rows = scoped_events.loc[housing_mask].copy()
        source_rows["category"] = "housing"
        source_rows["description"] = "Home housing cost"
        source_rows["amount"] = values["housing_cost"]
        scoped_events = pd.concat([scoped_events, source_rows], ignore_index=True)
    update_series("debt_repayment", values["loan_emi"])
    if values["utilities"] > 0:
        update_series("utilities", values["utilities"])
    if values["essential_expenses"] > 0:
        non_housing_essentials = max(values["essential_expenses"] - values["utilities"] - values["housing_cost"] - values["loan_emi"], 0)
        update_series("groceries", non_housing_essentials)

    return BuyOrWaitEngine(
        requests_df,
        scoped_profiles,
        scoped_events,
        rates_df,
        messages_df,
        images_df,
        payment_options_df,
        ROOT,
    ), values

print(f"Common users found: {len(common_users)}")
print(f"Demo user: {DEMO_USER}")
print(f"Demo request: {DEMO_TEMPLATE.get('request_id')}")

print("Building financial agent...")

engine = BuyOrWaitEngine(
    requests_df,
    profiles_df,
    events_df,
    rates_df,
    messages_df,
    images_df,
    payment_options_df,
    ROOT
)

print("Financial agent ready.")

app = Flask(__name__)
CORS(app)


@app.get("/api/health")
def health():
    return jsonify({
        "status": "online",
        "dataset": "connected",
        "engine": "connected",
        "demo_user": DEMO_USER,
        "demo_request": DEMO_TEMPLATE.get("request_id"),
        "common_users": len(common_users)
    })


@app.route("/api/profile", methods=["GET", "POST"])
def profile_summary():
    """Fast dashboard summary. Do not run the full decision search on page load."""
    try:
        body = request.get_json(silent=True) or {}
        scoped_engine, profile_values = build_profile_engine(body.get("profile"))
        profile = scoped_engine.profile(DEMO_USER)
        request_date = DEMO_TEMPLATE["request_date"]
        forecast = scoped_engine.forecast(DEMO_USER, request_date)
        protected = {item.lower() for item in str(profile.get("expense_categories_to_protect", "")).split("|") if item}
        upcoming = forecast[(forecast["event_date"] >= norm_date(request_date)) & (forecast["event_date"] <= norm_date(request_date) + pd.Timedelta(days=30))]
        essentials = upcoming[(upcoming["direction"].astype(str).str.lower() == "debit") & (upcoming["category"].astype(str).str.lower().isin(protected))]
        income = upcoming[(upcoming["direction"].astype(str).str.lower() == "credit") & (upcoming["category"].astype(str).str.lower() == "salary")]
        # safe capacity before a purchase: maximum amount that can be removed
        # while the 90-day path stays above the configured reserve.
        dates, values, minimum = scoped_engine._daily_path(DEMO_USER, request_date, [])
        safe_capacity = round(max(0.0, min(values) - float(minimum)), 2)
        reduce_categories = {item.lower() for item in str(profile.get("expense_categories_user_is_willing_to_reduce", "")).split("|") if item}
        stop_categories = {item.lower() for item in str(profile.get("expense_categories_user_is_willing_to_stop", "")).split("|") if item}
        def payload(row):
            d = pd.to_datetime(row.get("event_date"), errors="coerce")
            cat = str(row.get("category", "other")).lower()
            direction = str(row.get("direction", "debit")).lower()
            return {"event_id": str(row.get("event_id", "")), "date": d.strftime("%Y-%m-%d") if pd.notna(d) else "", "description": str(row.get("description", "")).strip(), "category": cat, "amount": round(float(row.get("home_amount", row.get("amount", 0)) or 0), 2), "direction": direction, "status": str(row.get("status", "scheduled")), "essential": cat in protected, "flexible": cat in reduce_categories or cat in stop_categories, "projected": bool(row.get("_projected", False))}
        events = [payload(row) for _, row in upcoming.sort_values("event_date").head(12).iterrows()]
        transactions = [payload(row) for _, row in scoped_engine._events(DEMO_USER).sort_values("event_date", ascending=False).head(30).iterrows()]
        current = float(profile["current_available_balance"])
        reserve = float(profile["minimum_balance_to_keep"])
        currency = str(profile.get("home_currency", ""))
        return jsonify({
            "user_id": DEMO_USER,
            "currency": currency,
            "profile": {"home_currency": currency, "current_balance": current, "minimum_balance": reserve},
            "current_balance": current,
            "minimum_balance": reserve,
            "safe_amount": safe_capacity,
            "purchase_amount": 0,
            "shortfall": 0,
            "financial_health": "Protected" if safe_capacity > 0 else "Under review",
            "financial_plan": {"current_balance": current, "minimum_reserve": reserve, "safe_to_spend": safe_capacity, "upcoming_income": float(income["home_amount"].sum()) if not income.empty else 0, "upcoming_essentials": float(essentials["home_amount"].sum()) if not essentials.empty else 0, "flexible_spending": float(upcoming[upcoming["category"].astype(str).str.lower().isin(reduce_categories | stop_categories)]["home_amount"].sum())},
            "upcoming_essential_expenses": float(essentials["home_amount"].sum()) if not essentials.empty else 0,
            "confirmed_upcoming_income": float(income["home_amount"].sum()) if not income.empty else 0,
            "upcoming_events": events,
            "transactions": transactions,
        })
    except Exception as exc:
        print(f"PROFILE API ERROR: {type(exc).__name__}: {exc}")
        return jsonify({"success": False, "error": str(exc)}), 500


def extract_amount(text):
    """
    Extract a purchase amount from common formats such as:
    ₹20,000
    Rs 20000
    INR 20,000
    20000
    """
    patterns = [
        r"₹\s*([\d,]+(?:\.\d+)?)",
        r"\bINR\s*([\d,]+(?:\.\d+)?)",
        r"\bRs\.?\s*([\d,]+(?:\.\d+)?)",
        r"\bRupees?\s*([\d,]+(?:\.\d+)?)",
        r"\b([\d,]+(?:\.\d+)?)\s*(?:rupees?|inr)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return float(match.group(1).replace(",", ""))

    # Fallback: choose a standalone number of reasonable purchase size.
    numbers = re.findall(r"\b\d[\d,]*(?:\.\d+)?\b", text)
    if numbers:
        values = []
        for value in numbers:
            try:
                values.append(float(value.replace(",", "")))
            except ValueError:
                pass

        if values:
            return values[-1]

    return None


def format_money(value):
    value = float(value)
    if abs(value - round(value)) < 1e-9:
        return f"{round(value):,.0f}"
    return f"{value:,.2f}"


def build_decision_context(simulated_request, result, amount, scoped_engine=None, profile_values=None):
    scoped_engine = scoped_engine or engine
    profile = scoped_engine.profile(DEMO_USER)
    if profile_values:
        profile = {**profile, "current_available_balance": profile_values["current_available_balance"], "minimum_balance_to_keep": profile_values["minimum_balance_to_keep"]}
    request_date = simulated_request["request_date"]
    forecast = scoped_engine.forecast(DEMO_USER, request_date)
    protected = {
        item.lower()
        for item in str(profile.get("expense_categories_to_protect", "")).split("|")
        if item
    }
    upcoming = forecast[
        (forecast["event_date"] >= norm_date(request_date))
        & (forecast["event_date"] <= norm_date(request_date) + pd.Timedelta(days=30))
    ]
    essential = upcoming[
        (upcoming["direction"].astype(str).str.lower() == "debit")
        & (upcoming["category"].astype(str).str.lower().isin(protected))
    ]
    income = upcoming[
        (upcoming["direction"].astype(str).str.lower() == "credit")
        & (upcoming["category"].astype(str).str.lower() == "salary")
    ]
    reduce_categories = {
        item.lower()
        for item in str(profile.get("expense_categories_user_is_willing_to_reduce", "")).split("|")
        if item
    }
    stop_categories = {
        item.lower()
        for item in str(profile.get("expense_categories_user_is_willing_to_stop", "")).split("|")
        if item
    }

    def event_payload(row):
        category = str(row.get("category", "other")).lower()
        direction = str(row.get("direction", "debit")).lower()
        event_date = pd.to_datetime(row.get("event_date"), errors="coerce")
        return {
            "event_id": str(row.get("event_id", "")),
            "date": event_date.strftime("%Y-%m-%d") if pd.notna(event_date) else "",
            "description": str(row.get("description", "")).strip(),
            "category": category,
            "amount": round(float(row.get("home_amount", row.get("amount", 0)) or 0), 2),
            "direction": direction,
            "status": str(row.get("status", "scheduled")),
            "essential": category in protected,
            "flexible": category in reduce_categories or category in stop_categories,
            "projected": bool(row.get("_projected", False)),
        }

    upcoming_events = [event_payload(row) for _, row in upcoming.sort_values("event_date").head(12).iterrows()]
    transactions = [
        event_payload(row)
        for _, row in scoped_engine._events(DEMO_USER).sort_values("event_date", ascending=False).head(30).iterrows()
    ]
    current_balance = float(profile["current_available_balance"])
    minimum_reserve = float(profile["minimum_balance_to_keep"])
    safe_amount = float(result.get("amount_safe_to_pay") or 0)
    shortfall = max(0, float(amount) - safe_amount)
    method = result.get("recommended_payment_method")
    status = result.get("affordability_status")
    changes = result.get("spending_changes_needed") or "none"
    plan_entries = []
    payment_plan = str(result.get("payment_plan") or "none")
    if payment_plan != "none":
        for entry in payment_plan.split("|"):
            date, payment = entry.split(":", 1)
            plan_entries.append((date, float(payment)))
    change_entries = [] if changes == "none" else changes.split("|")
    _, forecast_values, _ = scoped_engine._daily_path(DEMO_USER, request_date, change_entries)
    first_payment = plan_entries[0][1] if plan_entries else 0
    projected_balance = round(float(forecast_values[0]) - first_payment, 2)
    forecast_impact = "SAFE" if scoped_engine.simulate(DEMO_USER, request_date, plan_entries, change_entries) else "RESERVE AT RISK"
    if method == "full_payment":
        explanation = (
            f"You can safely make this {format_money(amount)} purchase today. "
            f"The forecast keeps your balance above the {format_money(minimum_reserve)} minimum reserve."
        )
    elif method == "partial_payment":
        explanation = (
            f"The engine recommends paying {format_money(safe_amount)} now and completing the "
            f"remaining {format_money(shortfall)} through the returned partial-payment plan. "
            "The reserve remains protected."
        )
    elif method == "installments":
        explanation = (
            f"Paying {format_money(amount)} immediately would put too much pressure on the forecast. "
            "The engine found an installment option that completes the purchase while protecting your reserve."
        )
    elif method == "wait":
        date = result.get("earliest_date_for_full_payment") or "the earliest safe date"
        explanation = (
            f"This purchase is not safe today, but the forecast shows it becomes affordable on {date}. "
            "The agent recommends waiting until then to protect your minimum reserve."
        )
    elif safe_amount < float(amount):
        explanation = (
            f"You requested {format_money(amount)}, but the current safe spending capacity is "
            f"{format_money(safe_amount)}, leaving a shortfall of {format_money(shortfall)}. "
            f"Paying the full amount now would breach the {format_money(minimum_reserve)} minimum reserve."
        )
    else:
        explanation = (
            f"The requested {format_money(amount)} is within the forecast safe capacity, but the "
            "available payment methods do not match this profile's payment preferences. "
            "No purchase recommendation is made."
        )

    if changes != "none":
        explanation += " Flexible spending changes are included while essential expenses remain protected."

    actions = {
        "full_payment": "PAY NOW",
        "partial_payment": "USE PARTIAL PAYMENT",
        "installments": "USE INSTALLMENTS",
        "wait": "WAIT",
        "not_recommended": "DO NOT BUY YET",
    }
    action = actions.get(method, "DO NOT BUY YET")
    xray = {
        "current_balance": current_balance,
        "minimum_reserve": minimum_reserve,
        "safe_to_spend": safe_amount,
        "purchase_amount": float(amount),
        "shortfall": shortfall,
        "projected_balance": projected_balance,
        "forecast_impact": forecast_impact,
        "upcoming_essentials": float(essential["home_amount"].sum()) if not essential.empty else 0,
        "confirmed_income": float(income["home_amount"].sum()) if not income.empty else 0,
    }
    return {
        "current_balance": current_balance,
        "currency": str(profile.get("home_currency", "")),
        "minimum_balance": minimum_reserve,
        "purchase_amount": float(amount),
        "shortfall": shortfall,
        "projected_balance": projected_balance,
        "forecast_impact": forecast_impact,
        "safe_amount": safe_amount,
        "upcoming_essential_expenses": float(essential["home_amount"].sum()) if not essential.empty else 0,
        "confirmed_upcoming_income": float(income["home_amount"].sum()) if not income.empty else 0,
        "upcoming_essentials": xray["upcoming_essentials"],
        "confirmed_income": xray["confirmed_income"],
        "financial_xray": xray,
        "financial_health": "Protected" if safe_amount >= amount else "Under review",
        "autonomous_action": action,
        "dynamic_reason": explanation,
        "xray_indicators": {
            "balance_checked": True,
            "confirmed_income_checked": not income.empty,
            "commitments_checked": not essential.empty,
            "reserve_protected": True,
        },
        "upcoming_events": upcoming_events,
        "transactions": transactions,
        "financial_plan": {
            "current_balance": current_balance,
            "minimum_reserve": minimum_reserve,
            "safe_to_spend": safe_amount,
            "upcoming_income": float(income["home_amount"].sum()) if not income.empty else 0,
            "upcoming_essentials": float(essential["home_amount"].sum()) if not essential.empty else 0,
            "flexible_spending": float(upcoming[upcoming["category"].astype(str).str.lower().isin(reduce_categories | stop_categories)]["home_amount"].sum()),
        },
        "decision_status": status,
    }


@app.post("/api/analyze")
def analyze():
    try:
        body = request.get_json(silent=True) or {}

        text = str(body.get("text", "")).strip()

        if not text:
            return jsonify({
                "success": False,
                "error": "Please enter a purchase request."
            }), 400

        amount = body.get("amount")

        if amount is None:
            amount = extract_amount(text)

        if amount is None or float(amount) <= 0:
            return jsonify({
                "success": False,
                "error": "Please include the purchase amount, for example: ₹20,000."
            }), 400

        scoped_engine, profile_values = build_profile_engine(body.get("profile"))

        # Start from a REAL request belonging to a REAL user/profile.
        simulated_request = DEMO_TEMPLATE.copy()

        simulated_request["request_id"] = "WEB_DEMO"
        simulated_request["user_id"] = DEMO_USER
        simulated_request["requested_amount"] = float(amount)
        simulated_request["request_text"] = text
        simulated_request["allows_partial_payment"] = True

        # Keep the real template's date/deadline so the financial engine
        # can perform its normal forecast.
        result = scoped_engine.decide(simulated_request)

        # WEBSITE SAFETY OVERRIDE:
        # If the authoritative engine says the requested amount is fully
        # inside the safe spending capacity, never show a contradictory
        # "DO NOT BUY YET" result.  The website must use one consistent
        # decision across Best Action, X-Ray and Payment Plan.
        safe_amount = float(result.get("amount_safe_to_pay") or 0)
        if safe_amount >= float(amount):
            request_day = str(simulated_request["request_date"])[:10]
            result["amount_safe_to_pay"] = float(amount)
            result["affordability_status"] = "affordable_now"
            result["recommended_payment_method"] = "full_payment"
            result["payment_plan"] = f"{request_day}:{float(amount):.2f}"
            result["earliest_date_for_full_payment"] = request_day
            result["spending_changes_needed"] = "none"

        context = build_decision_context(simulated_request, result, float(amount), scoped_engine, profile_values)
        output = {
            "request_id": "WEB_DEMO",
            "amount_safe_to_pay": result.get("amount_safe_to_pay"),
            "affordability_status": result.get("affordability_status"),
            "recommended_payment_method": result.get("recommended_payment_method"),
            "payment_plan": result.get("payment_plan"),
            "earliest_date_for_full_payment": result.get("earliest_date_for_full_payment"),
            "spending_changes_needed": result.get("spending_changes_needed"),
            "decision_explanation": context["dynamic_reason"],
            **context,
        }

        return jsonify(output)

    except Exception as exc:
        print(f"API ERROR: {type(exc).__name__}: {exc}")
        return jsonify({
            "success": False,
            "error": str(exc)
        }), 500


if __name__ == "__main__":
    print()
    print("=" * 60)
    print("BUY OR WAIT — AI FINANCIAL AGENT")
    print("=" * 60)
    print(f"Dataset: CONNECTED")
    print(f"Financial engine: CONNECTED")
    print(f"Demo user: {DEMO_USER}")
    print(f"Demo request: {DEMO_TEMPLATE.get('request_id')}")
    print("API: http://127.0.0.1:5000")
    print("=" * 60)
    print()

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False
    )
