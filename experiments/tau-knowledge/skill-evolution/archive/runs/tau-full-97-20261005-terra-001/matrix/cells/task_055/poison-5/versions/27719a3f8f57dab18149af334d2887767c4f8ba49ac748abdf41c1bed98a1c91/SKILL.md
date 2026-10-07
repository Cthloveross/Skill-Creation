---
name: travel-checking-recommendation-and-safe-opening
description: Recommend a travel-oriented personal checking account from supplied product records, disclose material foreign-use, wallet, fee, balance-waiver, and ATM-limit terms, and safely open an account only after explicit selection, identity verification, and all eligibility checks. Use for international-travel checking recommendations or requests to apply for a recommended checking account.
---

# Travel Checking Recommendation and Safe Opening

## Scope and governing approach

Separate product advice from an account-opening action. A statement such as “sign me up for whatever you recommend” authorizes a recommendation only; it does not authorize opening an unspecified account. Give the recommendation and material terms first. Open an account only after the customer explicitly selects the exact official account class and all opening prerequisites are confirmed.

Read **all** supplied records for each candidate product before responding. Product information in a FAQ, specification, ATM guide, or overview is available information even if it is absent from another record. Never say that a documented feature or term is unavailable, unconfirmed, or unsupported merely because it appears in a different supplied record. Never invent a product term, a supported named currency, an eligibility result, or a tool outcome.

## Required banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## 1. Establish the decision being made

Determine whether the customer wants information, a recommendation, or to apply now. Keep checking and savings decisions separate.

For a travel-checking recommendation, use known information or collect only genuinely missing decision-relevant information about:

- foreign card spending and foreign-transaction-fee tolerance;
- foreign ATM frequency, expected operator surcharges, and tolerance for a monthly rebate cap;
- conversion-markup tolerance;
- cash-withdrawal needs and the daily ATM limit;
- desire to retain foreign currency and named currencies of interest;
- expected balance and monthly-fee tolerance; and
- optional travel benefits, including insurance or lounge access.

If the customer has already stated frequent foreign card/ATM use, an expected balance, and a wish to hold currencies, provide the supported recommendation in that response. Do not transfer to a human or defer the recommendation simply because a named-currency membership, an eco feature, a premium comparison, or a savings decision is not documented.

If savings planning is deferred, finish the checking recommendation only. Do not infer a savings selection, eligibility, or opening authorization from interest in checking.

## 2. Consolidate the complete product fact sheet

For every plausible checking product, consolidate terms across the supplied documentation. Capture only source-supported values for:

1. foreign transaction fee;
2. bank foreign-ATM withdrawal fee;
3. ATM-operator-fee rebate cap, period, eligibility, posting timing, and exclusions;
4. conversion markup;
5. whether a multi-currency wallet exists and its documented currency capacity;
6. monthly maintenance fee and exact minimum-daily-balance waiver threshold;
7. daily ATM withdrawal limit;
8. relevant travel-benefit terms and caps; and
9. separate terminal-owner, network, or out-of-network charges, including uncertainty about applicability.

Use `scripts/rank_travel_checking.py` if facts are available in its structured input format. It highlights missing terms and balance-waiver tradeoffs, but review of the product records remains controlling.

### Keep cost concepts distinct

- A **bank foreign-ATM withdrawal fee** is distinct from an ATM terminal owner's surcharge.
- An **operator-fee rebate** refunds eligible posted fees only, is subject to its stated cap and conditions, and is not a promise that all ATM costs are refunded.
- A 0% foreign transaction fee is distinct from any currency-conversion markup. State both when documented.
- If a separate out-of-network fee is documented, disclose it independently and do not promise a net ATM cost when terminal type, coding, or rebate eligibility is uncertain.

## 3. Required customer-facing recommendation

Give one evidence-based recommendation when the supplied records support one. State the official account name and why it fits the customer's actual travel priorities. Do not call it universally best or imply every unavailable alternative was compared.

For a customer who uses foreign ATMs and cards, the response **must** state all documented material terms in the same customer-facing response:

- foreign transaction fee;
- bank foreign-ATM withdrawal fee;
- operator-fee rebate cap and period, plus that eligible fees are credited/refunded only after posting when documented;
- warning that terminal-owner charges may still occur and charges above the cap or ineligible charges remain the customer's responsibility;
- conversion markup;
- multi-currency-wallet availability and documented number of supported currencies;
- monthly maintenance fee;
- minimum daily balance needed to waive that fee; and
- daily ATM withdrawal limit.

Mention any documented travel-benefit cap that is relevant to the customer's priorities. Do not omit a known monthly fee or waiver merely because the customer is focused on travel costs.

### Balance-sensitive fee explanation

When an expected balance is provided, compare it explicitly to the documented **minimum daily balance** waiver threshold. State the actual monthly maintenance fee and threshold, then explain whether the stated balance is:

- always below the threshold;
- always at or above the threshold; or
- a range that spans the threshold.

For a range spanning the threshold, explain that the fee is waived only on days the actual daily balance meets or exceeds the threshold and that lower daily balances can result in the monthly fee. Do not replace known figures with vague language such as “a waiver may apply.”

### Foreign-currency wallet explanation

