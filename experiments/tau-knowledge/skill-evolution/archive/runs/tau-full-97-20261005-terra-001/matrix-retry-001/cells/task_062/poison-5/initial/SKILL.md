---
name: bank-account-overhaul
version: 1.0.0
description: Safely coordinate a verified customer's related personal savings and checking closures, business checking opening, personal savings opening, balance transfers, and linked debit-card prerequisites. Use when a request combines one or more of these banking changes.
---

# Bank Account Overhaul

Use this Skill for a multi-step banking request involving account openings, closures, and/or internal transfers. It converts the request into a dependency-ordered plan; it does not authorize assumptions or automatically perform banking actions.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Runtime inputs and tool discovery

Use only normal banking tools available to the execution agent. Do not give internal tools to the customer.

1. Locate the customer profile using a supplied identifier, but do not treat lookup as authentication.
2. Authenticate by collecting and matching two of the four profile fields: date of birth, email, phone number, and address. Obtain the current time and call `log_verification` only after two fields match. Retain the verification result for all subsequent actions.
3. Confirm the requester is authorized and the affected accounts belong to the verified customer.
4. Unlock and use `get_all_user_accounts_by_user_id_3847` to obtain current account IDs, types, classes, statuses, balances, and opening dates. Re-fetch data whenever a prior action could have changed it.
5. Unlock `get_bank_account_transactions_9173` for every account proposed for closure and identify any pending transactions.
6. For each checking account proposed for closure, unlock `get_debit_cards_by_account_id_7823`. All linked debit cards must be closed before the checking account can close. A debit-card closure additionally requires the card owner, ACTIVE or PENDING status, no pending card transactions, no pending refunds (unless the documented written-acknowledgment alternative is satisfied), and normally 14 days since issue. Lost, stolen, and fraud-suspected closures bypass only the card-age requirement. Obtain the card-closure reason and confirmation; use `account_closing` when that is the customer's confirmed reason.
7. Unlock action tools only after all prerequisites are met: `open_bank_account_4821`, `transfer_funds_between_bank_accounts_7291`, `close_debit_card_4721`, and `close_bank_account_7392`. Follow the runtime-discovered parameter schema exactly; do not invent parameters absent from that schema.

## Collect missing decisions before acting

Obtain explicit confirmation of each irreversible action and collect:

- exact requested business checking account class;
- exact requested personal savings account class, using its full official name ending in `Account`;
- the customer-selected, owned destination account for each closure balance;
- authorization for each transfer, including a positive USD amount;
- whether an immediate opening deposit should be moved from checking to the new savings account;
- card-closure reason and any required replacement preference; and
- confirmation to proceed after disclosing known fees, closure notice periods, and applicable deadlines.

If the customer has product preferences but has not chosen an exact class, provide only documented comparisons. Do not claim an account has no fees when documentation lists transaction, service, or conditional fees. Do not infer a transaction allowance, client-payment capability, business eligibility, or account class when the supplied product documentation does not establish it.

## Eligibility checks

### Personal savings opening

Before opening a personal savings account, confirm all of the following:

- verified identity and authority;
- at least one active/open personal checking account held for at least 14 days;
- fewer than five existing personal savings accounts;
- no account in collections and no negative account balance;
- selected official savings class ends in `Account`; and
- any documented opening deposit and product requirements.

Call `open_bank_account_4821` with `account_type` set to `savings` only after these checks and confirmed selection. If immediate funding is authorized, validate distinct owned source/destination IDs, OPEN or ACTIVE statuses, sufficient available funds, and a positive USD amount before calling `transfer_funds_between_bank_accounts_7291`. If funding is deferred, clearly state that the account must be funded within 30 days through an internal transfer or external deposit or it will be closed.

### Business checking opening

Before opening business checking, confirm:

- verified identity and authority;
- at least one existing personal checking account in OPEN status;
- the existing personal checking balance is at least $500;
- opening the new account will not exceed the six-business-checking-account limit;
- the customer has no CLOSED account; and
- the exact selected business checking account class and all product-specific requirements.

Use `open_bank_account_4821` only after eligibility and selection are confirmed. Preserve the selected class exactly as confirmed. Where the customer is considering a product, disclose documented recurring fees, minimum-balance requirements, and material transaction fees; do not treat a $0 monthly maintenance fee as a guarantee of no possible fee.

### Transfers

