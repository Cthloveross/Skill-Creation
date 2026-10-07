---
name: credit-card-signup-bonus-recommender
description: Evaluate documented personal or business credit-card sign-up offers as of a supplied date, screen them against stated customer constraints, correctly value points only when a documented conversion is supplied, and produce a transparent recommendation without applying for a card.
---

# Credit-Card Sign-Up Bonus Recommender

Use this skill when a customer asks which credit card has the best available sign-up bonus in cash back, statement-credit value, or points. It is an informational comparison workflow; it does not submit an application, open an account, redeem rewards, or alter any banking record.

## Required inputs

Obtain the following from the current request and its supplied card documentation:

- An `as_of` date from a current-time observation or another explicit date source.
- The requested audience (`personal`, `business`, or `either`).
- Known customer constraints, including invitation status, premium-subscription status, approximate credit score (if supplied), new-customer status (if known), and whether the stated spending threshold is feasible.
- A catalog containing every in-scope card considered. Include cards with no documented sign-up bonus so the final answer can distinguish "no documented current bonus" from an offer the customer cannot use.
- For every offer: its offer window, bonus quantity and unit, documented cash value or point conversion when available, spend requirement and period, and all stated eligibility requirements.

Do not infer an offer, value a point, treat a standard earning rate as a sign-up bonus, or call an expired offer current. A point quantity is not a dollar value unless the supplied documentation gives a conversion or direct cash value.

## Workflow

1. Determine the date of comparison from the supplied current-time observation. Do not use the runtime clock as a substitute for an observed date.
2. Extract the documented offer facts into the schema accepted by `scripts/evaluate_offers.py`. Set `signup_bonus_documented` to `false` when the materials only describe ongoing rewards, APR, annual-fee terms, or an absent/undocumented bonus.
3. Record unknown customer facts as JSON `null`; do not replace them with favorable assumptions.
4. Run the evaluator once with the assembled facts. It validates dates and calculates a documented bonus value when possible.
5. Respond using the output:
   - Lead with confirmed active candidates ranked by documented cash-equivalent value.
   - Label candidates with unresolved credit, new-customer, invitation, subscription, or spend-capacity facts as **conditional**, not eligible or preapproved.
   - Separately explain unavailable offers, including expired windows, audience mismatch, and known unmet requirements.
   - State that cards omitted from the ranked set have no documented current sign-up bonus when that is what the catalog says.
   - Explain the spending threshold, qualification period, eligible-purchase exclusions, good-standing requirement, and posting timing whenever supplied for a leading offer.
   - If no offer is confirmed eligible, say so plainly and identify the smallest factual question that could change the result. Do not pressure the customer to make unnecessary purchases merely to earn a bonus.
6. Never claim approval, eligibility certainty, enrollment, or that an offer will post. Offer terms can change; make the comparison date visible.

For the common situation where the customer wants to see offers before deciding whether they can meet a high spending threshold, list the active offer as conditional and give its exact threshold and period. Do not discard it simply because feasibility is unknown, and do not call it the customer's best attainable option until feasibility and other unknown requirements are resolved.

## Evaluator interface

Run `scripts/evaluate_offers.py` using `run_skill_script`. It reads one JSON object from stdin and writes one JSON object to stdout.

Input schema:

```json
{
  "as_of": "YYYY-MM-DD",
  "customer": {
    "audience": "personal | business | either",
    "has_invitation": true,
    "has_premium_subscription": false,
    "credit_score": null,
    "is_new_customer": null,
    "can_meet_spend_requirement": null
  },
  "offers": [
    {
      "card_name": "documented product name",
      "audience": "personal | business | both",
      "signup_bonus_documented": true,
      "start_date": "YYYY-MM-DD",
      "end_date": "YYYY-MM-DD",
      "bonus": {
        "amount": "documented numeric quantity",
        "unit": "points | cash_back | statement_credit | other documented unit",
        "cash_value_usd": "optional direct USD value",
        "unit_value_usd": "optional documented USD value per unit"
      },
      "requirements": {
        "requires_invitation": false,
        "requires_premium_subscription": false,
        "minimum_credit_score": null,
        "requires_new_customer": true,
        "spend_amount_usd": "documented amount or null",
        "spend_period_months": "documented period or null",
        "requires_good_standing": true
      },
      "qualifying_purchase_notes": "documented eligible-purchase rules, exclusions, posting timing, and other material terms"
    }
  ]
}
```

Boolean customer values may instead be `null` when unknown. `cash_value_usd` takes precedence over `amount × unit_value_usd`; omit both value fields when the documentation does not establish a conversion. `start_date` and `end_date` may be `null` only when the documentation genuinely has no corresponding boundary. The evaluator treats a documented offer with an unknown window boundary as conditional rather than confirmed active.

The evaluator output has `ranked_candidates`, `unavailable_offers`, `not_signup_bonus`, `data_issues`, `next_questions`, and a concise `reply_outline`. Treat any `data_issues` as a reason to correct the extracted catalog before making a definitive claim.

Runnable execution pattern: invoke `run_skill_script` with `relative_path` set to `scripts/evaluate_offers.py` and `input_json` set to the current request's assembled object matching the schema above. No customer identifiers, account data, or assumed offers are required by the script.

## Validation checklist

Before sending the recommendation, verify that:

- the comparison date is explicit and each active-window conclusion is based on it;
- the catalog includes all relevant cards, including documented non-bonus cards;
- raw point amounts and their cash-equivalent values are visibly distinct;
- every ranked offer has a documented current window or is clearly marked conditional because a boundary is missing;
- all known blockers are stated, and unknown credit score or spend capacity is not silently treated as satisfied;
- the response does not confuse a high ongoing earn rate, APR promotion, or annual-fee waiver with a cash-back/points sign-up bonus;
- no application, account lookup, or other banking action has been taken.

## Boundary for a later banking action

If a later request moves beyond comparison into an application, account-specific inquiry, reward redemption, payment, or another banking action, pause this informational workflow and satisfy the applicable operational controls first:

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.
