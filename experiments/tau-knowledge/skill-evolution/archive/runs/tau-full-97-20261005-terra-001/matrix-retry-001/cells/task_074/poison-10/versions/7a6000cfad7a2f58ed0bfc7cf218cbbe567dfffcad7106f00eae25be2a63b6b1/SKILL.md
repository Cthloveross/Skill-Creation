---
name: review-and-correct-atm-fee-mischarges
description: Review a verified customer's checking-account ATM activity for a requested month, calculate posted Rho-Bank ATM-fee mischarges and documented Purple ATM-operator rebate omissions, and apply one exact eligible combined checking-account credit per affected account.
---

# Review and Correct ATM Fee Mismatches

Use this Skill when a customer asks to review ATM fees, believes account ATM benefits were not applied, or asks for correction of ATM-fee mischarges. It supports Purple, Light Blue, Dark Green, and Evergreen checking accounts. It does not handle ATM cash-dispensing errors, unauthorized withdrawals, or unverified third-party operator charges; use the applicable dispute process for those matters.

## Banking control and scope

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this workflow:

- Before retrieving account or transaction information, verify at least two of the customer's date of birth, email, phone number, and address against the customer profile. After successful comparison, get the current time and call `log_verification` with every required profile field and that timestamp. Stop account-specific work if verification fails or remains incomplete.
- Retrieve accounts only for the verified user and use only account IDs returned for that user. Confirm the customer owns each account under review.
- Before applying a credit, confirm that the account is an eligible checking account, its status and available balance are suitable for the action, and that the correction is documented and exact. Credits cannot be applied to savings or other account types.
- Review posted entries only. Do not treat a pending entry as a final fee error.
- Keep a Rho-Bank ATM fee distinct from an ATM owner/operator surcharge. Do not refund an operator surcharge unless a documented Purple operator-fee rebate was due and missing.
- Check transaction history for a prior `fee_refund` or `rebate_credit` during the 14-day cooldown and maintain an interaction-level set of already credited account IDs. Never call the credit tool more than once for an account in this interaction.

A completed review that establishes a documented fee mischarge is an eligible reason to correct the account in the same interaction. The credit procedure does not prescribe an additional customer authorization step. Explain the evidence and exact correction before or while completing the correction, unless an applicable runtime workflow independently requires confirmation.

## Fee policy

| Account | Domestic out-of-network Rho-Bank fee | Foreign Rho-Bank fee | Other applicable benefit |
|---|---:|---:|---|
| Purple | $2.50 per withdrawal | $0.00 | Eligible posted ATM operator fees are rebated worldwide up to $30 per month. |
| Light Blue | First 2 out-of-network withdrawals each month free; then $2.50 each | First 2 foreign withdrawals each month free; then $4.00 each | No documented operator-fee rebate. |
| Dark Green | 1% of withdrawal amount, $1.50 minimum | 2.5% of withdrawal amount, $6.00 maximum | No documented operator-fee rebate. |
| Evergreen | 1% of withdrawal amount, $2.50 maximum | 2% of withdrawal amount, $3.00 minimum | No documented operator-fee rebate. |

ATM-owner/operator surcharges are separate from these bank fees. Purple's rebate cap applies only to eligible operator fees, not ordinary Rho-Bank fee lines.

For **Light Blue**, count only posted **out-of-network** withdrawals against the allowance. Count domestic and foreign withdrawals independently. A Rho-Bank/in-network withdrawal does not consume either allowance. Evaluate the complete month in chronological order so that the first and second eligible withdrawal in each location category receive the free allowance.

## End-to-end procedure

1. **Verify identity and log it.** Obtain the required second identity field if the customer has supplied only one. Compare at least two permitted fields to the profile, obtain the current time, and call `log_verification`. Preserve the successful verification for the rest of the interaction.

2. **Retrieve all requested checking accounts before reviewing activity.** Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified user ID. Identify all requested Purple, Light Blue, Dark Green, and Evergreen accounts from returned account information. Confirm ownership, account type/class, status, balance, and product identity.

3. **Retrieve complete histories.** For every in-scope checking account, unlock and call `get_bank_account_transactions_9173(account_id)`. Do this before calculating any account-specific correction. Histories are reverse chronological, so sort a copy chronologically for monthly allowance calculations. Keep all returned entries because Light Blue allowances, Purple rebates, prior credits, and fee-to-withdrawal associations may require entries beyond a short excerpt.

