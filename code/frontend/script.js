const API_URL = "http://127.0.0.1:5000/api/analyze";

const PROFILE_API_URL = "http://127.0.0.1:5000/api/profile";

const formatMoney = (value, currency) =>
    new Intl.NumberFormat("en-IN", {
        maximumFractionDigits: 2
    }).format(Number(value || 0));

const sessionStore = window.sessionStorage;

const escapeHtml = value =>
    String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");

const dateLabel = value => {
    if (!value || value === "none") return "Not available";

    const date = new Date(`${value}T00:00:00`);

    return Number.isNaN(date.getTime())
        ? value
        : date.toLocaleDateString("en-IN", {
            day: "2-digit",
            month: "short",
            year: "numeric"
        });
};


function show(id) {
    const element = document.getElementById(id);
    if (element) element.classList.remove("hidden");
}


function hide(id) {
    const element = document.getElementById(id);
    if (element) element.classList.add("hidden");
}


function setExample(text) {
    const input = document.getElementById("requestInput");

    if (!input) return;

    input.value = text;
    input.focus();
}


function showAuthError(message) {
    const old = document.querySelector(".auth-error");

    if (old) old.remove();

    const error = document.createElement("p");

    error.className = "auth-error";
    error.textContent = message;

    const card = document.querySelector(".auth-card:not(.hidden)");

    if (card) {
        card.append(error);
    }
}


/* =========================================================
   PROFILE DATA
========================================================= */

function activeProfile() {

    const fields = [
        ...document.querySelectorAll("[data-profile-field]")
    ];

    return {

        monthly_income: fields[0]?.value || "",
        other_regular_income: fields[1]?.value || "",
        income_frequency: fields[2]?.value || "",
        next_income_date: fields[3]?.value || "",

        housing: fields[4]?.value || "",
        current_balance: fields[5]?.value || "",

        monthly_rent: fields[6]?.value || "",
        home_emi: fields[7]?.value || "",
        maintenance: fields[8]?.value || "",
        household_contribution: fields[9]?.value || "",

        essential_expenses: fields[10]?.value || "",
        utilities: fields[11]?.value || "",
        loan_emi: fields[12]?.value || "",

        minimum_reserve: fields[13]?.value || "",
        max_installment_months: fields[14]?.value || "",

        payment_methods: fields[15]?.value || "",
        financial_priority: fields[16]?.value || ""
    };
}


async function loadProfile(profile = activeProfile()) {

    try {

        const response = await fetch(PROFILE_API_URL, {
            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify({
                profile
            })
        });

        const data = await response.json();

        window.profileData = data;

        const currency = data.currency || "";

        const plan = data.financial_plan || {};

        const currencyElement =
            document.getElementById("profileCurrency");

        if (currencyElement) {
            currencyElement.textContent =
                currency || "Unknown currency";
        }


        document.getElementById("overviewBalance").textContent =
            formatMoney(data.current_balance, currency);


        document.getElementById("overviewSafe").textContent =
            formatMoney(data.safe_amount, currency);


        document.getElementById("overviewExpenses").textContent =
            formatMoney(
                data.upcoming_essential_expenses,
                currency
            );


        document.getElementById("overviewHealth").textContent =
            data.financial_health || "Protected";


        renderUpcoming(
            data.upcoming_events || [],
            currency
        );


        renderTransactions(
            data.transactions || [],
            currency
        );


        renderFinancialPlan(
            plan,
            currency
        );

    } catch (error) {

        console.error("Profile loading error:", error);

        const health =
            document.getElementById("overviewHealth");

        if (health) {
            health.textContent = "Unavailable";
        }
    }
}


/* =========================================================
   ONBOARDING
========================================================= */

