---
name: savings-card-yield-advisor
description: Compare a customer's savings-account and one-credit-card options for one-year yield while accounting for balance thresholds, card fees, eligibility conditions, APY-bonus stacking rules, and unsupported assumptions. Use for informational banking-product comparisons; use the safeguarded action procedure only if the customer later asks to open or fund an account.
---

# Savings and Card Yield Advisor

Use this Skill to give a transparent, customer-specific comparison of savings and credit-card combinations. It is an advisory workflow by default: do not open an account, apply for a card, transfer funds, or inspect customer records merely because the customer asks which option is best.

## Scope and calculation rules

1. Identify the amount to be deposited, intended holding period, whether it must remain liquid, and whether the customer means **gross interest** or **net financial benefit after annual card/product fees**. For a one-year comparison, show both where a card has a fee.
2. Select only savings products whose documented opening and ongoing balance requirements can be met. A card-linked minimum-balance reduction applies only while the required card is active and associated with the savings account.
3. Determine the applicable base APY tier from the documented balance threshold. Treat an APY as an effective annual rate: estimated one-year gross interest is `principal × APY / 100`. Do not compound an already-stated APY again.
4. Add a credit-card APY bonus only when the card is eligible, active, linked under the same profile, and documented for that particular savings product. If multiple card bonuses could apply, use only the highest one; never sum card bonuses.
5. Add separately documented, qualifying non-card bonuses (for example, direct deposit or an eligible checking linkage) only when their conditions are confirmed. Linked-checking boosts also require that the exact checking/savings pairing qualifies; an account name that is not listed is not evidence of a boost.
6. Deduct the card's annual fee from first-year gross interest when presenting net benefit. Also disclose any required subscription or other cost whose amount is unknown rather than silently treating it as zero.
7. Do not invent approval, a credit score, subscription status, direct deposit, card linkage, opening-deposit terms, account tenure, or fee waivers. Mark a recommendation conditional when any required fact is missing.
8. If source prose gives a total APY that conflicts with its own explicit base rate and bonus, do not rely on the contradictory arithmetic. Calculate from the explicitly stated rate components, flag the discrepancy, and advise confirmation of the applicable disclosure before promising a dollar result.

Use `scripts/evaluate_savings_options.py` for deterministic comparisons after translating the applicable product terms into its JSON schema. The script is a calculation aid, not a source of product terms or eligibility decisions.

## Known product-term reference

Use `references/product_terms.md` to extract relevant published terms. It is a compact evidence reference, not a substitute for live disclosures. In particular, it identifies balance requirements, rate tiers, fees, card qualifications, bonus rules, and documented ambiguities relevant to account/card yield comparisons.

## Customer-facing response structure

For an advisory request:

1. State the leading combination **conditional on its prerequisites**, then name the account, card, applicable balance requirement, rate components, estimated gross one-year interest, known annual card fee, and estimated net result.
2. Name the best confirmed fallback if the leading option's credit, subscription, or other prerequisite is unknown or unavailable.
3. Briefly compare meaningful alternatives rather than listing every product. Explain why excluded options fail the balance requirement or yield less after fees.
4. Explicitly state which facts must be confirmed before a final recommendation or action, such as credit qualification, subscription cost/status, account/card linkage, direct-deposit enrollment, and whether the customer has other active cards.
5. State that rates and approval are subject to current disclosures and underwriting. Do not claim an account or card has been opened.
6. Ask whether the customer wants to proceed only after they have enough information to choose. If they do, begin the safeguarded action procedure below rather than treating the advisory conversation as authorization.

Avoid presenting a card's rewards, credit limit, or unrelated benefits as interest unless the customer asks for an overall rewards comparison.

## Calculator interface

Run with a JSON request on standard input and JSON output on standard output:

```text
python scripts/evaluate_savings_options.py < request.json
```

Input object:

- `deposit_amount` (required number): projected deposited balance.
- `term_years` (optional positive number, default `1`): comparison duration.
- `savings_accounts` (required array): each entry has `name`, optional `opening_minimum`, optional `ongoing_minimum`, and `rates` containing one or more `{ "min_balance": number, "apy_percent": number }` tiers. It may include `card_bonuses` (object mapping card name to percentage-point bonus), `other_confirmed_bonus_percent`, `linked_checking_boost_percent`, and `required_card_for_balance_override` with `card` and `ongoing_minimum`.
- `cards` (optional array): each entry has `name`, optional `annual_fee`, `eligibility_status` (`confirmed`, `conditional`, or `ineligible`), and optional `missing_conditions`.

The result contains candidate rate components, eligibility/feasibility status, gross interest, card fee, net result, missing conditions, and a descending ranking. Values are estimates based only on the supplied JSON. Populate the input from the current customer's stated amount and the current documented terms; never embed a prior customer's result in the request.

## Safeguarded account-opening procedure

Use this section only after a customer expressly chooses an account and asks to open or fund it.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For a personal savings-account opening:

1. Authenticate the customer by confirming two of the four identity fields (date of birth, email, phone number, address) against a retrieved customer record. Retrieve only the record needed for the presented identifier; obtain the current timestamp and call `log_verification` with all required record fields after successful verification.
2. Confirm the customer has authority over the relevant profile and checking account. Confirm the account selection and exact full official savings `account_class` name ending in `Account`.
3. Verify all documented opening prerequisites: at least one active Rho-Bank checking account, checking tenure of at least 14 days, fewer than five personal savings accounts, no accounts in collections or with negative balances, and all product-specific requirements.
4. Confirm the applicable opening deposit, the customer's selected source checking account, its available balance, all fees and limits, and explicit authorization for any transfer. Do not infer authorization from the earlier comparison.
5. Only after these checks, unlock and call the documented `open_bank_account_4821` agent tool with the authenticated user ID, `account_type` of `savings`, and the confirmed full account class. Do not use a savings-opening tool for a card application.
6. Ask whether the customer wants an immediate internal opening-deposit transfer. If authorized and the balance/limits are sufficient, unlock and use `transfer_funds_between_bank_accounts_7291` from the confirmed checking account to the newly created account for the required amount. If the customer declines, clearly state the documented 30-day funding deadline and closure consequence.
7. Report only tool-confirmed completion details and the funding status. If any prerequisite cannot be verified, do not proceed; explain the unmet condition or request the needed information.

Credit-card applications in the available product documentation are completed by the customer in their dashboard and require product-specific underwriting/documentation. Do not represent that a card was approved, and do not attempt an application through an account-opening workflow.
