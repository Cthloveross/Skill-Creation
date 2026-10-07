# Audit input and output schema

`audit_rewards.py` accepts a JSON object on standard input.

## Input

```text
{
  "transactions": [transaction, ...],
  "accounts": [account, ...]             // optional
}
```

Each `transaction` must contain:

- `transaction_id` (string)
- `credit_card_type` (string)
- `merchant_name` (string)
- `transaction_amount` (number or a currency string such as `$12.34`)
- `category` (string; EcoCard green eligibility is `Green`, case-insensitive)
- `status` (string; only `COMPLETED` is audited)
- `rewards_earned` (integer number of recorded points)

Optional transaction field:

- `subscription_age_months` (nonnegative number): required to resolve the Business Bronze Slack/Zoom/HubSpot/Salesforce exception. Age greater than 12 means zero points; age 12 or less means the normal rate.

Each optional `account` may contain `card_type` and `reward_points` (integer). Only a Business Bronze account produces a redemption-context balance result.

All amounts are handled with `Decimal`; do not pre-round them. Positive and negative fractional point calculations are truncated toward zero.

## Output

On valid input, the script returns:

- `ok: true`
- `audits`: one result per supplied transaction, preserving its transaction ID
- `balances`: Business Bronze point/cash-value and threshold context for any supplied supported account
- `summary`: counts by audit classification

An audit result has `classification` of `match`, `mismatch`, `indeterminate`, `skipped`, or `unsupported`. Conclusive results include `expected_points`, `recorded_points`, `difference_points`, and a human-readable `rule`.

On malformed input, output has `ok: false` and an `errors` list. The process still emits JSON so callers can present or handle the problem safely.
