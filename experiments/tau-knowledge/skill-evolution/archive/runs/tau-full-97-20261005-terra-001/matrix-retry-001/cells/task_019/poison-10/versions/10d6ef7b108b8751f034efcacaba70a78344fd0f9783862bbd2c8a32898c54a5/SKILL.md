---
name: credit-card-rewards-discrepancy-review
description: Authenticates a credit-card customer, reviews Gold Rewards Card and EcoCard rewards using whole-point truncation, explains transaction-level discrepancies, and provides customer-initiated cash-back dispute actions.
---

# Credit Card Rewards Discrepancy Review

Use for reports of missing, incorrect, or unexplained credit-card cash back or EcoCard sustainability points. This skill supports read-only review and customer-initiated disputes; it does not correct rewards or submit disputes for the customer.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Verification and scope

Before retrieving or discussing nonpublic account or transaction information:

1. Locate a candidate customer from a supplied name or email.
2. Verify identity by having the customer correctly confirm at least two stored fields from date of birth, email, phone number, or address. Do not disclose unconfirmed stored values as prompts.
3. Obtain the current time and log verification with the complete verified record only after the two successful confirmations.
4. Confirm authority and ownership: every reviewed account and transaction must belong to the verified user. Review only customer-authorized card products.
5. For this read-only rewards review, document that payment, transfer, redemption, recipient, credit-limit, fee, and cutoff checks are not applicable. Before a dispute, reconfirm the exact completed transaction, ownership, eligibility basis, and customer confirmation.

A name, account ID, or data merely found in a customer record is not identity verification.

## Workflow

1. After logged verification, retrieve the verified customer's credit-card accounts and transaction history with normal read-only banking tools.
2. Review only completed purchase transactions. Do not calculate pending, reversed, returned, refunded, disputed, negative, malformed, or non-purchase entries. Returned or refunded purchases require original-transaction context because rewards reverse at the original rate.
3. Run the retrieved records through `scripts/audit_rewards.py`; retain source transaction IDs and do not alter source data.
4. Validate every result shown to the customer against a retrieved transaction owned by the verified user and its recorded card type and completed status.
5. Clearly report each apparent under- or over-award with transaction ID, expected points, awarded points, shortfall or excess, and applicable rate. If green eligibility is not evidenced, state that the result is provisional and request merchant, receipt, or directory evidence rather than assume the higher rate.
6. In every customer-facing discrepancy review, explicitly state: **“All calculations use whole-point truncation (rounded down).”** State the count and total apparent missing points when under-awards exist. This wording is important even where the values are already whole numbers.
7. Ask the customer to identify and explicitly confirm each exact transaction ID they want to dispute. A summary of apparent discrepancies is not authorization to initiate a dispute.
8. After confirmation, provide—not invoke—`submit_cash_back_dispute_0589(user_id: str, transaction_id: str)` through the runtime user-tool handoff. Use the verified user ID and exactly one confirmed transaction ID in each handoff. Explain that the customer must run the tool separately once for each transaction.
9. If the customer reports being unable to access a provided action, re-provide a separate identical user-tool handoff for every confirmed transaction and again explain that each must be run separately. Do not submit it as the assistant.
10. Do not unlock or call internal reward-update tools during review or submission. Post-resolution adjustments are a separate workflow requiring a resolved approved dispute, independent recalculation, authorized update, transaction-history confirmation, and audit notes.

If the customer cannot name a transaction, complete the authenticated read-only review, summarize apparent discrepancies, and ask them to choose exact IDs. If none is identifiable, explain the calculation and offer to review a statement period or receipt.

## Reward rules

- **Gold Rewards Card:** all purchases earn 2.5% cash back. Stored points represent cash back at $0.01 each, so expected stored points are `floor(amount × 2.5)`.
- **EcoCard:** qualifying green purchases earn 5 sustainability points per dollar; other purchases earn 1 point per dollar. Expected points are `floor(amount × rate)`.
- All rewards use whole-point truncation: fractional points are rounded down.
- EcoCard merchant exclusions override a Green category: Target, Walmart, Amazon, and ThredUp receive the standard 1-point rate. Amazon-processed marketplace orders are Amazon purchases.
- EV charging receives 5 points per dollar only at Tesla Supercharger, ChargePoint, or EVgo; other charging networks receive the standard rate.
- An explicitly Green transaction may be treated as qualifying unless an exclusion overrides it. When neither explicit eligibility nor a Green category is present, use the standard rate and identify the lack of green-eligibility evidence. Do not assume gift cards, cash equivalents, mixed carts lacking item-level evidence, or non-green-parent marketplace/delivery charges qualify.

## Calculator interface

Run the packaged script with one JSON object on stdin:

```sh
python3 scripts/audit_rewards.py <<'JSON'
{"transactions": []}
JSON
```

Input requires `transactions`, a list of objects with `transaction_id`, `card_type`, `merchant_name`, `transaction_amount`, `category`, `status`, and `rewards_earned`. Amounts and awarded points may be numbers or strings such as `"12.34"`, `"$12.34"`, or `"30 points"`. Optional fields are `green_eligible` (boolean), `is_ev_charging` (boolean), and `certified_ev_networks` (list of strings).

Output is `{"reviews": [...], "summary": {...}, "errors": [...]}`. Reviewable entries contain expected, awarded, difference, rate, eligibility basis, and discrepancy. A positive `difference_points` means apparent under-award. Nonreviewable entries include a reason. Errors require corrected source data, not a rewards conclusion.