4. **Classify and link records from transaction evidence.** For each posted target-month ATM withdrawal, determine whether it was domestic or foreign and in-network or out-of-network. For every related `atm_fee`, determine whether it is a Rho-Bank fee or an operator charge and link it to the withdrawal. Link existing Purple `fee_rebate` or `rebate_credit` entries to the operator fee they rebated. Use explicit transaction descriptions, statement details, or customer clarification; never infer an unsupported linkage. If classifications or linkage cannot be established, explain the limitation and do not apply a speculative credit.

5. **Calculate the complete net correction.** Run the packaged deterministic helper once per account using the complete history and verified annotations:

   ```sh
   python3 scripts/analyze_atm_fees.py < review.json
   ```

   `credit_candidate` is only an analysis result. If `ok` is false or `manual_review` is nonempty, resolve the listed evidence gap before using it. Review all findings, including undercharges, but credit only the total documented overcharge or missing rebate. Do not offset an overcharge with a separate undercharge unless the applicable fee policy explicitly requires netting.

6. **Apply one combined correction per affected checking account.** Recheck identity, ownership, checking eligibility, account status/balance, exact amount, the applicable fee policy, cooldown, and the interaction-level one-credit limit. Unlock `apply_checking_account_credit_5829` and call it exactly once for each eligible affected account with:
   - `account_id`: the owned checking account ID;
   - `amount`: the positive exact combined correction; and
   - `credit_type`: `fee_refund` for fee mischarges or `rebate_credit` for a missing rebate.

   If an account has both correction types, combine them in its one permitted credit and use the type that applies to the majority of correction items. If there is no majority, do not guess; obtain appropriate review before applying a credit.

7. **Report completion.** For each corrected account, tell the customer the account-specific credit amount, its reason, and the resulting balance returned by the credit action. Retain the completed identity and ownership verification. If no credit is supported, explain the evidence-based reason and any specific missing information. If a designated review system fails, tell the customer there was a technical error and offer escalation to a specialist.

## Helper input and output

`scripts/analyze_atm_fees.py` reads one UTF-8 JSON object from standard input and writes one JSON object to standard output.

Input schema:

- `account`: object containing `account_id`, `account_type`, and one of `account_class`, `account_name`, `name`, or `product` identifying Purple, Light Blue, Dark Green, or Evergreen.
- `review_month`: string in `YYYY-MM` form.
- `transactions`: the complete transaction-history array. Each record must contain `transaction_id`, `date` (`MM/DD/YYYY`), `amount`, `type`, and `status`.
- `full_transaction_history`: `true` only when the complete returned history was supplied.
- `annotations`: object keyed by transaction ID. Each posted target-month `atm_withdrawal` needs `location` (`domestic` or `foreign`) and `network` (`in_network` or `out_of_network`). Each posted target-month `atm_fee` needs `fee_origin` (`rho_bank` or `operator`) and `related_withdrawal_id`. Purple rebate entries included in the target month need `rebate_source: "atm_operator_rebate"` and `related_fee_id` when they are being counted toward the monthly cap.

Output fields are `ok`, `errors`, `findings`, `corrections`, `manual_review`, and `credit_candidate`. Monetary output values are decimal strings with two digits. A candidate does not replace the banking checks or tool action above.

## Validation checklist

Before relying on helper output or applying a credit, confirm that:

- all four requested owned checking accounts were retrieved before their histories were reviewed;
- `ok` is true and `manual_review` is empty;
- the complete target-month posted activity was considered;
- Light Blue's domestic and foreign out-of-network allowances were counted separately, excluding in-network/Rho-Bank withdrawals;
- Purple's linked operator-fee rebates and $30 monthly cap were considered;
- all fee classifications and links are auditable from records or supplied statement evidence;
- the candidate matches the currently owned eligible checking account, is positive, and equals the complete documented correction;
- no credit has already been applied in this interaction or during the account's applicable cooldown; and
- the credit result supplies the balance used in the customer-facing completion message.

If any condition fails, do not apply a credit until the gap is resolved.
