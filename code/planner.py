from datetime import timedelta
import pandas as pd


def money(value):
    return f"{float(value):.2f}"


class PaymentPlanner:

    def __init__(
        self,
        simulator,
        request,
        payment_options,
        allowed_methods,
        max_installment_months=0,
    ):
        self.simulator = simulator
        self.request = request
        self.payment_options = (
            payment_options
        )

        self.allowed_methods = set(
            str(x).lower()
            for x in allowed_methods
        )

        self.max_installment_months = float(
            max_installment_months or 0
        )

        self.request_date = (
            pd.to_datetime(
                request["request_date"]
            ).normalize()
        )

        self.desired_date = (
            pd.to_datetime(
                request[
                    "desired_completion_date"
                ]
            ).normalize()
        )

        self.requested_amount = float(
            request[
                "requested_amount"
            ]
        )

    def full_payment_candidate(
        self,
        spending_changes=None,
    ):
        if "full_payment" not in self.allowed_methods:
            return None

        if not self.simulator.can_pay_on_date(
            self.requested_amount,
            self.request_date,
            spending_changes,
        ):
            return None

        return {
            "payment_method": "full_payment",
            "payment_plan": (
                f"{self.request_date.date()}:"
                f"{money(self.requested_amount)}"
            ),
            "completion_date": self.request_date,
            "start_date": self.request_date,
            "total_paid": self.requested_amount,
            "number_of_payments": 1,
            "spending_changes": (
                spending_changes or []
            ),
            "payment_option_id": 10**9,
        }

    def partial_payment_candidate(
        self,
        safe_amount,
        earliest_full_date,
        spending_changes=None,
    ):
        allows = str(
            self.request[
                "allows_partial_payment"
            ]
        ).lower()

        if allows not in {
            "true",
            "1",
            "yes",
        }:
            return None

        if "partial_payment" not in self.allowed_methods:
            return None

        if earliest_full_date is None:
            return None

        earliest = pd.to_datetime(
            earliest_full_date
        ).normalize()

        if earliest > self.desired_date:
            return None

        safe_amount = round(
            float(safe_amount),
            2,
        )

        if (
            safe_amount <= 0
            or safe_amount
            >= self.requested_amount
        ):
            return None

        remaining = round(
            self.requested_amount
            - safe_amount,
            2,
        )

        if not self.simulator.can_pay_on_date(
            remaining,
            earliest,
            spending_changes,
        ):
            return None

        return {
            "payment_method": "partial_payment",
            "payment_plan": (
                f"{self.request_date.date()}:"
                f"{money(safe_amount)}|"
                f"{earliest.date()}:"
                f"{money(remaining)}"
            ),
            "completion_date": earliest,
            "start_date": self.request_date,
            "total_paid": self.requested_amount,
            "number_of_payments": 2,
            "spending_changes": (
                spending_changes or []
            ),
            "payment_option_id": 10**9,
        }

    def installment_candidates(
        self,
        spending_changes=None,
    ):
        candidates = []

        if "installments" not in self.allowed_methods:
            return candidates

        if (
            self.payment_options is None
            or self.payment_options.empty
        ):
            return candidates

        for _, option in (
            self.payment_options.iterrows()
        ):
            try:
                amount = float(
                    option["payment_amount"]
                )

                number = int(
                    option["number_of_payments"]
                )

                first_date = pd.to_datetime(
                    option[
                        "first_payment_date"
                    ]
                ).normalize()

                frequency = int(
                    option[
                        "payment_frequency_days"
                    ]
                )

                option_id = int(
                    option[
                        "payment_option_id"
                    ]
                )

            except (
                ValueError,
                TypeError,
            ):
                continue

            if (
                amount <= 0
                or number <= 0
            ):
                continue

            if first_date < self.request_date:
                continue

            if (
                self.max_installment_months
                > 0
            ):
                months = (
                    (
                        first_date
                        + timedelta(
                            days=number
                            * frequency
                        )
                    )
                    - self.request_date
                ).days / 30.44

                if (
                    months
                    > self.max_installment_months
                ):
                    continue

            payments = []

            for i in range(number):
                date = (
                    first_date
                    + timedelta(
                        days=i * frequency
                    )
                )

                payments.append(
                    (
                        date,
                        amount,
                    )
                )

            completion = payments[-1][0]

            if completion > self.desired_date:
                continue

            result = self.simulator.simulate(
                payments=payments,
                spending_changes=(
                    spending_changes
                ),
            )

            if not result["is_safe"]:
                continue

            total_paid = round(
                sum(
                    amount
                    for _, amount
                    in payments
                ),
                2,
            )

            candidates.append(
                {
                    "payment_method": "installments",
                    "payment_plan": "|".join(
                        f"{date.date()}:"
                        f"{money(amount)}"
                        for date, amount
                        in payments
                    ),
                    "completion_date": completion,
                    "start_date": payments[0][0],
                    "total_paid": total_paid,
                    "number_of_payments": number,
                    "spending_changes": (
                        spending_changes or []
                    ),
                    "payment_option_id": option_id,
                }
            )

        return candidates

    def rank(self, candidates):
        if not candidates:
            return None

        def key(candidate):
            changes = candidate.get(
                "spending_changes",
                [],
            )

            return (
                len(changes),
                candidate["total_paid"],
                candidate["start_date"],
                candidate["number_of_payments"],
                candidate.get(
                    "payment_option_id",
                    10**9,
                ),
            )

        return sorted(
            candidates,
            key=key,
        )[0]