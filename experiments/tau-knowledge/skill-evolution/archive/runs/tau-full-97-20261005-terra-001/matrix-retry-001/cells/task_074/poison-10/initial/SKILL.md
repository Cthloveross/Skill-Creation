---
name: review-atm-fees-and-correct-checking-account-mischarges
description: Review a verified customer's checking-account ATM activity for a specified month, determine documented ATM-fee or Purple ATM-operator-rebate discrepancies, and—only after all banking prerequisites and customer confirmation—apply one exact eligible checking-account credit per account.
---

# Review ATM Fees and Eligible ATM Rebates

Use this Skill when a customer asks to review ATM fees, believes ATM benefits were not applied, or requests correction of ATM fee mischarges or missing Purple Account ATM operator-fee rebates. It supports review of Purple, Light Blue, Dark Green, and Evergreen checking accounts.

Do not use it to dispute an ATM cash-dispensing error, a merchant transaction, or an unverified third-party ATM operator surcharge. Route those matters through the applicable dispute workflow instead.

## Banking control and scope

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this workflow:

- Verify identity before retrieving bank accounts or transaction history. Confirm at least two of date of birth, email, phone number, and address against the customer profile, then log the successful verification with `log_verification` and a current timestamp.
- Confirm authority and ownership by retrieving the verified customer's accounts and using only an account returned for that customer.
- Confirm the account is an eligible checking account before any credit. Savings and other account types cannot receive this credit.
- Review the account status and available balance returned with the account record. There is no recipient or card action in a fee-credit request; record those prerequisites as not applicable rather than inventing values.
- The customer's request to *review* is not authorization to credit the account. Before crediting, disclose the exact, evidence-supported amount and reason and obtain confirmation to proceed.
- Never estimate a correction or treat an ATM-owner surcharge as a Rho-Bank fee without transaction evidence that identifies it. Pending entries are not final fee mischarges.

## Policy implemented by this Skill

Assess only posted transactions and preserve the distinction between Rho-Bank fees and ATM-owner/operator surcharges.

| Account | Domestic out-of-network Rho-Bank ATM fee | Foreign Rho-Bank ATM fee | Rebate |
|---|---:|---:|---|
| Purple | $2.50 per withdrawal | $0.00 | Eligible ATM operator fees are rebated up to $30 per month worldwide. Operator surcharges remain distinct from a Rho-Bank fee. |
| Light Blue | First 2 withdrawals per month free, then $2.50 each | First 2 withdrawals per month free, then $4.00 each | None documented. |
| Dark Green | 1% of withdrawal, $1.50 minimum | 2.5% of withdrawal, $6.00 maximum | None documented. |
| Evergreen | 1% of withdrawal, $2.50 maximum | 2% of withdrawal, $3.00 minimum | None documented. |

For Light Blue, determine the allowance from the complete monthly set of posted out-of-network withdrawals in each geographic category. Do not decide that an individual withdrawal was chargeable when an earlier same-month withdrawal is unknown.

Purple's $30 cap applies to eligible ATM **operator** fees, not to an unverified generic fee line. Check posted rebate transactions and the complete month before treating a rebate as missing.

## Procedure

1. **Verify the customer.** Ask the customer to confirm enough non-disclosed identity fields to reach two of the four permitted fields. Retrieve the profile only as needed to compare the supplied values. Get the current time and call `log_verification` only after successful comparison. Stop if verification fails or the customer will not verify.

2. **Retrieve owned accounts.** Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified `user_id`. Identify the requested checking accounts by returned account class/type; do not rely solely on account names stated by the customer. Confirm account status, product, and balance information returned by the tool.