function setOnboardingStep(step) {

    const incomeSection =
        document.getElementById("incomeStep");

    const homeSection =
        document.getElementById("homeStep");

    const safetySection =
        document.getElementById("safetyStep");


    if (!incomeSection || !homeSection || !safetySection) {
        return;
    }


    incomeSection.classList.add("hidden");
    homeSection.classList.add("hidden");
    safetySection.classList.add("hidden");


    if (step === 1) {
        incomeSection.classList.remove("hidden");
    }

    if (step === 2) {
        homeSection.classList.remove("hidden");
    }

    if (step === 3) {
        safetySection.classList.remove("hidden");
    }


    document.querySelectorAll(
        ".profile-progress span"
    ).forEach(item => {

        const itemStep =
            Number(item.dataset.step);

        item.classList.remove(
            "active",
            "completed"
        );

        if (itemStep === step) {
            item.classList.add("active");
        }

        if (itemStep < step) {
            item.classList.add("completed");
        }
    });


    const onboarding =
        document.getElementById("onboardingStep");

    if (onboarding) {

        onboarding.scrollIntoView({
            behavior: "smooth",
            block: "start"
        });
    }
}


function setupOnboarding() {

    const progressItems =
        document.querySelectorAll(
            ".profile-progress span[data-step]"
        );


    progressItems.forEach(item => {

        item.addEventListener("click", () => {

            const step =
                Number(item.dataset.step);

            setOnboardingStep(step);
        });
    });


    const continueIncome =
        document.getElementById("continueIncome");


    if (continueIncome) {

        continueIncome.addEventListener(
            "click",
            () => {

                setOnboardingStep(2);
            }
        );
    }


    const continueHome =
        document.getElementById("continueHome");


    if (continueHome) {

        continueHome.addEventListener(
            "click",
            () => {

                setOnboardingStep(3);
            }
        );
    }


    const finishButton =
        document.getElementById("finishOnboarding");


    if (finishButton) {

        finishButton.addEventListener(
            "click",
            async () => {

                const profile =
                    activeProfile();


                sessionStore.setItem(
                    "buyOrWaitDemoUser",
                    "true"
                );


                sessionStore.setItem(
                    "buyOrWaitDemoProfile",
                    JSON.stringify(profile)
                );


                hide("authShell");

                show("appShell");


                await loadProfile(profile);
            }
        );
    }


    const housing =
        document.getElementById("housingSelect");


    if (housing) {

        housing.addEventListener(
            "change",
            event => {

                const value =
                    event.target.value;


                const rent =
                    value === "Rent";


                const own =
                    value === "Own Home";


                const family =
                    value === "Living with Family";


                document
                    .getElementById("rentField")
                    ?.classList.toggle(
                        "hidden",
                        !rent
                    );


                document
                    .getElementById("homeExpenseField")
                    ?.classList.toggle(
                        "hidden",
                        !own
                    );


                document
                    .getElementById("maintenanceField")
                    ?.classList.toggle(
                        "hidden",
                        !own
                    );


                document
                    .getElementById("familyContributionField")
                    ?.classList.toggle(
                        "hidden",
                        !family
                    );
            }
        );
    }


    setOnboardingStep(1);
}


/* =========================================================
   UPCOMING EVENTS
========================================================= */

function renderUpcoming(events, currency) {

    const container =
        document.getElementById("upcomingEvents");


    if (!container) return;


    if (!events.length) {

        container.innerHTML = `
            <div class="empty-state">
                <span>—</span>

                <div>
                    <strong>
                        No upcoming events found
                    </strong>

                    <p>
                        The profile has no forecast records
                        in this window.
                    </p>
                </div>
            </div>
        `;

        return;
    }


    container.innerHTML = events.map(event => `

        <div class="commitment-row">

            <div>

                <span class="commitment-icon">
                    ${event.direction === "credit"
                        ? "↗"
                        : "⌂"}
                </span>

                <div>

                    <strong>
                        ${escapeHtml(
                            event.description ||
                            event.category
                        )}
                    </strong>

                    <small>
                        ${escapeHtml(
                            dateLabel(event.date)
                        )}
                        ·
                        ${escapeHtml(
                            event.category
                        )}
                        ·
                        ${
                            event.essential
                                ? "ESSENTIAL"
                                : event.flexible
                                    ? "FLEXIBLE"
                                    : "OTHER"
                        }
                    </small>

                </div>

            </div>

            <span class="event-amount ${
                event.direction === "credit"
                    ? "income"
                    : "expense"
            }">

                ${
                    event.direction === "credit"
                        ? "+"
                        : "−"
                }

                ${formatMoney(
                    event.amount,
                    currency
                )}

            </span>

        </div>

    `).join("");
}


