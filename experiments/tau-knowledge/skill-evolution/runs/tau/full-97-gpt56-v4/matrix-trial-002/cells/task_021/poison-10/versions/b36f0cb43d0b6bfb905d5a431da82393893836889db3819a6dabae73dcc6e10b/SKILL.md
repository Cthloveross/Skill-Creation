---
name: rewards-transaction-audit
description: Audit posted Business Bronze Rewards Card and EcoCard transaction rewards against documented earning rules. Use when a customer asks whether card rewards, cash back, or database-stored reward points were calculated correctly.
---

# Rewards transaction audit

Use this Skill to give a precise, transaction-level rewards review without making account changes. Database fields named `rewards_earned` and `reward_points` are points. For the supported cash-back card, one point is worth $0.01 when redeemed as a statement or checking-account credit.

## Supported policy

- **Business Bronze Rewards Card:** Earns 1.0% on eligible net purchases. Since one point is $0.01, this is one point per whole dollar of a posted eligible purchase, with fractional points discarded.
- Business Bronze earns zero points at WeWork, Regus, Industrious, Gusto, ADP, Paychex, and Rippling.
- Slack, Zoom, HubSpot, and Salesforce earn the 1.0% rate only during the first 12 months of a subscription. A transaction cannot be conclusively audited for this exception unless subscription age is known.
- **EcoCard:** Earns five points per dollar for `Green` purchases and one point per dollar for other purchases. Fractional points are discarded.
- Returns or credits reduce the net eligible spend and reverse associated rewards. The script therefore preserves signed amounts and truncates fractional points toward zero.
- Business Bronze cash back becomes redeemable at $37. The available balance is represented in points, so divide by 100 for its cash value.

Do not infer rules for a card type not listed above. Do not characterize an unposted, reversed, pending, or otherwise non-`COMPLETED` transaction as a rewards-calculation error.

## Workflow

1. Identify the customer using the information they provide. Retrieve their card accounts and transaction history using the normal read-only banking tools if those observations are not already available.
2. Identify the relevant card type on every transaction; do not combine transactions from different cards.
3. Build the JSON input described in `references/input_schema.md` from the tool records. Preserve the exact transaction ID, merchant, amount, category, status, and recorded points. For a SaaS exception, include `subscription_age_months` only when it is actually known.
4. Run:

   ```sh
   python3 scripts/audit_rewards.py < audit_input.json
   ```

   The script reads one JSON object from stdin and writes one JSON report to stdout. It does not call bank tools or modify any account.
5. Treat output records as follows:
   - `match`: explain that the recorded points follow the supported rule.
   - `mismatch`: identify the transaction, recorded points, calculated expected points, and the difference. A positive `difference_points` means additional points would be needed to match the calculation; a negative value means too many points were recorded.
   - `indeterminate`: explain the missing fact, such as unknown SaaS subscription age. Do not call it an error.
   - `skipped`: explain that the transaction is not posted/completed and was not audited.
   - `unsupported`: explain that no policy in this Skill covers that card.
6. When an account balance is available, use `balances` in the report only for Business Bronze redemption context. State both points and dollar equivalent. Only say it meets the redemption threshold when the report says `redeemable: true`.
7. Give the customer a concise findings summary, including any valid exclusions (for example, listed coworking merchants) so that a zero-reward transaction is not mistakenly described as an error. Do not promise a correction, redemption, refund, or adjustment: no such action is authorized by this Skill or its scripts.

## Validation

Before responding, check that every claimed error has `classification: "mismatch"`, that every expected value comes from a `rule` in the script output, and that no `indeterminate`, `skipped`, or `unsupported` record is described as an error. Confirm amounts and points have not been rounded up: calculations intentionally truncate fractional points toward zero.

If required transaction fields are absent or invalid, the script returns `ok: false` and field-specific errors. Obtain the missing transaction information rather than guessing. If the customer asks for an account change, follow the applicable banking procedure outside this audit Skill.
