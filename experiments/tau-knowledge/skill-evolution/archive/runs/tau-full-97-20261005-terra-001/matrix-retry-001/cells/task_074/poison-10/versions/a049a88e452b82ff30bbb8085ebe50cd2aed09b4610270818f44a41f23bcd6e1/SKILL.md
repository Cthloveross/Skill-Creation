---
name: review-and-correct-atm-fee-mischarges
description: Review a verified customer's Purple, Light Blue, Dark Green, or Evergreen checking-account ATM activity for a requested month, calculate documented ATM bank-fee mischarges or missing Purple operator-fee rebates, and apply one exact combined checking-account credit per affected account.
---

# Review and Correct ATM Fee Mismatches

Use this Skill when a customer asks to review ATM fees, believes ATM benefits were not applied, or requests correction of ATM-fee mischarges. It supports Purple, Light Blue, Dark Green, and Evergreen checking accounts. It does not handle ATM cash-dispensing errors, unauthorized activity, or unverified third-party operator charges; use the applicable dispute process for those matters.

## Banking control and scope

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this workflow:

- Before retrieving account or transaction information, compare at least two of the customer's date of birth, email, phone number, and address against the customer profile. After successful comparison, get the current time and call `log_verification` with every required profile field and that timestamp. Stop account-specific work if verification fails or remains incomplete.
- Retrieve accounts only for the verified user. Use only account IDs returned for that user and confirm ownership of every account under review.
- Before applying a credit, confirm checking-account type, product, open/eligible status, available balance or credit as applicable, exact correction amount, applicable fee terms, cooldown, and the interaction-level one-credit limit. Credits cannot be applied to savings or other account types.
- Review posted entries only. A pending entry is not a completed fee mischarge.
- Keep Rho-Bank ATM fees separate from ATM-owner/operator surcharges. Do not refund an operator surcharge unless a documented Purple operator-fee rebate was eligible and missing.
- Check history for prior `fee_refund` or `rebate_credit` entries relevant to the correction and observe the 14-day credit cooldown. Maintain an interaction-level set of credited account IDs. Never call the credit tool more than once for an account in an interaction.

A documented fee mischarge is eligible for correction in the same interaction. No additional customer authorization is prescribed by the credit policy once the banking prerequisites have been completed.

## Fee policy

| Account | Domestic out-of-network Rho-Bank fee | Foreign Rho-Bank fee | Other benefit |
|---|---:|---:|---|
| Purple | $2.50 per withdrawal | $0.00 | Eligible posted ATM operator fees are rebated worldwide, up to $30 monthly. |
| Light Blue | First 2 out-of-network withdrawals monthly free; then $2.50 each | First 2 foreign withdrawals monthly free; then $4.00 each | No documented operator-fee rebate. |
| Dark Green | 1% of withdrawal amount, $1.50 minimum | 2.5% of withdrawal amount, $6.00 maximum | No documented operator-fee rebate. |
| Evergreen | 1% of withdrawal amount, $2.50 maximum | 2% of withdrawal amount, $3.00 minimum | No documented operator-fee rebate. |

ATM-owner/operator surcharges are separate from bank fees.

**Light Blue allowance rule:** Count only posted **out-of-network** cash withdrawals against the allowance. Count domestic and foreign withdrawals independently, in chronological order for the full month. A Rho-Bank/in-network withdrawal consumes neither allowance. Therefore, both the first and second eligible domestic withdrawals are free, and both the first and second eligible foreign withdrawals are free.

**Multiple fee records rule:** Link every posted fee line to its withdrawal whenever statement detail establishes the connection. More than one Rho-Bank fee may be linked to one withdrawal. Sum all linked Rho-Bank fee lines, compare that total once with the fee permitted for the withdrawal, and refund the positive difference. A separate duplicate Rho-Bank fee is a fee mischarge, not an unresolved operator-fee rebate issue merely because it accompanies another fee line.

## End-to-end procedure

1. **Verify and log identity.** Obtain any missing identity field so two permitted fields can be compared to the profile. Compare the fields, obtain the current timestamp, and call `log_verification` with the full profile data and timestamp. Retain this completed verification for the interaction.

2. **Retrieve all requested checking accounts before review.** Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified user ID. Identify each requested Purple, Light Blue, Dark Green, and Evergreen account. Confirm ownership, checking type/class, status, current balance, and product identity.

3. **Retrieve complete histories first.** For every requested owned checking account, unlock and call `get_bank_account_transactions_9173(account_id)` before calculating a correction for any individual account. The result is reverse chronological; retain it and sort a working copy chronologically for monthly allowances and rebates.

