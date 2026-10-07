---
name: business-checking-recommendation
version: 1.0.0
description: Recommend one business checking account when a customer states hard requirements, especially overdraft-fee and monthly ATM-rebate requirements. Use this skill to confirm product fit, apply a time-bounded promotional ordering only among confirmed qualifying products, and state material caveats without opening an account.
---

# Business Checking Recommendation

## Purpose

Recommend a single account only after separating:

1. **Hard customer requirements** (for example, a $0 overdraft fee and a minimum monthly ATM-fee rebate),
2. **Product-specific eligibility** (for example, company-age rules),
3. **General account-opening eligibility**, which must be verified only if the customer asks to proceed with opening, and
4. **Preference ordering**, including an active promotion. A promotion is a tiebreaker among products that already meet every stated requirement; it never overrides a requirement.

This skill supports an informational recommendation. Do not open an account merely because the customer asked which account is best.

## Required runtime inputs

Use the current conversation, supplied knowledge, and any supplied current-time observation. Extract at least:

- Explicit hard requirements and their thresholds.
- Facts needed to establish each candidate's fit.
- Any product-specific eligibility condition and whether it is confirmed, unconfirmed, or failed.
- The date/time if applying a time-limited promotion.

Do not infer missing facts such as company formation date, customer verification status, personal-account status, account count, closed-account status, or balance.

## Decision procedure

1. Treat unambiguous phrases such as "non-negotiable," "absolutely cannot," and "need at least" as hard requirements.
2. For each candidate, verify the documented fee, rebate cap, and every other hard requirement. A cap equal to the requested minimum satisfies an "at least" requirement.
3. Mark a candidate **not confirmed** when a product-specific eligibility condition is unknown. Do not use an unknown condition as proof of eligibility.
4. Exclude products that fail a hard requirement or whose required product eligibility is not confirmed. If no candidate is confirmed, explain precisely what fact is needed; do not make a conditional product recommendation sound final.
5. If two or more candidates are confirmed, apply a promotion only when its active dates include the supplied current date. Apply its stated ranking only within that confirmed set.
6. Recommend the selected account directly. Give the customer the material facts supporting the choice and any meaningful associated charges, thresholds, or limitations relevant to their stated use. Do not turn the response into an unnecessary broad comparison.
7. If the customer asks to open the recommended business checking account, first complete the documented opening prechecks: identity verification; at least one OPEN personal checking account; no more than six business checking accounts; no CLOSED accounts; and an existing checking balance of at least $500. Only then use the documented account-opening workflow/tool with the customer's chosen account class. Do not claim these checks passed unless they were actually verified.

## Source-specific guidance available in this package

Read `references/documented_account_facts.md` before responding to requests involving the documented products. In the supplied knowledge set, the documented Lime Green facts support a $0 overdraft fee and up to $25 in eligible monthly out-of-network ATM-fee rebates. Its monthly maintenance fee, waiver threshold, minimum-balance requirement, and foreign-ATM fee are material disclosures when relevant.

The documented Sky Blue product has a $0 overdraft fee and up to $15 monthly ATM-fee rebates, but its company-age condition must be confirmed before it can qualify. Its promotional priority does not cure an unconfirmed condition. The promotion described in the reference applies only during its stated November 2025 window.

## Optional deterministic helper

Use `scripts/evaluate_candidates.py` when candidate facts have been structured. It reads one JSON object from stdin and emits one JSON object to stdout.

### Input schema

```json
{
  "requirements": {
    "overdraft_fee_must_equal": "0.00",
    "minimum_monthly_atm_rebate": "15.00"
  },
  "candidates": [
    {
      "name": "Account name",
      "product_eligibility": "eligible",
      "overdraft_fee": "0.00",
      "monthly_atm_rebate_cap": "25.00",
      "facts": {"optional": "facts to retain in output"}
    }
  ],
  "promotion": {
    "active": true,
    "ranking": ["Preferred qualifying account", "Next qualifying account"]
  }
}
```

`product_eligibility` must be `eligible`, `ineligible`, or `unknown`. Monetary values may be JSON numbers or decimal strings. Omit a requirement key if it is not a customer requirement. The helper intentionally does not assume that a missing fact passes.

### Output and validation

The output contains an evaluation for every candidate, the confirmed qualifying names, one `recommendation` or `null`, and `missing_or_blocking_facts`. Before using its conclusion, confirm that:

- every hard customer requirement appears in the input;
- monetary inputs use the account's stated monthly cap rather than a per-transaction fee;
- the promotion's `active` value was determined from the actual supplied date; and
- a `null` recommendation is handled by requesting only the fact needed to resolve eligibility or missing product evidence.

Example runnable call (replace all values with runtime facts):

```bash
python3 scripts/evaluate_candidates.py <<'JSON'
{"requirements":{"overdraft_fee_must_equal":"0.00","minimum_monthly_atm_rebate":"15.00"},"candidates":[{"name":"Candidate A","product_eligibility":"eligible","overdraft_fee":"0.00","monthly_atm_rebate_cap":"20.00"}],"promotion":{"active":false,"ranking":[]}}
JSON
```

## Response pattern

Use a concise customer-facing structure:

- **Recommendation:** name the one confirmed-fit account.
- **Why it fits:** connect each hard requirement to the documented figure.
- **Important practical note:** disclose relevant monthly fee/waiver, balance, ATM, or other stated-use details.
- **Eligibility/opening caveat:** mention only unverified prerequisites that actually matter, and offer the next step if the customer wants to apply.

Never describe a fee rebate as a waiver of an ATM operator's separate surcharge unless the source explicitly says that surcharge is eligible.
