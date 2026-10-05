---
name: lost-wallet-debit-card-security-and-replacement
description: Secure a verified customer's debit cards after a lost or stolen wallet report. Use this for locating cards across checking accounts, freezing eligible cards, handling the freeze-versus-permanent-close decision safely, conducting the required credit-card security check, and assessing replacement eligibility and tier-specific fees.
---

# Lost-wallet debit-card security and replacement

## Purpose and boundaries

Use this Skill when a customer reports that a wallet or debit card is lost or stolen and asks to freeze, close, or replace debit cards. A lost/stolen card is a security-sensitive event.

Do not infer card IDs, card ownership, the number of cards, a verified identity, replacement preferences, or permission for permanent closure. A freeze is reversible; a close is permanent and cannot be undone. A request to **freeze** is not authorization to close.

The supplied policy names specialized banking tools but does not publish their schemas. Before using any named specialized tool, unlock it and follow the runtime-provided schema exactly. Never invent an argument or use a guessed transaction/refund lookup tool.

## Required input at execution time

Collect or obtain at runtime:

- A customer identifier or enough identifying information to locate one customer.
- Confirmation of at least two of the four verification fields: date of birth, email, phone number, and address.
- The customer's explicit requested action for each affected card: freeze, permanent close, or both where the status transition is supported.
- For a replacement request: confirmed US domestic mailing address, delivery selection, design selection, and acceptance of applicable fees.
- Current date/time for card-age, account-age, and rolling-12-month calculations.

Known account and card results must be treated as data, not assumed from the customer's reported card count or card last four digits.

## Execution workflow

### 1. Identify and verify the customer

1. Locate the user using a provided name or email with `get_user_information_by_name` or `get_user_information_by_email`.
2. Ensure one unambiguous user is selected. If lookup is ambiguous or absent, ask for identifying information; do not disclose account/card information.
3. Ask the customer to confirm two independent fields from date of birth, email, phone number, and address. Merely having fields from a lookup is not confirmation.
4. Obtain current time with `get_current_time` and call `log_verification` only after the two-field confirmation. Send the selected user's full returned identity record and the observed timestamp.
5. If verification cannot be completed, do not reveal card details or execute freeze, close, or order actions.

### 2. Find every candidate debit card without relying on card digits

1. Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified `user_id`.
2. Retain checking accounts. Savings accounts do not support debit cards.
3. For each checking `account_id`, unlock and call `get_debit_cards_by_account_id_7823`.
4. Build the candidate set only from returned cards whose `user_id` equals the verified user and whose `account_id` equals the queried account. Record card ID, last four, status, issue reason, linked account, issued date, and account class.
5. Do not promise that there are three cards: report only the number found. Do not operate on a card with a mismatched owner or account.

### 3. Perform the lost/stolen cross-product security check

Call `get_credit_card_accounts_by_user` for the verified user after handling the immediate debit-card security request. If credit-card accounts exist, ask whether those cards were also in the wallet and offer a replacement credit card as a security precaution. If none exist, state that no Rho-Bank credit cards were found. Do not invent a credit-card action or order process not supplied by the runtime.

### 4. Freeze when this is the customer's authorized action

For each customer-authorized affected debit card:

- Verify it is owned by the customer and currently `ACTIVE`.
- Explain before action: new and recurring transactions will be declined, already-authorized pending transactions may still process, and the customer can later unfreeze through customer service or the mobile app.
- Unlock `freeze_debit_card_3892` and call it with the runtime schema (policy identifies `card_id` as required).
- Confirm success only from the tool result.

Do not call freeze for `PENDING`, `CLOSED`, or already `FROZEN` cards. Explain the applicable status rather than claiming the card was secured. A frozen card does not block ATM access merely because it is frozen; the customer must enable ATM Block separately in the mobile app if they need ATM access restricted.

### 5. Handle permanent closure separately and safely

For a confirmed lost/stolen wallet, recommend permanent closure because it is safer than an ongoing temporary freeze. Obtain clear, explicit authorization to close each selected card. Do not treat a statement such as “freeze them” as closure permission.

Before closing, validate all published requirements:

- Verified owner and matching `user_id`.
- Card status is `ACTIVE` or `PENDING`.
- No pending/processing transactions.
- No pending refunds, unless the customer provides the written acknowledgement required by policy that refunds will credit the linked checking account.
- For non-security closure reasons, card age is at least 14 days. The lost, stolen, and fraud-suspected reasons bypass only the minimum-card-age condition.

Use an authorized runtime capability for pending-transaction/refund evidence only if its name and schema are actually available. If required evidence cannot be obtained, do not falsely certify eligibility or guess a tool name; explain the blocker and leave the card frozen if it was successfully frozen.

