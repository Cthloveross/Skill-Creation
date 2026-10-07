---
name: business-checking-recommendation
version: 1.1.0
description: Recommend one business checking account when a customer states hard requirements, especially overdraft-fee and monthly ATM-rebate requirements. Use this skill to confirm product fit, apply time-bounded promotional ordering only among confirmed qualifying products, disclose material caveats, and complete a requested human handoff without opening an account before eligibility is established.
---

# Business Checking Recommendation

## Purpose

Recommend one account after separating:

1. **Hard customer requirements** (for example, a $0 overdraft fee or minimum monthly ATM-fee rebate),
2. **Product-specific eligibility** (for example, company-age rules),
3. **General account-opening eligibility**, which must be verified only when proceeding with an opening request, and
4. **Preference ordering**, including an active promotion.

A promotion is a tiebreaker only among products that already meet every stated requirement; it never overrides a requirement. Do not open an account merely because the customer asks which account is best.

## Required runtime inputs

Use the current conversation, supplied knowledge, documented tools, and any supplied current-time observation. Extract:

- Explicit hard requirements and thresholds.
- Facts needed to establish each candidate's fit.
- Any product-specific eligibility condition and whether it is confirmed, unconfirmed, or failed.
- The date/time if applying a time-limited promotion.
- Whether the customer asks for account opening or explicitly requests a human agent.

Do not infer missing facts such as company formation date, customer verification status, personal-account status, account count, closed-account status, or balance.

## Decision procedure

1. Treat unambiguous phrases such as "non-negotiable," "absolutely cannot," and "need at least" as hard requirements.
2. For each candidate, verify the documented fee, rebate cap, and every other hard requirement. A cap equal to the requested minimum satisfies an "at least" requirement.
3. Mark a candidate **not confirmed** when a product-specific eligibility condition is unknown. Do not use an unknown condition as proof of eligibility.
4. Exclude products that fail a hard requirement or whose required product eligibility is not confirmed. If no candidate is confirmed, explain precisely what fact is needed; do not make a conditional recommendation sound final.
5. If two or more candidates are confirmed, apply a promotion only when its active dates include the supplied current date. Apply its stated ranking only within that confirmed set.
6. Recommend the selected account directly. Connect every hard requirement to a documented figure, and disclose meaningful associated charges, thresholds, or limits relevant to the stated use. Do not turn the response into an unnecessary broad comparison.
7. If the customer asks to open the recommended business checking account, first complete the documented opening prechecks: identity verification; at least one OPEN personal checking account; no more than six business checking accounts; no CLOSED accounts; and an existing checking balance of at least $500. Only then use the documented account-opening workflow/tool with the customer's chosen account class. Do not claim these checks passed unless they were actually verified.

## Identity verification and opening limits

When an opening workflow requires identity verification and the supported identity tools are available:

1. Obtain the applicable customer record using an appropriate lookup.
2. Confirm the required identity fields with the customer according to the verification-tool policy.
3. Obtain the current timestamp if required by the logging tool.
4. Call `log_verification` using the matched record and the actual verification timestamp.
5. Treat identity as verified only after the logging result succeeds.

Verification alone does not establish the required existing-account relationship, account count, closed-account status, or checking-balance eligibility. Do not open the account when those required facts are unavailable. Explain the unresolved checks and offer an appropriate completion path.

## Mandatory human handoff

An express customer request for a human agent must be acted on, not merely acknowledged. This includes plain-language requests (for example, "I want a human") and explicit routing markers such as `###TRANSFER###`.

When such a request occurs:

1. Call `transfer_to_human_agents` promptly. Do not ask the customer to repeat the request or wait for additional account-opening facts.
2. Use `customer_requests_human_no_specific_reason` when the customer simply requests a person without another enumerated reason. If the conversation establishes a more specific supported reason, use that reason instead.
3. Provide a concise, factual `summary`. Include the recommendation or current product assessment, identity-verification status, the customer's requested account class if known, and every unresolved opening eligibility item that matters. Do not include invented eligibility results or sensitive facts not needed for the handoff.
4. Wait for and inspect the tool result. State that the transfer was completed only if the result is successful. If it fails, tell the customer that the handoff could not be submitted and provide the available next step; do not falsely claim transfer success.

For a customer seeking to open a recommended business checking account when relationship and balance records are unavailable, the handoff summary should say that identity is verified if logging succeeded and that existing OPEN personal-checking status, business-checking count, CLOSED-account status, and qualifying existing checking balance remain to be confirmed.

## Source-specific guidance available in this package

Read `references/documented_account_facts.md` before responding to requests involving the documented products. In the supplied knowledge set, documented Lime Green facts support a $0 overdraft fee and up to $25 in eligible monthly out-of-network ATM-fee rebates. Its monthly maintenance fee, waiver threshold, minimum-balance requirement, and foreign-ATM fee are material disclosures when relevant.

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

`product_eligibility` must be `eligible`, `ineligible`, or `unknown`. Monetary values may be JSON numbers or decimal strings. Omit a requirement key if it is not a customer requirement. The helper intentionally does not assume a missing fact passes.

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
- **Eligibility/opening caveat:** mention only unverified prerequisites that actually matter.
- **Handoff confirmation:** after an express human request, confirm transfer only after its tool result succeeds.

Never describe a fee rebate as a waiver of an ATM operator's separate surcharge unless the source explicitly says that surcharge is eligible.