/* =========================================================
   TRANSACTIONS
========================================================= */

function renderTransactions(
    events,
    currency,
    filter = "all",
    search = ""
) {

    const container =
        document.getElementById(
            "transactionTable"
        );


    if (!container) return;


    const rows =
        events.filter(event => {

            const matchesFilter =
                filter === "all" ||

                (
                    filter === "income" &&
                    event.direction === "credit"
                ) ||

                (
                    filter === "expense" &&
                    event.direction === "debit"
                ) ||

                (
                    filter === "essential" &&
                    event.essential
                ) ||

                (
                    filter === "flexible" &&
                    event.flexible
                );


            const haystack =
                `${event.description}
                 ${event.category}
                 ${event.status}`.toLowerCase();


            return (
                matchesFilter &&
                haystack.includes(
                    search.toLowerCase()
                )
            );
        });


    if (!rows.length) {

        container.innerHTML = `
            <div class="empty-state">

                <span>—</span>

                <div>

                    <strong>
                        No matching transactions
                    </strong>

                    <p>
                        Try another filter or search term.
                    </p>

                </div>

            </div>
        `;

        return;
    }


    container.innerHTML =
        rows.map(event => `

            <div class="transaction-row">

                <span>
                    ${escapeHtml(
                        dateLabel(event.date)
                    )}
                </span>

                <strong>
                    ${escapeHtml(
                        event.description ||
                        event.category
                    )}
                </strong>

                <span>
                    ${escapeHtml(
                        event.category
                    )}
                </span>

                <span class="${
                    event.direction === "credit"
                        ? "income"
                        : "expense"
                }">

                    ${
                        event.direction === "credit"
                            ? "+"
                            : "−"
                    }

                    ${formatMoney(
                        event.amount,
                        currency
                    )}

                </span>

                <span>

                    ${escapeHtml(
                        event.status
                    )}

                    ·

                    ${
                        event.essential
                            ? "essential"
                            : event.flexible
                                ? "flexible"
                                : "other"
                    }

                </span>

            </div>

        `).join("");
}


/* =========================================================
   FINANCIAL PLAN
========================================================= */

function renderFinancialPlan(
    plan,
    currency
) {

    const metrics =
        document.getElementById(
            "planMetrics"
        );


    if (!metrics) return;


    metrics.innerHTML = [

        ["Current balance", plan.current_balance],

        ["Minimum reserve", plan.minimum_reserve],

        ["Safe to spend", plan.safe_to_spend],

        ["Upcoming income", plan.upcoming_income],

        ["Upcoming essentials", plan.upcoming_essentials],

        ["Flexible spending", plan.flexible_spending]

    ].map(item => `

        <div class="plan-metric">

            <span>
                ${item[0]}
            </span>

            <strong>
                ${formatMoney(
                    item[1],
                    currency
                )}
            </strong>

        </div>

    `).join("");


    const state =
        Number(plan.safe_to_spend || 0) >
        Number(plan.minimum_reserve || 0)
            ? "SAFE"
            : "WATCH";


    document.getElementById(
        "planGuidance"
    ).innerHTML = `

        <p class="eyebrow">
            ${state} / DATA-BACKED GUIDANCE
        </p>

        <p>
            Your projected balance is checked against
            the ${formatMoney(
                plan.minimum_reserve,
                currency
            )} reserve. Upcoming income and essential
            commitments are shown from your financial profile.
        </p>
    `;
}


/* =========================================================
   NAVIGATION
========================================================= */

function switchView(view) {

    const result =
        document.getElementById(
            "resultSection"
        );

    const request =
        document.querySelector(
            ".request-panel"
        );

    const upcoming =
        document.querySelector(
            ".upcoming-section"
        );

    const transactions =
        document.getElementById(
            "transactionsView"
        );

    const plan =
        document.getElementById(
            "planView"
        );


    [
        request,
        upcoming,
        result,
        transactions,
        plan
    ].forEach(element => {

        if (element) {
            element.classList.add("hidden");
        }

    });


    if (view === "dashboard") {

        request?.classList.remove("hidden");

        upcoming?.classList.remove("hidden");

        if (result?.innerHTML) {
            result.classList.remove("hidden");
        }
    }


    if (view === "transactions") {
        transactions?.classList.remove("hidden");
    }


    if (view === "plan") {
        plan?.classList.remove("hidden");
    }


    document
        .querySelectorAll(".nav-item")
        .forEach(item => {

            item.classList.toggle(
                "active",
                item.dataset.view === view
            );

        });
}


