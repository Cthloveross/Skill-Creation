---
name: business-checking-referral-recommender
description: Provide eligibility-aware, read-only comparisons of documented business-checking referral programs. Use after checking the referrer's identity and referral history; support clearly labelled hypothetical comparisons when a customer expressly asks to assume remaining eligibility.
---

# Business Checking Referral Recommender

Use this skill when a customer asks which business checking account to refer a prospective business to in order to maximize the referrer's bonus. It is an informational skill only: it does not submit a referral, open an account, deposit funds, or alter customer data.

## Safety and policy boundaries

- Before giving account-specific referral terms, a product recommendation, or personalized referral guidance, check the referrer's identity and retrieve the referral history.
- Do not disclose private lookup data or individual referral records in conversation. State only the resulting cap/frequency determination when needed.
- Referrer tenure is measured from the earliest Rho-Bank checking-account opening date. The referrer does not need to hold the same account product being referred.
- Do not imply that a bonus is guaranteed. Qualification depends on every applicable program and common condition.
- Treat an amount described as “around,” “about,” or otherwise approximate as a planning amount, not a definite qualifying deposit.
- For an actual banking action, use only normal banking tools and first verify identity, authority, ownership, product eligibility, funds or credit, fees, limits, cutoffs, recipient/card details, and confirmation requirements.

## Required workflow

1. **Identify the referrer.** Obtain an exact name, user ID, or email and use the matching read-only identity lookup. Follow the runtime's identity-verification procedure before disclosing customer-specific information. If the runtime provides `log_verification`, confirm two of date of birth, email, phone number, and address, obtain the current time, then log the verified record with all required fields.
2. **Inspect referral history before advice.** Use `get_referrals_by_user` with the verified user ID. Obtain the current time and review the returned history before a substantive account comparison. Evaluate completed referrals for the annual account cap and the cross-program rolling nine-day cap.
3. **Collect or classify decision facts.** Determine whether the request is for a confirmed recommendation or an explicitly hypothetical/assumed comparison. For a confirmed recommendation, verify:
   - the exact, definite qualifying deposit amount and that it is new money rather than a Rho-Bank transfer;
   - the referrer's earliest-checking tenure and current good standing;
   - the prospective business is new to Rho-Bank, with no existing account or account closed in the past 12 months;
   - a different registered address and a different business primary owner/primary authorized signer from existing Rho-Bank business accounts;
   - 30-day post-qualification deposit retention, both accounts' continued good standing, no other new-account promotion, and one referral code only.
4. Normalize the observed history and facts and run `scripts/evaluate_referral.py`. Use `comparison_mode: "confirmed"` for a confirmed recommendation. Use `comparison_mode: "conditional"` only when the customer expressly requests an assumed/hypothetical comparison after steps 1–2.
5. Interpret the output conservatively. A confirmed recommendation requires `ok: true`, an eligible `referrer_gate`, an eligible rolling result, and an eligible program. A conditional comparison is explanatory only and must prominently retain its assumptions.

## Unknown facts: confirmed recommendation deferral

If the prospective LLC eligibility facts or the definite qualifying new-money deposit are unknown and the customer has not expressly requested an assumed comparison, begin the response with this exact sentence:

> I can't provide a confirmed account recommendation yet.

Request the unresolved facts. Include these concepts clearly: **new to Rho-Bank**, **past 12 months**, **different primary owner** (or **different primary authorized signer**), **different registered address**, **qualifying new money**, **30 days**, **good standing**, and **one referral code**.

Do not characterize a program as confirmed, guaranteed, or certain in that response. An approximate deposit cannot support a confirmed recommendation until the customer commits to an exact amount at or above the applicable threshold.

## Expressly requested conditional comparisons

After identity and referral-history review, a customer may ask for a comparison “assuming” the LLC meets the remaining conditions. Answer that request rather than continuing to defer all product information.

