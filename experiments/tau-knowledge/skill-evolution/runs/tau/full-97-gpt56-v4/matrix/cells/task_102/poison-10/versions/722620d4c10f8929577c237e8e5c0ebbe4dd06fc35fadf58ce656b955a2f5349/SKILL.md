---
name: checking-referral-eligibility-review
description: Safely assess a checking-account customer's ability to make one or more referrals, including identity and authority prerequisites, tenure and product requirements, annual product caps, the cross-product rolling nine-day bonus limit, and unresolved recipient eligibility facts. Use for referral questions, planning, or status explanations; it does not submit referrals.
---

# Checking Referral Eligibility Review

Use this Skill when a customer asks whether they can refer a person or business, wants help planning multiple referrals, or questions a referral limit. It is an advisory workflow only: do not represent a referral as created, approved, or guaranteed, and do not use an advisory result to initiate any banking action.

## Required controls and data collection

Before accessing or discussing customer-specific referral history, verify the customer's identity and authority under the normal banking procedure. Retrieve the account owner record only as needed to compare customer-supplied information; confirm at least two of the available identity fields (date of birth, email, phone number, address) against that record. Immediately log the completed verification using the normal verification tool **before** retrieving referral history or any other customer-specific banking record. Do not batch a referral-history lookup with the verification log. Preserve this prerequisite with any subsequent banking procedure.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

For a referral review, also obtain or verify:

1. The referrer's earliest checking-account opening date. Tenure is measured from that date, not from the current product. A historical referral record alone should not be treated as a substitute where the opening date is available.
2. The full referral history, including status and exact completion timestamps when assessing the rolling limit.
3. For each consumer recipient: intended product, age, whether they are a new Rho-Bank customer with no current account and no account closed in the prior 12 months, and whether their registered address differs from the referrer's.
4. For each business recipient: company formation age, new-customer status, different registered address where applicable, and confirmation that the primary authorized signer's SSN is not the primary owner/authorized signer for an existing Rho-Bank business account.
5. Whether another new-account promotion or sign-up bonus would be applied. A referral cannot be stacked with one, and only one referral code may be applied to a new account.

The referral program requires these eligibility checks before giving customer-specific referral recommendations or terms. If a fact is absent, label it **unconfirmed** rather than assuming it is satisfied.

## Review method

1. Establish the current timestamp and use the exact time zone shown by the banking system.
2. Verify the customer and authority against two customer-supplied identity fields, then log that verification. Complete this step before any referral-history lookup; do not issue the log and history calls in parallel.
3. Only after the verification log succeeds, obtain the referral history using the normal banking tools. Count only `COMPLETE` records toward earned referral-bonus caps unless the product system explicitly defines another status as paid.
4. Check the cross-product rolling limit: at most two successful referral bonuses may occur in the preceding rolling nine days. It applies across every checking product. If timestamps are date-only, request exact timestamps for records near the nine-day boundary; do not present a boundary result as certain.
5. Count completed referrals for the current calendar year by intended product. Do not rely on a customer's approximate count when records are available.
6. Confirm referrer tenure against the intended product's threshold and check the recipient-specific conditions below. Obtain the earliest checking-account opening date from the authoritative account record whenever the declared tools expose it; do not infer it from referral history where that record is available.
7. State separately (a) whether the product annual cap and rolling capacity leave room and (b) whether the proposed recipient is eligible. Capacity does not establish recipient eligibility.
8. Explain the remaining qualification conditions: the qualifying deposit must be new money, made within the product window, and retained for at least 30 days after the qualifying period ends. An account closed within 90 days may cause a bonus clawback; both accounts must remain in good standing.
9. If the customer wants an actual referral created, gather all required recipient and offer details, reconfirm eligibility and limits immediately before the action, obtain required confirmation, and use only the declared normal banking referral tool. If no such tool is available, explain that the Skill cannot create the referral.

## Product reference

| Product | Referrer tenure | Recipient/product condition | Qualifying deposit | Annual cap |
|---|---:|---|---:|---:|
| Gold Years | 30 days | Recipient must be age 62+ | $1,000 within 90 days | 6 |
| Dark Green | 45 days | Recipient opens Dark Green; primary holder age 17 through 26 | $1,000 within 60 days | 6 |
| Light Green | 14 days | Primary holder age 13 through 24; minors may participate with a guardian | $100 within 90 days | Not specified in available terms |
| Sky Blue | 45 days | Startup/company within 4 years of formation | at least $10,000 within 90 days | 8 |

Known referral rewards: Gold Years pays the referrer $50 and recipient $75; Dark Green pays the referrer $40 and recipient $30; Sky Blue pays the referrer $150 and the startup $250. Do not invent a reward amount where terms do not specify one.

## Communicating the result

Use a concise per-recipient result with these fields:

- **Proposed product and known product fit** (for example, age or company-age fit)
- **Capacity**: annual completed count/cap and rolling-window count/cap
- **Referrer condition**: tenure result or the exact information still needed
- **Recipient conditions**: satisfied, failed, or unconfirmed for every common and product-specific restriction
- **Next step**: the minimum facts or actions needed; include deposit amount, deadline, new-money requirement, retention, good-standing, and no-stacking conditions when relevant

Do not expose unnecessary personal data from account records. Explain that a refusal caused by the rolling limit cannot be reinstated within the same window and that the customer must wait until enough prior successful bonuses age out.

## Optional deterministic helper

Run `scripts/referral_assessment.py` with JSON on standard input to calculate annual completed counts, rolling-window capacity, and rule-based candidate findings. The script does not contact banking systems or create referrals.

Input schema:

```json
{
  "as_of": "ISO-8601 timestamp",
  "referrer": {"identity_verified": true, "earliest_checking_opened_at": "ISO-8601 timestamp"},
  "referrals": [{"date": "ISO-8601 timestamp or YYYY-MM-DD", "status": "COMPLETE", "account_type": "Gold Years Account"}],
  "candidates": [{
    "label": "recipient label",
    "product": "Gold Years|Dark Green|Light Green|Sky Blue",
    "kind": "consumer|business",
    "age": 62,
    "company_age_years": 2,
    "new_customer": true,
    "different_registered_address": true,
    "different_business_primary_owner": true,
    "other_promotion": false
  }]
}
```

`age` applies to consumer candidates; `company_age_years` and `different_business_primary_owner` apply to Sky Blue businesses. Boolean eligibility fields may be omitted when unknown. Referral records may use `status` or the normal banking tool's `referral_status`, and may use `account_type`, the normal banking tool's `referred_account_type`, or `product`. The output JSON reports unknowns explicitly, plus a conservative rolling capacity when a date-only history entry falls on the exact boundary. Validate that `as_of` and all supplied timestamps parse, candidate products are supported, and no candidate marked `ready` has a failed or unconfirmed prerequisite, including annual and cross-product rolling capacity.
