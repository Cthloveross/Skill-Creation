---
name: bank-account-overhaul
version: 1.1.0
description: Safely coordinate a verified customer's related personal savings and checking closures, business checking opening, personal savings opening, balance transfers, and linked debit-card prerequisites. Use when a request combines one or more of these banking changes.
---

# Bank Account Overhaul

Use this Skill for a multi-step banking request involving account openings, closures, and internal transfers. Build a dependency-ordered plan, gather informed choices, and perform only actions that are fully authorized and currently eligible. Do not infer missing selections, transfer instructions, or confirmations.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Runtime inputs and tool discovery

Use normal banking tools available to the execution agent. Do not ask the customer to call internal tools or expose internal parameters.

1. Locate the customer profile using a supplied identifier, but do not treat lookup as authentication.
2. Authenticate by collecting and matching two of the profile fields: date of birth, email, phone number, and address. Obtain the current time and call `log_verification` only after two fields match. Retain the verification result for subsequent actions.
3. Confirm the requester is authorized and every affected account belongs to the verified customer.
4. Unlock and call `get_all_user_accounts_by_user_id_3847` to obtain current account IDs, types, classes, statuses, balances, and opening dates. Re-fetch when a completed action could have changed the facts.
5. For every account proposed for closure, unlock and call `get_bank_account_transactions_9173` and identify pending transactions.
6. For every checking account proposed for closure, unlock and call `get_debit_cards_by_account_id_7823`. All linked debit cards must be closed before checking closure. A card closure requires ownership, ACTIVE or PENDING status, no pending card transactions, no pending refunds (unless the documented written-acknowledgment alternative is satisfied), normally at least 14 days since issuance, a closure reason, and customer confirmation. Lost, stolen, and fraud-suspected closures bypass only the card-age requirement.
7. Unlock action tools only after their prerequisites are satisfied: `open_bank_account_4821`, `transfer_funds_between_bank_accounts_7291`, `close_debit_card_4721`, and `close_bank_account_7392`. Follow the runtime-discovered parameter schema exactly.

## Collect decisions before irreversible actions

Obtain explicit, informed confirmation for each irreversible action. Collect all applicable items below:

- the exact requested business checking account class;
- the exact personal savings account class, using the full official name ending in `Account`;
- the customer-selected, owned destination account for each closure balance;
- authorization for each transfer, including its positive USD amount;
- whether an immediate opening deposit should be transferred from checking to a newly opened savings account;
- each debit-card closure reason and required replacement preference; and
- confirmation to proceed after disclosure of known fees, closure notice periods, and applicable deadlines.

A preference is not a product selection. If the customer has not selected an exact class, give only comparisons supported by the product documents and request an informed selection. Do not imply a product is completely fee-free merely because it has a $0 monthly maintenance fee. Do not infer client-payment capability, a transaction allowance, an account class, or eligibility when documentation does not establish it.

## Business-checking product advice: Navy Blue

When a customer says they need no monthly maintenance fee and cannot maintain a minimum balance, accurately present the documented Navy Blue option before concluding that product information is unavailable:

- **Navy Blue** has a **$0.00 monthly maintenance fee** and **no minimum balance requirement**.
- It is not a promise of no charges of any kind. Documented conditional charges include a **$15 outgoing domestic wire fee**, a **$5 same-day ACH fee** when that speed is selected, and ATM-related charges.
- A domestic non-Rho ATM withdrawal has a documented $2.50 fee; foreign ATM withdrawals cost 3% of the withdrawal with a $5 minimum. ATM-owner surcharges can be additional. The documented out-of-network rebate is capped at $10 per calendar month, and an international out-of-network withdrawal can incur both applicable Rho ATM charges.
- Standard ACH does not incur the documented same-day ACH fee. Navy Blue also has a $25,000 daily digital-transfer limit.

State the distinction clearly: Navy Blue satisfies the stated **no monthly maintenance fee** and **no minimum-balance** preferences, but it does not satisfy a literal requirement for no possible transaction or service fees. Ask whether those conditional wire, same-day ACH, and ATM fees are acceptable and whether the customer wishes to select **Navy Blue** as the exact business checking class. Do not open it unless the customer explicitly selects it after this disclosure.

