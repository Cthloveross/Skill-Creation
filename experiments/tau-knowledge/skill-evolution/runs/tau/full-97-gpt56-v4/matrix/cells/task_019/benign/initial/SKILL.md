---
name: credit-card-rewards-discrepancy-audit
description: Audit completed Gold Rewards Card and EcoCard purchase rewards against published earning rules, identify under- or over-awards, and prepare a customer-safe discrepancy report. Use when a customer asks why card rewards or cash back look wrong.
---

# Credit-card rewards discrepancy audit

## Scope and policy rules

Use this Skill for a transaction-level review of rewards already shown in card history. It does not change reward balances, create adjustments, or promise that an adjustment will be made.

Apply these rules:

- **Gold Rewards Card:** earn 2.5% on every purchase. Because stored points represent cents of cash back, expected points are `floor(amount in dollars × 2.5)`.
- **EcoCard:** earn `floor(amount × 5)` sustainability points for qualifying green purchases and `floor(amount × 1)` otherwise.
- Points are always rounded **down** to whole points.
- EcoCard transactions at Target, Walmart, Amazon, and ThredUp earn the standard rate even if the item appears eco-friendly.
- EV charging earns the EcoCard green rate only on Tesla Supercharger, ChargePoint, or EVgo. Treat a confirmed session at another charging network as standard-rate.
- A transaction categorized Green or Sustainable may be assessed at the elevated EcoCard rate unless a stated exclusion applies. If the available record does not establish green eligibility, do not claim that the transaction was under-awarded at the green rate; identify that eligibility needs confirmation.
- Points on both cards have a redemption value of $0.01 per point. For a discrepancy, `expected points - displayed points` is therefore also the corresponding dollar difference in cents.
- Returned, refunded, reversed, pending, declined, or otherwise non-completed records require review against the original purchase and should not be treated as a normal completed-purchase discrepancy.

## Safe operating procedure

1. Clarify whether the customer wants a specific period, card, or transaction reviewed. If no period is available, explain the period that will be reviewed before summarizing it.
2. Follow the bank's identity-verification requirement before retrieving or disclosing account-specific activity. Confirm two of the four identity fields (date of birth, email, phone, address), obtain the current timestamp, then call `log_verification` with all required record fields. A name alone is not sufficient verification. Do not disclose profile values merely to solicit confirmation.
3. Retrieve the customer's card accounts and transaction history using the normal banking tools. Limit the review to the requested period when one is known. Use only transactions belonging to the cards being reviewed.
4. Convert the relevant transaction records into the JSON schema below and run `scripts/audit_rewards.py`. The helper performs calculations only; it does not call bank tools or make account changes.
5. Inspect `discrepancies`, `needs_review`, and skipped entries. Recheck the transaction amount, card type, merchant, category, status, and any known merchant-eligibility facts before describing a result to the customer.
6. Give a concise report by card and transaction: date, merchant, amount, displayed points, expected points, difference, and the rule used. Call stored Gold points “cash back represented as points” and keep EcoCard rewards labeled “sustainability points.” State the dollar equivalent only as a redemption value, not as a cash adjustment already made.
7. If the review finds a credible discrepancy and a correction or deeper merchant-category investigation is needed, do not alter balances or invent an adjustment tool. Explain that the rewards team must investigate it; use the normal escalation path when available (for example, `transfer_to_human_agents` with `complex_billing_dispute` when transferring an unresolved rewards dispute). Include the transaction facts, calculation, and eligibility uncertainty in the handoff summary.
8. If no discrepancy is found, explain the applicable rate and truncation calculation. Offer to review a different period or a receipt/merchant-eligibility detail if relevant.

Do not expose unnecessary account identifiers, contact details, full balances, or unrelated transactions in the final customer-facing response.

## Audit helper

Run from the Skill package with JSON on standard input:

```sh
python3 scripts/audit_rewards.py < audit-input.json
```

### Input schema

The input is a JSON object:

```json
{
  "transactions": [
    {
      "transaction_id": "string (optional)",
      "credit_card_type": "Gold Rewards Card or EcoCard",
      "merchant_name": "string",
      "transaction_amount": "decimal amount, number, or dollar-formatted string",
      "transaction_date": "string (optional)",
      "category": "string (optional)",
      "status": "COMPLETED",
      "rewards_earned": "integer points",
      "green_eligible": "boolean (optional, confirmed merchant eligibility)",
      "is_ev_charging": "boolean (optional, confirmed charging transaction)"
    }
  ]
}
```

`green_eligible` should be supplied only when eligibility is actually confirmed from the transaction, receipt, or merchant directory. `is_ev_charging` enables the charging-network restriction. Inputs may include other cards; they are returned as skipped rather than guessed.

### Output schema and validation

The script emits one JSON object with:

- `audits`: evaluated completed Gold/Eco transactions, including calculated rate, expected and actual whole points, point/dollar difference, classification basis, and outcome.
- `discrepancies`: the subset with an under- or over-award.
- `needs_review`: completed EcoCard transactions whose category/eligibility was not sufficient to determine elevated-rate eligibility confidently.
- `skipped`: non-completed, refund/non-positive, unsupported-card, or malformed records and the reason.
- `summary`: counts and total point difference across confirmed discrepancies.

Validate that every discussed transaction appears in `audits` or `skipped`; that expected points are integers; that each completed Gold result uses a 2.5 points-per-dollar rate; that each completed Eco result uses either 1 or 5 points per dollar; and that any discrepancy equals `expected_points - actual_points`. Do not treat a helper error or an eligibility-review flag as proof of a bank error.