Important status conflict: published closure requirements permit only `ACTIVE` or `PENDING`, while freeze changes an active card to `FROZEN`. Therefore never automatically unfreeze a card solely to make it closable. If the customer first authorized only freezing and later asks for closure, disclose this conflict and obtain explicit consent before any unfreeze/close sequence; proceed only if runtime policy/tool results support it.

When all conditions are met, unlock `close_debit_card_4721` and call it using its actual schema with the policy reason (use `lost` for a reported lost wallet). Confirm that closure is permanent, recurring payments need updating, and pending transactions may still settle. Do not claim that a closed card can be reactivated.

### 6. Assess and place debit-card replacements

A replacement should be handled only after permanent-closure/status prerequisites and ordering eligibility are supported by available evidence. Do not imply that freezing alone creates a replacement order.

For each requested replacement account, verify:

1. Customer remains verified and the linked account is a checking account in `OPEN` status.
2. The account has been open at least three business days, excluding weekends.
3. The verified date of birth establishes an age of at least 18.
4. Balance is at least $25.
5. There is no conflicting active card and no `PENDING` debit-card order/card for that account under the applicable ordering policy.
6. The customer confirmed a valid US domestic delivery address.
7. The requested delivery method and design are permitted for the account tier and the customer agreed to all fees deducted from the checking account.
8. Replacement history within the rolling prior 12 months is within the tier limit, or a documented allowed excess-fee route is available.

Use `scripts/replacement_policy.py` to consistently compute tier delivery/design fees, permitted delivery options, account weekday age, and replacement-history count. Supply the actual returned data; the script does not query bank systems or place orders.

Replacement count rules: count only cards with issue reasons `lost`, `stolen`, `fraud`, or `damaged` and issued within the prior rolling 12 months. Do not count `new_account`, `first_card`, `expired`, `upgrade`, or `bank_reissue`.

If the replacement limit is exceeded:

- ENTRY: the customer may wait until the oldest replacement falls outside the window or use the stated $25 excess replacement option.
- MID: the customer may wait or use the stated $15 excess replacement option.
- PREMIUM: the customer must wait; no fee option exists.
- ELITE: no limit applies.

The published order interface specifies exact `delivery_fee` and `design_fee`, but does not specify how an excess-replacement fee is passed. Do not guess a parameter or fold that fee into another field. Use only a runtime-confirmed supported mechanism; otherwise explain that the fee route cannot be completed with the available interface.

After all requirements, selections, and exact runtime parameters are available, unlock `order_debit_card_5739` and place the order using its runtime schema. Provide the tier-derived exact delivery and design fees where required. Confirm only tool-reported success, delivery window, and deducted fees. Advise that the new card activates on first PIN use, subject to the separate activation policy.

## Replacement fee reference

| Tier | Allowed replacement delivery / delivery fee | CLASSIC | PREMIUM | CUSTOM | Limit |
|---|---|---:|---:|---:|---:|
| ENTRY | STANDARD $0 | $0 | $10 | $25 | 2 / 12 months |
| MID | STANDARD $0; EXPEDITED $15 | $0 | $10 | $25 | 3 / 12 months |
| PREMIUM | STANDARD $0; EXPEDITED $0; RUSH $35 | $0 | $0 | $15 | 5 / 12 months |
| ELITE | STANDARD, EXPEDITED, RUSH all $0 | $0 | $0 | $0 | unlimited |

ENTRY replacement cards require a 48-hour wait after closure. MID, PREMIUM, and ELITE have no published post-closure wait. Do not promise RUSH for ENTRY or MID.

## Communicating incomplete cases

When a required choice is missing, ask narrowly for it: permanent-close consent, specific affected card selection if needed, confirmed domestic address, delivery method, design, or fee acceptance. If a policy condition cannot be checked with supplied data/runtime tools, state exactly which condition is unresolved and do not represent the replacement as ordered.

## Script interface and validation

Run the helper with JSON on stdin:

```json
{
  "as_of_date": "YYYY-MM-DD",
  "account_opened_date": "YYYY-MM-DD",
  "account_class": "ENTRY|MID|PREMIUM|ELITE",
  "delivery_option": "STANDARD|EXPEDITED|RUSH",
  "design": "CLASSIC|PREMIUM|CUSTOM",
  "cards": [{"issue_reason": "lost", "date_issued": "YYYY-MM-DD"}]
}
```

It emits JSON containing allowed delivery status, exact delivery/design fees, rolling-window replacement count and limit, any excess option, and whether the account has at least three weekday business days. Validate `valid_input` is true and review `blocking_reasons` before relying on its calculation. It deliberately does not validate account status, balance, identity, address, card owner, card status, pending transactions/refunds, or tool success; those require live banking data and agent checks.
