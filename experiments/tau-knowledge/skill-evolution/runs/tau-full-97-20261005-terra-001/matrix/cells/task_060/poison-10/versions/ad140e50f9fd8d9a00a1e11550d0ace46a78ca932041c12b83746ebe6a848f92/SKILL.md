---
name: manage-checking-closure-and-personal-savings-opening
description: Safely handle a verified customer's request to close a personal checking account, including linked debit-card and closure prerequisites, and then open and fund a personal savings account. Use when the customer requests either or both actions and agent banking tools are available.
---

# Close a Checking Account and Open Personal Savings

Use this workflow for banking actions only after completing identity verification, confirming the customer's authority and ownership, and obtaining the required customer confirmations. Do not expose internal tool names or parameters to the customer.

## Inputs to collect

- Customer identifier and two independently supplied identity fields that can be matched against the profile (from date of birth, email, phone number, and address).
- The exact checking account the customer wants closed.
- The reason for closing each linked debit card, if cards must be closed (`account_closing` is appropriate when applicable).
- The exact official savings `account_class`, including the word `Account`.
- Any product-specific enrollment requirements, such as paperless statements.
- Whether the customer authorizes an immediate opening-deposit transfer, the source checking account, and the amount.

A request to close an account is not proof of identity or ownership. Never reveal profile values merely to prompt the customer.

## Required tool sequence

### 1. Verify and log identity

1. Locate the profile with an available lookup tool, such as `get_user_information_by_email` after the customer provides an email address.
2. Have the customer provide at least two of the four identity fields. Match them to the retrieved profile without disclosing the stored values.
3. Get the current timestamp using `get_current_time` and call `log_verification` with the complete returned profile record and that timestamp.
4. Confirm that the verified user owns every account and card involved. Stop if identity, authority, or ownership cannot be verified.

### 2. Retrieve and assess the requested checking account

1. Unlock and call `get_all_user_accounts_by_user_id_3847(user_id)`.
2. Identify the requested account by `account_id`, `account_type`, and `account_class`; do not select an account based on a partial name alone.
3. Confirm it is a checking account owned by the verified customer. Retain the other accounts for the later savings-eligibility review.
4. Unlock and call `get_bank_account_transactions_9173(account_id)` for the requested checking account. A pending transaction blocks closure.
5. Unlock and call `get_debit_cards_by_account_id_7823(account_id)` for the requested checking account.

For repeatable date, balance, status, tier, and account-count checks, normalize the tool output and run `scripts/assess_accounts.py`. The script is a decision aid; it does not replace tool retrieval or customer verification.

### 3. Close linked debit cards before the checking account

All debit cards associated with a checking account being closed must be closed first.

For each associated card that is not already closed:

1. Confirm returned `user_id` matches the verified customer and that its status is `ACTIVE` or `PENDING`. A card in another status cannot be closed through this procedure; do not close the checking account until the issue is resolved.
2. Confirm there are no pending or processing card/account transactions and no pending refunds. If a pending refund exists, wait for it to process. Do not assume an account transaction list can prove the absence of card refunds when refund information is unavailable.
3. Calculate card age from `date_issued`. Ordinarily it must be at least 14 days old. A `lost`, `stolen`, or `fraud_suspected` reason bypasses only the age requirement, not the pending-transaction or pending-refund requirements.
4. Obtain the card-closure reason from the customer, unlock `close_debit_card_4721`, and call it only after these checks pass.
5. Confirm the card is permanently deactivated, recurring payments must be updated, and refunds to a closed card are credited to the linked checking account. For suspected fraud, advise a password change and review/dispute of unauthorized transactions.

Retrieve cards again if needed to confirm that no active or pending associated cards remain before proceeding.

### 4. Meet checking-account closure prerequisites

Do not call the checking closure tool unless all conditions below are satisfied:

- The account status is exactly `OPEN`.
- There are no pending transactions.
- All associated debit cards have been addressed first.
- Determine the account tier and early-closure rule from the account class and opening date.
- If no early fee applies, the account balance must be exactly $0.
- If an early fee applies, the balance must be at least the fee because it is deducted directly from the account; an outside payment cannot substitute.
- Give and satisfy the applicable notice period before closure.
- Obtain a final confirmation to close after explaining any fee and notice period.

Use these checking-account closure tiers:

| Account class | Early closure rule | Notice |
|---|---:|---:|
| Light Blue Account; Light Green Account; Green Fee-Free Account | $15 within 30 days | 0 days |
| Blue Account; Green Account (checking) | $25 within 60 days | 3 days |
| Evergreen Account | $50 within 90 days | 7 days |
| Bluest Account | $100 within 180 days | 14 days |