- Lead with language such as “Assuming the remaining eligibility conditions are met” or “Conditionally.”
- Compare documented programs against the stated planning amount, but say the actual deposit must be a definite amount at or above the stated threshold and must be qualifying new money.
- Use the documented threshold ladder. For a planned deposit of at least $25,000 but less than $50,000, World Blue is the highest documented referrer bonus compatible with that amount: $300, with a $25,000 qualifying new-money deposit within 90 days. True Blue pays $350 but needs $50,000 within 120 days; Beige pays $500 but needs $100,000 within 120 days.
- This is a conditional product comparison, not a promise that the referral qualifies. State the relevant remaining conditions: LLC/new-customer restrictions, new-money source, 30-day retention after the qualification period, both accounts' good standing, no promotion stacking, one referral code, annual cap, and rolling nine-day cap.
- Do not use a conditional comparison to bypass a known failed or blocked requirement. If history shows an annual or rolling cap is reached, say so and do not recommend proceeding.

## Documented program data

| Referred account | Referrer bonus | Annual cap | Qualifying new-money deposit | Deposit window | Referrer tenure |
|---|---:|---:|---:|---:|---:|
| Beige Account | $500 | 15 | $100,000 | 120 days | 120 days |
| True Blue Account | $350 | 15 | $50,000 | 120 days | 90 days |
| World Blue Account | $300 | 12 | $25,000 | 90 days | 90 days |
| Lime Green Account | $200 | 12 | $15,000 | 90 days | 90 days |
| Hunter Green Account | $175 | 10 | $10,000 | 90 days | 60 days |
| Cobalt Blue Account | $150 | 10 | $7,500 | 90 days | 60 days |
| Navy Blue Account | $100 | 10 | $5,000 | 90 days | 60 days |

Sky Blue has a documented $150 referrer bonus and annual limit of 8, but supplied terms do not establish its qualifying-deposit or referrer-tenure rules. Never present Sky Blue as confirmed eligible.

The annual cap counts `COMPLETE` referrals for the target program in the calendar year of the assessment. The universal rolling cap permits at most two completed referral bonuses in any rolling nine-day window across all checking products. Date-only records on the exact nine-day boundary require an exact timestamp for a confirmed result.

## Evaluator interface

Run the packaged evaluator with one JSON object on standard input. It emits exactly one JSON object on standard output:

```sh
printf '%s' "$REFERRAL_FACTS_JSON" | python3 scripts/evaluate_referral.py
```

Input schema:

```json
{
  "comparison_mode": "confirmed or conditional",
  "as_of": "ISO-8601 timestamp including an offset",
  "proposed_deposit": "number",
  "proposed_deposit_confirmed": "boolean",
  "referrer": {
    "identity_verified": "boolean",
    "checking_tenure_days": "integer",
    "good_standing": "boolean"
  },
  "candidate": {
    "new_customer_no_accounts_in_last_12_months": "boolean",
    "different_registered_address": "boolean",
    "different_business_primary_owner": "boolean",
    "qualifying_deposit_is_new_money": "boolean",
    "will_retain_deposit_30_days_after_qualification_period": "boolean",
    "will_remain_in_good_standing": "boolean",
    "no_other_new_account_promotion": "boolean",
    "one_referral_code_only": "boolean"
  },
  "referrals": [
    {
      "referred_account_type": "documented account type/name",
      "referral_status": "COMPLETE or another documented status",
      "bonus_timestamp": "ISO-8601 timestamp, or YYYY-MM-DD"
    }
  ]
}
```

`confirmed` mode requires every candidate field and `proposed_deposit_confirmed: true`. `conditional` mode is for an expressly assumed comparison; candidate facts may be false or absent, but the output is not an eligibility determination. In both modes, identity verification, current assessment time, and referral history are required. Convert runtime `MM/DD/YYYY` referral dates to `YYYY-MM-DD` before invoking the evaluator.

The output provides `rolling_window`, per-program determinations, `recommendations` for confirmed eligibility, and `conditional_recommendations` for planning comparisons. Do not disclose raw history contained in the input or output.

## Response checklist

For a confirmed result, lead with the highest confirmed referrer bonus, account, qualifying new-money threshold, deposit window, and tenure requirement. For a conditional result, label it conditional and identify the same comparison details while explaining why larger bonuses do not fit the stated plan. In both cases, mention new money, 30-day retention, good standing, promotion/referral-code restrictions, annual cap, and rolling cap as applicable.