4. **Classify the evidence.** For each posted target-month ATM withdrawal, identify domestic/foreign and in-network/out-of-network from transaction descriptions, statement detail, or reliable account evidence. For each target-month `atm_fee`, identify whether it is a Rho-Bank fee or operator surcharge and link it to the associated withdrawal. Link any relevant Purple `fee_rebate` or `rebate_credit` to the operator-fee line it rebated. Do not invent a link. If an entry's description itself establishes that two Rho-Bank fee records concern one withdrawal, link both records to that withdrawal.

5. **Calculate the complete correction.** Run the packaged analyzer once per account after preparing explicit annotations:

   ```sh
   python3 scripts/analyze_atm_fees.py < review.json
   ```

   Treat `credit_candidate` only as a calculation. Do not apply it if `ok` is false or `manual_review` is nonempty. Resolve the evidence gap first.

   Review every finding. Credit only documented customer overcharges or documented missing eligible rebates; do not use a lower-than-scheduled bank charge to reduce a customer refund. In particular, verify all of these frequent error patterns:

   - an in-network withdrawal with any linked Rho-Bank fee has an expected bank fee of zero;
   - a Purple foreign withdrawal has an expected Rho-Bank fee of zero;
   - all fee lines linked to a withdrawal are included, including duplicates;
   - a fee above a permitted rate produces a refund only for the excess; and
   - Light Blue's domestic and foreign free allowances are separate and exclude Rho-Bank withdrawals.

6. **Apply exactly one combined credit per affected checking account.** Recheck identity, authority, ownership, product/type, account status and balance, exact amount, eligibility, prior credits, cooldown, and interaction-level one-credit limit. Unlock `apply_checking_account_credit_5829` and call it exactly once for each eligible affected account using:

   - `account_id`: the owned checking account ID;
   - `amount`: the positive exact combined correction; and
   - `credit_type`: `fee_refund` for fee mischarges or `rebate_credit` for a missing rebate.

   If both correction types are documented for one account, combine them because only one call is permitted. Use the type applying to the majority of correction items. If no majority exists, do not guess; obtain appropriate review before crediting.

7. **Report completion.** For each correction, tell the customer the account-specific credit, the reason, and the resulting balance returned by the credit action. Retain completed identity and ownership verification. If no correction is supported, give the evidence-based reason. If a designated review system errors, explain the technical error and offer escalation to a specialist.

## Analyzer input and output

`scripts/analyze_atm_fees.py` reads one UTF-8 JSON object on stdin and writes one JSON object on stdout. It performs no banking actions.

Input schema:

- `account`: object with `account_id`, `account_type`, and one of `account_class`, `account_name`, `name`, or `product` identifying Purple, Light Blue, Dark Green, or Evergreen.
- `review_month`: `YYYY-MM`.
- `transactions`: complete returned transaction-history array. Each record needs `transaction_id`, `date` (`MM/DD/YYYY`), `amount`, `type`, and `status`.
- `full_transaction_history`: `true` only when the complete returned history was supplied.
- `annotations`: object keyed by transaction ID:
  - each posted target-month `atm_withdrawal` needs `location` (`domestic` or `foreign`) and `network` (`in_network` or `out_of_network`);
  - each posted target-month `atm_fee` needs `fee_origin` (`rho_bank` or `operator`) and `related_withdrawal_id`;
  - a target-month Purple `fee_rebate` or `rebate_credit` counted toward the operator-fee benefit needs `rebate_source: "atm_operator_rebate"` and `related_fee_id`.

Output contains `ok`, `errors`, `findings`, `corrections`, `manual_review`, and `credit_candidate`. Monetary values are two-decimal strings. The candidate does not replace the prerequisite checks or banking-tool call.

## Validation checklist

Before applying a credit, confirm all of the following:

- all requested owned checking accounts were retrieved before any account-specific review;
- complete transaction histories and all posted target-month ATM records were considered;
- `ok` is true and `manual_review` is empty;
- every relevant fee has an auditable origin and withdrawal link, including multiple fees for a single withdrawal;
- Light Blue domestic and foreign allowances were independently counted, excluding in-network withdrawals;
- Purple operator-fee rebates, linked rebate postings, and the $30 cap were considered when applicable;
- the candidate is positive, exact, and for the currently owned eligible checking account;
- no prior correction, cooldown restriction, or interaction-level duplicate prevents the action; and
- the credit response supplies the resulting balance for the customer message.

If any condition fails, do not apply a speculative credit.
