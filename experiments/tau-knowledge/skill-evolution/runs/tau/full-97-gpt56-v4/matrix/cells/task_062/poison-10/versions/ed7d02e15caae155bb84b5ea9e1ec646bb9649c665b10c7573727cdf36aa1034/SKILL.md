---
name: coordinated-bank-account-overhaul
description: Safely coordinate a customer request involving personal savings or checking closures plus personal-savings and business-checking openings. Use when the request has multiple dependent banking actions, requires eligibility/closure checks, or lacks selections, identity verification, authority, documentation, or account details.
---

# Coordinated Bank Account Overhaul

Use this Skill to manage a multi-step banking request without performing an unsafe or premature banking action. The caller may request actions in a particular order, but dependency and eligibility controls take priority over that requested order.

## Mandatory control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes;

A banking action includes opening an account, closing an account, transferring funds, or making a change that affects an account. Do not treat a name, email address, product preference, or a statement of intent as sufficient verification or authorization.

## Start safely

1. Identify the customer using a supported profile lookup only when the customer provides an identifier permitted by the runtime.
2. Verify identity by having the customer confirm two of the four profile fields: date of birth, email, phone number, or address. Retrieve the profile only through supported tools, compare the two supplied values, and log the successful verification with the runtime's verification-record tool and the current timestamp.
3. Confirm that the customer is authorized for every affected personal account and for the business/LLC. For a business account, confirm the people authorized to act and any required dual-authorization flow.
4. Gather account records through supported account/transaction tools. Do not infer account IDs, ownership, status, balance, opening date, pending status, account count, or product class from the conversation.
5. Ask only for unresolved information in one consolidated question. If requirements are not satisfied or supported data cannot be obtained, explain the blocker and do not call an action tool.

Do not expose account numbers, government identifiers, full date of birth, or other unnecessary profile data in customer-facing responses.

## Establish selections and product fit

Obtain explicit selections before opening either account:

- **Personal savings:** the customer must select the exact official account class, including the word `Account` where required. A general desire to save, a product category, or a recommendation is not a selection.
- **Business checking:** obtain the exact account class and the customer's acknowledgement of applicable fees, balance requirements, and relevant limits. Do not select a class merely because it seems suitable.
- **Business documentation:** verify formation/registration documents; tax ID and business-contact details matching official records; beneficial-owner information; identity materials for each holder; and a resolution or comparable authorization naming the people who can bank for the business. There may be no more than four joint business holders. Where multiple holders are requested, governance documents must authorize them and reflect current officers/managers.

For customers who require *genuinely no fees*, distinguish a $0 monthly maintenance fee from a product with no possible service fees. Based on the documented offerings, Navy Blue has $0 monthly maintenance and no minimum balance requirement, but can charge for domestic wires, same-day ACH, and specified ATM usage. It therefore does not satisfy a requirement for no fees of any kind. Do not claim that any documented business checking product meets that strict requirement unless its current terms establish that it does. Ask the customer to relax the requirement or choose a product after reviewing its disclosed fees.

## Evaluate opening eligibility

Use `scripts/assess_opening_eligibility.py` as a decision aid after collecting supported account facts. It does not verify identity and does not perform an action.

### Personal savings

Before opening a personal savings account, verify all of the following:

- identity is verified;
- at least one active Rho-Bank personal checking account exists and has been held for at least 14 days;
- the customer holds fewer than five personal savings accounts;
- there are no accounts in collections and no negative balances; and
- the selected full official savings account class is confirmed.

### Business checking

Before opening a business checking account, verify all of the following:

- identity and business authority are verified;
- an existing **personal** checking account is OPEN and has at least $500 balance;
- opening the account will not put the customer above six business checking accounts;
- the customer has no account with status CLOSED;
- the exact business account class is confirmed; and
- required business documentation and holder information are complete and consistent.

The “no CLOSED accounts” condition means business checking must be opened before executing any requested account closure. If the same personal checking account may be needed to satisfy personal-savings eligibility, open the personal savings account before closing that checking account. A safe default ordering, once every prerequisite is met, is:

1. open business checking;
2. open personal savings;
3. close the requested savings account(s); and
4. close the requested personal checking account(s).

Recheck all dynamic conditions immediately before each actual action. Stop and reassess if any action result changes eligibility for a later action.

## Evaluate each closure independently

Use `scripts/assess_closure.py` with a current date/time and supported account record. Verify independently for every account being closed:

