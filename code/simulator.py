import pandas as pd
from datetime import timedelta


class SafetySimulator:

    INVALID_STATUSES = {
        "failed",
        "cancelled",
        "canceled",
        "rejected",
    }

    VARIABLE_CATEGORIES = {
        "groceries",
        "transport",
        "dining",
        "shopping",
        "entertainment",
    }

    STRUCTURAL_CATEGORIES = {
        "rent",
        "housing",
        "utilities",
        "education",
        "debt_repayment",
        "insurance",
        "family_support",
        "healthcare",
        "salary",
        "cloud_storage",
        "music_subscription",
        "streaming",
        "delivery_membership",
        "gym",
    }

    def __init__(
        self,
        user_state,
        request_date,
    ):
        self.state = user_state

        self.request_date = (
            pd.to_datetime(
                request_date
            ).normalize()
        )

    def _valid_events(self):
        events = self.state["events"].copy()

        if events.empty:
            return events

        events["event_date"] = pd.to_datetime(
            events["event_date"],
            errors="coerce",
        )

        events = events.dropna(
            subset=["event_date"]
        )

        events = events[
            ~events["status"]
            .astype(str)
            .str.lower()
            .isin(self.INVALID_STATUSES)
        ]

        return events

    def _series_key(
        self,
        row,
        category_level=False,
    ):
        direction = str(
            row.get(
                "direction",
                "",
            )
        ).lower()

        category = str(
            row.get(
                "category",
                "",
            )
        ).lower()

        if category_level:
            return (
                direction,
                category,
            )

        description = str(
            row.get(
                "description",
                "",
            )
        ).lower()

        return (
            direction,
            category,
            description,
        )

    def _detect_recurring_series(
        self,
        events,
        start,
    ):
        recurring = []

        if events.empty:
            return recurring

        historical = events[
            events["event_date"] < start
        ].copy()

        if historical.empty:
            return recurring

        for category_level in (
            False,
            True,
        ):

            groups = historical.groupby(
                lambda index:
                    self._series_key(
                        historical.loc[index],
                        category_level,
                    )
            )

            for _, group in groups:

                category = str(
                    group.iloc[0].get(
                        "category",
                        "",
                    )
                ).lower()

                if (
                    category_level
                    and category
                    not in self.VARIABLE_CATEGORIES
                ):
                    continue

                if (
                    not category_level
                    and category
                    in self.VARIABLE_CATEGORIES
                ):
                    continue

                dates = sorted(
                    pd.to_datetime(
                        group["event_date"]
                    )
                    .dt.normalize()
                    .unique()
                )

                if len(dates) < 3:
                    continue

                gaps = [
                    int(
                        (
                            dates[i]
                            - dates[i - 1]
                        )
                        / pd.Timedelta(days=1)
                    )
                    for i in range(
                        1,
                        len(dates),
                    )
                ]

                if not gaps:
                    continue

                median_gap = int(
                    round(
                        pd.Series(
                            gaps
                        ).median()
                    )
                )

                # Common recurring frequencies.
                if median_gap not in {
                    7,
                    14,
                    28,
                    30,
                    31,
                }:
                    continue

                deviation = max(
                    abs(
                        gap
                        - median_gap
                    )
                    for gap in gaps
                )

                if deviation > 3:
                    continue

                last = group.sort_values(
                    "event_date"
                ).iloc[-1]

                amount = float(
                    group["home_amount"]
                    .median()
                )

                recurring.append(
                    {
                        "key": self._series_key(
                            last,
                            category_level,
                        ),
                        "category": category,
                        "direction": str(
                            last.get(
                                "direction",
                                "",
                            )
                        ).lower(),
                        "amount": amount,
                        "last_date": pd.Timestamp(
                            last["event_date"]
                        ).normalize(),
                        "gap": median_gap,
                        "category_level": (
                            category_level
                        ),
                        "flexibility": str(
                            last.get(
                                "flexibility",
                                "",
                            )
                        ).lower(),
                        "event_id": str(
                            last.get(
                                "event_id",
                                "",
                            )
                        ),
                    }
                )

        # Remove duplicate structural series.
        unique = {}

        for item in recurring:
            key = (
                item["key"],
                item["gap"],
            )
            unique[key] = item

        return list(
            unique.values()
        )

    def _build_recurring_events(
        self,
        events,
        start,
        end,
    ):
        projected = []

        if events.empty:
            return events

        explicit_future = events[
            events["event_date"] >= start
        ].copy()

        recurring = (
            self._detect_recurring_series(
                events,
                start,
            )
        )

        existing_keys = set()

        for _, row in explicit_future.iterrows():
            existing_keys.add(
                (
                    self._series_key(
                        row,
                        False,
                    ),
                    row["event_date"].date(),
                )
            )

        income_end = False

        for item in recurring:
            if (
                item["direction"]
                == "credit"
                and item["category"]
                == "salary"
            ):
                description = str(
                    item["key"][-1]
                ).lower()

                if "final" in description:
                    income_end = True

        for item in recurring:

            if (
                income_end
                and item["direction"]
                == "credit"
                and item["category"]
                == "salary"
            ):
                continue

            next_date = (
                item["last_date"]
                + timedelta(
                    days=item["gap"]
                )
            )

            while next_date <= end:

                if next_date >= start:

                    # Don't duplicate an explicit event.
                    duplicate = False

                    for _, row in explicit_future.iterrows():
                        if (
                            abs(
                                (
                                    row["event_date"]
                                    - next_date
                                ).days
                            )
                            <= 1
                            and str(
                                row.get(
                                    "category",
                                    "",
                                )
                            ).lower()
                            == item["category"]
                            and str(
                                row.get(
                                    "direction",
                                    "",
                                )
                            ).lower()
                            == item["direction"]
                        ):
                            duplicate = True
                            break

                    if not duplicate:

                        base = events[
                            events.apply(
                                lambda r:
                                    self._series_key(
                                        r,
                                        item[
                                            "category_level"
                                        ],
                                    )
                                    == item["key"],
                                axis=1,
                            )
                        ]

                        if not base.empty:
                            new_row = (
                                base.sort_values(
                                    "event_date"
                                ).iloc[-1].copy()
                            )

                            new_row[
                                "event_date"
                            ] = next_date

                            new_row[
                                "home_amount"
                            ] = item["amount"]

                            new_row[
                                "_projected"
                            ] = True

                            projected.append(
                                new_row
                            )

                next_date += timedelta(
                    days=item["gap"]
                )

        if not projected:
            return events

        return pd.concat(
            [
                events,
                pd.DataFrame(
                    projected
                ),
            ],
            ignore_index=True,
        )

    def _apply_changes(
        self,
        events,
        spending_changes,
    ):
        if not spending_changes:
            return events

        events = events.copy()

        for change in spending_changes:

            parts = str(change).split(":")

            if len(parts) < 2:
                continue

            action = parts[0]
            event_id = parts[1]

            source = self.state["events"]

            source_rows = source[
                source["event_id"]
                .astype(str)
                == str(event_id)
            ]

            if source_rows.empty:
                continue

            source_row = source_rows.iloc[0]

            category = str(
                source_row.get(
                    "category",
                    "",
                )
            ).lower()

            description = str(
                source_row.get(
                    "description",
                    "",
                )
            ).lower()

            mask = (
                events["category"]
                .astype(str)
                .str.lower()
                == category
            )

            # For structural recurring expenses,
            # also require the same description.
            if category not in self.VARIABLE_CATEGORIES:
                mask = (
                    mask
                    &
                    (
                        events[
                            "description"
                        ]
                        .astype(str)
                        .str.lower()
                        == description
                    )
                )

            if action == "stop":
                events = events[
                    ~mask
                ]

            elif (
                action == "reduce_to"
                and len(parts) >= 3
            ):
                try:
                    new_amount = float(
                        parts[2]
                    )

                    events.loc[
                        mask,
                        "home_amount",
                    ] = new_amount

                except ValueError:
                    pass

        return events

    def _direction(self, row):
        return str(
            row.get(
                "direction",
                "",
            )
        ).lower()

    def simulate(
        self,
        payments=None,
        spending_changes=None,
        horizon_days=90,
    ):
        payments = payments or []

        start = self.request_date

        end = (
            start
            + timedelta(
                days=horizon_days
            )
        )

        events = self._valid_events()

        events = self._build_recurring_events(
            events,
            start,
            end,
        )

        events = events[
            (events["event_date"] >= start)
            &
            (events["event_date"] <= end)
        ].copy()

        events = self._apply_changes(
            events,
            spending_changes,
        )

        payment_map = {}

        for date, amount in payments:

            date = pd.to_datetime(
                date
            ).date()

            payment_map[date] = (
                payment_map.get(
                    date,
                    0.0,
                )
                + float(amount)
            )

        balance = float(
            self.state["current_balance"]
        )

        minimum = float(
            self.state["minimum_balance"]
        )

        daily = []

        for day in pd.date_range(
            start,
            end,
            freq="D",
        ):

            day_events = events[
                events["event_date"].dt.date
                == day.date()
            ]

            for _, event in day_events.iterrows():

                direction = (
                    self._direction(
                        event
                    )
                )

                amount = float(
                    event["home_amount"]
                )

                if direction == "credit":
                    balance += amount

                elif direction == "debit":
                    balance -= amount

            if day.date() in payment_map:
                balance -= payment_map[
                    day.date()
                ]

            daily.append(
                (
                    day.date(),
                    round(
                        balance,
                        2,
                    ),
                )
            )

            if (
                balance
                < minimum - 1e-9
            ):
                return {
                    "is_safe": False,
                    "minimum_balance_reached": round(
                        balance,
                        2,
                    ),
                    "daily_balances": daily,
                }

        return {
            "is_safe": True,
            "minimum_balance_reached": round(
                min(
                    value
                    for _, value
                    in daily
                ),
                2,
            ),
            "daily_balances": daily,
        }

    def compute_max_safe_initial_payment(
        self,
        requested_amount,
        spending_changes=None,
    ):
        requested_amount = float(
            requested_amount
        )

        if requested_amount <= 0:
            return 0.0

        low = 0.0
        high = requested_amount

        for _ in range(55):

            mid = (
                low + high
            ) / 2

            result = self.simulate(
                payments=[
                    (
                        self.request_date,
                        mid,
                    )
                ],
                spending_changes=(
                    spending_changes
                ),
            )

            if result["is_safe"]:
                low = mid
            else:
                high = mid

        return round(
            low,
            2,
        )

    def can_pay_on_date(
        self,
        amount,
        payment_date,
        spending_changes=None,
    ):
        return self.simulate(
            payments=[
                (
                    payment_date,
                    amount,
                )
            ],
            spending_changes=(
                spending_changes
            ),
        )["is_safe"]

    def find_earliest_date_for_full_payment(
        self,
        amount,
        max_days=90,
    ):
        for offset in range(
            max_days + 1
        ):

            date = (
                self.request_date
                + timedelta(
                    days=offset
                )
            )

            if self.can_pay_on_date(
                amount,
                date,
                None,
            ):
                return str(
                    date.date()
                )

        return None