Before every transfer, confirm customer authorization, same-customer ownership, valid and distinct IDs, source and destination status of OPEN or ACTIVE, positive USD amount, sufficient available source funds, applicable limits/cutoffs, and recipient details. After a successful transfer, verify it posted and do not initiate a duplicate.

## Closure workflow

Evaluate each closure independently before initiating any action.

1. Confirm target account ownership, OPEN status, no pending transactions, and closure confirmation.
2. Determine its class-specific early-fee window, fee, and notice period from the table below using the account opening date and current date.
3. If no early fee applies, reduce the balance to exactly $0 before closure. If an early fee applies, the balance must be at least the fee; transfer only the excess after the customer authorizes the transfer. The fee is deducted from the account and has no alternative payment method.
4. Complete the required notice period before calling `close_bank_account_7392`.
5. For a checking closure, first complete closure of every linked debit card. Do not close a linked card merely because it is listed: validate the card-specific prerequisites and capture its reason and confirmation.
6. Re-check status, balances, pending activity, cards, and fee conditions immediately before the close call. Confirm the completed result and any fee charged.

| Account category and class | Early closure fee | Early-fee window | Notice | Extra requirement |
| --- | ---: | ---: | ---: | --- |
| Personal savings: Bronze Account | $20 | within 60 days | 1 day | — |
| Personal savings: Silver Account, Silver Plus Account | $35 | within 90 days | 5 days | — |
| Personal savings: Gold Account, Gold Plus Account, Gold Years Account | $75 | within 180 days | 10 days | — |
| Personal savings: Platinum Account, Platinum Plus Account, Diamond Elite Account | $150 | within 270 days | 21 days | manager approval |
| Personal checking: Light Blue Account, Light Green Account, Green Fee-Free Account | $15 | within 30 days | 0 days | — |
| Personal checking: Blue Account, Green Account (checking) | $25 | within 60 days | 3 days | — |
| Personal checking: Evergreen Account | $50 | within 90 days | 7 days | — |
| Personal checking: Bluest Account | $100 | within 180 days | 14 days | — |

If any required data is unavailable, pending activity exists, a linked card remains open, a balance cannot satisfy the rule, approval is missing, or a notice period has not elapsed, do not call the closure tool. Explain the concrete blocker and the next required customer or operational step.

## Recommended sequencing for combined requests

1. Verify identity, authority, ownership, and all account data.
2. Capture account classes, transfer destinations, authorizations, and closure/card confirmations.
3. Evaluate eligibility for both openings before changing the qualifying checking-account landscape.
4. Open eligible requested accounts only after final confirmation.
5. Execute authorized transfers needed to prepare closures, leaving an applicable early fee in the source account.
6. Resolve linked debit-card closures before closing a checking account.
7. Observe closure notice periods and then close eligible accounts, re-validating immediately before each call.
8. Confirm account details, transfer/funding status, fee/notice results, and any 30-day savings funding deadline.

Do not use a newly opened account as a transfer destination until its creation result supplies a valid account ID and its status permits transfers.

## Optional deterministic preflight helper

`scripts/evaluate_overhaul.py` evaluates supplied, normalized account facts and produces blockers, eligibility flags, and closure fee/notice calculations. It performs no banking action and does not replace live tool lookups.

Input JSON schema:

```json
{
  "as_of": "YYYY-MM-DD",
  "identity_verified": true,
  "authority_confirmed": true,
  "has_collections": false,
  "accounts": [
    {
      "account_id": "string",
      "account_type": "checking|savings",
      "account_class": "string",
      "customer_role": "personal|business",
      "status": "OPEN|ACTIVE|CLOSED|...",
      "balance": 0,
      "date_opened": "YYYY-MM-DD"
    }
  ],
  "selected_business_class": null,
  "selected_savings_class": null,
  "closures": [
    {
      "account_id": "string",
      "pending_transactions": false,
      "linked_card_statuses": [],
      "notice_already_satisfied": false,
      "manager_approval": false
    }
  ]
}
```

The output is JSON with `savings_opening`, `business_opening`, `closures`, and `global_blockers`. Each eligibility value is conservative: `false` means a required condition is missing or cannot be determined from the supplied data. A runtime may call the helper with the JSON object above through `run_skill_script` using relative path `scripts/evaluate_overhaul.py`. Validate that its blockers have been resolved with fresh live data before using any action tool.