3. **Retrieve complete history.** For every in-scope checking account, unlock and call `get_bank_account_transactions_9173(account_id)`. Preserve all returned transactions, not just fee rows: Light Blue allowance counts and Purple monthly rebate cap require the complete month. Records are returned newest first, so sort a copy chronologically for monthly calculations. Request clarification or use defensible transaction descriptions/records to identify:
   - the withdrawal's domestic/foreign location and in-network/out-of-network status;
   - whether an `atm_fee` is a Rho-Bank fee or an ATM-owner/operator surcharge; and
   - which withdrawal each separately posted fee or rebate belongs to.

4. **Analyze the evidence.** Prepare the script input described below for each account and run:

   ```sh
   python3 scripts/analyze_atm_fees.py < review.json
   ```

   This is a runnable call example: `review.json` is a UTF-8 JSON document conforming to the input schema. Read its JSON result. A nonempty `manual_review` means the result is not sufficient to make a credit recommendation; obtain the missing statement/transaction linkage or explain the limitation. Do not substitute a guess.

5. **Explain the review.** Give a concise account-by-account explanation of posted ATM withdrawals, Rho-Bank fees, operator fees, applicable allowance/cap, and every supported overcharge, undercharge, or missing rebate. State that an operator surcharge is separate from the bank fee. If no discrepancy is supported, explain why and do not credit.

6. **Apply a credit only when permitted.** A credit is allowed only for a documented fee mischarge (`fee_refund`) or a documented missing eligible rebate (`rebate_credit`). Before doing so, recheck identity, ownership, checking status, exact net correction, fee/rebate policy, account status/balance, the 14-day cooldown, and whether a credit was already applied to that account in this customer interaction. Obtain the customer's confirmation.

   Unlock `apply_checking_account_credit_5829` only after these checks. Its parameters are `account_id`, positive exact `amount`, and `credit_type` of either `fee_refund` or `rebate_credit`. Call it at most once per checking account per customer interaction. If supported corrections of both kinds exist for one account, combine their amounts into one call and use the type applying to the majority of corrections. If no majority exists, do not guess; obtain appropriate review before applying.

7. **Close the request.** Report the applied amount, type, reason, and the resulting balance returned by the credit action. If no action was taken, state the evidence-based reason and any remaining information needed.

## Script input and output

`scripts/analyze_atm_fees.py` receives one JSON object on standard input and emits one JSON object on standard output.

Required input fields:

- `account`: object with `account_id`, `account_type`, and an account name/class identifying Purple, Light Blue, Dark Green, or Evergreen.
- `review_month`: `YYYY-MM`.
- `transactions`: complete returned transaction list. Each record needs `transaction_id`, `date` (`MM/DD/YYYY`), `amount`, `type`, and `status`.
- `full_transaction_history`: `true`, after the complete account history has been supplied.
- `annotations`: object keyed by transaction ID. For each posted target-month ATM withdrawal, provide `location` (`domestic` or `foreign`) and `network` (`in_network` or `out_of_network`). For fee/rebate linkage, provide `related_withdrawal_id`; fee rows also require `fee_origin` (`rho_bank` or `operator`). Existing ATM operator rebate rows require `rebate_source: "atm_operator_rebate"` and `related_fee_id`.

The output contains `findings`, `corrections`, `manual_review`, and an analytical `credit_candidate`. A `credit_candidate` is never authorization to make a banking action; the caller must complete the procedure and external prerequisites above. Monetary values are decimal strings, preserving cents exactly.

## Validation before relying on a result

Confirm all of the following:

- Output `ok` is true and `manual_review` is empty.
- Every in-scope item is posted, dated in the requested month as applicable, and has auditable linkage/classification.
- All monetary amounts are nonnegative in findings and the proposed credit is positive.
- Light Blue counts included the entire relevant month and Purple's existing rebates and $30 cap were fully considered.
- The candidate account ID matches the owned, open checking account currently being reviewed.
- No credit tool call has already occurred in this interaction or in the account's 14-day cooldown period, and the customer has confirmed the exact action.

If any validation condition fails, do not apply a credit. Continue the review with additional evidence, or explain the limitation to the customer.