/* =========================================================
   LOGOUT
========================================================= */

function logout() {

    sessionStore.clear();

    localStorage.removeItem(
        "buyOrWaitDemoUser"
    );

    localStorage.removeItem(
        "buyOrWaitDemoProfile"
    );


    hide("appShell");

    show("authShell");

    hide("otpStep");

    hide("onboardingStep");

    show("loginStep");


    const contact =
        document.getElementById(
            "loginContact"
        );

    const otp =
        document.getElementById(
            "otpInput"
        );


    if (contact) contact.value = "";

    if (otp) otp.value = "";
}


/* =========================================================
   AUTHENTICATION
========================================================= */

function bootAuth() {

    const savedUser =
        sessionStore.getItem(
            "buyOrWaitDemoUser"
        );


    if (savedUser === "true") {

        hide("authShell");

        show("appShell");


        const savedProfile =
            sessionStore.getItem(
                "buyOrWaitDemoProfile"
            );


        let profile = null;


        try {

            profile =
                savedProfile
                    ? JSON.parse(savedProfile)
                    : null;

        } catch {

            profile = null;
        }


        loadProfile(
            profile || activeProfile()
        );
    }


    const sendOtp =
        document.getElementById(
            "sendOtpButton"
        );


    if (sendOtp) {

        sendOtp.addEventListener(
            "click",
            () => {

                const contact =
                    document.getElementById(
                        "loginContact"
                    ).value.trim();


                if (!contact) {

                    showAuthError(
                        "Add a mobile number or email to continue."
                    );

                    return;
                }


                hide("loginStep");

                show("otpStep");


                document
                    .getElementById("otpInput")
                    ?.focus();
            }
        );
    }


    document
        .getElementById("backToLogin")
        ?.addEventListener(
            "click",
            () => {

                hide("otpStep");

                show("loginStep");
            }
        );


    document
        .getElementById("verifyOtpButton")
        ?.addEventListener(
            "click",
            () => {

                const otp =
                    document.getElementById(
                        "otpInput"
                    ).value.trim();


                if (otp !== "123456") {

                    showAuthError(
                        "Use the six-digit code shown above."
                    );

                    return;
                }


                hide("otpStep");

                show("onboardingStep");

                setupOnboarding();
            }
        );
}


/* =========================================================
   LOADING ANIMATION
========================================================= */

function showLoading() {

    show("loadingSection");

    hide("resultSection");


    const messages = [

        "Reading your financial profile.",

        "Checking upcoming commitments.",

        "Forecasting cash flow.",

        "Comparing payment options.",

        "Finding the safest action."

    ];


    let index = 0;


    const steps =
        [
            ...document.querySelectorAll(
                ".analysis-steps li"
            )
        ];


    steps.forEach(
        (step, position) => {

            step.className =
                position === 0
                    ? "active"
                    : "";

        }
    );


    window.loadingTimer =
        setInterval(
            () => {

                index += 1;


                document.getElementById(
                    "loadingMessage"
                ).textContent =
                    messages[
                        index % messages.length
                    ];


                steps.forEach(
                    (step, position) => {

                        step.className =
                            position <= index
                                ? "done"
                                : "";

                    }
                );


                if (steps[index]) {
                    steps[index].className =
                        "active";
                }

            },
            430
        );
}


function stopLoading() {

    clearInterval(
        window.loadingTimer
    );

    hide("loadingSection");
}


/* =========================================================
   PAYMENT PLAN
========================================================= */

