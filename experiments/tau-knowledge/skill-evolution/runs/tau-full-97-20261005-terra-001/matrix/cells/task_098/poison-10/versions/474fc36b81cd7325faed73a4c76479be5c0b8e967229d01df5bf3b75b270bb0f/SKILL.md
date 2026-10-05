---
name: checking-referral-recommendation
description: Assess a checking customer's referral eligibility and compare documented checking referral programs to identify the highest combined bonus that is confirmed or conditionally available. Use for referral-bonus questions, qualifying-deposit comparisons, referral-status interpretation, and rolling-window checks. Do not use to create a referral, open an account, or make any banking change.
---

# Checking Referral Recommendation

Use this skill for read-only, evidence-based referral guidance. A bonus comparison is not itself an eligibility approval. Check referrer eligibility before representing a program as available or a referral as approved; where a material fact remains unresolved, give only a clearly labelled conditional comparison.

## Required facts

Obtain or request the following at runtime:

- Referrer identity and authority to discuss account-specific records. Use the normal identity-verification workflow before accessing or discussing those records.
- The opening date of the referrer's **earliest Rho-Bank checking account**. Current account type and later accounts do not reset tenure.
- Referral records, their statuses, and the most precise available completion/bonus timestamps.
- Current time and time zone.
- Whether the prospective customer is new to Rho-Bank, with no existing account and no account closed in the last 12 months.
- Whether the two people have different registered addresses.
- Prospective customer's age or date of birth and, for a minor-specific program, any required guardian arrangement.
- Planned deposit amount, source, and timing.
- Current authoritative program terms for all products being compared.

Do not infer adulthood, new-customer status, address difference, qualifying-new-money source, exact completion time, or tenure from silence. A user statement may support a conditional assessment, but it does not convert an unresolved restriction into confirmed eligibility.

## Workflow

1. **Verify and retrieve records when needed.** Follow the normal banking identity-verification process before record access. Retrieve the referrer's referral history and the earliest checking-account opening date when those tools or records are available.
2. **Assess referrer eligibility first.** For every program, calculate tenure from the earliest checking opening, apply its annual cap, and evaluate the shared rolling nine-day cap. Only `COMPLETE` represents a successful referral bonus. `IN_PROGRESS` means an account is open but has not yet met its qualifying deposit; it is not a completed bonus and does not count as one.
3. **Apply shared customer restrictions.** The referred person must be a new customer, live at a different registered address, and normally be at least 18. Consider a minor only if the selected product expressly permits that age and its guardian requirements are confirmed. For a business referral, also verify a different primary owner by the primary authorized signer's SSN.
4. **Evaluate product-specific requirements.** Check age bounds, referrer tenure, annual cap, rolling cap, qualifying-deposit amount, deposit deadline, and whether the planned deposit is qualifying new money.
5. **Rank results.** Rank confirmed eligible products by `referrer_bonus + referred_bonus`. Exclude products that fail a known requirement. Keep products with only unknown requirements in a separate conditional ranking.
6. **Respond accurately.** State the best confirmed option, or state that none is confirmed. If the available policy identifies a leading conditional option, provide it rather than claiming the terms are unavailable. Name every open condition and do not say the customer “should use” a product, or that it is approved, until those conditions are satisfied.

## Conditional-comparison rule

When the user asks what to do next and a product is the highest option compatible with the known deposit plan, provide useful conditional guidance even if another eligibility fact is unknown. Use wording such as:

> “If the prospective customer confirms that she meets the age and other general eligibility requirements, [Account] is the highest disclosed option compatible with a deposit of at least [amount] in qualifying new money: [referrer bonus] for you plus [new-customer bonus] for her, [combined] combined. This is not yet a confirmed eligibility decision because [unresolved conditions].”

Then state the stated deposit deadline and all general conditions still applicable. In particular, a paycheck described as “about” an amount supports only a threshold comparison: say it must actually be at least the threshold and qualify as new money, not an internal Rho-Bank transfer.

This conditional guidance is permitted only after the available referrer and restriction checks have been performed as far as the facts allow. It must never be phrased as an unconditional adult-referral recommendation when the prospective customer's age is unknown.

## General conditions to retain

For any referral option discussed, explain as relevant that:

- The deposit must be qualifying **new money**, not a transfer from another Rho-Bank account, and must be made within the product-specific window.
- The deposit must remain for at least 30 days after the qualifying period ends.
- Both accounts must remain in good standing.
- A bonus may be clawed back if the referred account closes within 90 days.
- A referral bonus cannot be combined with another new-account promotion or sign-up bonus, and only one referral code may be used per new account.

### Rolling nine-day limit

