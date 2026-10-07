---
name: credit-card-rewards-discrepancy
version: 1.3.0
description: Handle a suspected credit-card cash-back or rewards discrepancy, including Gold Rewards and EcoCard calculations when the provided terms establish a rate; guide the customer through the required per-transaction dispute submission and safely process only resolved, approved corrections.
---

# Credit-card rewards discrepancy handling

Use this Skill when a customer believes any credit-card transaction has incorrect rewards. The customer-directed cash-back-dispute process applies to all credit-card transactions. The supplied earning-rate evidence supports calculations for Gold Rewards Card and EcoCard only; for another card, identify and submit the transaction but do not estimate a rate without its applicable terms. Do not ask for a card number, CVV, or other card credentials.

## Privacy and access

Use a name or email only to locate a candidate user record for comparison; do not disclose anything from that record yet. Before accessing or disclosing customer-specific accounts, transactions, disputes, or a user ID, verify the customer under the runtime policy. Match two of date of birth, email, phone number, and address to one candidate record; obtain the current time and call `log_verification` with the complete returned record and timestamp. If two fields cannot be confirmed, explain that account review must wait.

After verification, obtain the user's accounts and transaction history as needed. Share only enough recent transaction context (merchant, date, amount, card, rewards, and transaction ID) to let the verified customer select a purchase; do not reveal unrelated sensitive account data.

## Reward rules and review method

Transaction rewards are stored as points. For cash-back cards, **1 point = $0.01** when redeemed. A Gold Rewards Card earns **2.5 points per dollar (2.5% cash back) on all purchases**.

EcoCard earns **5 sustainability points per dollar** on a qualifying green purchase and **1 point per dollar** otherwise. A refund or return reverses rewards at the original rate. Use the transaction category and merchant evidence available in the record, receipt, or customer explanation to assess the rate:

* Green examples include public transportation, eligible EV charging, renewable-energy providers, certified sustainable retailers/products, bike share, and micromobility.
* Target, Walmart, Amazon, and ThredUp are always standard-rate EcoCard purchases, even for eco-friendly products.
* EV charging is high-rate only for Tesla Supercharger, ChargePoint, or EVgo. Treat an EV-charging merchant outside those named networks as standard-rate even if a generic category says Green.
* Marketplaces, mixed carts, gift cards/cash equivalents, and payments processed by a non-green parent may not qualify. Request receipt/seller-of-record or eligibility context where it would determine the rate; never claim a merchant is a certified partner merely from its name.

Calculate `amount × applicable points-per-dollar` independently; do not use an expected-rewards value from a dispute. The correction tool requires whole points, but the supplied terms do not specify rounding. Do not assume a rounding rule merely because a result has a decimal. Preserve the exact result for review and make a whole-point correction only when the applicable system/rate evidence establishes the treatment. The included helper can report exact values and apply a caller-supplied documented rounding rule.

A recorded value inconsistent with **both** EcoCard rates is still a valid review candidate even if green eligibility is unknown. A recorded standard-rate value for a potentially green purchase needs eligibility review before asserting the higher rate.

## Intake, identification, and customer-directed submission

1. Acknowledge the concern and ask for the statement period or affected transactions. If the customer cannot identify one, and is verified, review the available recent history and identify only transactions with a clear mismatch or a rate-dependent item needing evidence.
2. Explain the rate and calculation concisely. Confirm each exact `transaction_id` the customer wants reviewed. Do not alter rewards at this stage.
3. The customer, not the agent, must file each dispute. For **each selected transaction**, give the user the discoverable tool `submit_cash_back_dispute_0589` with JSON arguments containing that customer's `user_id` and that exact `transaction_id`:
   ```json
   {"user_id":"<verified user id>","transaction_id":"<confirmed transaction id>"}
   ```
   Tell the customer to run it once per transaction. If their UI does not accept prefilled arguments, repeat the exact tool name and instruct them to enter the same two values when prompted. Do not submit it yourself and do not substitute, guess, or reuse a transaction ID.
4. Tell the customer that supporting category, merchant, receipt, or promotion context may be requested during review. Lack of evidence is not a reason to fabricate eligibility; the customer can submit the review with available information.

## Correcting only resolved disputes

A filed, queued, open, or under-review dispute is **not** approval. Do not unlock or call an update tool for it.

Only after verification and an actual resolved/approved outcome:

1. Unlock and use `get_user_dispute_history_7291` with the verified `user_id`; inspect the returned dispute records and select only resolved/approved records that identify the affected transaction. Do not rely on a dispute's `expected_rewards` field.
2. Independently establish the transaction amount/status, card rule, applicable category/merchant eligibility, and a supported whole-point rounding treatment. If any is missing or ambiguous, do not update.
3. Unlock `update_transaction_rewards_3847`, then call it with the exact transaction ID and `new_rewards_earned` exactly formatted as `"X points"`, where `X` is the independently established whole number.
4. Re-query transaction history to confirm the updated reward value and retain the calculation basis in the authorized internal case record. If a tool error leaves completion unknown, do not repeat the update; investigate/escalate through available procedures.

## Local calculation helper

`scripts/audit_rewards.py` reads one JSON object from stdin and emits one JSON object on stdout. It performs no banking actions.

Input schema:
```json
{
  "rounding": "unresolved|floor|nearest|ceiling",
  "transactions": [{
    "transaction_id": "string",
    "card_type": "Gold Rewards Card|EcoCard",
    "amount": "decimal string or number",
    "status": "optional transaction status",
    "rewards_earned": "optional integer or 'N points'",
    "category": "optional category",
    "merchant_name": "optional merchant",
    "eco_green_eligible": "optional true/false"
  }]
}
```

`eco_green_eligible`, if supplied, takes precedence over a category indication except that a documented excluded merchant or nonpartner EV charger remains standard-rate. For EcoCard, a documented excluded merchant produces standard rate; the three named EV networks produce high rate; a `Green` category otherwise produces a `green_indicated` assessment, while an absent/other category produces a standard-rate assessment. Review its `eligibility_assessment` before using a calculation. With `rounding: "unresolved"`, the helper intentionally emits no whole-point correction. With a documented rounding mode it emits `expected_whole_points` and a comparison to recorded points. Validate that every desired transaction has a calculation status rather than `invalid_input` or `insufficient_rate_information`, and treat `needs_rounding_confirmation` as a stop for automatic correction; separately stop if the merchant/category evidence needed to apply a rate is ambiguous.

Example runtime call:
```sh
python3 scripts/audit_rewards.py <<'JSON'
{"rounding":"unresolved","transactions":[{"transaction_id":"example","card_type":"Gold Rewards Card","amount":"10.00","rewards_earned":"25 points"}]}
JSON
```
