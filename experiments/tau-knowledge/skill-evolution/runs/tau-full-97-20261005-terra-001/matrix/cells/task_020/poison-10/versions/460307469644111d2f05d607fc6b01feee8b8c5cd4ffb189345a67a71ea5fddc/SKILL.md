---
name: cash-back-rewards-audit-and-dispute
version: 1.1.0
description: Audit posted Business Silver Rewards Card and Silver Rewards Card transactions against documented cash-back rules, identify genuine reward-point shortfalls, explain results, provide customer-executable dispute actions only for supported shortfalls, and apply only resolved corrections.
---

# Cash-Back Rewards Audit and Dispute

Use this Skill for a customer who reports missing, incorrect, or unexpectedly low cash back on a Business Silver Rewards Card or Silver Rewards Card. It supports a full transaction review when the customer cannot identify a specific charge, and a single-transaction review when they can.

## Banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this workflow, do not disclose account or transaction details, submit a dispute, or change rewards until identity has been verified. Obtain and compare two of these four fields against the customer record: date of birth, email, phone number, and address. Then obtain the current timestamp and create the required verification audit record with `log_verification`. Confirm that the card account and transactions belong to the verified user, and that the customer is authorized to discuss them. Review the applicable card, transaction status, merchant/category data, promotion eligibility, and any confirmation requirement before an action.

## Reward rules used by this Skill

- Rewards stored as points on these cash-back cards represent cash back at **1 point = $0.01**.
- Calculate points as `floor(transaction amount × cash-back rate as a decimal × 100)`. Always truncate fractional points; never round to nearest.
- Only posted/completed purchases should be evaluated as finalized earnings. Returned, refunded, reversed, pending, or otherwise non-final entries need transaction-history review rather than an automatic expected-points calculation.
- **Business Silver Rewards Card:** eligible travel and software purchases earn 10%; other purchases earn 1%. The posted merchant category controls eligibility.
- Apply Business Silver named merchant exclusions **before** any promotional multiplier. Concur, SAP Concur, Expensify, Navan, Apple, Microsoft, Dell, Xbox Game Pass, PlayStation Plus, Nintendo Switch Online, Coursera, Udemy, LinkedIn Learning, Skillshare, and Pluralsight earn the 1% standard rate rather than the 10% bonus rate. A merchant name that begins with a listed merchant name followed by a descriptor is also treated as that named merchant (for example, a product or service suffix).
- Business Silver double-cash-back promotion: accounts opened from 2024-11-14 through 2025-11-14 qualify for twice the otherwise applicable rate for the first six calendar months after account opening. This doubles both the bonus rate and standard rate, while exclusions remain ineligible for the travel/software bonus.
- **Silver Rewards Card:** eligible travel and software purchases earn 4%. The supplied policy does not establish a non-bonus base rate for this card. Supply the current approved standard rate as `silver_standard_rate_percent` when auditing non-travel/non-software transactions; otherwise those rows are reported as needing policy review.
- A travel or software label is not enough if merchant-category evidence conflicts with it. Use the posted category supplied by transaction history and flag questionable merchant coding for review.

## Procedure