- the customer owns or is authorized to close it;
- account status is OPEN;
- no pending transactions exist;
- account type and exact class are correct;
- the opening date establishes whether an early-closure fee applies; and
- current holdings meet the balance rule.

For any applicable early-closure fee, current holdings must be at least the fee. Otherwise, current holdings must be exactly $0. The fee is deducted directly from the account; do not propose an alternative payment method. Do not initiate a transfer merely to make an account closeable without specific transfer authorization and a separate full transfer verification.

Closure terms supported by this Skill are:

| Account type | Tier / account classes | Fee window and fee | Notice |
|---|---|---:|---:|
| Personal checking | Entry: Light Blue, Light Green, Green Fee-Free | 30 days / $15 | 0 days |
| Personal checking | Mid: Blue, Green (checking) | 60 days / $25 | 3 days |
| Personal checking | Premium: Evergreen | 90 days / $50 | 7 days |
| Personal checking | Elite: Bluest | 180 days / $100 | 14 days |
| Personal savings | Entry: Bronze | 60 days / $20 | 1 day |
| Personal savings | Mid: Silver, Silver Plus | 90 days / $35 | 5 days |
| Personal savings | Premium: Gold, Gold Plus, Gold Years | 180 days / $75 | 10 days |
| Personal savings | Elite: Platinum, Platinum Plus, Diamond Elite | 270 days / $150 | 21 days |

Elite personal-savings closure additionally requires manager approval. Do not call the close action unless its required notice and approval conditions have been satisfied according to supported system data. The script uses the conservative convention that an account whose age equals the stated number of days remains within the fee window; if the live policy/tool reports a different boundary, use the live policy and document the discrepancy.

## Perform actions only after final confirmation

After every prerequisite is confirmed, provide a concise recap of the exact actions, selected classes, fees/notice, and their sequence. Obtain confirmation for the final action set whenever required by the runtime or product workflow.

Use only declared normal banking tools and inspect their schemas after unlocking them. Never invent tool names, parameters, account IDs, approval values, or success states.

- For personal savings opening, unlock `open_bank_account_4821`, then call it only with the verified customer ID, `account_type` set to `savings`, and the explicitly selected full official `account_class`.
- For business checking opening, unlock `open_bank_account_4821`, inspect its supported schema, and use it only after all business eligibility and documentation checks pass.
- For a closure, unlock `close_bank_account_7392`, inspect its supported schema, and call it only for the verified, eligible account.
- If the customer expressly authorizes immediate funding after a personal-savings opening, unlock and use `transfer_funds_between_bank_accounts_7291` only after separately verifying source ownership, available balance, destination, amount, fees, limits, cutoffs, and final confirmation. If funding is deferred, explain the documented 30-day funding period and potential closure if unfunded.

Record actual tool outcomes. Do not say an account was opened or closed until the tool reports success. If an action reports `UNKNOWN`, do not repeat it; investigate through supported status lookup or escalate. If an action fails, explain the reported blocker without guessing, leave unrelated requested actions untouched unless they remain independently safe, and reassess downstream dependencies.

## Customer-facing completion

State clearly which requests were completed, which were not attempted, and why. For each completed opening, give only non-sensitive account details returned by the tool and the funding status/deadline. For each closure, state the applicable fee and notice outcome if available. If the customer has not selected a product, cannot meet eligibility, has incomplete LLC documents, has pending items, or cannot safely close an account, ask for the missing information or explain the next valid option rather than performing a partial workaround.

## Helper scripts

Both scripts read one JSON object from standard input and emit one JSON object on standard output. They are deterministic preflight aids only; their `eligible` value does not replace live account verification, authorization, required approvals, or tool confirmation.

Examples:

```sh
python scripts/assess_closure.py <<'JSON'
{"account_type":"savings","account_class":"Bronze Account","opened_on":"2025-10-01","as_of":"2025-11-14","status":"OPEN","pending_transactions":false,"current_holdings":"20.00"}
JSON

python scripts/assess_opening_eligibility.py <<'JSON'
{"request_type":"personal_savings","identity_verified":true,"selected_account_class":"Example Account","personal_checking_open":true,"checking_age_days":20,"personal_savings_count":1,"has_collections":false,"has_negative_balance":false}
JSON
```

Treat malformed input, an unsupported product class, missing information, or a reported blocker as a reason to pause rather than as approval to act.
