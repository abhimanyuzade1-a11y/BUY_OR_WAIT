import sys

import pandas as pd

sys.path.insert(
    0,
    "code",
)

from config import (
    PROFILES_PATH,
    EVENTS_PATH,
    EXCHANGE_RATES_PATH,
    MESSAGES_PATH,
    IMAGES_PATH,
    PAYMENT_OPTIONS_PATH,
    SAMPLE_REQUESTS_PATH,
)

from engine import BuyOrWaitEngine


CHECK_COLUMNS = [
    "amount_safe_to_pay",
    "affordability_status",
    "recommended_payment_method",
    "payment_plan",
    "earliest_date_for_full_payment",
    "spending_changes_needed",
]


def normalize(
    value
):
    if pd.isna(value):
        return "none"

    return str(
        value
    ).strip()


def numbers_match(
    expected,
    actual,
):
    try:

        return abs(
            float(expected)
            - float(actual)
        ) <= 0.01

    except (
        ValueError,
        TypeError,
    ):

        return (
            normalize(expected)
            == normalize(actual)
        )


def main():

    print("=" * 70)
    print("BUY OR WAIT - SAMPLE EVALUATION")
    print("=" * 70)

    requests = pd.read_csv(
        SAMPLE_REQUESTS_PATH
    )

    profiles = pd.read_csv(
        PROFILES_PATH
    )

    events = pd.read_csv(
        EVENTS_PATH
    )

    rates = pd.read_csv(
        EXCHANGE_RATES_PATH
    )

    messages = pd.read_csv(
        MESSAGES_PATH
    )

    images = pd.read_csv(
        IMAGES_PATH
    )

    payment_options = pd.read_csv(
        PAYMENT_OPTIONS_PATH
    )

    engine = BuyOrWaitEngine(
        requests=requests,
        profiles=profiles,
        events=events,
        rates=rates,
        messages=messages,
        images=images,
        payment_options=payment_options,
        repo_root=".",
    )

    actual = engine.process(
        requests
    )

    total = 0
    matched = 0

    print()
    print("=" * 70)
    print("COMPARISON")
    print("=" * 70)

    for _, expected in requests.iterrows():

        request_id = str(
            expected[
                "request_id"
            ]
        )

        rows = actual[
            actual["request_id"]
            .astype(str)
            == request_id
        ]

        if rows.empty:

            print(
                f"{request_id}: MISSING"
            )

            continue

        result = rows.iloc[0]

        row_matches = 0

        mismatches = []

        for column in CHECK_COLUMNS:

            total += 1

            expected_value = expected[
                column
            ]

            actual_value = result[
                column
            ]

            if (
                column
                == "amount_safe_to_pay"
            ):

                match = numbers_match(
                    expected_value,
                    actual_value,
                )

            else:

                match = (
                    normalize(
                        expected_value
                    )
                    ==
                    normalize(
                        actual_value
                    )
                )

            if match:

                matched += 1
                row_matches += 1

            else:

                mismatches.append(
                    (
                        column,
                        normalize(
                            expected_value
                        ),
                        normalize(
                            actual_value
                        ),
                    )
                )

        print(
            f"{request_id}: "
            f"{row_matches}/6 fields matched"
        )

        for (
            column,
            expected_value,
            actual_value,
        ) in mismatches:

            print(
                f"   {column}:"
                f" expected={expected_value}"
                f" | actual={actual_value}"
            )

    print()
    print("=" * 70)
    print("FINAL SCORE")
    print("=" * 70)

    print(
        f"Matched fields: "
        f"{matched}/{total}"
    )

    percentage = (
        matched / total * 100
        if total
        else 0
    )

    print(
        f"Field accuracy: "
        f"{percentage:.2f}%"
    )

    print()
    print("Actual decisions:")

    print(
        actual[
            [
                "request_id",
                "amount_safe_to_pay",
                "affordability_status",
                "recommended_payment_method",
                "payment_plan",
                "earliest_date_for_full_payment",
                "spending_changes_needed",
            ]
        ].to_string(
            index=False
        )
    )


if __name__ == "__main__":
    main()