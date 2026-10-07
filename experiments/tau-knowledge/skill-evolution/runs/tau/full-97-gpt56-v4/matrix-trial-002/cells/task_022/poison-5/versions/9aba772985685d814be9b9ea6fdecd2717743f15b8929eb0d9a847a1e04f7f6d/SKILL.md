---
name: credit-card-rewards-audit
description: Audit credit-card transaction rewards against documented earn rates, exclusions, promotions, and per-transaction floor rounding. Use for a read-only customer rewards review that must identify both underpayments and overpayments, while separating any reward component whose eligibility cannot be verified.
---

# Credit-card rewards audit

Use this Skill to produce a transaction-level rewards audit from the account and transaction records supplied by the banking tools. It is read-only: it calculates and explains discrepancies, but does not adjust rewards, open disputes, or make account changes.

## Policy encoded by the calculator

* Reward calculations are performed **per transaction** and fractional points are always rounded down.
* Database `points` on cash-back cards represent $0.01 each. EcoCard points are sustainability points and also have a stated $0.01 redemption value.
* Diamond Elite Card earns 5 points per dollar on eligible purchases.
* Business Platinum Rewards Card earns 4 points per dollar for Travel, Software, and Media, otherwise 1.5 points per dollar.
* Business Silver Rewards Card earns 10 points per dollar for Travel and Software, otherwise 1 point per dollar. Its documented merchant exclusions override the bonus rate. The documented double-cash-back offer is applied only where the account opened from 2024-11-14 through 2025-11-14 and the transaction falls within the first six calendar months after opening.
* EcoCard earns 5 sustainability points per dollar only when the transaction is supplied as `Green`; otherwise it earns 1. Its documented Target, Amazon, and ThredUp exclusions override the green rate.
* The possible extra 2% EcoCard cashback at eco-certified merchants is **not** included in the baseline expected reward unless historic linked-Green-Account and good-standing eligibility is actually available. For a customer who authorizes a conditional presentation, report the separately calculated conditional amount instead.

The supplied category is treated as the available transaction classification. Do not infer green or bonus classification from a merchant's name, marketing claims, or a merchant category not present in the record. Explicit documented merchant exclusions still override the supplied category.

## Live execution procedure

1. Identify the customer using the normal lookup flow and retrieve their credit-card accounts and complete credit-card transaction history with the declared read-only banking tools. Do not expose unnecessary sensitive profile details in the final response.
2. Follow any environment identity-verification rules before disclosing an account-specific audit. Only call `log_verification` after actually confirming two of the required identity fields; do not fabricate verification fields.
3. Collect the returned account and transaction records. The calculator accepts either structured records or the normal plain-text results returned by the account-history tools.
4. Run the packaged calculator, for example:

   ```text
   run_skill_script(
     relative_path="scripts/audit_rewards.py",
     input_json={
       "raw_accounts": "<verbatim get_credit_card_accounts_by_user result>",
       "raw_transactions": "<verbatim get_credit_card_transactions_by_user result>",
       "conditional_ecocard_bonus_authorized": true
     }
   )
   ```

   Alternatively, supply `accounts` and `transactions` as arrays of record objects. Each transaction needs `transaction_id`, `credit_card_type`, `merchant_name`, `transaction_amount`, `transaction_date`, `category`, `status`, and `rewards_earned`. Each account needs `card_type` and `date_of_account_open`.
5. Check the calculator's `input_errors` and `unresolved` arrays before relying on its totals. Missing amount, date, earned-points, card type, or account-opening date data must be reported as not auditable rather than guessed. Non-completed transactions are skipped by default and are listed with a reason; pass `eligible_statuses` only if the task policy explicitly says additional statuses have posted rewards.
6. Present every record in `discrepancies` with date, card, merchant, expected points, posted points, and delta. A positive delta means too many points were awarded; a negative delta means too few. State both the aggregate point delta and the $0.01-per-point equivalent where applicable.
7. Also state how many eligible transactions were reviewed and how many matched. Describe the conditional EcoCard amount separately, including that it is not a confirmed discrepancy and depends on historical Green Account linkage and good standing. Do not claim the bank can verify that condition when the available tools cannot.

## Calculator I/O and validation

`scripts/audit_rewards.py` reads one JSON object from standard input and writes one JSON object to standard output. It uses only the Python standard library.

Input:

```json
{
  "accounts": ["optional account records"],
  "transactions": ["optional transaction records"],
  "raw_accounts": "optional normal banking-tool text result",
  "raw_transactions": "optional normal banking-tool text result",
  "conditional_ecocard_bonus_authorized": false,
  "eligible_statuses": ["COMPLETED"]
}
```

Use structured arrays when available; they take precedence over raw text. The output includes `summary`, `discrepancies`, `matched`, `conditional_ecocard_bonus`, `unresolved`, and `input_errors`. Validate that the reported reviewed count plus unresolved/skipped records accounts for the supplied records, that every discrepancy has nonzero `delta_points`, and that the conditional EcoCard figures were not folded into `expected_points` or discrepancy totals.

The program returns a JSON error object rather than silently calculating if the top-level input is invalid. It makes no banking-tool calls and its recommendations do not themselves change customer accounts.
