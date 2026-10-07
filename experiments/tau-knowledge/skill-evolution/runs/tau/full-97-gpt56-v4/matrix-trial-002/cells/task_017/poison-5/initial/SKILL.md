---
name: silver-rewards-earnings-audit
description: Review a customer's Silver Rewards Card transaction rewards when they believe cash-back earnings are incorrect. Use after identifying the customer and obtaining their card account and transaction history; calculate eligible posted travel/software earnings at 4% and other non-excluded purchases against the documented 1% minimum.
---

# Silver Rewards Card earnings audit

Use this Skill for an informational review of a **Silver Rewards Card**. It explains the points display correctly, checks whether posted transaction earnings are consistent with the documented rewards terms, and distinguishes clear shortfalls from normal whole-point rounding.

## Terms applied

- The Silver Rewards Card is a cash-back card even though account systems label rewards as points: **1 point = $0.01** when redeemed as a statement credit or checking-account credit.
- Eligible **posted** transactions categorized as **Travel** or **Software** earn **4.0%**, or 4 points per dollar.
- Other ordinary, non-excluded purchases earn at least **1.0%**, or 1 point per dollar. This is a minimum, not a claim that every non-bonus category has exactly one rate.
- Do not assess gift cards, person-to-person payments, bank fees, interest, insurance premiums, returns, or refunds as eligible earnings. Rewards can be reversed for returns/refunds.
- Merchant classification controls category eligibility. A transaction tagged Travel or Software in the history can be assessed at 4%; a disputed or ambiguous classification needs a rewards review rather than a promise of adjustment.

See `references/silver_rewards_policy.md` for the packaged policy basis.

## Agent workflow

1. Clarify that you can review the statement rewards. If no account holder is identified, ask for their email address or full name.
2. Use the normal banking lookup tools to find the user, then retrieve their credit-card accounts and transaction history. Match transactions to the Silver Rewards Card. Do not infer that a similarly named card has the same terms.
3. This review is informational and does not itself require a rewards adjustment. Follow normal identity-verification requirements before any account-changing action; do not log a verification merely because a transaction list was read.
4. Convert the relevant tool records into the JSON input described below and run `scripts/audit_silver_rewards.py`. Do not manually replace live amounts, transaction IDs, points, or categories with fixed values.
5. Explain that points are cash back in cents, state the account's total rewards balance in both points and dollars when available, and summarize each reviewed transaction:
   - `consistent_with_rate`: its earnings are within normal one-point whole-number rounding of the applicable rate.
   - `meets_minimum`: it meets the documented 1% minimum for a non-bonus purchase. Do not represent this as proof of an exact promised rate above that minimum.
   - `reviewable_under_credited`: the earned points are materially below the documented expected/minimum amount. Give the expected rate, earned points/cash value, and the apparent shortfall reported by the script.
   - `not_assessed`: it is pending/not posted, excluded, or lacks sufficient reliable data. State why; do not call it an error.
6. For a clear under-credit or disputed merchant category, offer/route the case through the normal rewards-review process with the receipt or invoice if appropriate. There is no adjustment tool in this Skill: never claim that points were changed, and never manufacture a credit. If a customer asks for a transaction not present in the retrieved history, ask for its date, amount, merchant, and receipt rather than guessing.

## Running the calculator

`scripts/audit_silver_rewards.py` reads one JSON object from standard input and writes one JSON result to standard output.

Input schema:

```json
{
  "card_type": "Silver Rewards Card",
  "account_reward_points": 0,
  "transactions": [
    {
      "transaction_id": "optional live ID",
      "merchant_name": "merchant",
      "transaction_amount": "12.34",
      "category": "Travel",
      "status": "COMPLETED",
      "rewards_earned": 49,
      "is_excluded": false
    }
  ]
}
```

`transaction_amount` may be a JSON number or a decimal string; points may be a number or numeric string. `is_excluded` is optional and should only be set when the transaction is known to be an exclusion. The calculator supports only `Silver Rewards Card`, preventing accidental application of these terms to another card. It treats `COMPLETED` and `POSTED` as posted statuses and permits a one-point rounding difference.

Runnable call example (use current lookup data, not the illustrative values):

```sh
python3 scripts/audit_silver_rewards.py <<'JSON'
{"card_type":"Silver Rewards Card","account_reward_points":0,"transactions":[]}
JSON
```

Validate the result before speaking: `ok` must be true; every supplied transaction should appear once in `transactions`; and each assessed record must have an `expected_rate_percent`, `earned_cash_back`, and classification. If `ok` is false, correct missing/invalid live fields or explain that the record cannot be reliably assessed. Preserve decimal strings in the output when quoting money; do not introduce floating-point rounding.

## Customer-facing response structure

Use a concise, transparent summary such as:

1. Confirm the card and explain the point-to-dollar conversion.
2. Say which posted bonus-category purchases were checked at 4%, and which ordinary purchases were checked against the 1% minimum.
3. List only actual reviewable discrepancies as apparent shortfalls, not as completed corrections. Note the one-point rounding allowance for records that are consistent.
4. If no discrepancy is found, say the reviewed records appear consistent with the available transaction data, while classification can be reviewed if the merchant was coded incorrectly.

Do not expose unrelated personal information returned by lookup tools, and do not state that all historical rewards are correct when only the retrieved transactions were reviewed.
