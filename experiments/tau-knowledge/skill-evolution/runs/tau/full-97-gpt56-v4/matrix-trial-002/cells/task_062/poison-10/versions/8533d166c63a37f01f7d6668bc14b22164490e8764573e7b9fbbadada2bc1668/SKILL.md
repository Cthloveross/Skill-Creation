---
name: multi_account_banking_service
summary: Safely verify a customer and coordinate personal savings openings, business checking openings, account closures, and internal funding transfers using the documented bank tools.
---

# Multi-Account Banking Service

Use this Skill when a customer asks to open, close, or fund the documented personal savings or business checking accounts. It is especially useful when several requests interact (for example, closing the only qualifying checking account before opening savings).

## Safety and sequencing

Before **every** banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

1. Treat a supplied name, email, account number, or prior conversation statement as a lookup lead, not identity verification.
2. Retrieve the profile with the appropriate user-information lookup. Ask the customer to confirm at least two of these four profile fields: date of birth, email, phone number, and address. Compare the customer-provided values to the retrieved profile.
3. After two fields match, get the current timestamp with `get_current_time` and call `log_verification` with every required profile field, the timestamp, and the user ID. Do not take account actions before this succeeds.
4. Confirm the customer is authorized to act for each personal account and, for a business account, for the business. Obtain the requested exact account class and explicit authorization for each irreversible action.
5. Build a dependency-aware plan before acting. In particular, do not close a checking account if it is needed to satisfy an opening requirement or fund a requested savings account. Explain any necessary change from the requested order and obtain the customer's agreement.
6. Never expose internal tool names, parameters, or instructions for calling tools to the customer. The agent performs qualified actions directly.

If identity cannot be verified, authority is unclear, required data or documents are missing, a required condition fails, or the available tools cannot carry out a mandatory notice/approval process, do not guess or proceed. State what is needed and, when appropriate, transfer to a human specialist.

## Discover and assess current accounts

Unlock and use `get_all_user_accounts_by_user_id_3847` with the verified user ID. It returns the account ID, type, class, status, balance, and opening date. Use it to identify all requested accounts and to evaluate account-count, status, balance, and tenure requirements.

For each account proposed for closure, unlock and use `get_bank_account_transactions_9173` with that account ID. Do not close an account with any pending transaction. Use the current time and `date_opened` to determine whether an early-closure window still applies.

Ask only for information that cannot be established from the tools or documented customer conversation. Explicitly distinguish a product recommendation from a customer-confirmed selection.

## Closing personal accounts

For each closure, confirm that the named account belongs to the verified customer, is `OPEN`, has no pending transactions, and that the customer explicitly authorizes closure after being told applicable fees and notice.

Balance rule for all documented closures:
- If an early fee applies, the account must have at least that fee in `current_holdings`; the fee is deducted from that account and cannot be paid another way.
- If no early fee applies, the account balance must be zero.

Apply the documented tier terms precisely:

| Account class | Early-fee window and fee | Notice | Extra requirement |
|---|---:|---:|---|
| Bronze Account | $20 within 60 days | 1 day | none |
| Silver Account / Silver Plus Account | $35 within 90 days | 5 days | none |
| Gold Account / Gold Plus Account / Gold Years Account | $75 within 180 days | 10 days | none |
| Platinum Account / Platinum Plus Account / Diamond Elite Account | $150 within 270 days | 21 days | manager approval |
| Light Blue Account / Light Green Account / Green Fee-Free Account | $15 within 30 days | 0 days | none |
| Blue Account / Green Account (checking) | $25 within 60 days | 3 days | none |
| Evergreen Account | $50 within 90 days | 7 days | none |
| Bluest Account | $100 within 180 days | 14 days | none |

If funds must be consolidated before closure, use an internal transfer only after validating both accounts and obtaining transfer authorization as described below. Where the available workflow lacks a way to record or wait for a required notice, do not falsely claim closure is complete; explain the notice requirement and escalate if completion is requested.

Once all closure conditions, notice, and any required approval are satisfied, unlock `close_bank_account_7392` and call it for the confirmed account. Report the actual tool outcome, not an assumed outcome.

## Opening personal savings

Before opening, verify all of the following from the account lookup and current facts:

- The customer is verified.
- At least one active Rho-Bank checking account exists and has been open at least 14 days.
- The customer has fewer than five personal savings accounts.
- No customer account is in collections or has a negative balance.
- The customer has selected an exact official personal-savings `account_class` ending in `Account`.

If any condition fails, do not open the account. Explain the specific blocker (for short checking tenure, give the eligible date if it can be calculated). Do not infer a selection from a discussion of preferences. Offer only documented product facts; if the customer's preferences do not identify one exact class, request their choice.

For example, documented products include Bronze Account (minimum opening deposit $0, no minimum balance, daily compounding, no monthly maintenance fee), Silver Account (minimum opening deposit $500, $1,000 ongoing minimum, 10 free withdrawals per statement cycle, daily compounding), and Silver Plus Account (minimum opening deposit $1,000, $2,500 ongoing minimum, 15 free withdrawals monthly, daily compounding; an $8 monthly fee may apply below $2,500). Do not claim withdrawal limits or fees that are not documented.

After eligibility, selection, and authorization are confirmed, unlock `open_bank_account_4821` and call it with the verified user ID, `account_type` set to `savings`, and the exact confirmed class. Capture the returned new account ID.

Tell the customer the required opening amount for the selected product. Ask whether they authorize an immediate transfer from a specified eligible checking account. If they decline, tell them they have 30 days to fund the new savings account through an internal transfer or external deposit or it will be closed.

## Opening business checking

Require verified identity and authority to act for the business. Obtain and review the required formation/registration records, authorization resolution or comparable authority document naming authorized actors, identity and beneficial-ownership materials for holders, and matching tax-identification and business-contact details. Business accounts can have up to four joint business account holders.

Before opening, verify:

- The customer has an existing personal checking account with status `OPEN` and a balance of at least $500.
- The customer holds no more than six business checking accounts.
- The customer has no account with status `CLOSED`.
- The exact business checking class is selected and the customer authorizes the opening.

Do not substitute a recommendation for a selection. For Navy Blue, documented facts are $0.00 monthly maintenance fee, no minimum balance, and unlimited digital transfers subject to a $25,000 daily limit. These facts do not waive the eligibility or documentation requirements.

After all conditions are met, unlock `open_bank_account_4821` and call it with the verified user ID, `account_type` set to `checking`, and the exact confirmed business class. Report only the returned result and any applicable funding information.

## Internal transfers and funding

Before calling a transfer, confirm explicit authorization, same-customer ownership, distinct source and destination IDs, both accounts in `ACTIVE` or `OPEN` status, a positive USD amount, and sufficient available source funds. Confirm the amount meets the selected account's required opening deposit when funding a new account.

Unlock `transfer_funds_between_bank_accounts_7291` and call it with `source_account_id`, `destination_account_id`, and `amount`. After success, re-check or otherwise verify the posting when available, and do not initiate a duplicate transfer. If the transfer fails, do not retry blindly; explain the reported issue and revalidate conditions before any new attempt.

## Completion response

Summarize each request separately as completed, pending, declined, or blocked. Include actual account details returned by successful actions, the funding status or deadline for a new savings account, and any remaining notice period, fee, missing document, eligibility blocker, or required customer decision. Never claim an action occurred unless its tool call succeeded.