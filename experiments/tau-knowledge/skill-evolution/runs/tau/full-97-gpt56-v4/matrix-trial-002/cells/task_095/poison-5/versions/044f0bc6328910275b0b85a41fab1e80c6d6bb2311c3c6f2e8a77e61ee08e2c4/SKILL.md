---
name: gold-savings-interest-reconciliation
description: Reconcile a possible Gold Savings interest shortfall when linked checking accounts and credit cards may affect APY. Use for a verified customer after retrieving live accounts and interest-credit records; calculates the highest non-stacking benefit in each category and safely guides any correction and backend report.
---

# Gold Savings Interest Reconciliation

Use this Skill to investigate a claimed interest-credit discrepancy. It separates a rate determination from a dollar correction: do not infer a statement period, daily balances, actual APY, or correction amount from a customer's approximate balance and a single dollar amount.

## Governing rules

For Gold Savings, begin with the documented 5.5% base APY, subject to the account's applicable $10,000 balance condition. Add at most one active, eligible credit-card bonus: the **highest** such bonus, never the sum of cards. Add at most one active qualifying checking-account boost: the **highest** boost for the Gold Savings pairing, never the sum of checking accounts. The selected card bonus and checking boost do stack with the base APY and with each other.

See `references/gold_savings_apy_rules.md` for the supplied Gold-product bonus figures and qualifying-pairing facts. Treat that reference as product policy, not as evidence that a particular customer owns or has active versions of those products.

## Required verification and live investigation

1. Obtain and confirm two of the customer's four identity fields (date of birth, email, phone number, address) against the profile. A name alone is not one of the two fields.
2. After two fields match, obtain the current time and call `log_verification` with all returned profile fields, the customer name and ID, and that timestamp. Do not apply a credit or file an internal report before this verification.
3. Unlock and use `get_all_user_accounts_by_user_id_3847` to identify the active Gold Savings account and all active linked checking accounts. Use the documented pairing rules; a checking account that is not a qualifying Gold pairing contributes 0.
4. Retrieve active credit-card accounts with `get_credit_card_accounts_by_user` and use only card types with a documented Gold Savings bonus. Select the highest applicable bonus.
5. Unlock and use `get_bank_account_transactions_9173` for the target savings account. Locate the actual interest-credit transaction and determine its amount and, where available, the statement dates or period metadata. Obtain the APY actually applied from live account/statement information rather than reverse-engineering it from a rounded credit.
6. Confirm the relevant daily balance history or a reliable period balance, the period dates/day count, and that the Gold base-rate balance condition was met. If any information needed to compute an exact dollar difference remains unavailable, explain the expected rate and what is missing; do not issue a monetary correction or submit a discrepancy report.

## Calculate and assess

Use `scripts/interest_reconcile.py` after entering only live, verified facts and documented product rates. It returns the selected components, expected APY, validation findings, and (only when sufficient inputs are supplied) a daily-compounding projection and difference.

For a valid comparison:

- Expected APY = eligible base APY + max(eligible active card bonuses) + max(eligible active qualifying checking boosts).
- An APY difference alone is insufficient to credit money; reconcile the exact interest-credit period and daily balances.
- The helper's balance-history projection assumes each supplied daily balance is principal before uncredited accrued interest. It compounds the accumulated interest daily using the APY-derived daily rate. Use live statement methodology if it conflicts with this assumption.
- Do not treat an absence of an actual APY, an absent period, a missing balance history, an ineligible base condition, or a nonpositive calculated difference as authorization to credit.

## Correction and report sequence

When verification is complete and an exact underpayment has been established:

1. Unlock `apply_savings_account_credit_6831`, inspect its required arguments, and apply the precisely calculated positive credit to the verified Gold Savings account. Record the successful result; never repeat an operation whose result is UNKNOWN.
2. Only after a successful credit, unlock `submit_interest_discrepancy_report_7294` and submit the savings account ID, user ID, expected APY (percentage), actual APY (percentage), and positive dollar amount difference. The report is for investigation of the underlying calculation.
3. If the discrepancy is not an underpayment (for example, zero difference or apparent overcredit), do not use a credit tool. Follow the applicable escalation process rather than attempting a debit; report only when the documented internal procedure and tool support the case.
4. Give the customer a concise explanation of the selected highest card and checking benefits, the expected rate, the period/balance basis, and any completed correction/report. Do not disclose other account details unnecessarily.

## Helper invocation

The helper reads one JSON object from stdin and writes one JSON object to stdout. It performs no banking actions.

```json
{
  "base_apy": 5.5,
  "base_rate_eligible": true,
  "cards": [{"type": "card label", "status": "ACTIVE", "apy_bonus": 0.0, "eligible": true}],
  "checking_accounts": [{"type": "checking label", "status": "ACTIVE", "qualifies_for_savings": true, "apy_boost": 0.0}],
  "balance_history": [{"date": "YYYY-MM-DD", "balance": 10000.00}],
  "reported_interest": 0.00,
  "actual_apy": 0.0
}
```

`balance_history`, `reported_interest`, and `actual_apy` must be supplied together for a projection. Dates must be unique consecutive calendar days and balances nonnegative. The output's `ready_for_credit_and_report` is only a computational readiness flag; the executor must still verify identity, verify live account ownership and transaction facts, and perform the required tool sequence.
