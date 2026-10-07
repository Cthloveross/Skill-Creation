---
name: atm-fee-review-and-authorized-correction
description: Review November ATM fees across Purple, Light Blue, Evergreen, and transitioned Dark Green checking accounts; calculate only documented corrections; apply one authorized checking credit when fully supported; or transfer a customer who requests a human.
---

# ATM fee review and correction

Use this Skill for a customer who questions ATM fees, rebates, or operator surcharges on one or more checking accounts. It distinguishes the bank's own ATM fees from third-party ATM-operator surcharges and does not infer missing facts from account names or transaction types alone.

## Immediate routing

If the customer expressly asks to be connected to a human, or their final response is a transfer marker such as `###TRANSFER###`, transfer promptly. Call `transfer_to_human_agents` with reason `customer_requests_human_no_specific_reason` and a concise summary that includes the account-fee review request, any identity/account lookup already completed, and that no unsupported credit was applied. Do not claim that the bank lacks transaction-history access: the documented internal account and transaction tools can be used after appropriate verification.

For the supplied interaction, the terminal clarification is an explicit transfer marker. Therefore the executor should transfer rather than start a new investigation or apply a credit.

## Standard investigation procedure

Use these steps when the customer has not requested transfer.

1. **Identify and verify before disclosing history.** Locate the customer from a supplied full name or email using the ordinary user lookup tool. Ask the customer to confirm two of the four identity fields (date of birth, email, telephone number, or address); do not read the values out as prompts. Compare both answers to the returned profile. On success, obtain the current timestamp and call `log_verification` with the complete returned profile and timestamp. If two fields cannot be confirmed, do not disclose account history or make a credit.
2. **Get the accounts.** Unlock `get_all_user_accounts_by_user_id_3847`, then call it with the verified user ID. Select active checking accounts and record each account ID, class, status, and balance. Do not rely only on the customer's remembered account names.
3. **Get the histories.** Unlock `get_bank_account_transactions_9173`, then call it once for every relevant checking account ID. It returns reverse-chronological transactions. Retain all posted November ATM withdrawals, `atm_fee` rows, and `fee_rebate`, `rebate_credit`, and `fee_refund` rows, including date, description, amount, and status. Pending items are not final fee discrepancies. A fee may post on a different date from its withdrawal, so use descriptions, dates, and amounts to establish an association; do not pair ambiguous rows automatically.
4. **Classify before calculating.** Determine from the transaction evidence whether each withdrawal is domestic out-of-network, foreign, in-network, and/or an ATM-operator surcharge. An operator surcharge is third-party and is not automatically a Rho fee. If the description does not establish the category, report that the entry cannot be adjudicated from the available record rather than guessing.
5. **Apply the relevant account rule.** Use the policy table below. The optional `scripts/audit_atm_events.py` helper makes a transparent calculation only after transactions have been normalized and reliably paired; it does not retrieve data, authorize a credit, or execute banking actions.
6. **Validate any correction.** For every proposed correction, confirm the charged amount, the applicable fee schedule, the actual withdrawals/allowance ordering, and any rebate already posted. A legitimate fee must not be refunded merely because an operator surcharge was also charged. A missing Purple operator-fee rebate must be eligible and within the monthly $30 cap.
7. **Credit only when authorized.** Credits are permitted only to a verified checking account for a missing eligible rebate or a fee mischarge. Sum all exact, supported corrections for that account. Confirm no correction credit has already been applied in this customer interaction and that the account has not hit its enforced 14-day cooldown. Unlock `apply_checking_account_credit_5829` and call it at most once for the account with a positive exact amount. Use `rebate_credit` if missing rebates are the majority of corrections; use `fee_refund` if fee mischarges are the majority. If the correction types tie, eligibility is unclear, an amount would require an undocumented rounding assumption, or account type is not checking, do not make a credit; explain or transfer for review.
8. **Respond clearly.** Provide an account-by-account explanation of reviewed posted entries, the applicable rule, existing rebates, any exact credit actually applied, and remaining uncertainty. State that ATM-owner surcharges are separate from bank fees.

## Account policy table

| Account / situation | Determinable rule |
|---|---|
| Purple, domestic or otherwise documented out-of-network withdrawal | Rho fee is $2.50 per out-of-network cash withdrawal. It is separate from an ATM-owner surcharge. |
| Purple, foreign ATM fee | Purple has no foreign ATM withdrawal fee. Do not treat this alone as proof that an out-of-network fee is invalid; determine the fee's actual category from the entry. Eligible posted ATM-operator fees may be rebated up to a total of $30 per month. Exclude Rho's own $2.50 fee from the operator-fee rebate calculation. |
| Light Blue domestic out-of-network | Two free withdrawals each month; each subsequent domestic out-of-network withdrawal is $2.50. |
| Light Blue foreign ATM | Two free foreign ATM cash withdrawals each month; each later foreign withdrawal is $4.00. Treat foreign and domestic-out-of-network allowances as distinct unless the transaction terms expressly establish otherwise. Operator charges remain separate. |
| Evergreen out-of-network | Fee is 1% of cash dispensed, capped at $2.50 per withdrawal. The operator surcharge is separate. The source does not specify how fractions of a cent are rounded; do not credit based on an assumed rounding convention. |
| Dark Green at or after age 26 | The account transitions to a regular checking account at age 26. Use the account-list result to identify the successor account and its actual class. The supplied material does not state the successor regular account's ATM-fee schedule; do not apply the former Dark Green terms or adjudicate its fee without the successor terms. |

For Purple's $30 cap, total only documented *eligible ATM-operator fees* and subtract verified rebates already posted in the same month. A cap reached, miscoding, posting-window issue, or ineligible terminal/location can explain an absent rebate. Do not classify a general `atm_fee` row as an eligible operator charge without supporting description or other transaction evidence.

## Helper script

`scripts/audit_atm_events.py` reads one JSON object from stdin and writes one JSON object to stdout. It is a calculation aid for normalized, already-paired posted events.

Input schema:

```json
{
  "account_kind": "purple|light_blue|evergreen|dark_green_or_successor",
  "events": [
    {
      "date": "YYYY-MM-DD",
      "status": "posted",
      "category": "domestic_out_of_network|foreign|out_of_network|unknown",
      "withdrawal_amount": "positive decimal string",
      "rho_fee_charged": "nonnegative decimal string",
      "operator_surcharge": "nonnegative decimal string",
      "operator_fee_eligible": true,
      "operator_rebate_posted": "nonnegative decimal string"
    }
  ]
}
```

`category` must be based on the actual transaction evidence. For Purple, use `out_of_network` only when that classification is documented; use `foreign` for a foreign-withdrawal fee review. For Light Blue, use `domestic_out_of_network` or `foreign`. Fields omitted from an event are treated as unknown or zero as appropriate. Only posted events are calculated.

The output lists each event's expected Rho fee where the rule is determinate, overcharge amounts, missing eligible Purple rebate amounts, warnings, and a possible exact single-credit recommendation. A `credit_ready: false` result means the executor must not call the credit tool based on the helper. In particular, the helper intentionally refuses an Evergreen percentage result that is not already an exact cent because the supplied policy has no rounding rule.

Example runtime invocation after constructing normalized evidence:

```text
run_skill_script(relative_path="scripts/audit_atm_events.py", input_json={"account_kind":"evergreen","events":[...]})
```

Validate helper output against the actual transaction rows before any banking action. The helper is not evidence that a fee row belongs to a withdrawal.