function renderPlan(
    plan,
    currency
) {

    if (!plan || plan === "none") {

        return `

            <div class="empty-state">

                <span>—</span>

                <div>

                    <strong>
                        No payment plan recommended
                    </strong>

                    <p>
                        The engine found no scheduled
                        plan that improves this decision.
                    </p>

                </div>

            </div>
        `;
    }


    const rows =
        plan
            .split("|")
            .map(
                (item, index) => {

                    const [
                        date,
                        amount
                    ] = item.split(":");


                    return `

                        <div class="timeline-row">

                            <div class="timeline-marker">
                                ${index + 1}
                            </div>

                            <div>

                                <small>
                                    PAYMENT ${index + 1}
                                </small>

                                <strong>
                                    ${escapeHtml(
                                        dateLabel(date)
                                    )}
                                </strong>

                            </div>

                            <b>
                                ${formatMoney(
                                    amount,
                                    currency
                                )}
                            </b>

                        </div>

                    `;
                }
            )
            .join("");


    const total =
        plan
            .split("|")
            .reduce(
                (sum, item) =>
                    sum +
                    Number(
                        item.split(":")[1] || 0
                    ),
                0
            );


    return `

        ${rows}

        <div class="plan-total">

            <span>
                Total payable
            </span>

            <strong>
                ${formatMoney(
                    total,
                    currency
                )}
            </strong>

        </div>
    `;
}


/* =========================================================
   SPENDING CHANGES
========================================================= */

function renderChanges(
    changes,
    currency
) {

    if (
        !changes ||
        changes === "none"
    ) {

        return `

            <div class="empty-state positive-state">

                <span>✓</span>

                <div>

                    <strong>
                        No spending changes required
                    </strong>

                    <p>
                        Your purchase is safe without
                        changing your current spending.
                    </p>

                </div>

            </div>
        `;
    }


    return changes
        .split("|")
        .map(change => {

            const [
                action,
                event,
                value
            ] = change.split(":");


            return `

                <div class="change-card">

                    <span class="change-icon">
                        ${
                            action === "stop"
                                ? "Ⅱ"
                                : "↓"
                        }
                    </span>

                    <div>

                        <small>
                            ${
                                action === "stop"
                                    ? "PAUSE"
                                    : "REDUCE"
                            }
                        </small>

                        <strong>
                            ${escapeHtml(event)}
                        </strong>

                        ${
                            value
                                ? `
                                    <p>
                                        New amount:
                                        ${formatMoney(
                                            value,
                                            currency
                                        )}
                                    </p>
                                `
                                : `
                                    <p>
                                        Flexible spending event
                                    </p>
                                `
                        }

                    </div>

                </div>

            `;
        })
        .join("");
}


/* =========================================================
   RESULT
========================================================= */

