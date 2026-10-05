---
name: credit-card-reward-discrepancy-review
description: Verify a credit-card customer, review documented reward rates for posted transactions, report every supported reward mismatch including both shortages and overages, provide customer-executable dispute actions when appropriate, and apply corrections only after an approved resolved dispute.
---

# Credit-Card Reward Discrepancy Review

Use this Skill when a customer asks to investigate incorrect credit-card cash back or rewards.

## Supported reward policies

- **Crypto-Cash Back:** 2.0% on eligible purchases.
- **Business Platinum Rewards Card:** 4.0% on posted Travel, Software, and Media purchases; 1.5% on other purchases. Cash equivalents, balance transfers, and fees earn no rewards.
- **Silver Rewards Card:** 4.0% on posted Travel and Software purchases. Do not infer a rate for other categories without an authoritative policy.
- **EcoCard:** 5 points per dollar on qualifying green purchases and 1 point per dollar otherwise. Target, Walmart, Amazon, and ThredUp receive the standard rate. EV charging earns 5 points per dollar only at Tesla Supercharger, ChargePoint, or EVgo.

Transaction reward values stored as `points` have a cash-equivalent value of $0.01 per point. The calculation convention used by this Skill is whole-point truncation: `floor(amount × points-per-dollar)`.

## Banking controls and prerequisites

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Treat transaction retrieval, rewards review, disputes, and adjustments as banking work.

1. Confirm that the requester is the customer or an authorized representative. Before exposing nonpublic card or transaction information, verify two of date of birth, email, phone number, and address against the customer record.
2. After successful verification, obtain the current time and call `log_verification` with the verified customer record and timestamp. Do not retrieve accounts or transactions first.
3. Retrieve accounts and transaction history only for the verified user. Confirm each reviewed transaction belongs to that user and its card type is among that user's accounts.
4. Confirm product eligibility and that each reviewed transaction is posted/completed, positive, and not a return or credit. Rewards are calculated from net purchases after returns and credits. Available credit, transfer recipients, payment fees, and cutoffs are normally inapplicable to a read-only review; state that they were not operative rather than treating them as checked transaction facts.
5. Do not make an agent-side adjustment simply because a calculation differs. A correction additionally requires a located resolved and approved dispute, authority to correct it, independent recalculation, and confirmation after the update.

If identity, authority, ownership, status, or necessary policy facts cannot be established, do not disclose details or submit/update anything. Explain the missing prerequisite and use normal support escalation where needed.

## Review workflow

1. Establish the review scope with the customer. If rate coverage is absent, label the transaction **not reviewable**; do not invent a rate. Unless authoritative Silver terms are supplied, only review Silver Travel and Software transactions.
2. Retrieve all in-scope posted transactions and invoke `scripts/review_rewards.py` with the JSON schema below.
3. Reconcile the output: every in-scope input row must appear exactly once; no `invalid` output may be used as a reward finding; expected points must be whole numbers; and output counts must total the input rows.
4. Compare expected and recorded rewards in **both directions**. Report **every** supported row where `expected_points != actual_points`; never describe an over-earned transaction as a match or omit it from the review.
5. For each mismatch, tell the customer the transaction ID, merchant, date, amount, posted category, recorded points, expected points, point difference, and dollar equivalent of the difference. A positive difference means under-earned; a negative difference means over-earned. Preserve calculation assumptions and reasons in internal case notes.
6. Explain unsupported, unresolved, returned, pending, or out-of-scope rows separately. Do not characterize them as confirmed errors.

For an overage, disclose that the recorded value exceeds the documented calculation and route it to the appropriate rewards/support review path. Do not automatically reverse rewards, create an agent adjustment, or frame the overage as a customer cash-back-underpayment dispute. For under-earnings the customer elects to challenge, provide the customer dispute action described below.

### Script interface

Run:

```sh
python3 scripts/review_rewards.py < review-input.json
```

The script reads one JSON object from stdin and emits one JSON object to stdout. It uses only the Python standard library and makes no banking-tool calls.

Input schema:

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "string",
      "merchant_name": "string",
      "transaction_amount": "USD amount or number",
      "transaction_date": "optional date",
      "category": "optional posted category",
      "status": "COMPLETED or POSTED",
      "rewards_earned": "whole points or X points",
      "is_return_or_credit": false,
      "is_cash_equivalent": false,
      "is_balance_transfer": false,
      "is_fee": false,
      "is_ev_charging": false,
      "green_eligible": true,
      "merchant_of_record_confirmed": true
    }
  ],
  "scope": {
    "include_card_types": ["optional card types"],
    "whole_point_rounding": "floor"
  }
}
```

`transactions` is required. `include_card_types` limits the review when supplied. The only supported rounding mode is `floor` (and is the default). The output contains `findings`, per-disposition counts, `reward_mismatches`, and assumptions. Findings use:

- `under_earned`: expected points exceed recorded points.
- `over_earned`: recorded points exceed expected points.
- `matches`: recorded and expected points agree.
- `not_reviewable`: a row is outside scope, not final, returned/credited, excluded, or lacks documented rate coverage.
- `unresolved`: available facts do not establish a required eligibility fact.
- `invalid`: required data is malformed or absent.

## Interpretation rules

- The posted category governs Business Platinum and Silver bonus-category calculations; do not award a bonus solely from a merchant name.
- Business Platinum Media includes media advertising when posted as Media. Travel, Software, and Media receive 4 points per dollar, while other documented purchase categories receive 1.5 points per dollar.
- Silver non-Travel/non-Software rows are not reviewable under this Skill. Gift cards, person-to-person payments, fees, interest, insurance premiums, returns, and refunds do not receive the documented 4% bonus.
- For EcoCard, a Green/Sustainable posted category or established green eligibility supports 5 points per dollar except the named merchant exclusions and nonpartner EV charging. If known merchant-of-record facts conflict with claimed green eligibility, return `unresolved`.
- The analyzer cannot establish unknown promotions, item-level green qualification, merchant-category corrections, or an unknown product's rate. Escalate those questions for review rather than fabricating an expected amount.

## Customer-initiated under-earning disputes

For each supported `under_earned` transaction the customer chooses to challenge, reconfirm the exact transaction ID and provide the customer this tool:

`submit_cash_back_dispute_0589(user_id: str, transaction_id: str)`

Use `give_discoverable_user_tool` with discoverable tool name `submit_cash_back_dispute_0589` and a JSON `arguments` string containing the verified customer's own `user_id` and the exact selected `transaction_id`. The customer, not the agent, executes it. Do not supply sensitive card details, submit automatically, or claim approval. Receipts, category context, and promotion evidence may be requested during review.

## Approved internal corrections only

Only after a cash-back dispute is resolved and approved:

1. Locate the resolved dispute record and identify the exact transaction IDs requiring correction. Never use an `expected_rewards` field from that record as the calculation source.
2. Re-verify identity, authority, ownership, card/product eligibility, transaction status, resolved approval, and correction authority.
3. Independently recalculate from the documented policy and established facts, retaining calculation notes.
4. Unlock `update_transaction_rewards_3847` with `unlock_discoverable_agent_tool`.
5. Call it through `call_discoverable_agent_tool` using the exact `transaction_id` and `new_rewards_earned` formatted exactly as `"X points"`. Supply the corrected total, not a point delta.
6. Retrieve transaction history again, verify the resulting reward value, and retain the confirmation in the internal case record.

If resolved-dispute records, approval, authority, the update tool, or post-update confirmation are unavailable, do not update. Escalate through the authorized internal process instead.
