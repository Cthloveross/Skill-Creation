---
name: credit-card-rewards-discrepancy-review
description: Review posted credit-card reward transactions against documented card rates, exclusions, promotions, and truncation rules; identify supportable discrepancies and safely route or apply corrections only after the required dispute and verification prerequisites are met.
---

# Credit-Card Rewards Discrepancy Review

Use this Skill when a customer reports that cash back or rewards points appear incorrect, or when an approved rewards-dispute correction must be calculated and applied. It supports comparison and calculation; it does not itself change a bank record.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For an account-specific review or any dispute/correction action:

1. Identify the customer only through an approved lookup.
2. Ask the customer to confirm at least two of the four identity fields: date of birth, email, phone number, and address. A name alone, an account lookup result, or information supplied by the agent is not confirmation.
3. After confirmation, obtain the current timestamp and call `log_verification` with the complete verified record.
4. Confirm the relevant account belongs to the verified customer and that each reviewed transaction belongs to that customer and card. Do not reveal unconfirmed account or transaction details.
5. For a customer-initiated dispute, confirm the exact transaction identifier with the customer. Do not collect card numbers or other unnecessary sensitive details.

If identity cannot be verified, explain that account-specific investigation and changes require verification. The agent may give general program information but must not disclose transaction data, create a dispute, or change rewards.

## Rewards interpretation and calculation rules

* Rewards stored as `points` are cash back for cash-back cards. One point has a $0.01 statement-credit/checking-credit value.
* Convert a percentage reward rate to points as `purchase_amount × rate_percent`; for example, 4% means 4 points per dollar.
* Round down (truncate) each individual transaction's computed point value to a whole point. Never round to nearest and never aggregate fractional remainders across purchases.
* Use the posted transaction's category, merchant, date, and status. A pending, returned, refunded, reversed, fee, interest, gift-card, insurance-premium, or person-to-person entry must not be treated as an ordinary qualifying purchase without applicable policy support.
* Product rate schedules, exclusions, and offer terms must be taken from the current supplied knowledge/policy for the case. Do not infer a higher rate merely from a merchant name.

For the documented Silver Rewards Card policy, qualifying posted Travel and Software transactions use the enhanced rate; other ordinary purchases use the standard rate. For the documented Business Silver Rewards Card policy, start from the base or Travel/Software bonus rate, apply explicit merchant exclusions before a promotion multiplier, and apply a promotion only if both account-opening and transaction-date conditions are satisfied. An exclusion changes the applicable rate but does not justify ignoring a separately documented all-purchase promotion.

## Review workflow

1. Complete the mandatory identity and ownership checks above.
2. Retrieve the customer's card accounts and transactions using the normal read-only banking tools. Record the card type, account-open date, transaction ID, posted date, merchant, category, amount, status, and awarded points.
3. Build a policy object from the supplied case knowledge. Include each card's base and bonus percentage, eligible categories, explicit excluded merchants, and any promotion's opening-date range, multiplier, and months-from-opening window. Do not hardcode current-case dates, IDs, merchants, or expected awards into this Skill or a case file.
4. Run `scripts/audit_rewards.py` with structured copies of those account and transaction records and the policy. The helper returns assessed transactions, `under_credited` and `over_credited` subsets of mismatches, and transactions it deliberately could not assess. A cash-back shortfall candidate must be in `under_credited`; do not treat an over-credit as a customer loss.
5. Manually validate every mismatch against the source policy and the transaction's posted status/category. Resolve ambiguity in merchant coding, refunds, or missing terms before claiming an error.
6. Explain the review clearly: awarded points, calculated whole points, and cash-value equivalent ($0.01 per point). State that merchant classification after posting controls eligibility.
7. If the customer wants a discrepancy investigated, provide the customer-facing `submit_cash_back_dispute_0589(user_id, transaction_id)` via `give_discoverable_user_tool` only after the prerequisites and exact transaction ID are confirmed. The customer initiates that tool; do not submit it on their behalf.
8. Do not change rewards merely because this audit finds a mismatch. An internal correction requires a resolved and approved dispute. Inspect the authorized resolved-disputes source (the `cash_back_disputes` source when available) to identify the exact affected transaction and confirm its status. If the runtime instead explicitly supplies an authoritative approved/resolved result after the customer runs the required dispute tool, that supplied result may establish the status; a bare customer assertion without an authoritative result is not sufficient. Independently calculate the award (do not trust an `expected_rewards` field), unlock `update_transaction_rewards_3847`, and call it with the exact transaction ID and `new_rewards_earned` formatted exactly as `"X points"`. Before a call, re-read the transaction if needed to ensure the correction has not already been applied. Then re-read transaction history and confirm the exact updated award. Retain the calculation and source-policy notes in the authorized case record.

If resolution/approval cannot be confirmed, a required tool is unavailable, any policy fact is missing, or an operation returns an unknown outcome, do not apply or repeat a correction. Tell the customer the case needs review or route it through the documented support/dispute path.

## Calculator script

Run `scripts/audit_rewards.py` with JSON on standard input. It emits one JSON object on standard output and uses only the input supplied at runtime.

Input schema:

```json
{
  "accounts": [
    {"card_type": "string", "date_of_account_open": "YYYY-MM-DD"}
  ],
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "string",
      "merchant_name": "string",
      "transaction_amount": "decimal or $decimal",
      "transaction_date": "YYYY-MM-DD",
      "category": "string",
      "status": "COMPLETED",
      "rewards_earned": "whole points or N points"
    }
  ],
  "policy": {
    "programs": {
      "card type": {
        "base_rate_percent": "decimal",
        "bonus_rate_percent": "decimal",
        "bonus_categories": ["category"],
        "excluded_merchants": ["merchant"],
        "promotion": {
          "open_start": "YYYY-MM-DD",
          "open_end": "YYYY-MM-DD",
          "months_after_open": 6,
          "multiplier": "decimal"
        }
      }
    }
  }
}
```

`promotion` is optional. When present, the account must have an opening date; the opening date must be within the inclusive offer opening range; and the transaction date must fall from opening through, but not including, the calendar-month anniversary. Merchant/category comparisons are case-insensitive after whitespace normalization. An excluded merchant matches an exact posted merchant name or a word-boundary extension of the listed merchant name (such as a listed brand followed by a product descriptor), not a merely similar prefix. Each listed excluded merchant receives the program's base rate before any eligible all-purchase multiplier. The assessed record reports `matched_exclusion` so it can be manually verified.

Output includes `mismatches` plus `under_credited` and `over_credited` subsets. Each assessed record has `expected_points`, `actual_points`, `difference_points` (expected minus actual), `discrepancy_type`, rate, promotion status, matched exclusion (if any), and cash values; `not_assessed` explains unsafe or unsupported records; and `errors` identifies malformed or ambiguous input. Only transactions with status `COMPLETED` are calculated. Review `not_assessed` and `errors` rather than treating omitted records as correct.

Example invocation format (use live case data, not example values):

```sh
python3 scripts/audit_rewards.py < review_input.json
```

Validation before a correction: ensure there are no relevant `errors`, the candidate is in `under_credited` (not merely `mismatches`), its expected points match an independent Decimal calculation using the documented policy, the dispute is confirmed resolved and approved, and a subsequent transaction-history read shows the exact requested `X points` value.
