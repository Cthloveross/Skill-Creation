---
name: credit-card-rewards-audit-and-dispute
version: 1.0.0
description: Audit posted credit-card transaction rewards against documented card/category rules, identify supportable discrepancies, and guide a verified account holder through cash-back dispute submission. Use for questions about potentially incorrect reward earnings; do not use it to change rewards before a dispute is resolved.
---

# Credit-card rewards audit and dispute

## Scope and safety

Use this Skill to review a customer's posted transactions and calculate expected whole-number rewards only where the supplied card terms establish a rate. Recorded rewards for cash-back cards are stored as points, where **1 point = $0.01** of cash back. EcoCard points also redeem at $0.01 per point.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For a rewards review or dispute, do not expose transaction/account details or provide a customer-specific submission tool until identity is verified. Confirm any two of date of birth, email, phone number, and address against the account record, then call `log_verification` with the complete returned identity record and a current timestamp. Confirm the customer is authorized for the located account(s). If verification or authority is not established, stop and request the required information; do not query or disclose account details.

Do not alter transaction rewards during an initial review. A suspected mismatch is not an approved correction.

## Runtime inputs and output

Run `scripts/audit_rewards.py` with JSON on stdin. It emits JSON on stdout.

Input schema:

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "Crypto-Cash Back | Business Platinum Rewards Card | Silver Rewards Card | EcoCard",
      "merchant_name": "string",
      "transaction_amount": "decimal number or currency string",
      "category": "string",
      "status": "COMPLETED",
      "rewards_earned": "integer or text ending in 'points'",
      "is_cash_equivalent": false,
      "is_balance_transfer": false,
      "is_fee": false
    }
  ],
  "rounding": "truncate"
}
```

The three boolean exclusion fields are optional and default to `false`. Set them from transaction evidence when available; excluded items earn zero and are not ordinary purchase discrepancies. `rounding` defaults to `truncate`, producing whole stored points by discarding a fractional point. Do not override this convention without product evidence.

Output includes every row's normalized amount, actual points, assessment status, applicable rule, expected points when determinable, and a `discrepancies` array. Rows are `not_assessed` if they are not completed, have unsupported/missing data, or use an unsupported card/rate. Treat `needs_review` as an evidence gap, not a confirmed error.

Example execution:

```sh
python3 scripts/audit_rewards.py < transactions.json
```

Validate that (1) each in-scope completed purchase appears once, (2) card type, posted category, merchant, amount, status, and recorded points agree with the statement, (3) expected points are whole nonnegative numbers, and (4) each discrepancy has a documented rate and exact transaction ID. Recheck merchant/category evidence for a disputed category before submitting.

## Documented rate rules implemented

- **Crypto-Cash Back:** 2.0% on eligible purchases, or 2 points per dollar.
- **Business Platinum Rewards Card:** 4.0% (4 points per dollar) for Travel, Software, and Media; 1.5% (1.5 points per dollar) for other purchases.
- **Silver Rewards Card:** 4.0% (4 points per dollar) for posted Travel and Software transactions. The available terms do not establish its non-bonus base rate, so other categories are not assessed.
- **EcoCard:** 5 points per dollar for qualifying Green/Sustainable purchases and 1 point per dollar otherwise. Target, Walmart, Amazon, and ThredUp receive 1 point per dollar even when green; EV charging qualifies at the higher rate only for Tesla Supercharger, ChargePoint, or EVgo. The script conservatively marks an EV charging claim outside these certified networks `needs_review` unless the posted category itself establishes Green/Sustainable eligibility.
- Cash equivalents, balance transfers, and fees earn zero under the available cash-back terms. Returns, refunds, or credits are not treated as positive earning purchases.

Rewards depend on the posted merchant category. Do not recategorize a transaction based only on what the customer bought or on a merchant name.

## End-to-end procedure

1. Obtain an account locator (name, email, or user ID) and locate the account using the ordinary banking tools.
2. Verify two identity fields, log verification, confirm authority/account ownership, and retrieve the customer's card accounts and transactions. Work only on accounts returned for that user.
3. Limit the audit to posted/completed purchase transactions. Capture the exact transaction ID, card type, merchant, amount, posted category, status, and recorded rewards.
4. Run the audit script and independently review its `needs_review` rows. Explain recorded points and expected points in both points and, for cash-back cards, dollars if helpful.
5. Present only supportable mismatches and any material unknowns. Ask the customer which specific transaction(s) they want disputed. Do not make a dispute decision or promise approval.
6. For each selected transaction, confirm the exact ID and give the customer the documented self-service tool using `give_discoverable_user_tool` with `discoverable_tool_name` set to `submit_cash_back_dispute_0589`. Tell them to use their own `user_id` and the selected `transaction_id`; provide no sensitive card details. Supporting receipts/category context may be requested in review.
7. Record the calculation rationale in the applicable case record if such a record is available. Do not submit an internal rewards update at this stage.

If the customer asks to dispute a transaction whose rate cannot be established, explain the uncertainty and they may still submit the dispute with their transaction ID and relevant receipt/category evidence.

## Resolved-dispute corrections only

Perform this section only after a dispute is demonstrably resolved and approved, the account holder/authority and all banking prerequisites above remain verified, and the case identifies the exact transaction(s). Look up resolved records in the `cash_back_disputes` database. Never rely on an `expected_rewards` field; recalculate using the rules above and applicable terms at the purchase date.

Then unlock `update_transaction_rewards_3847` using `unlock_discoverable_agent_tool`, and call it through `call_discoverable_agent_tool` once per approved transaction with JSON arguments containing the exact `transaction_id` and `new_rewards_earned` formatted exactly as `"X points"`, where `X` is the independently calculated whole number. Confirm the update in `credit_card_transaction_history` after the call and retain calculation notes in the internal case record. If the dispute is not approved, data/rates are insufficient, or confirmation fails, do not update; escalate through the normal support process.
