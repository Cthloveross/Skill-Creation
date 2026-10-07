---
name: business-checking-referral-recommendation
description: Verify a checking customer's referral eligibility before providing business-checking referral guidance, then select the highest referrer bonus that the proposed business and deposit can qualify for. Use for questions about referring a business, referral bonuses, eligibility, or account choice.
---

# Business Checking Referral Recommendation

Use this Skill for informational referral guidance only. It does not create a referral, apply a code, open an account, move money, or promise a bonus.

## Required checks before any referral recommendation

Do not give account-specific referral terms or a recommendation until eligibility has been checked. For account-specific records or any banking action, first verify identity under the normal banking procedure: obtain and match two of date of birth, email, phone number, and address; retrieve the customer record; obtain the current timestamp; and log the successful verification with `log_verification`.

Then establish all of the following from customer confirmation and available records:

1. The referrer's earliest checking-account opening date. Tenure is measured from the first checking account, not the account currently held.
2. Referral-bonus history, including exact timestamps of successful (`COMPLETE`) bonuses in the preceding rolling nine days and completed referrals in the current calendar year.
3. The proposed referred business is a new Rho-Bank customer and has had no checking, savings, or closed account in the preceding 12 months.
4. The businesses are registered at different addresses.
5. The proposed business has a primary owner whose primary authorized-signer SSN differs from every existing Rho-Bank business account. Do not infer this merely because the customer calls the person a partner or says they have a separate office.
6. The anticipated qualifying deposit is enough for the proposed product, is new external money rather than a Rho-Bank transfer, and can remain in the account for 30 days after the applicable deposit window ends.
7. The product-specific annual cap has not been reached.

A customer statement can be used as a stated fact where no verification tool exists, but identify any unresolved prerequisite and ask a focused question. If exact timestamps are unavailable for a potentially relevant recent bonus, do not guess whether the rolling window has elapsed.

## Referral rules to apply

All checking referral programs have a shared maximum of two referral bonuses in any rolling nine-day window, across account types. A third or later referral in that period is automatically denied and cannot be reinstated during that window. Count successful/`COMPLETE` bonuses, using exact timestamps. A referred account must remain in good standing; closing it within 90 days can result in a clawback. A referral cannot be combined with another new-account promotion, and only one referral code may be applied.

Use these supported product terms. Omit a product rather than inventing a missing requirement.

| Product | Referrer bonus | Referred qualifying deposit | Deposit window | Referrer tenure | Annual cap |
|---|---:|---:|---:|---:|---:|
| World Blue | $300 | $25,000 | 90 days | 90 days | 12 |
| True Blue | $350 | $50,000 | 120 days | 90 days | 15 |
| Beige | $500 | $100,000 | 120 days | 120 days | 15 |
| Lime Green | $200 | $15,000 | 90 days | 90 days | 12 |
| Hunter Green | $175 | $10,000 | 90 days | 60 days | 10 |
| Navy Blue | $100 | $5,000 | 90 days | 60 days | 10 |
| Sky Blue | $150 | Unsupported by available referral terms | Unsupported | Unsupported | 8 |

The qualifying deposit must be new money and must remain for at least 30 days after the qualifying period ends. For World Blue, the referred business must open World Blue and deposit at least $25,000 within 90 days. For a reward-maximization request, choose the eligible supported product with the greatest *referrer* bonus; do not optimize the referred business's welcome bonus.

From November 1 through November 30, 2025, promotional ordering applies only if multiple accounts meet every stated customer requirement. In that situation prefer Sky Blue, then Lime Green, then other qualifying products. Do not let that ordering override an explicit request to maximize the referrer's bonus or compensate for missing product terms.

## Runtime workflow

1. Determine whether the request asks about a referral or a business-checking recommendation.
2. If it does, complete the prerequisite checks above before disclosing referral information. When identity verification is necessary, use the normal banking tools and log it before proceeding.
3. Retrieve referrals using `get_referrals_by_user` only after resolving the authenticated customer ID. Retrieve current time when recording verification or evaluating time-sensitive caps.
4. Convert tool results and customer confirmations into the JSON input for `scripts/evaluate_referral.py`. The script is a deterministic aid; it does not perform banking actions.
5. If the result is `needs_information`, ask only for the listed missing facts. If it is `ineligible`, explain the applicable blocking condition without claiming a bonus will be paid. If it is `eligible`, communicate the recommended product, the referrer bonus, the required deposit and window, and the remaining general conditions.
6. Never submit a referral or apply an offer code from this workflow. If the customer wants to proceed, direct them to the normal authorized referral process or appropriate relationship manager where applicable.

## Script interface

Run `scripts/evaluate_referral.py` with one JSON object on stdin. It writes one JSON object to stdout.

Input fields:

- `now` (required): ISO-8601 timestamp with timezone when possible.
- `referrer`: object with `identity_verified` (boolean), `first_checking_opened` (ISO date/timestamp), and optional `customer_record_resolved` (boolean).
- `referred_business`: object with booleans `new_customer_no_account_in_last_12_months`, `different_registered_address`, and `different_primary_owner_from_existing_business_accounts`.
- `deposit`: object with numeric `amount` and boolean `is_new_money`.
- `referrals`: array of objects containing `date` (ISO date/timestamp), `referred_account_type`, and `referral_status`. Completed records are used for caps.

The output includes `status` (`needs_information`, `ineligible`, or `eligible`), prerequisite issues, a recommendation only when it is safe to make one, and product qualification details. Date-only referral records that could fall inside the nine-day boundary cause a `needs_information` result because exact timestamps are required.

Example invocation schema (use live values, never these placeholders as facts):

```json
{
  "now": "2025-01-01T12:00:00-05:00",
  "referrer": {"identity_verified": true, "first_checking_opened": "2024-01-01", "customer_record_resolved": true},
  "referred_business": {"new_customer_no_account_in_last_12_months": true, "different_registered_address": true, "different_primary_owner_from_existing_business_accounts": true},
  "deposit": {"amount": 30000, "is_new_money": true},
  "referrals": []
}
```

## Validate before responding

- Check that no recommendation appears if identity, tenure, customer/newness, address, owner, or new-money facts are absent or false.
- Confirm that `COMPLETE` referrals across all product types are used for the rolling nine-day cap and that only same-product completed referrals are used for that product's annual cap.
- Confirm the recommended bonus is the highest eligible referrer bonus, not a welcome bonus.
- State that qualification and payment remain subject to the deposit, timing, good-standing, retention, cap, and promotion-stacking conditions. Do not represent a result as guaranteed.
