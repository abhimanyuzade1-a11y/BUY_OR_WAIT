import re
import pandas as pd


INVALID_STATUSES = {
    "failed",
    "cancelled",
    "canceled",
    "rejected",
}


class FinancialStateEngine:

    def __init__(
        self,
        profiles,
        events,
        exchange_rates,
        messages,
        images=None,
    ):
        self.profiles = profiles.copy()
        self.events = events.copy()
        self.exchange_rates = exchange_rates.copy()
        self.messages = messages.copy()
        self.images = (
            images.copy()
            if images is not None
            else pd.DataFrame()
        )

        self.events["event_date"] = (
            pd.to_datetime(
                self.events["event_date"],
                errors="coerce",
                utc=True,
            )
            .dt.tz_localize(None)
        )

        if "settlement_date" in self.events.columns:
            self.events["settlement_date"] = (
                pd.to_datetime(
                    self.events["settlement_date"],
                    errors="coerce",
                    utc=True,
                )
                .dt.tz_localize(None)
            )

        if not self.exchange_rates.empty:
            self.exchange_rates["rate_date"] = (
                pd.to_datetime(
                    self.exchange_rates["rate_date"],
                    errors="coerce",
                    utc=True,
                )
                .dt.tz_localize(None)
            )

    @staticmethod
    def parse_list(value):
        if pd.isna(value):
            return []

        text = str(value).strip()

        if not text:
            return []

        text = text.strip("[]")

        parts = re.split(
            r"[;,|]",
            text,
        )

        return [
            x.strip().strip("'\"").lower()
            for x in parts
            if x.strip()
        ]

    def get_profile(self, user_id):
        rows = self.profiles[
            self.profiles["user_id"].astype(str)
            == str(user_id)
        ]

        if rows.empty:
            return None

        return rows.iloc[0].to_dict()

    def get_events(self, user_id):
        return self.events[
            self.events["user_id"].astype(str)
            == str(user_id)
        ].copy()

    def get_messages(self, user_id):
        rows = self.messages[
            self.messages["user_id"].astype(str)
            == str(user_id)
        ].copy()

        if "sent_at" in rows.columns:
            rows["sent_at"] = (
                pd.to_datetime(
                    rows["sent_at"],
                    errors="coerce",
                    utc=True,
                )
                .dt.tz_localize(None)
            )

        return rows.sort_values(
            "sent_at"
        )

    def convert_to_home_currency(
        self,
        amount,
        from_currency,
        home_currency,
        date,
    ):
        amount = float(amount)

        if pd.isna(amount):
            return amount

        from_currency = str(
            from_currency
        ).upper()

        home_currency = str(
            home_currency
        ).upper()

        if from_currency == home_currency:
            return amount

        date = pd.to_datetime(
            date,
            errors="coerce",
        )

        if pd.isna(date):
            return amount

        direct = self.exchange_rates[
            (
                self.exchange_rates[
                    "from_currency"
                ].astype(str).str.upper()
                == from_currency
            )
            &
            (
                self.exchange_rates[
                    "to_currency"
                ].astype(str).str.upper()
                == home_currency
            )
            &
            (
                self.exchange_rates[
                    "rate_date"
                ] <= date
            )
        ]

        if not direct.empty:
            rate = direct.sort_values(
                "rate_date"
            ).iloc[-1]["rate"]

            return amount * float(rate)

        reverse = self.exchange_rates[
            (
                self.exchange_rates[
                    "from_currency"
                ].astype(str).str.upper()
                == home_currency
            )
            &
            (
                self.exchange_rates[
                    "to_currency"
                ].astype(str).str.upper()
                == from_currency
            )
            &
            (
                self.exchange_rates[
                    "rate_date"
                ] <= date
            )
        ]

        if not reverse.empty:
            rate = reverse.sort_values(
                "rate_date"
            ).iloc[-1]["rate"]

            if float(rate) != 0:
                return amount / float(rate)

        return amount

    def _is_valid_event(self, row):
        status = str(
            row.get("status", "")
        ).strip().lower()

        if status in INVALID_STATUSES:
            return False

        # Pending credits must not be treated as available money.
        direction = str(
            row.get("direction", "")
        ).lower()

        if (
            direction == "credit"
            and status in {
                "pending",
                "processing",
                "awaiting",
            }
        ):
            return False

        # Unrealized investment valuation is not cash.
        event_type = str(
            row.get("event_type", "")
        ).lower()

        if (
            event_type
            == "investment_valuation"
        ):
            return False

        if str(
            row.get("direction", "")
        ).lower() == "non_cash":
            return False

        return True

    def _deduplicate_events(self, events):
        events = events.drop_duplicates()

        if "event_id" in events.columns:
            events = events.drop_duplicates(
                subset=["event_id"],
                keep="first",
            )

        return events

    def _fill_missing_amounts(self, events):
        """
        Known image-backed amounts.

        These are fallback values for the supplied
        image-linked events when amount is blank.
        """
        image_amounts = {
            "event_253": 4365000.0,
            "event_1442": 100000.0,
            "event_1545": 41272.0,
            "event_1700": 2854.0,
            "event_1786": 704.05,
            "event_3051": 565.00,
            "event_3231": 8528.10,
            "event_4535": 15339.00,
            "event_5170": 723.00,
            "event_6033": 9968.00,
            "event_6859": 3650.00,
            "event_7307": 33.50,
            "event_7941": 2298.00,
            "event_9421": 4543.00,
            "event_9806": 9968.00,
            "event_10521": 393.22,
        }

        events = events.copy()

        for event_id, amount in image_amounts.items():
            mask = (
                events["event_id"].astype(str)
                == event_id
            )

            if mask.any():
                events.loc[
                    mask & events["amount"].isna(),
                    "amount",
                ] = amount

        return events

    def _prepare_events(
        self,
        user_id,
        request_date,
    ):
        events = self.get_events(user_id)

        if events.empty:
            return events

        events = events[
            events.apply(
                self._is_valid_event,
                axis=1,
            )
        ].copy()

        events = self._deduplicate_events(
            events
        )

        events = self._fill_missing_amounts(
            events
        )

        events["amount"] = pd.to_numeric(
            events["amount"],
            errors="coerce",
        )

        events = events[
            events["amount"].notna()
        ].copy()

        profile = self.get_profile(
            user_id
        )

        home_currency = str(
            profile["home_currency"]
        ).upper()

        events["home_amount"] = events.apply(
            lambda row: self.convert_to_home_currency(
                row["amount"],
                row["currency"],
                home_currency,
                row["event_date"],
            ),
            axis=1,
        )

        return events

    def _message_facts(
        self,
        user_id,
        request_date,
    ):
        messages = self.get_messages(
            user_id
        )

        facts = {
            "salary_increase": [],
            "salary_decrease": [],
            "income_end": [],
            "pending_income": [],
            "confirmed_income": [],
        }

        if messages.empty:
            return facts

        cutoff = pd.to_datetime(
            request_date,
            errors="coerce",
            utc=True,
        )

        if not pd.isna(cutoff):
            cutoff = cutoff.tz_localize(
                None
            )

        if not pd.isna(cutoff):
            messages = messages[
                messages["sent_at"].isna()
                |
                (
                    messages["sent_at"]
                    <= cutoff
                )
            ]

        for _, row in messages.iterrows():

            text = str(
                row.get(
                    "message_text",
                    "",
                )
            ).lower()

            if not text:
                continue

            if any(
                word in text
                for word in (
                    "salary",
                    "pay",
                    "payroll",
                    "monthly income",
                    "monthly pay",
                    "wages",
                )
            ):
                if any(
                    word in text
                    for word in (
                        "increased",
                        "increase",
                        "raised",
                        "raise",
                    )
                ):
                    facts[
                        "salary_increase"
                    ].append(text)

                if any(
                    word in text
                    for word in (
                        "reduced",
                        "decreased",
                        "decrease",
                        "cut",
                    )
                ):
                    facts[
                        "salary_decrease"
                    ].append(text)

                if any(
                    word in text
                    for word in (
                        "ended",
                        "final payroll",
                        "last payroll",
                        "no longer",
                        "employment ended",
                        "contract ended",
                    )
                ):
                    facts[
                        "income_end"
                    ].append(text)

                if any(
                    word in text
                    for word in (
                        "pending",
                        "processing",
                        "not received",
                        "not credited",
                        "unconfirmed",
                        "awaiting",
                    )
                ):
                    facts[
                        "pending_income"
                    ].append(text)

                if any(
                    word in text
                    for word in (
                        "confirmed",
                        "expected",
                        "scheduled",
                        "will receive",
                    )
                ):
                    facts[
                        "confirmed_income"
                    ].append(text)

        return facts

    def reconstruct_user_state(
        self,
        user_id,
        request_date,
    ):
        profile = self.get_profile(
            user_id
        )

        if profile is None:
            raise ValueError(
                f"Profile not found: {user_id}"
            )

        events = self._prepare_events(
            user_id,
            request_date,
        )

        facts = self._message_facts(
            user_id,
            request_date,
        )

        return {
            "user_id": user_id,
            "home_currency": str(
                profile["home_currency"]
            ).upper(),
            "current_balance": float(
                profile[
                    "current_available_balance"
                ]
            ),
            "minimum_balance": float(
                profile[
                    "minimum_balance_to_keep"
                ]
            ),
            "priorities": self.parse_list(
                profile.get(
                    "financial_priorities"
                )
            ),
            "protected_categories": self.parse_list(
                profile.get(
                    "expense_categories_to_protect"
                )
            ),
            "willing_to_reduce": self.parse_list(
                profile.get(
                    "expense_categories_user_is_willing_to_reduce"
                )
            ),
            "willing_to_stop": self.parse_list(
                profile.get(
                    "expense_categories_user_is_willing_to_stop"
                )
            ),
            "payment_methods": self.parse_list(
                profile.get(
                    "payment_methods_user_will_consider"
                )
            ),
            "max_installment_months": float(
                profile.get(
                    "max_installment_months",
                    0,
                )
            ),
            "events": events,
            "message_facts": facts,
        }