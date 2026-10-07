---
name: credit-card-rewards-audit
description: Audit posted credit-card reward transactions against documented earn rates, exclusions, promotions, and per-transaction truncation. Use for a customer-authorized, read-only review that identifies under- and over-credited reward entries without changing account balances or rewards.
---

# Credit Card Rewards Audit

Use this Skill to produce a reproducible, transaction-level rewards audit. It evaluates each supported completed transaction separately, floors fractional points, and distinguishes definite discrepancies from records that require manual review.

## Controls and prerequisites

Before accessing or disclosing customer account, card, or transaction data, obtain and log identity verification using two of the four supported identity fields (date of birth, email, phone number, address). Confirm the requester is authorized for the account and that each card being audited belongs to that customer. This Skill is read-only: do not post a reward adjustment, redemption, credit, dispute, or other account change.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this audit, collect current time, verified customer information, all of the customer's card accounts (including card type and open date), and all relevant transaction records. Match a transaction to an account by `account_id` when available; otherwise, only infer the account from card type when the customer has exactly one account of that type. If there are multiple matching accounts, do not make a determination without an account identifier.

## Method

1. Supply normalized account and transaction JSON to `scripts/audit_rewards.py`.
2. Review `needs_review` entries before making conclusions. Typical causes are unknown cards, missing amounts/rewards, a non-completed status, no unambiguous Business Silver account, or unsupported transaction types such as returns and fees.
3. For `audited` entries, compare `expected_points` with `recorded_points`. A nonzero `point_delta` is `expected - recorded`: positive is under-credited and negative is over-credited.
4. Report every discrepancy with transaction ID, date, card, merchant, recorded points, expected points, signed point difference, and applied rule. For cash-back cards, also state the cash equivalent of the point difference at $0.01 per point. EcoCard points are sustainability points; do not characterize them as cash back.
5. State that the result is an audit finding and does not itself change the account. Escalate unclear merchant coding, qualifying status, or return/credit linkage for review rather than guessing.

## Rule implementation

The helper uses `Decimal` and computes `floor(transaction_amount × points-per-dollar)` for each transaction; it never rounds to nearest. It supports:

- Diamond Elite: 5 points per dollar on eligible purchases; fees, cash equivalents, balance transfers, and similar non-earning categories receive zero.
- Business Platinum: 4 points per dollar for Travel, Software, Media, or Advertising; 1.5 otherwise; non-earning transaction types receive zero.
- Business Silver: 10 points per dollar for Travel and Software, or 1 point otherwise. Listed excluded merchants receive 1 point even in a bonus category. A qualifying new-account promotion doubles the applicable rate only when the account was opened from 2024-11-14 through 2025-11-14 and the transaction falls within the first six calendar months after opening, no later than 2025-11-14.
- EcoCard: 5 points per dollar for a qualifying green category or certified EV partner; otherwise 1. Target, Walmart, Amazon, and ThredUp are always standard-rate. EV charging is enhanced only for Tesla Supercharger, ChargePoint, or EVgo.

The source data must provide the transaction's actual merchant/category. Merchant-category-code disputes and green eligibility not represented by these documented conditions are not safely decidable by this helper.

## Script interface

Run `scripts/audit_rewards.py` with one JSON object on stdin:

```json
{
  "accounts": [
    {"account_id": "<optional account id>", "card_type": "<supported card>", "date_of_account_open": "YYYY-MM-DD"}
  ],
  "transactions": [
    {
      "transaction_id": "<id>",
      "account_id": "<optional account id>",
      "credit_card_type": "<supported card>",
      "merchant_name": "<merchant>",
      "transaction_amount": "<dollar amount>",
      "transaction_date": "YYYY-MM-DD",
      "category": "<category>",
      "status": "COMPLETED",
      "rewards_earned": "<integer points>"
    }
  ]
}
```

Dollar amounts may be numeric or currency-formatted strings. The output is JSON with `summary`, `discrepancies`, `correct_transactions`, and `needs_review`. Each audit row is self-contained and includes the applied points-per-dollar rate and rule explanation. Validate that the number of rows across those three lists equals the input transaction count and that every listed discrepancy has a nonzero `point_delta`.