function showResult(data) {

    const indicators =
        data.xray_indicators || {};

    const currency =
        data.currency || "";

    const status =
        data.affordability_status ||
        "not_affordable";


    const statusLabel = {

        affordable_now:
            "Affordable now",

        affordable_with_plan:
            "Affordable with plan",

        affordable_later:
            "Affordable later",

        not_affordable:
            "Not affordable"

    }[status] || status;


    const values = [

        data.current_balance,

        data.safe_amount,

        data.upcoming_essential_expenses

    ];


    [
        "overviewBalance",
        "overviewSafe",
        "overviewExpenses"

    ].forEach(
        (id, index) => {

            const element =
                document.getElementById(id);

            if (element) {

                element.textContent =
                    formatMoney(
                        values[index],
                        currency
                    );
            }
        }
    );


    document.getElementById(
        "overviewHealth"
    ).textContent =
        data.financial_health ||
        "Protected";


    document.getElementById(
        "resultSection"
    ).innerHTML = `

        <div class="result-hero">

            <div>

                <p class="eyebrow">
                    AI FINANCIAL DECISION
                </p>

                <h2>
                    ${escapeHtml(
                        data.autonomous_action ||
                        "WAIT"
                    )}
                </h2>

                <p class="result-subtitle">
                    ${escapeHtml(
                        data.request_text ||
                        "Purchase request analyzed"
                    )}
                </p>

            </div>

            <span class="status-badge ${status}">
                ${statusLabel}
            </span>

        </div>


        <div class="metrics">

            <div>
                <small>SAFE TO SPEND</small>
                <strong>
                    ${formatMoney(
                        data.safe_amount,
                        currency
                    )}
                </strong>
            </div>

            <div>
                <small>PURCHASE PRICE</small>
                <strong>
                    ${formatMoney(
                        data.purchase_amount,
                        currency
                    )}
                </strong>
            </div>

            <div>
                <small>SHORTFALL</small>
                <strong>
                    ${formatMoney(
                        data.shortfall,
                        currency
                    )}
                </strong>
            </div>

        </div>


        <div class="action-card">

            <div class="action-icon">
                ✦
            </div>

            <div>

                <p class="eyebrow">
                    AUTONOMOUS BEST ACTION
                </p>

                <h3>
                    ${escapeHtml(
                        data.autonomous_action
                    )}
                </h3>

                <p>
                    ${escapeHtml(
                        data.dynamic_reason
                    )}
                </p>

                ${
                    data.earliest_date_for_full_payment &&
                    data.earliest_date_for_full_payment !== "none"
                        ? `
                            <span class="date-chip">
                                Earliest safe date ·
                                ${escapeHtml(
                                    dateLabel(
                                        data.earliest_date_for_full_payment
                                    )
                                )}
                            </span>
                        `
                        : ""
                }

            </div>

        </div>


        <div class="result-columns">

            <div class="result-card">

                <div class="card-heading">

                    <span class="section-icon">
                        ⌕
                    </span>

                    <div>

                        <p class="eyebrow">
                            FINANCIAL X-RAY
                        </p>

                        <h3>
                            What the agent considered
                        </h3>

                    </div>

                </div>


                <div class="xray-grid">

                    <div>
                        <span>Current balance</span>
                        <strong>
                            ${formatMoney(
                                data.current_balance,
                                currency
                            )}
                        </strong>
                    </div>

                    <div>
                        <span>Minimum reserve</span>
                        <strong>
                            ${formatMoney(
                                data.minimum_balance,
                                currency
                            )}
                        </strong>
                    </div>

                    <div>
                        <span>Safe capacity</span>
                        <strong>
                            ${formatMoney(
                                data.safe_amount,
                                currency
                            )}
                        </strong>
                    </div>

                    <div>
                        <span>Purchase price</span>
                        <strong>
                            ${formatMoney(
                                data.purchase_amount,
                                currency
                            )}
                        </strong>
                    </div>

                    <div>
                        <span>Upcoming essentials</span>
                        <strong>
                            ${formatMoney(
                                data.upcoming_essential_expenses,
                                currency
                            )}
                        </strong>
                    </div>

                    <div>
                        <span>Confirmed income</span>
                        <strong>
                            ${formatMoney(
                                data.confirmed_upcoming_income,
                                currency
                            )}
                        </strong>
                    </div>

                    <div>
                        <span>Projected balance</span>
                        <strong>
                            ${formatMoney(
                                data.projected_balance,
                                currency
                            )}
                        </strong>
                    </div>

                    <div>
                        <span>Forecast impact</span>
                        <strong>
                            ${escapeHtml(
                                data.forecast_impact ||
                                "Not available"
                            )}
                        </strong>
                    </div>

                </div>


                <ul class="signals">

                    <li class="${
                        indicators.balance_checked
                            ? "ok"
                            : "warn"
                    }">
                        ✓ Current balance checked
                    </li>

                    <li class="${
                        indicators.confirmed_income_checked
                            ? "ok"
                            : "muted-signal"
                    }">
                        ✓ Confirmed income checked
                    </li>

                    <li class="${
                        indicators.commitments_checked
                            ? "warn"
                            : "muted-signal"
                    }">
                        ⚠ Upcoming commitments checked
                    </li>

                    <li class="ok">
                        🔒 Minimum reserve protected
                    </li>

                </ul>

            </div>


            <div class="result-card">

                <div class="card-heading">

                    <span class="section-icon">
                        ↗
                    </span>

                    <div>

                        <p class="eyebrow">
                            PAYMENT PLAN
                        </p>

                        <h3>
                            Recommended schedule
                        </h3>

                    </div>

                </div>


                <div class="timeline">

                    ${renderPlan(
                        data.payment_plan,
                        currency
                    )}

                </div>

            </div>

        </div>


        <div class="result-card changes-card">

            <div class="card-heading">

                <span class="section-icon">
                    ⌁
                </span>

                <div>

                    <p class="eyebrow">
                        SPENDING CHANGES
                    </p>

                    <h3>
                        Flexible actions
                    </h3>

                </div>

            </div>


            <div class="changes-list">

                ${renderChanges(
                    data.spending_changes_needed,
                    currency
                )}

            </div>

        </div>


        <div class="why-card">

            <p class="eyebrow">
                WHY THIS DECISION?
            </p>

            <p>
                ${escapeHtml(
                    data.dynamic_reason
                )}
            </p>

        </div>
    `;


    show("resultSection");


    document
        .getElementById("resultSection")
        .scrollIntoView({
            behavior: "smooth",
            block: "start"
        });
}


