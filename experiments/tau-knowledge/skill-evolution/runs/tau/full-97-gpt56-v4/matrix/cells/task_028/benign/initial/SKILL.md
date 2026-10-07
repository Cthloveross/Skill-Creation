---
name: credit-card-reward-audit
description: Review posted credit-card transaction rewards against documented earn rates, whole-point truncation, and EcoCard eligibility limits; identify supported discrepancies and guide the customer to the required self-service cash-back dispute tool.
---

# Credit-card reward audit

Use this Skill when a customer asks whether credit-card cash back or reward points were calculated correctly. It supports reviews of EcoCard, Silver Rewards Card, Business Platinum Rewards Card, and Crypto-Cash Back transactions where transaction amount, card type, category, status, and recorded reward points are available.

## Important interpretation rules

* Transaction rewards are stored as **points**. One point is worth $0.01 when redeemed as a statement credit or checking-account credit. This applies to cash-back cards and EcoCard sustainability points.
* Calculate each transaction independently and always truncate fractional points down: `floor(transaction amount × points per dollar)`.
* Do not round to the nearest point, aggregate purchases before rounding, or promise a manual adjustment.
* Review posted/completed purchase transactions. Returns, refunds, fees, cash equivalents, balance transfers, and non-posted transactions need separate handling and should not be treated as ordinary eligible purchases.

## Rates supported by the audit

| Card | Enhanced rate | Standard rate |
|---|---:|---:|
| EcoCard | 5 points/$ on qualifying green purchases | 1 point/$ on other purchases |
| Silver Rewards Card | 4 points/$ on Travel or Software | 1 point/$ otherwise |
| Business Platinum Rewards Card | 4 points/$ on Travel, Software, or Media/Media Advertising | 1.5 points/$ otherwise |
| Crypto-Cash Back | 2 points/$ on eligible purchases | N/A |

For EcoCard, Target, Walmart, Amazon, and ThredUp are standard-rate merchants even for environmentally themed merchandise. EV charging receives the green rate only on Tesla Supercharger, ChargePoint, or EVgo. Prefer an explicit `green_eligible` transaction field when available. If it is absent, a `Green` category is a useful provisional indication, but say that merchant recognition/category coding determines final qualification.

The separate EcoCard 2% eco-certified-merchant bonus requires a linked Green Account (savings) in good standing. Do **not** infer that eligibility from transaction data or claim that the bonus was included. If no authorized account/link-status lookup is available, explicitly say that this extra bonus cannot be verified with the available information while still completing the standard-rate audit.

## Procedure

1. Obtain an account identifier from information the customer provides, then use the normal read-only banking tools to retrieve the customer’s card accounts and transaction history. Do not expose unrelated personal fields returned by a lookup.
2. Collect or use transaction records with `transaction_id`, `credit_card_type`, `merchant_name`, `transaction_amount`, `category`, `status`, and `rewards_earned`.
3. Run the deterministic audit helper:
   ```sh
   python3 scripts/audit_rewards.py < transactions.json
   ```
   The helper reads one JSON object from stdin and writes one JSON report to stdout. Its schema is documented below.
4. Review `discrepancies` only after checking that the record is a completed purchase and that the helper's eligibility basis matches the available facts. Treat `manual_review` records as inconclusive, not as confirmed errors.
5. Tell the customer, concisely, which transactions match and which supported transactions differ. For a discrepancy, give the transaction date/merchant, recorded versus expected whole points, and the point difference. You may also state the dollar equivalent as `points × $0.01`.
6. For each transaction the customer wants disputed, provide the documented customer-operated tool `submit_cash_back_dispute_0589(user_id: str, transaction_id: str)` using `give_discoverable_user_tool`. Supply the customer’s own user ID and that exact transaction ID as arguments. This initiates review; it does not guarantee an adjustment. Confirm the transaction ID before offering the tool.
7. If the available facts cannot establish the card rate, merchant qualification, account-link eligibility, or status, explain the specific limitation and do not manufacture a discrepancy. A customer can still submit a dispute for a specific transaction if they believe its category or promotion was wrong.

Do not call a dispute-submission tool as an agent and do not repeat an action with an unknown result. Normal read-only account and transaction lookups do not themselves require a verification log; if a workflow separately verifies two identity fields, use the normal verification logging requirement.

## Helper input/output

Input must be a JSON object:

```text
{
  "transactions": [transaction, ...],
  "eco_account_bonus_eligible": true | false | null,
  "strict_eco_eligibility": true | false
}
```

Each transaction requires `transaction_id`, `credit_card_type`, `transaction_amount`, `category`, `status`, and `rewards_earned`; `merchant_name` and `green_eligible` are optional. Amounts may be JSON numbers or currency strings. `green_eligible`, when present, overrides category inference. Set `strict_eco_eligibility` to true to place EcoCard green-category transactions without explicit eligibility evidence into `manual_review` instead of treating the Green category as a provisional qualifying signal.

The output has `matched`, `discrepancies`, `manual_review`, and `skipped` arrays. A discrepancy contains `expected_points`, `recorded_points`, `difference_points`, `rate_points_per_dollar`, and the rate/eligibility basis. The report includes an `eco_account_bonus` note and never folds the conditional 2% bonus into standard expected points.

Validation before relying on output: ensure every supported completed record appears exactly once in `matched`, `discrepancies`, or `manual_review`; confirm expected points are whole nonnegative integers; and manually confirm any merchant/category fact the helper marked provisional.