There may be at most two successful referral bonuses across all checking products in a rolling nine-day interval. The limit uses exact successful-bonus timestamps, not calendar weeks. A third referral in the window is automatically denied and cannot be reinstated in that same window.

Do not count `IN_PROGRESS`, `APPLIED`, `NO_PROGRESS`, `REJECTED`, or `ERROR` as successful bonuses. A date-only `COMPLETE` record establishes that a completion occurred but cannot conclusively establish an exact rolling-window boundary result. In that case, say the rolling-cap outcome remains unconfirmed and obtain an exact timestamp before claiming the cap is available. A date-only record can still be used for an annual calendar-year count if its year is known.

### Annual caps

Apply the relevant program's annual referral limit to completed bonuses for that program in the relevant calendar year. If the product or calendar year cannot be established, mark the result unknown rather than guessing.

## Program catalog schema

Build `programs` from authoritative terms available in the current task. Do not reuse stale terms or substitute similarly named accounts. Each program object supplied to the helper must contain:

```json
{
  "account_type": "Official Account Name",
  "referrer_bonus": 0,
  "referred_bonus": 0,
  "annual_cap": 0,
  "qualifying_deposit": 0,
  "deposit_window_days": 0,
  "referrer_tenure_days": 0,
  "candidate_age_min": 18,
  "candidate_age_max": null,
  "guardian_required_under_18": false
}
```

Amounts are numeric dollars. Use `null` only where the product truly has no stated maximum age. Preserve any product-specific restrictions not represented by this schema in the narrative assessment.

## Helper

`scripts/evaluate_referrals.py` reads one JSON object from stdin and writes one JSON object to stdout. It performs only deterministic, read-only eligibility evaluation; it does not access bank systems or initiate a referral.

Input schema:

```json
{
  "now": "ISO-8601 timestamp with timezone",
  "programs": ["program catalog objects"],
  "referrer": {"first_checking_opened_at": "ISO-8601 timestamp with timezone or null"},
  "candidate": {
    "is_new_customer": true,
    "different_registered_address": true,
    "age": 21,
    "guardian_confirmed": false,
    "planned_deposit_amount": 600,
    "planned_deposit_is_new_money": true,
    "planned_deposit_within_window": true
  },
  "referrals": [
    {
      "referral_status": "COMPLETE",
      "referred_account_type": "Official Account Name",
      "completed_at": "ISO-8601 timestamp with timezone or null",
      "date": "YYYY-MM-DD or null"
    }
  ]
}
```

Use `null` for unknown facts. `completed_at` must be an exact timezone-aware timestamp when supplied; a date-only `date` is retained as imprecise history and makes the rolling-window result unknown. Output includes `confirmed_ranked_options`, `conditional_options`, `ineligible_options`, `rolling_window`, and reason codes.

Example runnable call:

```sh
python3 scripts/evaluate_referrals.py <<'JSON'
{"now":"2025-01-15T12:00:00-05:00","programs":[],"referrer":{"first_checking_opened_at":null},"candidate":{"is_new_customer":null,"different_registered_address":null,"age":null,"guardian_confirmed":null,"planned_deposit_amount":null,"planned_deposit_is_new_money":null,"planned_deposit_within_window":null},"referrals":[]}
JSON
```

## Output validation

Before relying on helper output:

- Verify every program has a nonempty official account name, nonnegative numeric bonuses/caps/deposit/window values, and a positive tenure threshold.
- Verify `now` and every non-null exact timestamp are timezone-aware ISO-8601 values.
- Reject malformed input instead of silently treating it as eligible.
- Ensure a definitive recommendation appears in `confirmed_ranked_options`, has no reason codes, and its combined bonus equals the component-bonus sum.
- A conditional option must be identified as conditional and accompanied by its unresolved reason codes in the customer-facing response.

## Human handoff

If the user explicitly requests a human agent, complete the normal human-transfer procedure. Do not withhold already available, policy-grounded conditional guidance merely because the transfer is requested; provide it before or alongside the handoff when safe. Include material context in the transfer summary: verified referrer identifier where available, relevant referral statuses and dates, unresolved eligibility facts, the conditional leading option, and any timing-precision limitation.

## Boundaries

- This skill is informational. Do not create a referral, open an account, apply a promotion, alter a profile, or disclose another person's account information.
- If a customer asks to complete a banking action, use its applicable procedure and satisfy every prerequisite before acting.
- If records conflict, a required lookup fails, or an eligibility issue cannot be reconciled, explain the limitation and use ordinary support escalation rather than inventing a result.
- A `REJECTED` referral due to the rolling limit requires waiting until the relevant successful bonus is more than nine days old; it cannot be reinstated within that window.

## Banking-action control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.
