---
name: open-personal-checking-account
description: Safely compare, verify eligibility for, and open a personal checking account when a customer requests a new checking product. Use this for product comparison, identity verification, eligibility review, customer confirmation, and the final account-opening action.
---

# Open a Personal Checking Account

## Scope and safety rule

Use this workflow only for a customer who is requesting a personal checking account. Do not open an account merely because the customer asked for product information or expressed a preference. A final, unambiguous selection of the official account class and confirmation to open are required.

Before **any** banking action, verify and record the applicable prerequisites: customer identity, authority to act, account ownership, product eligibility, available balance or credit where funding is required, fees, limits, cutoffs, recipient and card details where applicable, and confirmation requirements. For opening a checking account, recipient and card details are normally not applicable; state that they are not applicable rather than silently skipping them.

## Required inputs at runtime

Gather or retrieve the following; do not assume facts from a prior conversation are still valid:

- Customer identifier, resolved from a customer-provided identifying value.
- Two customer-confirmed identity fields from date of birth, email, phone number, and address.
- Current timestamp for the verification audit record.
- Customer authority: the requester is the customer and is authorized to open an account for themself.
- All bank accounts for the customer, including type, class, status, balance, and opening date.
- A separate, authoritative review of whether any checking account was closed for cause during the preceding six months. The account-listing response alone is insufficient if it has no closure reason and date.
- The selected full official `account_class`, any product-specific opening-funding requirement, confirmation that required funding is available, and final consent to open.

Do not disclose stored identity values in order to solicit a confirmation. Ask the customer to provide two fields independently, then compare them against the retrieved customer record.

## Procedure

1. **Understand the request and disclose relevant product terms.** Identify requirements such as foreign ATM pricing, early direct deposit, opening deposit, monthly fee, balance waiver, or other stated preferences. Use current authorized product materials, not remembered terms. Explain material fees, limits, funding requirements, and product trade-offs before requesting a selection.

2. **Resolve and verify identity.** Use an appropriate customer lookup tool with information supplied by the requester (for example, an email or exact name). If lookup is ambiguous or fails, stop and request a usable customer-provided identifier.
   - Obtain confirmation of at least two of the four permitted identity fields: date of birth, email, phone number, or address.
   - Compare each customer-provided field with the retrieved record. A name alone, a lookup result, or information revealed by the agent is not a second confirmation.
   - Once two fields match, call `get_current_time` and then `log_verification` with the complete retrieved identity record and that timestamp.
   - If fields do not match, do not perform an account-opening action. Resolve the discrepancy through the approved identity process or transfer when necessary.

3. **Establish authority and intent.** Confirm that the verified customer is requesting an account for themself. Confirm their desired product using the complete official account-class label. Do not normalize, abbreviate, or invent a class name. Personal-checking labels must use the official full name documented for the product, such as `Blue Account` or `Green Account (checking)`.

4. **Retrieve and assess account history.** Unlock and use `get_all_user_accounts_by_user_id_3847` with the verified `user_id` to obtain the current account record. Review personal checking account type/class and status. Confirm that opening the requested account will not leave the customer with more than four personal checking accounts. If statuses are unclear, do not guess which accounts count.
   - Independently verify there has been no checking-account closure for cause in the previous six months. If the available tools do not expose closure reason and date, the condition is unverified: do not open the account until an approved source verifies it or the case is routed appropriately.

5. **Check age and product eligibility.** Calculate age from the verified date of birth using the current date. Customer must be at least 18. Confirm all product-specific eligibility and funding requirements using current authorized terms. When a product requires an opening deposit, verify available funds or credit through the normal banking tools and obtain the customer's confirmation before proceeding. Do not promise a fee waiver, benefit, or funding result that has not been verified.

6. **Present the decision and get final confirmation.** State the selected official class, material fees/limits, opening deposit requirement, and any condition that affects the requested use case. Then obtain explicit final consent, for example: “I confirm I want to open [official account class] and meet the required opening funding.” If the customer has not selected a product or cannot confirm funding, stop after providing options; no opening action is authorized.

7. **Open only after every gate passes.** Unlock `open_bank_account_4821` and use it with the verified customer and the confirmed official account class, following the parameter schema made available by the normal banking runtime. Do not fabricate undocumented arguments. The action must be taken only after identity logging, authority, all eligibility checks, funding verification where required, and final consent. Report the actual tool outcome, including any account identifier returned.

8. **Handle failures safely.** If eligibility fails, clearly state the specific non-sensitive reason and do not retry the opening action. If a required fact, tool capability, or product term is unavailable, explain that the account cannot yet be opened and request the missing confirmation or use the approved escalation path. Do not substitute another account class without fresh customer selection and confirmation.

## Deterministic eligibility helper

Use `scripts/check_personal_checking_eligibility.py` to make an auditable preliminary eligibility assessment once authoritative runtime data has been gathered. The helper does not verify identity, query bank systems, prove funding, or open an account. It emits `eligible_to_continue: true` only when its supplied evidence establishes all checks it can assess.

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

`existing_personal_checking_count` must be the authoritative count that will remain open after excluding accounts that no longer count; do not send a guessed count. For a funded product, set both `funding_required` and `funding_verified` appropriately. `closures_for_cause_within_last_6_months` must be `null` if not independently verified.

### Example invocation

```sh
python3 scripts/check_personal_checking_eligibility.py <<'JSON'
{"date_of_birth":"YYYY-MM-DD","as_of":"YYYY-MM-DD","identity_verified":true,"authority_confirmed":true,"existing_personal_checking_count":0,"closures_for_cause_within_last_6_months":false,"official_account_class_confirmed":true,"final_opening_consent":true,"funding_required":false,"funding_verified":true}
JSON
```

The example contains placeholders, not customer data. The script writes one JSON object to stdout with `checks`, `blocking_reasons`, `missing_evidence`, `eligible_to_continue`, and `resulting_personal_checking_count`.

## Validation before the banking action

Confirm all of the following in the live case:

- A successful verification audit record exists after two independently customer-confirmed identity-field matches.
- The requester’s authority and self-service intent are confirmed.
- Age is at least 18.
- The resulting total personal checking count is at most four.
- No closure for cause in the last six months has been independently verified.
- The selected class is an exact current official personal-checking class.
- Applicable product fees, ATM terms, limits, opening-funding terms, and benefit conditions were disclosed.
- Required funding is actually verified, if applicable.
- The customer supplied final, product-specific consent.
- The `open_bank_account_4821` result is retained and accurately communicated.