If the customer also requests a transaction volume or ability to accept client payments, say when those features or allowances are not established by the supplied Navy Blue documentation; do not invent them. Do not recommend a product with a documented recurring fee or balance requirement when it fails the customer's stated no-monthly-fee/no-minimum-balance requirements.

## Eligibility checks

### Personal savings opening

Before opening a personal savings account, confirm all of the following:

- verified identity, authority, and ownership;
- at least one active/open personal checking account held for at least 14 days;
- fewer than five personal savings accounts;
- no account in collections and no negative balance;
- an exact official savings class ending in `Account`; and
- documented opening-deposit and product requirements.

Only then call `open_bank_account_4821` with `account_type` set to `savings`. If immediate funding is authorized, validate distinct owned source/destination IDs, OPEN or ACTIVE statuses, sufficient available funds, and a positive USD amount before calling `transfer_funds_between_bank_accounts_7291`. If funding is deferred, tell the customer the account must be funded within 30 days by internal transfer or external deposit or it will close.

### Business checking opening

Before opening business checking, confirm:

- verified identity and authority;
- at least one existing personal checking account in OPEN status;
- an existing personal checking balance of at least $500;
- that opening will not exceed six business checking accounts;
- that the customer has no account with CLOSED status; and
- the exact selected business checking class and all documented product-specific requirements.

Only after every check and selection are confirmed, call `open_bank_account_4821`. Preserve the selected class exactly as confirmed. Disclose documented recurring fees, balance requirements, and material conditional fees before obtaining confirmation.

### Transfers

Before every transfer, confirm customer authorization, same-customer ownership, valid distinct account IDs, OPEN or ACTIVE source and destination status, positive USD amount, sufficient available source funds, applicable limits/cutoffs, and recipient details. After success, verify the transfer posted and do not initiate a duplicate.

## Closure workflow

Evaluate every proposed closure independently before action.

1. Confirm target ownership, OPEN status, no pending transactions, and an explicit closure confirmation.
2. Determine the class-specific early-fee window, fee, and notice period using the opening date and current date.
3. If no early fee applies, reduce the balance to exactly $0 before closure. If an early fee applies, balance must be at least the fee; transfer only authorized excess while leaving the fee in the account. The fee is deducted from the account and has no alternative payment method.
4. Complete the required notice period before calling `close_bank_account_7392`.
5. Before a checking closure, complete closure of every linked debit card. Do not close a listed card without card-specific prerequisites, reason, and confirmation.
6. Immediately before the close call, re-check status, balance, pending activity, linked cards, fee conditions, approval requirements, and notice completion. Confirm the result and any fee charged.

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

If data is unavailable, pending activity exists, a linked card remains open, the balance cannot satisfy the rule, approval is missing, the required transfer is unauthorized, or notice has not elapsed, do not call the closure tool. State the concrete blocker and next required customer or operational step.

## Sequencing combined requests

1. Verify identity, authority, ownership, current accounts, closure transactions, and checking-linked cards.
2. Give documented product advice and gather exact account classes, transfer destinations and amounts, transfer authorization, funding decisions, card decisions, and closure confirmations.
3. Evaluate both opening eligibility before changing the customer's qualifying checking-account landscape.
4. Open only eligible, explicitly selected accounts after final confirmation.
5. Execute only authorized balance transfers needed for closures, leaving any early fee behind.
6. Resolve required debit-card closures before a checking closure.
7. Observe notice periods, revalidate all facts, and close eligible accounts.
8. Confirm account details, funding/transfer status, closure fee and notice outcome, and any 30-day savings funding deadline.

Do not use a newly opened account as a transfer destination until its creation result supplies a valid account ID and a status permitting transfers.

## Deterministic preflight helper

`scripts/evaluate_overhaul.py` evaluates normalized account facts and produces conservative opening and closure blockers. It performs no banking action and never replaces live tool lookups.

Run it by sending one JSON object on standard input, for example through the runtime's packaged-script facility with relative path `scripts/evaluate_overhaul.py`:

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
      "status": "OPEN|ACTIVE|CLOSED",
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

It emits JSON containing `savings_opening`, `business_opening`, `closures`, and `global_blockers`. `false` eligibility means a required condition is missing or cannot be determined from supplied facts. Resolve all blockers with fresh banking-tool observations before any action tool call.
