---
name: credit-card-rewards-audit
description: Audit posted credit-card transaction rewards against supported Diamond Elite, Business Platinum, Business Silver, and EcoCard earning rules. Use when a customer asks why rewards appear too high or low, or requests a transaction-by-transaction rewards review.
---

# Credit-card rewards audit

Use this Skill for a read-only calculation audit. It determines the expected integer database reward points for each supplied transaction, identifies discrepancies, and explains rates without treating cash-back database points as EcoCard sustainability points.

## Required runtime inputs

Obtain the customer's account records and transaction history using the normal read-only banking tools. An account-name lookup identifies a record but is not identity verification. Do not log verification unless the customer has actually confirmed two required identity fields and verification is needed for a later protected action.

Supply the normalized results to `scripts/audit_rewards.py` as JSON. The script does not query banking tools and does not make corrections.

Input schema:

```json
{
  "accounts": [
    {"card_type": "...", "date_of_account_open": "MM/DD/YYYY"}
  ],
  "transactions": [
    {
      "transaction_id": "...",
      "credit_card_type": "...",
      "merchant_name": "...",
      "transaction_amount": 12.34,
      "transaction_date": "MM/DD/YYYY",
      "category": "...",
      "status": "COMPLETED",
      "rewards_earned": 123
    }
  ]
}
```

`transaction_amount` may also be a string containing `$` and comma separators. A completed or posted transaction is auditable; other statuses are returned as skipped because rewards are based on posted net purchases. Each audited transaction needs a numeric amount, date, category, merchant, card type, and recorded integer rewards. If multiple accounts share a card type, include `account_open_date` in each affected transaction so the Business Silver promotion can be evaluated unambiguously.

Run:

```sh
python3 scripts/audit_rewards.py < audit_input.json > audit_result.json
```

The script emits JSON with an item for every supplied transaction, plus `discrepancies`, counts, and point totals. A discrepancy has `direction` (`over_earned` or `under_earned`) and `difference_points`, calculated as recorded minus expected. Its validation object reports malformed rows, skipped rows, and ambiguity warnings; do not claim a complete audit if these are nonempty.

## Rules implemented

The expected result is truncated down to a whole point per transaction, matching an integer transaction database representation.

* **Diamond Elite Card:** 5.0% cash back on eligible purchases, represented as 5 points per dollar.
* **Business Platinum Rewards Card:** 4.0% (4 points/dollar) for category-coded Travel, Software, or Media purchases; 1.5% (1.5 points/dollar) otherwise.
* **Business Silver Rewards Card:** 10.0% (10 points/dollar) for category-coded Travel or Software and 1.0% otherwise. Apple, Microsoft, Dell, the named gaming subscriptions, named online-learning platforms, and named expense platforms are explicit exclusions and earn the standard rate. The limited promotion is applied only if the account opened between 2024-11-14 and 2025-11-14 inclusive, the transaction is on or after opening, and is before the six-calendar-month anniversary of opening. It doubles the otherwise applicable rate. Eligibility still depends on merchant coding, so categories in the supplied transaction record are used rather than guesses from a merchant name.
* **EcoCard:** 5 sustainability points per dollar when category-coded Green, otherwise 1 point/dollar. The explicit Target, Walmart, Amazon, and ThredUp exclusions always receive 1 point/dollar. Tesla Supercharger, ChargePoint, and EVgo are certified EV networks; an identified transaction at one of these networks qualifies for 5 points/dollar. Do not describe EcoCard points as cash back.

For cash-back cards, explain that one stored point is $0.01 when redeemed. Thus, the dollar equivalent of a discrepancy is `abs(difference_points) × $0.01`. EcoCard sustainability points also redeem at $0.01 per point, but their earning rate is points per dollar and should be labeled as such.

## Customer response procedure

1. Confirm the review covers every returned transaction and state the number reviewed, skipped, and needing clarification.
2. Summarize only discrepancy rows, grouped into too many and too few points. Give transaction date, merchant, card, recorded points, expected points, difference, and rate reason. Avoid presenting an expected rate as certain if the category/coding is missing.
3. Clearly distinguish a cash-back point discrepancy's redemption-value equivalent from its point count. Describe EcoCard separately.
4. For transactions that match, give an aggregate count rather than a needlessly long list unless the customer requests the full reconciliation.
5. This Skill is calculation-only. Do not alter balances, issue credits, or promise a correction. If the customer asks for remediation or disputes merchant coding, follow currently available bank policy/tools; if no supported resolution path exists, explain that it needs review rather than inventing an adjustment.

## Output validation

Before responding, ensure: every input transaction appears once in either `audits` or `skipped`; `discrepancy_count` equals the length of `discrepancies`; every expected and recorded value is integral; and cash-back dollar equivalents use exactly $0.01 per point. The script emits these checks in `validation`.
