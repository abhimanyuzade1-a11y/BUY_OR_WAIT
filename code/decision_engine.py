import itertools
import pandas as pd

from simulator import SafetySimulator
from planner import PaymentPlanner


class DecisionEngine:

    def __init__(
        self,
        state_engine,
        payment_options_df,
    ):
        self.state_engine = state_engine
        self.payment_options_df = (
            payment_options_df
        )

    def _options_for_request(
        self,
        request_id,
    ):
        return self.payment_options_df[
            self.payment_options_df[
                "request_id"
            ].astype(str)
            == str(request_id)
        ].copy()

    def _allowed_changes(
        self,
        state,
    ):
        events = state["events"]

        if events.empty:
            return []

        reduce_categories = set(
            state.get(
                "willing_to_reduce",
                [],
            )
        )

        stop_categories = set(
            state.get(
                "willing_to_stop",
                [],
            )
        )

        protected = set(
            state.get(
                "protected_categories",
                [],
            )
        )

        changes = []

        # Only recurring/flexible expenses
        # should be candidates.
        for _, event in events.iterrows():

            direction = str(
                event.get(
                    "direction",
                    "",
                )
            ).lower()

            if direction != "debit":
                continue

            flexibility = str(
                event.get(
                    "flexibility",
                    "",
                )
            ).lower()

            if flexibility not in {
                "reducible",
                "stoppable",
                "reducible_or_stoppable",
                "flexible",
                "optional",
                "discretionary",
            }:
                continue

            category = str(
                event.get(
                    "category",
                    "",
                )
            ).lower()

            if category in protected:
                continue

            event_id = str(
                event["event_id"]
            )

            if category in stop_categories:
                changes.append(
                    f"stop:{event_id}"
                )

            elif category in reduce_categories:

                minimum = event.get(
                    "minimum_allowed_amount"
                )

                if pd.notna(minimum):
                    changes.append(
                        f"reduce_to:"
                        f"{event_id}:"
                        f"{float(minimum):.2f}"
                    )

        return list(
            dict.fromkeys(changes)
        )

    def _change_combinations(
        self,
        changes,
    ):
        combinations = [[]]

        for size in range(
            1,
            min(
                3,
                len(changes),
            )
            + 1,
        ):
            combinations.extend(
                itertools.combinations(
                    changes,
                    size,
                )
            )

        return [
            list(x)
            for x in combinations
        ]

    def _format_result(
        self,
        request,
        safe_amount,
        status,
        candidate,
        earliest_date,
        explanation,
    ):
        changes = candidate.get(
            "spending_changes",
            [],
        )

        return {
            "request_id": request[
                "request_id"
            ],
            "amount_safe_to_pay": round(
                safe_amount,
                2,
            ),
            "affordability_status": status,
            "recommended_payment_method": (
                candidate[
                    "payment_method"
                ]
            ),
            "payment_plan": candidate[
                "payment_plan"
            ],
            "earliest_date_for_full_payment": (
                earliest_date
                if earliest_date
                else "none"
            ),
            "spending_changes_needed": (
                "|".join(changes)
                if changes
                else "none"
            ),
            "decision_explanation": explanation,
        }

    def decide(
        self,
        request,
    ):
        request_id = request[
            "request_id"
        ]

        user_id = request[
            "user_id"
        ]

        request_date = request[
            "request_date"
        ]

        requested_amount = float(
            request[
                "requested_amount"
            ]
        )

        state = (
            self.state_engine
            .reconstruct_user_state(
                user_id,
                request_date,
            )
        )

        simulator = SafetySimulator(
            state,
            request_date,
        )

        allowed_methods = state.get(
            "payment_methods",
            [],
        )

        options = (
            self._options_for_request(
                request_id
            )
        )

        planner = PaymentPlanner(
            simulator,
            request,
            options,
            allowed_methods,
            state.get(
                "max_installment_months",
                0,
            ),
        )

        # -------------------------------------------------
        # 1. Safe amount TODAY without optional changes.
        # -------------------------------------------------

        safe_now = (
            simulator
            .compute_max_safe_initial_payment(
                requested_amount
            )
        )

        # -------------------------------------------------
        # 2. Earliest full-payment date WITHOUT changes.
        # -------------------------------------------------

        earliest_full = (
            simulator
            .find_earliest_date_for_full_payment(
                requested_amount
            )
        )

        # -------------------------------------------------
        # 3. Full payment today.
        # -------------------------------------------------

        candidate = (
            planner.full_payment_candidate()
        )

        if candidate:

            return self._format_result(
                request,
                safe_now,
                "affordable_now",
                candidate,
                request_date,
                (
                    "The full amount is safe "
                    "to pay today while keeping "
                    "the required minimum balance."
                ),
            )

        # -------------------------------------------------
        # 4. Generate allowed spending changes.
        # -------------------------------------------------

        changes = self._allowed_changes(
            state
        )

        combinations = (
            self._change_combinations(
                changes
            )
        )

        changed_candidates = []

        for combination in combinations:

            full = (
                planner.full_payment_candidate(
                    combination
                )
            )

            if full:
                changed_candidates.append(
                    full
                )

            partial = (
                planner.partial_payment_candidate(
                    safe_now,
                    earliest_full,
                    combination,
                )
            )

            if partial:
                changed_candidates.append(
                    partial
                )

            installments = (
                planner.installment_candidates(
                    combination
                )
            )

            changed_candidates.extend(
                installments
            )

        if changed_candidates:

            best = planner.rank(
                changed_candidates
            )

            return self._format_result(
                request,
                safe_now,
                "affordable_with_plan",
                best,
                earliest_full,
                (
                    "The request is affordable "
                    "with an eligible payment plan "
                    "or permitted flexible-spending "
                    "adjustment."
                ),
            )

        # -------------------------------------------------
        # 5. Partial payment without changes.
        # -------------------------------------------------

        partial = (
            planner.partial_payment_candidate(
                safe_now,
                earliest_full,
            )
        )

        if partial:

            return self._format_result(
                request,
                safe_now,
                "affordable_with_plan",
                partial,
                earliest_full,
                (
                    "Pay the maximum safe amount "
                    "today and complete the remaining "
                    "amount when the full payment "
                    "becomes safe."
                ),
            )

        # -------------------------------------------------
        # 6. Installments without changes.
        # -------------------------------------------------

        installments = (
            planner.installment_candidates()
        )

        if installments:

            best = planner.rank(
                installments
            )

            return self._format_result(
                request,
                safe_now,
                "affordable_with_plan",
                best,
                earliest_full,
                (
                    "Use an eligible installment "
                    "schedule that completes the "
                    "request before the deadline."
                ),
            )

        # -------------------------------------------------
        # 7. Wait.
        # -------------------------------------------------

        if (
            earliest_full
            and "full_payment"
            in allowed_methods
        ):

            return {
                "request_id": request_id,
                "amount_safe_to_pay": round(
                    safe_now,
                    2,
                ),
                "affordability_status": (
                    "affordable_later"
                ),
                "recommended_payment_method": (
                    "wait"
                ),
                "payment_plan": (
                    f"{earliest_full}:"
                    f"{requested_amount:.2f}"
                ),
                "earliest_date_for_full_payment": (
                    earliest_full
                ),
                "spending_changes_needed": (
                    "none"
                ),
                "decision_explanation": (
                    "Do not pay today. The full "
                    "amount becomes safe later "
                    "without reducing protected "
                    "expenses."
                ),
            }

        # -------------------------------------------------
        # 8. Not affordable.
        # -------------------------------------------------

        return {
            "request_id": request_id,
            "amount_safe_to_pay": round(
                safe_now,
                2,
            ),
            "affordability_status": (
                "not_affordable"
            ),
            "recommended_payment_method": (
                "not_recommended"
            ),
            "payment_plan": "none",
            "earliest_date_for_full_payment": (
                earliest_full
                if earliest_full
                else "none"
            ),
            "spending_changes_needed": (
                "none"
            ),
            "decision_explanation": (
                "Do not proceed. The requested "
                "amount cannot be completed safely "
                "within the forecast using the "
                "user's eligible payment methods."
            ),
        }