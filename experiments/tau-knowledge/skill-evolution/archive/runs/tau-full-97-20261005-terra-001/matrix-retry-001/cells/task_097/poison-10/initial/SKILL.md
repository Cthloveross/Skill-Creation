---
name: savings-interest-discrepancy-correction
description: Investigate a claimed savings-interest shortfall, calculate only a documented and supportable interest correction, apply an authorized savings credit, and file the required backend discrepancy report. Use for savings interest-calculation disputes; do not use for ordinary balance inquiries or unsupported compensation requests.
---

# Savings Interest Discrepancy Correction

Use this workflow when a customer asserts that monthly savings interest was incorrect. A customer-provided estimate, current balance, or rough payment amount is not enough to issue a credit.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Preconditions and evidence standard

1. Verify the caller's identity by having them confirm at least two of date of birth, email, phone number, and address against the user record. Obtain the current timestamp and call `log_verification` only after the two-field match. A name, email lookup, or prior conversation alone is not verification.
2. Verify authority and ownership for each account under review. Retrieve the customer's accounts with `get_all_user_accounts_by_user_id_3847`; confirm that each target is an active savings account owned by the verified user. Record its account ID, class, status, and current balance.
3. Retrieve `get_bank_account_transactions_9173(account_id)` for every target savings account. Identify the relevant posted `interest_credit` transaction(s), including exact amount and date. Do not use pending transactions or an unverified customer recollection as the actual credit.
4. Establish the exact statement/interest period and the daily balance history (or a reliable equivalent) for that period. Establish which qualifying products, account links, direct deposit, and relationship criteria were active during that same period. If the period, balance history, or eligibility cannot be established, explain that a correction cannot yet be calculated; request the statement dates/balances or investigate the account records. Do not apply a speculative credit.

Use the runtime's discoverable-tool process where necessary: unlock each named agent tool before calling it, and use the normal banking tool interface for actual banking actions.

## APY determination

Determine the documented APY for each individual savings account and period:

- Select the applicable base or balance-tier APY day by day when the product is tiered.
- Add documented qualifying bonuses that were active for the period, including direct-deposit and relationship bonuses when their qualification is proven.
- Consider only documented checking/savings pairings under the same profile. When more than one qualifying checking boost exists, apply **only the highest** applicable checking boost; checking boosts never stack with one another.
- Consider the card-bonus schedule for the specific savings product and active cards under the same profile. Apply **only the highest** applicable card bonus; card bonuses never stack with one another.
- The chosen checking boost and card bonus may each stack with documented base/tier, direct-deposit, and relationship components when applicable.
- Do not infer an unpublished boost value, a relationship qualification, or a card/checking product's historical eligibility. If required documentation is absent, treat it as unresolved.

For tiered accounts or changing balances, split the calculation by day or by segments sharing the same balance and APY components. Interest is daily compounded and monthly credited. Use the packaged calculator to keep the computation repeatable, but independently ensure that its input is supported by retrieved records.

## Calculator

`scripts/interest_math.py` accepts one JSON object on standard input and emits one JSON result on standard output.

Run it with a prepared evidence-derived request file:

```sh
python3 scripts/interest_math.py < request.json
```

Input schema:

```json
{
  "daily_principal_balances": ["decimal dollar amount for each calendar day in the period"],
  "expected": {
    "base_or_tier_apy": "percentage",
    "checking_boosts": ["eligible percentage boosts"],
    "card_bonuses": ["eligible percentage bonuses"],
    "other_additive_bonuses": ["eligible percentage bonuses"]
  },
  "actual_interest_credit": "posted positive dollar amount",
  "actual_apy": "optional known applied APY percentage"
}
```

`daily_principal_balances` must contain one nonnegative principal balance per period day, in chronological order. The script chooses the maximum supplied checking and card values, adds the other documented components, compounds daily using the APY-equivalent daily rate, rounds the final expected credit to cents, and computes the expected-minus-actual discrepancy. If `actual_apy` is absent, it derives an equivalent actual APY from the credited amount and supplied daily balances. The result identifies blockers, selected bonuses, the expected APY/interest, actual APY, and the positive correction amount (if any).

Validate before relying on the output:

- Ensure every daily input corresponds to the same verified interest period and account.
- Ensure the selected inputs represent only proven active and qualifying benefits.
- Match `actual_interest_credit` to the posted `interest_credit` transaction amount.
- Review `blockers`; do not proceed if nonempty.
- A zero or negative `correction_amount` is not an authorized credit. Investigate apparent overpayments or inconsistent evidence without using the credit tool.

## Authorized action sequence

Proceed only after all preconditions and calculations are complete and the result establishes a positive shortfall.

1. Preserve the verified identity, authority, account ownership, active savings product, target account ID, statement period, posted interest transaction, APY components, expected APY, actual APY, exact positive difference, and credit rationale in the work record.
2. Unlock and call `apply_savings_account_credit_6831` with the verified savings `account_id`, the exact positive `correction_amount`, and `credit_type: "interest_correction"`. Never substitute a fee refund or goodwill credit type for an interest shortfall.
3. Confirm the credit result and obtain the resulting balance through the normal account information flow. If the credit call fails or returns an ambiguous result, do not retry blindly or submit a report claiming success; inspect the account/transaction record first.
4. Only after the credit is confirmed, unlock and call `submit_interest_discrepancy_report_7294` with the same savings `account_id`, verified `user_id`, calculated `expected_apy`, actual applied/derived `actual_apy`, and exact positive `amount_difference`.
5. Tell the customer which account was corrected, the amount, the updated balance if confirmed, and that the backend report was filed. Do not promise a root-cause or remediation timeline.

## Failure handling

Do not apply a credit or file an interest discrepancy report if identity/authority is unverified, the account is not an owned active savings account, the relevant interest transaction cannot be confirmed, period balances are unavailable, benefit eligibility is unresolved, the amount is not positive, or actual APY cannot be established. State the missing evidence and request it or continue read-only investigation. For a system/tool failure after a confirmed credit, avoid duplicate action and escalate through the available support path with the preserved records.
