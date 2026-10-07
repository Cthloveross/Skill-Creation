---
name: cash-back-discrepancy-audit
version: 1.0.0
description: Audit posted credit-card transactions for documented cash-back reward discrepancies, including Business Silver promotional eligibility, exclusions, and whole-point truncation. Use after identity verification to explain potential discrepancies and to route a customer to the documented self-service dispute tool; use the correction workflow only for resolved disputes.
---

# Cash-Back Discrepancy Audit

Use this Skill when a customer reports missing or incorrect credit-card cash back, including when they cannot initially identify the affected transaction. It supports a review of posted transactions using the merchant category recorded on the transaction, applicable card rules, documented exclusions, promotions, and point rounding.

## Safety and banking controls

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

1. Do not reveal transaction, card, account, or reward details merely because a caller supplied a name or an email address.
2. Verify the customer by confirming at least two of the four identity fields: date of birth, email, phone number, and address. Obtain the reference values with the supported user lookup, compare the customer-provided values, then call `log_verification` with all required fields and the current timestamp.
3. Confirm authority and ownership by ensuring that the cards and transactions being reviewed belong to the verified user. Confirm the relevant card type and target transaction with the customer before any dispute submission or correction.
4. Obtain the account record and record the available balance or credit information supplied by it. Check applicable fees, limits, cutoffs, and confirmation requirements in the applicable product/process documentation. Do not invent any where documentation does not provide them; treat unknown requirements as a blocker for an action, not as satisfied.
5. Rewards reviews do not transfer money or designate a recipient. A dispute is initiated by the customer using the prescribed user tool. A rewards correction is an internal action permitted only after a dispute is resolved and approved.

## Review workflow

1. **Establish the review scope.** Ask for the card and transaction or statement period, received rewards, and expected rewards. If the customer cannot identify a transaction, after verification retrieve their accounts and posted transaction history and perform a bounded review of the available records. Explain that an audit can identify candidates but merchant category and eligibility may require further review.
2. **Collect runtime records.** Retrieve the customer's credit-card accounts and transactions only after verification. Include each card's type and account-opening date. Audit completed/posted purchases; do not calculate final rewards for pending, returned, or refunded activity.
3. **Calculate independently.** Run `scripts/audit_rewards.py` with runtime-supplied account and transaction JSON. The helper applies only documented rules and returns either an expected whole-point amount or `review_needed` with a reason.
4. **Interpret points correctly.** On cash-back cards, stored "points" equal cash back at 1 point = $0.01. Rewards are always truncated down to a whole point, never rounded to nearest.
5. **Discuss results.** Identify only records marked `mismatch` after verification. Present the recorded category, applicable documented rate, expected points, observed points, and the reason. Do not promise an adjustment: category coding, posting changes, credits, and other eligibility facts can affect the final result.
6. **Submit a customer dispute.** The documented dispute process requires a verified user ID and a specific transaction ID. Once the customer confirms the candidate transaction, provide `submit_cash_back_dispute_0589(user_id: str, transaction_id: str)` through `give_discoverable_user_tool` and instruct the customer to run it with their own identifiers. Do not collect card numbers or other sensitive card details. If no transaction can be identified or confirmed, request one before offering the tool.
7. **Apply corrections only after approval.** For resolved, approved disputes, locate the relevant transaction IDs in the cash-back-disputes database; do not rely on an `expected_rewards` field. Recalculate independently. Unlock `update_transaction_rewards_3847`, invoke it with the exact transaction ID and `new_rewards_earned` formatted exactly as `"X points"`, and confirm the result in credit-card transaction history. Retain calculation notes in the internal case record. If resolved-dispute records or confirmation access are unavailable, do not update rewards.

## Documented calculation rules

- **Business Silver Rewards Card:** eligible travel and software purchases earn 10.0% cash back; other purchases earn 1.0%.
- A Business Silver eligible travel/software purchase earns the enhanced rate only when the recorded merchant category is Travel or Software and the merchant is not excluded. Eligibility rests on merchant processing/category coding.
- Business Silver exclusions that receive the ordinary 1.0% rate are Concur, SAP Concur, Expensify, Navan, Apple, Microsoft, Dell, Xbox Game Pass, PlayStation Plus, Nintendo Switch Online, Coursera, Udemy, LinkedIn Learning, Skillshare, and Pluralsight. The helper recognizes a named merchant and a merchant name beginning with a listed name (for example, a branded subscription), but flags ambiguous matching for review.
- The Business Silver double-cash-back offer doubles the applicable 10.0% or 1.0% rate for the first six months after account opening, provided the account was opened from 2024-11-14 through 2025-11-14. The helper treats the six-month anniversary as the first non-promotional day.
- **Silver Rewards Card:** transactions recorded as eligible Travel or Software earn 4.0%. The supplied material does not establish an ordinary non-bonus rate for this card. Supply `other_rate_percent` in the card policy only when that rate is supported by applicable documentation; otherwise, the helper returns `review_needed` for non-Travel/non-Software transactions.
- The transaction category is evidence of merchant coding, not proof that a merchant will ultimately qualify. Do not override category coding based solely on the merchant name.

## Helper interface

Run `scripts/audit_rewards.py` with a JSON object on stdin and read one JSON object from stdout.

Input schema:

```json
{
  "accounts": [
    {"card_type": "Business Silver Rewards Card", "date_of_account_open": "YYYY-MM-DD"}
  ],
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "string",
      "merchant_name": "string",
      "transaction_amount": "12.34",
      "transaction_date": "YYYY-MM-DD",
      "category": "Travel",
      "status": "COMPLETED",
      "rewards_earned": "123 points"
    }
  ],
  "card_policies": {
    "Silver Rewards Card": {"other_rate_percent": "1"}
  }
}
```

`card_policies` is optional. Use it only to provide documented supplemental rates; it never changes Business Silver's fixed documented rates. The output contains `results`, each with a `disposition` of `match`, `mismatch`, `review_needed`, or `skipped`, plus rate, expected-point, and explanatory fields where calculable. Top-level `errors` reports malformed input without fabricating a result.

Example runnable call:

```sh
python3 scripts/audit_rewards.py <<'JSON'
{"accounts":[],"transactions":[]}
JSON
```

## Validation before acting

- Confirm all transaction IDs are unique, every reviewed transaction has a matching account-opening date, monetary values parse exactly, and dates are valid.
- Confirm only completed/posted transactions were treated as final.
- For every `mismatch`, verify `expected_points == floor(amount_in_dollars * rate_percent)` before discussing or submitting it. This expression yields points because one percentage point of one dollar is one point.
- Treat missing account dates, unrecognized cards, unrecorded categories, invalid amounts/dates, unparseable actual rewards, and ambiguous merchant matches as `review_needed`; do not submit or correct them automatically.
- Before an internal correction, re-read the post-update transaction record and ensure its reward value exactly equals the calculated `"X points"` value.