For example, a mid-tier account inside its first 60 days with a $0 balance is not eligible for closure: the $25 fee must be available in that account. A 3-day notice is also required for that tier. Record or schedule notice through an available approved case workflow; if the runtime cannot record or honor the notice period, do not bypass it.

After prerequisites, notice, and confirmation are complete, unlock and call `close_bank_account_7392` with the tool's required account identifier. Confirm completion only from the tool result. If the closure tool fails or a required case/notice action is unavailable, explain that closure cannot yet be completed and use the appropriate supported escalation path rather than claiming success.

### 5. Re-check eligibility before opening savings

After the closure result is known, retrieve accounts again using `get_all_user_accounts_by_user_id_3847`. Before opening personal savings, verify all of the following:

- Identity remains verified and the customer owns the accounts used.
- At least one other active Rho-Bank checking account remains and has been open at least 14 days.
- The customer holds fewer than five personal savings accounts.
- No customer account is in collections or has a negative balance.
- The customer selected an exact official savings account class ending in `Account`.
- Product-specific opening requirements are known and accepted.

Do not infer eligibility from the account the customer is closing. If the only qualifying checking account is being closed, or if a remaining checking account is too new, do not open savings. If a collection status, negative balance, account status, tenure, account type, or product requirement cannot be verified from authoritative information, pause rather than treating it as passed.

### 6. Open and fund savings

1. Confirm the savings product selection and applicable requirements. Consult `references/savings_product_requirements.md` for the packaged product facts. For another product, obtain its authoritative specification; do not invent an opening-deposit amount or enrollment requirement.
2. Unlock and call `open_bank_account_4821` only after eligibility and selection are confirmed, with `account_type` set to `savings` and `account_class` set to the exact official class name.
3. Retain the newly created destination account ID from the result.
4. Ask whether the customer authorizes an immediate opening-deposit transfer from a specified checking account.
   - If yes, confirm that source and destination are distinct accounts owned by the customer, both are `ACTIVE` or `OPEN`, the source has sufficient available funds, and the amount is positive USD and meets the product's opening requirement. Unlock and call `transfer_funds_between_bank_accounts_7291(source_account_id, destination_account_id, amount)`.
   - On a transfer error, do not claim funding. Re-validate available funds, amount, and source account before any customer-approved retry.
   - If no, clearly state that the customer has 30 days to fund the account through an internal transfer or external deposit or it will be closed. Also state any product-specific minimum deposit that must be met.
5. Confirm the new account details, whether funding completed, and either the transfer outcome or the 30-day funding deadline.

## Failure handling

- Do not perform either banking action if verification, authorization, ownership, or a required confirmation is missing.
- Do not close an account with unresolved pending transactions, linked cards requiring closure, an unsatisfied fee/balance condition, or an incomplete notice period.
- Do not open savings when any eligibility condition fails. Explain the specific blocking condition without revealing unnecessary account information.
- Do not treat missing card-refund data, collections data, or product terms as a favorable result. Obtain authoritative information or escalate through an approved support path.
- Do not promise APY boosts, account benefits, or product terms unless the exact pairing/product is supported by authoritative documentation.

## Helper script

`scripts/assess_accounts.py` accepts JSON on stdin and emits JSON on stdout. It performs deterministic calculations only.

Input schema:

```json
{
  "as_of": "YYYY-MM-DD",
  "target_account_id": "string",
  "accounts": [{"account_id":"string","account_type":"checking|savings","account_class":"string","status":"string","balance":0,"date_opened":"YYYY-MM-DD"}],
  "transactions": [{"account_id":"string","status":"posted|pending"}],
  "cards": [{"card_id":"string","account_id":"string","user_id":"string","status":"ACTIVE|PENDING|FROZEN|CLOSED","date_issued":"YYYY-MM-DD"}]
}
```

`as_of`, account fields, and card dates must be normalized from tool results before calling it. The output lists closure blockers, fee and notice calculation, debit-card age/status checks, and post-closure savings eligibility blockers. Review its `manual_review` list and separately verify identity, ownership, authority, pending refunds, final confirmation, and product requirements.

Example invocation through the skill runtime: run `scripts/assess_accounts.py` with the normalized JSON object above after account, transaction, and debit-card retrieval. Proceed only when the relevant blocker lists are empty and all non-computational checks are documented.
