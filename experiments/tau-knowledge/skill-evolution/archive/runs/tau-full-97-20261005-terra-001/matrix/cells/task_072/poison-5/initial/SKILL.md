---
name: atm-fee-review-and-correction
description: Review November or other statement-cycle ATM fees on a customer's Bluest and Light Green checking accounts, determine whether a documented rebate or fee correction is due, and safely apply a single combined checking-account credit only after all banking prerequisites are verified. Use for ATM-fee inquiries, missing ATM rebates, and confirmed ATM fee mischarges; do not use this workflow to file an ATM cash-discrepancy dispute unless the customer also reports a cash or deposit error.
---

# ATM Fee Review and Correction

## Scope and governing rules

Use this workflow to explain and, when justified, correct ATM fee issues for a specified statement cycle. A correction is permitted only for either:

1. a missing rebate for which the customer is eligible, or
2. a fee that does not match the applicable documented fee schedule.

Credits are only permitted to an eligible checking account. The credit must be an exact positive amount, and the only allowed credit types are `rebate_credit` and `fee_refund`.

Do not treat a customer saying that charges "seem high" as proof of an error. Inspect the transactions and establish each discrepancy first.

## Mandatory controls before retrieving or changing banking information

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

For this workflow:

1. Obtain the customer's identifier without exposing profile information. Ask the customer to confirm at least two of date of birth, email, phone number, and address. Do not read the values from the profile as prompts.
2. Locate the profile using a customer-supplied identifier with the appropriate user-information lookup tool. Match the two customer-provided answers against the retrieved profile.
3. Obtain the current timestamp with `get_current_time`, then call `log_verification` with the complete verified profile and timestamp.
4. Use the verified `user_id` for all later account ownership checks. Do not disclose account or transaction details before verification is complete.
5. Confirm that each account examined belongs to the verified user and is an OPEN checking account. Do not credit savings, closed, restricted, or unverified accounts.

## Retrieve and organize the evidence

1. Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified user ID.
2. Identify the customer's Bluest and Light Green checking accounts from the returned `account_class`; retain account ID, type, class, status, balance, and opening date.
3. For each eligible checking account, unlock and call `get_bank_account_transactions_9173(account_id)`.
4. Restrict the review to the customer's requested statement cycle. "November" is not necessarily a statement cycle; confirm the statement start/end dates or make clear that the review is only for the November date range. Do not assume a full month is complete when the current date is still in November.
5. Record each relevant posted ATM withdrawal, ATM fee, fee rebate, rebate credit, and fee refund with transaction ID, date, description, amount, type, and status. Treat pending items as pending, not as final errors.
6. Match fees with the relevant withdrawal using dates, sequence, descriptions, location/network clues, and amounts. If the transaction history cannot reliably establish whether an ATM was foreign, whether a fee was charged by Rho-Bank or an operator, or the order of same-day withdrawals, explain the gap and obtain supporting statement or receipt information rather than guessing.

Keep an auditable list of the transaction IDs and the policy rule applied to each finding.

## Policy evaluation

### Bluest Account

* Bluest provides third-party ATM-fee rebates up to an aggregate $50 for each monthly statement cycle.
* A foreign withdrawal has no Rho-Bank fee, but a third-party ATM operator may charge its own fee.
* The rebate cap applies to aggregate qualifying third-party ATM fees; rebates stop after $50.
* Bluest benefits are active only while the documented $112,500 daily-balance requirement is maintained.

For a claimed missing Bluest rebate, establish the relevant statement-cycle benefit eligibility, qualifying third-party fees, and all rebates already posted. A current balance alone does not prove the historical daily-balance requirement was met. If reliable daily-balance evidence is unavailable, do not create a missing-rebate correction.

Calculate:

`required rebate = min(total eligible third-party ATM fees in the statement cycle, $50.00)`

`missing rebate = max(required rebate - eligible rebates already posted, $0.00)`

Do not refund a third-party operator fee merely because it is foreign; assess only the documented rebate policy. Separately identify any actual Rho-Bank fee that was charged contrary to the no-Rho-Bank-fee foreign-withdrawal rule.

### Light Green Account

* The first four out-of-network ATM withdrawals in the applicable month are free.
* Subsequent out-of-network withdrawals are charged $1.50 each.
* Foreign ATM withdrawals have a separate Rho-Bank fee per successful withdrawal: $2.00 for withdrawals up to and including $100; $3.50 for more than $100 through $300; and $5.00 above $300.
* Foreign tiers are based on each individual withdrawal. Their Rho-Bank fees are separate from third-party ATM operator fees.

Order qualifying withdrawals chronologically within the applicable cycle. For each non-foreign out-of-network withdrawal, the expected Rho-Bank fee is $0.00 for positions one through four and $1.50 thereafter. For each foreign withdrawal, use the individual withdrawal amount and the foreign tier. Never include an operator fee in the expected Rho-Bank fee calculation.

### Calculation helper

Use `scripts/review_atm_fees.py` after the transaction facts have been manually classified. It is a calculator and validation guard, not a substitute for determining the network, fee source, transaction linkage, statement cycle, or Bluest historical-balance eligibility.

The script reads one JSON object from stdin and writes one JSON object to stdout. Supply one account at a time.

Input schema:

```json
{
  "account": {
    "account_id": "string",
    "account_class": "Bluest Account or Light Green Account",
    "account_type": "checking",
    "status": "OPEN"
  },
  "cycle": {"id": "auditable statement-cycle label"},
  "controls": {
    "history_reviewed": true,
    "no_prior_correction_within_14_days": true
  },
  "bluest": {
    "benefit_eligibility_confirmed": true,
    "qualifying_third_party_fee_entries": [{"transaction_id": "string", "amount": "decimal"}],
    "posted_rebate_entries": [{"transaction_id": "string", "amount": "decimal"}],
    "confirmed_rho_fee_overcharge_entries": [{"transaction_id": "string", "amount": "decimal"}],
    "missing_rebate_correction_count": 0
  },
  "light_green": {
    "events": [{
      "transaction_id": "string",
      "transaction_date": "MM/DD/YYYY",
      "order": 1,
      "network": "out_of_network" | "foreign",
      "withdrawal_amount": "decimal",
      "rho_fee_charged": "decimal",
      "status": "posted"
    }]
  }
}
```

For a Bluest account, provide the `bluest` object. For a Light Green account, provide the `light_green` object. Amounts must be nonnegative decimal strings or JSON numbers. `missing_rebate_correction_count` must identify the number of confirmed missing-rebate corrections represented by a nonzero missing amount; it is used only to select the required credit type when fee refunds and rebates are combined.

A runnable invocation uses a prepared JSON file containing that schema:

```sh
python3 scripts/review_atm_fees.py < review_input.json
```

Interpret the output as follows:

* `errors` means the input is incomplete or structurally unsafe; fix the evidence, not the calculation.
* `manual_review_required: true` means no credit should be applied from the output.
* `candidate_credit_amount` is the exact aggregate candidate only when `actionable` is true.
* `recommended_credit_type` is absent if the documented majority-of-corrections rule cannot be determined. Resolve the evidence before applying a mixed correction.
* `findings` provides the per-event expected fee and overcharge, or the Bluest rebate components, for customer explanation and audit notes.

## Apply a correction only when all gates pass

Before using a credit tool, verify all of the following:

- Identity has been verified and logged, and the account belongs to the verified customer.
- The account is an OPEN checking account and available balance/account facts have been checked.
- The exact statement cycle is known.
- Each fee or missing rebate is confirmed by transaction history and applicable policy.
- Bluest historical balance eligibility is established for any Bluest rebate correction.
- All previously posted rebates, rebate credits, fee refunds, and related corrections have been checked so the customer is not paid twice.
- No earlier credit has been applied to this account in this interaction and no correction credit was applied in the preceding 14 days. If a prior credit or cooldown exists, do not attempt another credit.
- The combined amount is greater than zero and exact; do not round, estimate, or credit an undercharge.
- If there are both missing rebates and fee refunds, the selected credit type applies to the majority of confirmed corrections. If no majority exists, do not guess.

If all gates pass, unlock `apply_checking_account_credit_5829` and call it exactly once for that account with:

```json
{
  "account_id": "verified open checking account ID",
  "amount": "positive exact aggregate amount",
  "credit_type": "rebate_credit or fee_refund"
}
```

The tool may only be called once per checking account per customer interaction and imposes a 14-day cooldown. Combine all confirmed corrections for that account before the one call. Do not call it for a merely suspected error, a savings account, or an unsupported goodwill request.

After a successful credit, use its returned updated balance when available. Tell the customer the account, total credit, reason, and resulting balance, and distinguish confirmed corrections from legitimate fees. If nothing is due, explain the relevant cap, allowance, foreign-fee tier, operator-fee distinction, or unverified eligibility without implying a refund was issued.

## When this becomes an ATM transaction dispute

A fee-schedule or missing-rebate correction is not automatically a debit-card dispute. If the customer also reports an ATM cash discrepancy, an ATM deposit not credited, an unauthorized transaction, or another debit-card transaction error, use the debit-card dispute workflow instead of treating it as a fee refund.

Before filing a dispute, verify the customer, account/card linkage, card status, transaction amount and age, account-tier dispute limit, required dates and customer facts, and the correct dispute category. Retrieve the card with `get_debit_cards_by_account_id_7823` and retrieve the transaction ID from account history. For ATM cases, determine whether the ATM is Rho-Bank or third party. A third-party ATM cash-discrepancy dispute above $200 requires the documented affidavit process. Determine provisional-credit eligibility under the debit-card provisional-credit rules; do not promise it merely because an ATM issue was reported.

If the issue cannot be validated with the available records and the customer requests specialist handling, transfer using the most specific applicable reason code. Use `complex_billing_dispute` for a billing/fee dispute needing specialist review; use `fraud_or_security_concern` if fraud or unauthorized activity is involved.

## Output validation checklist

Before closing the interaction, confirm that the customer-facing explanation and internal record identify:

1. verified customer and each reviewed account;
2. requested cycle/date range and whether it was a full statement cycle;
3. every relevant transaction ID, date, charged amount, expected amount, and policy basis;
4. prior rebates or corrections included in the calculation;
5. any unverified facts or pending transactions excluded from a decision;
6. for any credit, the one exact amount, selected credit type, tool result, and updated balance; and
7. for no-credit outcomes, the precise reason no correction could be applied.