/* =========================================================
   ANALYZE REQUEST
========================================================= */

async function analyzeRequest() {

    const input =
        document.getElementById(
            "requestInput"
        );


    const text =
        input.value.trim();


    if (!text) {

        showError(
            "Describe the purchase and include its amount, for example ₹20,000."
        );

        return;
    }


    const button =
        document.getElementById(
            "askFinancialAgent"
        );


    button.disabled = true;

    button.innerHTML =
        "Analyzing...";


    showLoading();


    try {

        const response =
            await fetch(
                API_URL,
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({

                        text,

                        profile:
                            activeProfile()

                    })
                }
            );


        const data =
            await response.json();


        if (!response.ok) {

            throw new Error(
                data.error ||
                "The agent could not analyze that request."
            );
        }


        data.request_text = text;


        showResult(data);

    } catch (error) {

        console.error(error);

        showError(
            error.message
        );

    } finally {

        stopLoading();

        button.disabled = false;

        button.innerHTML =
            'Ask Financial Agent <span>→</span>';
    }
}


/* =========================================================
   ERROR
========================================================= */

function showError(message) {

    stopLoading();


    const result =
        document.getElementById(
            "resultSection"
        );


    result.innerHTML = `

        <div class="error-card">

            <strong>
                We need one more detail
            </strong>

            <p>
                ${escapeHtml(message)}
            </p>

        </div>

    `;


    show("resultSection");
}


/* =========================================================
   START APPLICATION
========================================================= */

document.addEventListener(
    "DOMContentLoaded",
    () => {

        bootAuth();


        document
            .getElementById("logoutButton")
            ?.addEventListener(
                "click",
                logout
            );


        document
            .getElementById("headerLogoutButton")
            ?.addEventListener(
                "click",
                logout
            );


        document
            .querySelectorAll("[data-example]")
            .forEach(button => {

                button.addEventListener(
                    "click",
                    () =>
                        setExample(
                            button.dataset.example
                        )
                );
            });


        document
            .getElementById("askFinancialAgent")
            ?.addEventListener(
                "click",
                analyzeRequest
            );


        document
            .querySelectorAll(".nav-item")
            .forEach(
                (button, index) => {

                    const views = [
                        "dashboard",
                        "transactions",
                        "plan"
                    ];


                    const view =
                        views[index];


                    button.dataset.view =
                        view;


                    button.addEventListener(
                        "click",
                        () =>
                            switchView(view)
                    );
                }
            );


        document
            .querySelectorAll(".filter")
            .forEach(button => {

                button.addEventListener(
                    "click",
                    () => {

                        document
                            .querySelectorAll(".filter")
                            .forEach(item =>
                                item.classList.remove(
                                    "active"
                                )
                            );


                        button.classList.add(
                            "active"
                        );


                        renderTransactions(

                            window
                                .profileData
                                ?.transactions || [],

                            window
                                .profileData
                                ?.currency || "",

                            button.dataset.filter,

                            document
                                .getElementById(
                                    "transactionSearch"
                                )
                                .value
                        );
                    }
                );
            });


        document
            .getElementById("transactionSearch")
            ?.addEventListener(
                "input",
                event => {

                    renderTransactions(

                        window
                            .profileData
                            ?.transactions || [],

                        window
                            .profileData
                            ?.currency || "",

                        document
                            .querySelector(
                                ".filter.active"
                            )
                            ?.dataset.filter ||
                            "all",

                        event.target.value
                    );
                }
            );
    }
);


window.analyzeRequest =
    analyzeRequest;