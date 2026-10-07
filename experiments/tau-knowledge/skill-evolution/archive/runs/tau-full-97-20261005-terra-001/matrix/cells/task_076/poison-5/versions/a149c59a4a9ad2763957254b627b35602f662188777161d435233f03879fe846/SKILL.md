---
name: open-personal-checking-account
description: Compare available personal checking accounts, verify a customer's eligibility, and open a selected account only after identity, funding, account-history, and explicit-consent requirements are satisfied. Use this for new personal checking requests, especially travel/ATM and direct-deposit comparisons.
---

# Open a Personal Checking Account

## Scope and non-negotiable safety rule

Use this workflow for a request to open a personal checking account. Product information, a tentative preference, silence, a `STOP` response, or an identity lookup is **not** authorization to open an account.

Before any banking action, verify the applicable prerequisites: customer identity, authority, account ownership where applicable, product eligibility, available balance or credit for required funding, fees, limits, cutoffs, recipient and card details where applicable, and confirmation requirements. For a new checking account, recipient and card details are normally not applicable; record that they are not applicable rather than silently omitting them.

Never call `open_bank_account_4821` unless every opening gate in this Skill has passed. Do not transfer a customer merely because a documented product comparison is needed; provide the grounded comparison first. Transfer only when a required fact cannot be established through approved tools or process, the customer requests a human, or another approved transfer condition applies.

## Required runtime evidence

Collect current evidence rather than assuming facts from a prior conversation:

- Authorized current product terms relevant to the customer's stated needs.
- A customer-provided lookup value and the resulting unambiguous customer record.
- Two independently customer-confirmed matching identity fields from: date of birth, email, phone number, or address.
- A current timestamp and a successful `log_verification` audit record after those two matches.
- Confirmation that the requester is the customer and is authorized to open an account for themself.
- The customer's complete account listing, including account type, class, status, balance, and opening date.
- An authoritative determination of whether a checking account was closed for cause within the previous six months. If the account listing does not supply closure reason and date, it does not establish this condition.
- A final selection of an exact official personal-checking `account_class` ending in `Account`.
- Product-specific requirements, including confirmed and actually verified funding where an opening deposit is required.
- Explicit final consent to open the selected account.

Do not reveal stored identity data merely to solicit a match. Ask the customer to independently provide a second permitted identity field, then compare it to the retrieved record. A name, a lookup result, or a field supplied by the agent is not one of the two required identity confirmations.

## Mandatory first customer-facing comparison for travel/ATM requests

When a customer asks which checking account has the lowest foreign or travel ATM cost and also requires early direct deposit, give the available product comparison **before the first banking-tool call or handoff**. Use the authorized terms available at runtime. Do not say product information is unavailable when the materials provide it.

For the documented travel comparison currently packaged in `references/travel_checking_comparison.md`, explain all material tradeoffs:

- **Bluest Account** has a $0 Rho-Bank foreign ATM withdrawal fee, up to $50 in monthly ATM-fee rebates, and early direct deposit up to two days early. Third-party ATM operator charges can still apply. It requires a $75,000 opening deposit; maintaining benefits requires a $112,500 daily balance, and the monthly maintenance fee below that balance is $75.
- **Purple Account** also has a $0 Rho-Bank foreign ATM withdrawal fee and early direct deposit up to two days early. Its global ATM-fee rebate cap is up to $30 per month; third-party ATM operator charges can still apply. Its monthly maintenance fee is $15 unless the customer maintains a $3,750 minimum daily balance.

For the stated ATM-fee and two-day-early-direct-deposit criteria, describe Bluest as the stronger documented ATM-fee candidate because it has the same $0 Rho foreign-ATM withdrawal fee and a higher documented monthly rebate cap. Do **not** claim it is unconditionally cheapest overall: the $75,000 opening deposit and its ongoing $112,500/$75 conditions are material and may make Purple more appropriate for a customer who cannot meet them.

After the comparison, ask for a choice. A suitable form is:

> “Would you like to open **Bluest Account** and can you fund its required $75,000 opening deposit, or would you prefer **Purple Account**? Purple also has $0 Rho foreign-ATM withdrawal fees and up to two-day early direct deposit, with up to $30 in monthly ATM-fee rebates and a $15 monthly fee unless a $3,750 daily balance is maintained.”

Treat no response, `STOP`, an ambiguous response, or a response that does not affirm Bluest funding as no selection. Do not open an account in that circumstance.

If authorized runtime product materials differ from the packaged reference, disclose the current authorized terms and follow them. If materials genuinely do not establish a needed term, say exactly which term is unavailable; do not invent it or make a cost guarantee.

## End-to-end procedure

1. **Understand and compare.** Identify the customer's requested capabilities and relevant conditions: for example foreign ATM withdrawal fees, ATM-operator rebate caps, early direct-deposit timing, foreign transaction fees, opening deposits, maintenance fees, balance waivers, and withdrawal limits. Give the grounded comparison described above before gathering identity or invoking banking tools when it answers the customer's request.

