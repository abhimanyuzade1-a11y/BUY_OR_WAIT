from pathlib import Path

import pandas as pd

from config import (
    REQUESTS_PATH,
    PROFILES_PATH,
    EVENTS_PATH,
    EXCHANGE_RATES_PATH,
    MESSAGES_PATH,
    IMAGES_PATH,
    PAYMENT_OPTIONS_PATH,
    OUTPUT_PATH,
    OUTPUT_COLUMNS,
)

from engine import BuyOrWaitEngine


def main():

    print("=" * 65)
    print("BUY OR WAIT")
    print("=" * 65)

    print("Loading datasets...")

    requests = pd.read_csv(
        REQUESTS_PATH
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

    print(
        f"Requests: {len(requests)}"
    )

    print(
        f"Profiles: {len(profiles)}"
    )

    print(
        f"Events: {len(events)}"
    )

    print(
        f"Messages: {len(messages)}"
    )

    print(
        f"Images: {len(images)}"
    )

    print(
        f"Payment options: "
        f"{len(payment_options)}"
    )

    print()
    print("Building financial agent...")

    engine = BuyOrWaitEngine(
        requests=requests,
        profiles=profiles,
        events=events,
        rates=rates,
        messages=messages,
        images=images,
        payment_options=payment_options,
        repo_root=Path(__file__).resolve().parent.parent,
    )

    print("Processing requests...")

    output = engine.process(
        requests
    )

    output = output[
        OUTPUT_COLUMNS
    ]

    output.to_csv(
        OUTPUT_PATH,
        index=False,
    )

    print()
    print("=" * 65)
    print("COMPLETE")
    print("=" * 65)

    print(
        f"Output: {OUTPUT_PATH}"
    )

    print(
        f"Rows: {len(output)}"
    )


if __name__ == "__main__":
    main()