When the customer asks about retaining a particular currency:

- If records document a multi-currency wallet and a supported-currency count, state both facts plainly.
- If records do not list the requested currency individually, say that the supplied records do not name individual wallet currencies and therefore do not establish whether that particular currency is included.
- Do not promise a named currency is supported without a record specifically naming it.
- Do not deny, qualify away, or characterize as unconfirmed the documented general wallet capability or its documented capacity.

### Required response sequence

Use this order, filling each item solely from current records:

1. Make the checking recommendation and tie it to the customer's international card and ATM usage.
2. Explain foreign card and ATM costs, eligible rebate mechanics, cap, and remaining third-party-cost risk.
3. Explain conversion markup and the multi-currency wallet/capacity; handle the named-currency caveat separately and narrowly.
4. Explain the maintenance fee, waiver threshold, and the customer's particular balance tradeoff.
5. State the daily ATM withdrawal limit and relevant travel benefits.
6. Ask whether the customer wants to select the exact official checking account class and begin an application. If savings was deferred, offer to discuss it afterward.

Do not say an account “cannot confirm,” “does not support,” “does not include,” or “does not provide” a monthly fee, waiver, ATM limit, multi-currency wallet, or foreign-currency-holding capability when current records establish the general feature. A further lookup or human escalation is appropriate only for a genuinely unsupported detail, such as whether a specific named currency is among an otherwise documented wallet's currencies, an unlisted eco feature, or an unavailable comparison.

## 4. Opening a personal checking account

Perform this section only after the customer explicitly confirms the exact official checking account class to open. A recommendation, general interest, intent to apply later, or a request to discuss products is not sufficient confirmation.

1. **Authenticate and verify identity.** Obtain and confirm two of the four identity fields—date of birth, email, phone number, and address—against the customer record using a supported customer-information lookup for the available identifier. After successful verification, obtain the current timestamp with `get_current_time` and call `log_verification` with all required record fields and that timestamp.
2. **Retrieve account information.** Use `get_all_user_accounts_by_user_id_3847` with the authenticated user's ID to review account types, statuses, balances, and opening dates as relevant.
3. **Verify every checking-opening requirement before opening.** Confirm the customer is verified, is at least 18 years old, has no more than four personal checking accounts, and has had no checking account closed for cause in the prior six months. Calculate age from verified date of birth. If a required fact is unavailable or a requirement is not met, do not open the account.
4. **Reconfirm the selection and material terms.** Repeat the full exact account class selected by the customer. It must use the documented official name ending in `Account`. Reconfirm the material fees, threshold, limits, and foreign-use conditions already disclosed.
5. **Open only after all checks pass.** Unlock and use the normal agent banking tool `open_bank_account_4821` with the authenticated `user_id`, account type `checking`, and confirmed full `account_class`.
6. **Report only the actual outcome.** Confirm opening only after a successful tool result. If a check fails or the tool errors, provide a non-sensitive explanation and do not retry blindly.

Never ask the customer to call internal banking tools or expose tool parameters as customer tasks.

## 5. Savings follow-up

If savings planning resumes, collect rate priorities, expected balance, minimum-balance and fee tolerance, liquidity needs, and withdrawal needs. Assess only the supplied savings records and do not select a savings product based on checking terms alone.

Before opening savings, verify identity; confirm an active checking account held for at least 14 days; confirm fewer than five personal savings accounts; and confirm no accounts in collections or with negative balances. Obtain the exact selected savings account class before opening.

For an internal opening-deposit transfer, obtain explicit customer authorization for the source account and a positive USD amount. Before transferring, verify that both accounts belong to the customer, are ACTIVE or OPEN, have valid distinct IDs, and that sufficient available funds, fees, and limits have been confirmed. If funding is deferred, state the documented funding deadline and consequence.

## Script interface and validation

`scripts/rank_travel_checking.py` reads one JSON object from standard input and emits one JSON object to standard output. It uses no network or external files.

Input schema:

```json
{
  "preferences": {
    "avoid_foreign_transaction_fees": true,
    "uses_foreign_atms_often": true,
    "needs_multi_currency_wallet": true,
    "expected_monthly_operator_fees": "decimal string or number",
    "expected_balance_min": "decimal string or number",
    "expected_balance_max": "decimal string or number"
  },
  "products": [{
    "name": "Official Account Name",
    "foreign_transaction_fee_percent": "decimal string or number",
    "foreign_atm_withdrawal_fee": "decimal string or number",
    "monthly_atm_operator_rebate_cap": "decimal string or number",
    "currency_conversion_markup_percent": "decimal string or number",
    "multi_currency_wallet": true,
    "supported_wallet_currencies": 0,
    "monthly_maintenance_fee": "decimal string or number",
    "minimum_daily_balance_to_waive_fee": "decimal string or number",
    "daily_atm_withdrawal_limit": "decimal string or number"
  }]
}
```

All product facts must be extracted at runtime from current supplied records. The output contains ranked candidates, missing fields, hard-need results, and a balance-waiver assessment. Validate every output fact against source records; manually add rebate posting and eligibility conditions; and never infer support for a named currency from wallet capacity alone. A script recommendation is informational only, not customer consent or proof of opening eligibility.