2. **Obtain an official selection and material confirmations.** Ask the customer to select one full, official account-class name. Explain the selected product's material fees, limits, funding requirements, and conditions. For a product with an opening deposit, get a direct affirmation that the customer can provide it; this affirmation is necessary but does not replace balance/credit verification. Do not silently substitute a different account class.

3. **Resolve identity.** Use a normal lookup tool with an identifier independently provided by the customer, such as an email address or exact full name. If no unique record is found, request a usable identifier and do not continue to an opening action.

4. **Verify identity and authority.** Obtain two matching customer-supplied fields from date of birth, email, phone number, and address. Once both match the retrieved record, use `get_current_time` and then call `log_verification` with the complete retrieved record and returned timestamp. Confirm that the verified person is acting for themself and authorizes this account request. If identity fields do not match or authority is unclear, do not open an account.

5. **Retrieve account history and assess eligibility.** Unlock and call `get_all_user_accounts_by_user_id_3847` for the verified user. Determine the authoritative number of personal checking accounts and ensure that opening the requested account will not result in more than four. Independently establish that no checking account was closed for cause in the prior six months. If closure reason/date, account status, or counting rules are unavailable, eligibility is unverified and opening must stop pending an approved source or appropriate escalation.

6. **Check age and funding.** Using verified date of birth and the current date, establish that the customer is at least 18. Confirm product-specific eligibility. For a required opening deposit, verify that available balance or credit can satisfy it through normal banking tools; do not infer funds from an affirmation, account tenure, or a product recommendation.

7. **Make the final confirmation explicit.** Immediately before opening, restate the exact selected official class and all material conditions. Obtain clear product-specific consent, such as: “I confirm that I want to open Bluest Account and meet its required opening funding.” The consent must follow the comparison and selection, not precede them.

8. **Open only when all gates pass.** Unlock `open_bank_account_4821` and call it only with the verified customer and confirmed official account class, using the parameter schema supplied by the normal banking runtime. Do not fabricate arguments or report a successful opening before the tool succeeds. Retain and accurately communicate the actual outcome and account identifier, if returned.

9. **Handle missing or failed evidence safely.** State the blocking condition without disclosing unnecessary sensitive data. Do not retry an opening that failed eligibility. If no final selection, funding affirmation, funding verification, account-history review, closure-for-cause review, or identity verification exists, provide the next needed step and do not call the opening tool.

## Opening gates

Every item below must be true before `open_bank_account_4821` is called:

- Two independently customer-confirmed permitted identity fields match, and `log_verification` succeeded.
- The customer is at least 18 years old on the current date.
- The requester is confirmed as authorized to open the account for themself.
- `get_all_user_accounts_by_user_id_3847` was used and the resulting personal checking count after opening is at most four.
- No closure for cause within the preceding six months has been independently verified.
- The customer selected an exact, official personal checking account class.
- Relevant fees, ATM terms, benefits, limits, opening deposit, and balance conditions were disclosed.
- Required opening funding was both affirmatively acknowledged by the customer and actually verified.
- The customer gave final, product-specific consent after the disclosure.

## Deterministic eligibility helper

Use `scripts/check_personal_checking_eligibility.py` after gathering authoritative evidence to produce an auditable preliminary assessment. The helper does not contact banking systems, verify identity, establish closure history, prove funding, or open an account. Unknown evidence is a blocker.

### Input JSON schema

```json
{
  "date_of_birth": "MM/DD/YYYY or YYYY-MM-DD",
  "as_of": "YYYY-MM-DD or timestamp beginning YYYY-MM-DD",
  "identity_verified": true,
  "authority_confirmed": true,
  "existing_personal_checking_count": 0,
  "closures_for_cause_within_last_6_months": false,
  "official_account_class_confirmed": true,
  "final_opening_consent": true,
  "funding_required": false,
  "funding_verified": true
}
```

`existing_personal_checking_count` must be derived from the authoritative account lookup, not guessed. Set `closures_for_cause_within_last_6_months` to `null` when no independent review has established it. For a funded product, `funding_required` and `funding_verified` must both accurately reflect the evidence.

### Runnable invocation

```sh
python3 scripts/check_personal_checking_eligibility.py <<'JSON'
{"date_of_birth":"YYYY-MM-DD","as_of":"YYYY-MM-DD","identity_verified":true,"authority_confirmed":true,"existing_personal_checking_count":0,"closures_for_cause_within_last_6_months":false,"official_account_class_confirmed":true,"final_opening_consent":true,"funding_required":false,"funding_verified":true}
JSON
```

The placeholder values are illustrative only. The script emits one JSON object with `checks`, `blocking_reasons`, `missing_evidence`, `resulting_personal_checking_count`, and `eligible_to_continue`. Proceed only when `eligible_to_continue` is `true` and the live tool evidence remains current.