1. **Verify before accessing or acting.** Ask for two identity fields if they have not already been confirmed. Look up the customer only using the provided identifier, compare the supplied fields, obtain the current time, and log successful verification. Confirm account ownership from the card-account record. If verification, authority, or ownership cannot be established, stop without revealing records or taking an action.
2. **Collect authoritative records.** Retrieve the customer’s credit-card accounts and transaction history using normal banking tools. Restrict the review to the verified customer’s requested card(s) and requested timeframe when one is available. Confirm relevant entries are posted/completed and preserve transaction ID, card type, account opening date, merchant, category, amount, date, and recorded points.
3. **Audit deterministically.** Build the JSON input described below and run `scripts/audit_rewards.py`. Do not use an `expected_rewards` value from a dispute record as an input to the calculation. Inspect `errors`, `needs_review`, `shortfalls`, and `overcredits` before drawing conclusions. `discrepancies` includes both under- and over-crediting; it is not itself a dispute-candidate list.
4. **Explain the review.** State the applicable rate, whether a Business Silver promotion applied, the truncation rule, expected points, recorded points, and difference for each calculated row needing explanation. Explain that points equal cents of cash back. Do not characterize excluded merchants as bonus-eligible. If recorded points are equal to or greater than expected points, say there is no missing-cash-back shortfall and do not offer a dispute action. If category is uncertain, explain that the posted merchant category governs and request a receipt or merchant-coding review.
5. **Correct prior misinformation promptly.** If the customer selected a transaction because it was previously described incorrectly as under-credited, explicitly acknowledge and correct the result before listing supported actions. Name the merchant, explain any applicable exclusion, state the correct promotional or base rate, truncated expected points, recorded points, and that no shortfall supports a dispute. Do not provide or retain a dispute action for that transaction absent new relevant evidence.
6. **Provide a customer dispute action only for a confirmed shortfall.** Confirm the transaction ID with the verified customer. For every individually confirmed item in `shortfalls`, use the normal discoverable-user-tool mechanism to give `submit_cash_back_dispute_0589` with structured arguments containing the verified user's `user_id` and that one exact `transaction_id`. The customer initiates this tool; do not submit it on their behalf. Never give the tool for `overcredits`, matches, policy-review rows, or unsupported transactions. Supporting category or promotion context may be requested during review.
7. **Apply corrections only after resolution and approval.** Locate resolved, approved cash-back disputes in the applicable disputes record source and identify the exact transaction IDs. Independently rerun the calculation from transaction, card, merchant-category, and promotion data. Unlock `update_transaction_rewards_3847`, then call it with the exact `transaction_id` and `new_rewards_earned` formatted exactly as `"X points"`. Confirm the resulting transaction-history record and retain the rate, promotion, eligibility, floor calculation, and resolution reference in the internal case record. If the dispute is not resolved and approved, do not update rewards.

## Audit helper

Run `scripts/audit_rewards.py` with JSON on stdin. It emits one JSON object on stdout.

Input schema:

- `accounts`: array of objects with `card_type`, `date_of_account_open` (`YYYY-MM-DD`), and optionally `account_id`.
- `transactions`: array of objects with `transaction_id`, `credit_card_type`, `transaction_amount` (number or currency string), `transaction_date` (`YYYY-MM-DD`), `category`, `merchant_name`, `status`, `rewards_earned` (integer or `"N points"`), and optionally `account_id`.
- `silver_standard_rate_percent`: optional numeric/string current approved non-bonus rate for Silver Rewards Card. It is required to calculate personal-Silver non-bonus rows.

A minimal structural invocation is:

```json
{"accounts": [], "transactions": []}
```

Output schema:

- `ok`: whether input validation completed without blocking errors.
- `audits`: calculation or review result for every supplied transaction.
- `discrepancies`: all completed calculations where recorded and expected points differ.
- `shortfalls`: calculated entries where recorded points are below expected points; only these can support a dispute action after customer confirmation.
- `overcredits`: calculated entries where recorded points exceed expected points; these are not missing-cash-back disputes.
- `needs_review`: entries skipped because of non-final status, missing policy, uncertain mapping, or unsupported card data.
- `errors`: malformed input, missing required calculation fields, or ambiguous account mapping.
- `summary`: counts and point totals for calculated discrepancies.

Validate before acting: every correction candidate must have a nonempty transaction ID, an unambiguous matching account, a supported card type, a final transaction status, a numeric nonnegative amount, a valid transaction date, a whole-number expected result, and a positive expected-minus-recorded difference. Treat helper output as calculation evidence, not as authorization to alter an account.

## Failure handling

- If the customer cannot complete identity verification, explain that verification is required before account-specific review and offer to continue when they have two verification fields available.
- If no specific transaction can be identified, complete a read-only review after verification and ask the customer to confirm each shortfall candidate before providing its dispute tool.
- If a customer requests a dispute for a calculated match or over-credit, explain the relevant calculation and that a missing-cash-back dispute cannot be supported on the available evidence.
- If a personal Silver non-bonus rate is unavailable, do not infer one from recorded points; obtain the approved current terms or report that row as policy review.
- If merchant category, status, refund status, account mapping, promotion window, or dispute resolution status is unclear, do not update rewards. Request the missing record or route it through the normal review process.
- If the correction tool or dispute-record access is unavailable, document the independently calculated result and use the institution’s approved escalation path; do not claim a correction was applied.
