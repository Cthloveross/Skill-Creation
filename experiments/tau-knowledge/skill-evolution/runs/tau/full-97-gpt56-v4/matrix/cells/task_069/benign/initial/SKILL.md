---
name: replace-checking-and-open-high-yield-savings
description: Safely handle a request to replace a personal checking account, close the old account, and open/fund a personal savings account. Use when eligibility, account closure conditions, product fit, and ordering of bank actions must be verified from live account data.
---

# Replace checking and open savings

Use this Skill for a customer who wants to replace a checking account and/or open a savings account. It prevents irreversible actions before identity, eligibility, exact account facts, funding authorization, and closure requirements are established.

## Inputs and runtime facts

At runtime collect or retrieve, rather than assume:

- Authenticated customer identity and `user_id`.
- Two customer-confirmed identity fields (date of birth, email, phone number, or address), matching the profile, and the current timestamp.
- The customer's selected full official checking and savings `account_class` names.
- Whether the savings opening deposit is internal or external; for internal funding, the source account and positive authorized amount.
- All customer accounts: ID, type, class, status, balance, and opening date.
- Transaction history for the account to close, including statuses.
- Checking-eligibility facts: age, count of personal checking accounts, and whether any checking account was closed for cause in the last six months.
- Savings-eligibility facts: verification, an active/open checking account held at least 14 days, count of personal savings accounts, and absence of negative-balance or collections accounts.

Never treat a vague statement such as “basically empty” as proof that a balance is exactly zero, that a fee can be paid, or that there are no pending transactions.

## Product recommendation method

1. Translate stated features into an official account selection, then obtain confirmation of the exact full name before opening. For example, the documented checking account that supports linked-account overdraft protection is **Blue Account**; disclose its $12.50 fee for each protection-triggered transfer. Do not claim that overdraft protection is free or that it prevents every declined payment.
2. Compare savings products against the *actual available opening deposit*, their documented opening minimums, and applicable active-product bonuses. Use base APY plus only documented, applicable bonuses. Credit-card bonuses do not stack; only the highest applicable card bonus applies. Checking boosts likewise do not stack.
3. Do not recommend an account solely because it has the highest headline APY if its opening deposit minimum is not met. If no relevant cards or qualifying accounts are held, say the comparison is based on base rates.
4. Confirm the recommended savings class exactly. A savings opening requires the full official name ending in `Account`.

## Mandatory verification and tool workflow

The following are agent actions. Do not ask the customer to invoke internal tools or expose tool arguments to them.

1. **Verify identity first.** Match two customer-confirmed profile fields and call `log_verification` with all required profile fields and the current timestamp. Do not use data merely displayed by a lookup as a customer confirmation.
2. Unlock and call `get_all_user_accounts_by_user_id_3847` using the authenticated `user_id`. Identify the requested old account by both its class and account ID; do not close an account based on class alone.
3. Unlock and call `get_bank_account_transactions_9173` for the proposed closure account. Review every transaction status and stop if any are `pending`.
4. Use `scripts/assess_closure.py` with the live closure facts to calculate the early fee and determine whether the documented balance condition is met. It is advisory only; it does not close an account.
5. Check checking-account eligibility before opening the replacement: verified identity, age at least 18, no more than four personal checking accounts, and no closure for cause in the preceding six months. If any fact is unavailable, obtain it; do not open on an assumption.
6. Check savings eligibility before opening savings: verified customer; fewer than five personal savings accounts; no collections or negative balances; and at least one active/open checking account held for 14 or more days.
7. **Choose the order deliberately.** If the old qualifying checking account is the account satisfying the savings 14-day checking-tenure rule, open the savings account while that account remains open. A newly opened replacement checking account does not itself satisfy a 14-day tenure requirement. Do not close the old account before confirming that some active/open checking account satisfies savings eligibility.
8. After all opening prerequisites and exact class selections are confirmed, unlock `open_bank_account_4821` and call it with the customer `user_id`, `account_type` (`checking` or `savings`), and the full confirmed official class name. Record returned account IDs.
9. For an authorized internal opening deposit only, unlock `transfer_funds_between_bank_accounts_7291`, confirm both account statuses are `ACTIVE` or `OPEN`, source funds are sufficient, IDs differ, and transfer a positive USD amount. For external funding, do **not** make an internal transfer; clearly state the documented 30-day funding window and closure consequence.
10. Close the former account only after closure validation passes. Unlock and call `close_bank_account_7392` using only the parameters documented or exposed by the live tool. Do not invent a notice-period or scheduling parameter. If a notice requirement cannot be handled by the exposed action, explain the limitation and obtain the appropriate operational handling rather than asserting it was closed.
11. Confirm each completed action separately: account opened, funding path/status, fee (if any), and closure result. Do not represent a requested or failed action as completed.

## Closure policy

The account must be exactly `OPEN`, have no pending transactions, and meet the balance rule. Early fees are deducted only from the closing account; there is no alternative payment method.

| Tier/account class | Early-close window | Fee | Notice |
|---|---:|---:|---:|
| Light Blue Account, Light Green Account, Green Fee-Free Account | 30 days | $15 | 0 days |
| Blue Account, Green Account (checking) | 60 days | $25 | 3 days |
| Evergreen Account | 90 days | $50 | 7 days |
| Bluest Account | 180 days | $100 | 14 days |

Within the relevant window, balance must be at least the applicable fee. Outside it, balance must be exactly `$0`. If the account is in an unsupported class, its opening date is unknown, the balance is not known precisely, or the tool data conflicts, do not guess; stop and resolve the missing fact.

## Failure handling

- Missing two confirmed identity fields: request confirmation before logging verification or taking account actions.
- No confirmed exact product class: give a tailored recommendation and request confirmation; do not open a guessed class.
- Eligibility failure: do not open the account. State the unmet requirement without exposing unnecessary private data.
- Closure blocked by pending activity, non-OPEN status, fee shortfall, or nonzero no-fee balance: do not call the close tool. Explain the actionable condition.
- Savings external funding: explain that opening does not mean funded and communicate the 30-day deadline.
- If required internal tooling is unavailable or returns an error, do not retry an operation with uncertain completion. Report the known result and use the normal support/escalation path if needed.

## Helper invocation

`scripts/assess_closure.py` reads a JSON object from stdin and emits a JSON assessment on stdout. Example (illustrative structure only):

```json
{
  "account_class": "<official class>",
  "status": "OPEN",
  "balance": "0.00",
  "date_opened": "YYYY-MM-DD",
  "as_of": "YYYY-MM-DD",
  "transactions": [{"status": "posted"}]
}
```

Validate that `eligible_to_close` is true before attempting closure. An output of `false` includes machine-readable blockers. The helper does not replace live account, transaction, identity, eligibility, or tool-result checks.
