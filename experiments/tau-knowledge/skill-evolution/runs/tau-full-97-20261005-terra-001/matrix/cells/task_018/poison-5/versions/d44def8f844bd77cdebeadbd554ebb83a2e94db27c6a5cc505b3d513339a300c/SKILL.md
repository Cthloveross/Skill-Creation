---
name: credit-card-rewards-review-and-dispute
version: 1.0.0
description: Review completed credit-card transactions for reward discrepancies using documented card rules, explain results in points and dollars, and route unresolved discrepancies to the customer-initiated dispute process. Use when a customer asks to check cash back or reward points across one or more cards.
---

# Credit-Card Rewards Review and Dispute

Use this workflow to conduct a scoped or full review of credit-card reward earnings. It supports documented rules for Crypto-Cash Back, Business Platinum Rewards Card, Silver Rewards Card, and EcoCard. Do not infer an unprovided card's rates, promotions, or merchant coding.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

### Prerequisite checklist

1. Establish the requested scope (one transaction, one card, or all cards) and the customer's authority to request the review.
2. Verify identity by having the customer confirm at least two of the four stored fields: date of birth, email, phone number, and address. Do not disclose a stored value as the prompt. A name alone is not a completed verification.
3. Once two fields match, obtain the current timestamp and call `log_verification` with the complete returned profile and timestamp.
4. Before accessing or discussing account-specific results, confirm the relevant accounts and transactions belong to the verified user and that the card product is eligible for rewards review.
5. Before offering a dispute or applying a correction, verify the exact transaction ID, card details, applicable program rules at the purchase date, any promotions, reward-adjustment limits, fees, cutoffs, and whether customer confirmation or an approved dispute is required. Stop and explain any prerequisite that cannot be confirmed.

If prior read-only observations exist but there is no completed two-field verification and audit log, complete verification before communicating customer-specific findings or taking any action.

## Review method

1. Retrieve the verified customer's credit-card accounts and transactions. Review only transactions in the customer-approved scope. Use completed or posted transactions for a final earning review; label other statuses as not final rather than treating them as errors.
2. Gather any card terms, active promotion, merchant-category, and transaction-eligibility information available at the purchase date. Rewards use the posted merchant category; merchant names alone do not override it except for explicit documented EcoCard exclusions.
3. Build a JSON review input and run:

   ```sh
   python3 scripts/review_rewards.py < review_input.json
   ```

   The script reads one JSON object from standard input and emits one JSON object to standard output. It does not contact banking systems or perform any account action.
4. Validate the result before using it: `errors` must be empty; every eligible completed/posted input transaction must have exactly one result; and each `under_credited` result must include a numeric `recommended_new_rewards_earned` and a documented rate. Treat `needs_rate_confirmation`, `unsupported_card`, and `not_final` as review limitations, not confirmed discrepancies.
5. Present a concise customer-facing report with transaction date, merchant, recorded points and dollar equivalent, expected points and dollar equivalent where determinable, and the reason for each discrepancy. Points on all listed cash-back cards and EcoCard redeem at $0.01 per point. Do not claim that a point balance itself was changed.
6. For records not flagged as discrepancies, summarize the count reviewed and any records that could not be conclusively evaluated. Ask for receipts only when merchant classification or eligibility needs review.

## Supported rate rules

Use only rates documented for the card and transaction, unless a verified historical promotion or rate override is supplied in the script input.

- **Crypto-Cash Back:** 2.0% on eligible purchases.
- **Business Platinum Rewards Card:** 4.0% for Travel, Software, and Media; 1.5% for other purchases. Cash equivalents, balance transfers, and fees earn no rewards.
- **Silver Rewards Card:** 4.0% for Travel and Software. The supplied policy establishes that ordinary spend earns *at least* 1.0%, not an exact universal base rate. The script therefore conclusively evaluates bonus categories and performs only a minimum-rate check for other categories unless `silver_base_rate_percent` is supplied from applicable terms.
- **EcoCard:** 5 points per dollar for qualifying Green/Sustainable purchases, otherwise 1 point per dollar. Target, Walmart, Amazon, and ThredUp always receive the standard rate. EV charging is higher-rate only at Tesla Supercharger, ChargePoint, or EVgo. A `Green`/`Sustainable` transaction category is evidence of qualification unless an explicit exclusion overrides it; do not invent partner status from a merchant name.

A rewards ledger stores whole-number points. The helper truncates fractional calculated points toward zero, consistent with the supplied statement-style records. If program terms provide a different rounding rule, do not use the helper's determination until it is updated or a documented rate override resolves the issue.

## Helper input schema

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "card_type": "string",
      "merchant_name": "string",
      "category": "string",
      "transaction_amount": "currency amount",
      "rewards_earned": "whole points or a string such as '123 points'",
      "status": "COMPLETED or POSTED",
      "reward_eligible": true,
      "rate_override_percent": 4.0
    }
  ],
  "silver_base_rate_percent": 1.0
}
```

`transactions` is required. `reward_eligible` is optional; set it to `false` only when eligibility has been independently established as false. `rate_override_percent` is optional and is for verified historical promotions or product terms. `silver_base_rate_percent` is optional; provide it only when the exact applicable Silver base rate is known. Currency amounts may be numbers or strings such as `$12.34`.

The output contains `results`, `summary`, and `errors`. Result states include `matches`, `under_credited`, `over_credited`, `ineligible_with_rewards`, `needs_rate_confirmation`, `unsupported_card`, and `not_final`. A correction candidate has `recommended_new_rewards_earned` formatted as `"X points"`; that is a calculation recommendation only.

## Discrepancy handling

Do not directly alter a transaction merely because the helper found a discrepancy.

1. Confirm with the customer which specific transaction(s) they want disputed and verify the exact transaction IDs. Explain the calculated shortfall and any assumptions.
2. For a customer who wants to proceed, provide the customer-run tool `submit_cash_back_dispute_0589`. Use `give_discoverable_user_tool` to make it available, and instruct the customer to run:

   `submit_cash_back_dispute_0589(user_id: str, transaction_id: str)`

   with their own user ID and the specific transaction ID. Do not collect card numbers or sensitive card details for this step. Supporting category or receipt information may be requested during review.
3. Do not use an expected-rewards value stored in a dispute record as the basis for a correction.

## Applying an approved correction

This portion is internal-only and applies **only after** a cash-back dispute is resolved and approved.

1. Look up resolved disputes to identify affected transaction IDs. Confirm the dispute, transaction, account, and card belong to the verified and authorized customer; re-check product eligibility, exact card and transaction details, applicable historical rate/promotion, rewards adjustment limits, fees, cutoffs, and confirmation requirements.
2. Independently recompute whole points using the rules above and the transaction's original facts. Record the calculation rationale in the internal case record.
3. Call `unlock_discoverable_agent_tool` for `update_transaction_rewards_3847`.
4. Call `update_transaction_rewards_3847` through `call_discoverable_agent_tool` with the exact `transaction_id` and `new_rewards_earned` in the exact form `"X points"`.
5. Re-read the transaction in `credit_card_transaction_history` and confirm the stored reward value matches the approved calculation. If the result does not match, do not retry blindly; document the failure and escalate through the appropriate internal process.

Do not use this internal correction flow for pending, denied, unresolved, or customer-unconfirmed disputes.
