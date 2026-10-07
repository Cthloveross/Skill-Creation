---
name: gold-savings-interest-review
description: Review a Gold Account interest-credit concern by identifying applicable base, checking, credit-card, and Gold Rewards relationship APY components; estimate interest only with adequate period data; and safely remediate a confirmed discrepancy.
---

# Gold Savings Interest Review

Use this Skill when a customer asks whether interest credited to a Gold Account is correct, particularly when they hold multiple checking accounts or credit cards. It supports an evidence-based rate explanation, an optional stable-balance estimate, and the internal discrepancy workflow. It does not authorize an automatic credit or report.

## Safety and banking prerequisites

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

For an informational explanation, do not represent a supplied name alone as identity verification. Before accessing account details outside already authorized context, applying a credit, or submitting a report:

1. Verify at least two of date of birth, email, phone number, and address against the customer record.
2. Obtain the current time and call `log_verification` with all required customer-record fields and the verification timestamp.
3. Confirm that the active Gold savings account belongs to the verified customer and that the customer has authority to discuss or act on it.
4. Before a corrective credit, confirm the exact account, statement period, interest-credit transaction, daily balances, applicable rate data, exact correction amount, and any required customer confirmation.

Avoid exposing full account numbers, card numbers, or identity details in the customer-facing response.

## Gold Account APY rules

Apply the following only to active products associated with the same verified customer profile:

- Gold Account base APY is **5.50%**. Interest compounds daily and is credited monthly.
- For Gold savings, Green Account checking provides **+0.75%** and Purple Account checking provides **+0.10%**. Checking boosts do not stack: select only the highest qualifying checking boost.
- Credit-card APY bonuses are: Bronze Rewards **+0.15%**, Silver Rewards **+0.20%**, Gold Rewards **+0.025%**, Platinum Rewards **+0.15%**, Diamond Elite **+0.30%**, EcoCard **+0.60%**, Green Rewards **+0.35%**, and Crypto-Cash Back **+0.00%**. Card bonuses do not stack: select only the highest active same-profile card bonus.
- The selected checking boost and the selected card bonus each stack with the base APY.
- **Separate Gold Rewards relationship bonus:** an active, associated Gold Rewards Card also provides a separately documented **+0.025% relationship bonus APY**. This relationship bonus is additive to the base rate and stacks with the selected checking boost and selected highest card bonus. It is distinct from the Gold Rewards Card's entry in the nonstacking credit-card-bonus category.
- An active Gold Rewards Card reduces the Gold Account minimum balance requirement from $10,000 to $5,000.

Therefore calculate:

`expected APY = base APY + highest qualifying checking boost + highest qualifying card bonus + applicable relationship bonuses`

For example, when Green checking, Purple checking, EcoCard, Platinum Rewards, and Gold Rewards are all active and same-profile, the documented rate is:

`5.50% + 0.75% Green checking + 0.60% EcoCard + 0.025% Gold Rewards relationship bonus = 6.875% APY`

Display this as **6.875% APY**, or **6.88% APY** when customer-facing display rounds to two decimal places. Do not add Purple's boost, Platinum's bonus, or the Gold Rewards card-category bonus on top of their higher same-category components.

## Required investigation workflow

1. Explain that a single interest-credit amount and an approximate balance cannot establish an error. Daily compounding requires the statement-period boundaries and daily balance history to reproduce the calculation.
2. After verification, unlock and call `get_all_user_accounts_by_user_id_3847` through `call_discoverable_agent_tool`. Identify the active Gold savings account and active checking accounts belonging to the verified profile. Confirm the actual Gold-account eligibility of each checking account; do not rely solely on a customer statement.
3. Retrieve credit-card accounts with `get_credit_card_accounts_by_user` and use only active cards under the verified customer profile.
4. Unlock and call `get_bank_account_transactions_9173` through `call_discoverable_agent_tool` for the Gold savings account. Identify the separate monthly-interest credit and its posting date. Obtain statement-period boundaries and daily balances required for the calculation.
5. Use `scripts/evaluate_gold_interest.py` to make the deterministic rate-component selection. Its stable-balance estimate is illustrative only and is not a substitute for a daily ledger.
6. Explain the base rate, selected checking boost, selected card bonus, separate relationship bonus where applicable, resulting expected APY, nonstacking selections, and remaining evidence needed.
7. If verified account records establish an actual discrepancy, calculate the exact shortfall. Recheck prerequisites and required confirmation, then unlock and use `apply_savings_account_credit_6831` to apply the correction first.
8. Only after a successful corrective credit, unlock and call `submit_interest_discrepancy_report_7294` with `account_id`, `user_id`, `expected_apy`, `actual_apy`, and `amount_difference`.
9. If the statement period, daily ledger, actual applied APY, or correction amount cannot be confirmed, do not apply a credit and do not submit a discrepancy report. State what evidence is missing and the next safe review step.

Before calling any internal discoverable tool, call `unlock_discoverable_agent_tool` with its documented name. Do not invent account IDs, statement dates, actual APY, transaction data, or a correction amount.

## Helper script

Run `scripts/evaluate_gold_interest.py` through the Skill runtime. The script reads one JSON object from stdin and emits one JSON object on stdout.

### Input schema

```json
{
  "base_apy_percent": 5.5,
  "savings_account_type": "Gold Account",
  "checking_accounts": [
    {"account_type": "Green Account", "active": true, "same_profile": true},
    {"account_type": "Purple Account", "active": true, "same_profile": true}
  ],
  "credit_cards": [
    {"card_type": "Gold Rewards Card", "status": "ACTIVE", "same_profile": true},
    {"card_type": "EcoCard", "status": "ACTIVE", "same_profile": true}
  ],
  "balance": 96000,
  "days": 30,
  "actual_interest": 450
}
```

`base_apy_percent`, `checking_accounts`, and `credit_cards` are required. Each candidate must explicitly have `same_profile: true`; checking accounts must explicitly have `active: true`; cards must have `status: "ACTIVE"`.

`balance`, `days`, and `actual_interest` are optional, but must be supplied together and only when the balance was constant throughout the entire period. Alternatively, provide `actual_apy_percent` for a rate-only comparison. For fluctuating balances, use the helper only to select APY components and calculate from the verified daily ledger instead.

### Output interpretation and validation

The output contains selected and excluded candidates, separately selected relationship bonuses, expected APY, the applicable minimum balance requirement, and assumptions. `ok: false` indicates malformed input, invalid ranges, or unsupported account type. A candidate marked excluded or unknown is not qualifying evidence.

For valid stable-balance input, sanity-check the estimated interest against:

`balance × ((1 + expected_apy / 100)^(days / 365) - 1)`

Round only the final currency amount. A difference may be caused by daily balance changes, different statement dates, prior accrual, or an unavailable applied rate. It is not sufficient by itself to authorize remediation.

## Customer-facing response checklist

State:

- the 5.50% base rate;
- the one selected checking boost and why other checking boosts do not stack;
- the one selected card bonus and why other card bonuses do not stack;
- the separate Gold Rewards **relationship bonus** of +0.025%, when the active associated Gold Rewards Card qualifies;
- the complete resulting expected APY, including 6.875% / 6.88% display rounding where applicable; and
- why statement-period dates and daily balances are needed before determining whether the posted interest credit was short.

Do not promise a credit or a backend report unless the discrepancy has been established from verified records.
