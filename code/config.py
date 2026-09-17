from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = REPO_ROOT / "dataset"

REQUESTS_PATH = DATASET_DIR / "requests.csv"
PROFILES_PATH = DATASET_DIR / "financial_profiles.csv"
EVENTS_PATH = DATASET_DIR / "financial_events.csv"
MESSAGES_PATH = DATASET_DIR / "messages.csv"
IMAGES_PATH = DATASET_DIR / "images.csv"
EXCHANGE_RATES_PATH = DATASET_DIR / "exchange_rates.csv"
PAYMENT_OPTIONS_PATH = DATASET_DIR / "request_payment_options.csv"
SAMPLE_REQUESTS_PATH = DATASET_DIR / "sample_requests.csv"

OUTPUT_PATH = REPO_ROOT / "output.csv"

OUTPUT_COLUMNS = [
    "request_id",
    "amount_safe_to_pay",
    "affordability_status",
    "recommended_payment_method",
    "payment_plan",
    "earliest_date_for_full_payment",
    "spending_changes_needed",
    "decision_explanation",
]