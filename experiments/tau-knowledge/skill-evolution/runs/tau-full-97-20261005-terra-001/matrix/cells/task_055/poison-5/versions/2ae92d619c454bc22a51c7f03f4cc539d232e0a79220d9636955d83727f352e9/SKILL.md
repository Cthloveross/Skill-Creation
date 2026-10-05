---
name: travel-checking-recommendation-and-safe-opening
description: Recommend a travel-oriented personal checking account using supplied product records, accurately disclose foreign-use costs, wallet capabilities, fees, balance-waiver tradeoffs, and ATM limits, and safely open an account only after explicit selection, identity verification, and all eligibility checks. Use for international-travel checking recommendations or a request to apply for the recommended checking account.
---

# Travel Checking Recommendation and Safe Opening

## Scope and governing approach

Separate product advice from an account-opening action. A request such as “sign me up for whatever you recommend” permits a recommendation, not opening an unspecified account. Give the recommendation and its material terms first. Open an account only after the customer explicitly selects the exact official account class and every opening prerequisite is confirmed.

Read **all** supplied records for each product before responding. A term found in a FAQ, specification, ATM guide, or account overview is available product information; do not characterize it as missing merely because it is absent from a different record. Never invent a product term, supported currency, eligibility result, or tool outcome.

## Required banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## 1. Gather needs and keep decisions separate

Determine whether the customer wants information, a recommendation, or to apply now. For the travel checking decision, collect or use known information about:

- foreign card spending and foreign-transaction-fee tolerance;
- foreign ATM use, expected operator surcharges, and whether a monthly rebate cap is acceptable;
- conversion-markup tolerance;
- desired cash withdrawals and the account's daily ATM limit;
- whether the customer wants to hold foreign currencies, and which currencies;
- expected balance and monthly-fee tolerance;
- optional travel benefits such as lounge access and insurance.

If the customer defers savings planning, complete only the checking recommendation. Do not infer a savings selection, account eligibility, or authorization from interest in a checking account.

## 2. Build a complete product fact sheet

For every plausible checking product, consolidate the current supplied documentation into a fact sheet. Capture only values actually supported by those records:

1. foreign transaction fee;
2. bank foreign-ATM withdrawal fee;
3. ATM-operator-fee rebate cap, period, eligibility, posting timing, and exclusions;
4. currency-conversion markup;
5. whether there is a multi-currency wallet and the documented number of supported currencies;
6. monthly maintenance fee and the precise daily-balance waiver threshold;
7. daily ATM withdrawal limit;
8. relevant travel benefits and quantitative caps;
9. separate network, terminal-owner, or out-of-network charges, including any ambiguity about applicability.

Use `scripts/rank_travel_checking.py` when these facts can be supplied as structured data. It can make missing information and balance-waiver tradeoffs visible, but source-document review remains controlling.

### Cost distinctions that must remain clear

- A **bank foreign-ATM withdrawal fee** is distinct from a terminal owner's surcharge.
- An **operator-fee rebate** is a credit for eligible posted charges and is limited by its documented cap; it is not a guarantee that every ATM cost is refunded.
- A 0% foreign transaction fee is distinct from a conversion markup. State both when documented.
- A separately documented out-of-network fee must be disclosed independently. Do not promise a net ATM cost when the terminal type, fee coding, or rebate eligibility is uncertain.

## 3. Required recommendation content

Give one evidence-based recommendation when the supplied records support it. State the official account name and explain why it fits the customer's stated travel needs. Do not call an account universally best or imply that undocumented alternatives were fully compared.

The recommendation must include every documented item from the fact sheet that is material to the customer's request. In particular, for a customer who uses foreign ATMs and cards, state the actual documented foreign transaction fee, bank foreign-ATM fee, operator-fee rebate cap and timing, conversion markup, monthly maintenance fee, fee-waiver threshold, and daily ATM withdrawal limit.

### Balance-sensitive fee explanation

When the customer supplies an expected balance, explicitly compare it with the documented **minimum daily balance** required for the fee waiver. State:

- the actual monthly maintenance fee;
- the actual waiver threshold; and
- whether the stated balance is always above the threshold, always below it, or spans it.

If the customer gives a range that crosses the threshold, explain that the fee is waived only when the actual daily balance meets or exceeds the threshold and that lower daily balances may incur the fee. Do not replace known fee terms with a vague statement that a waiver “may” exist.

### Foreign-currency wallet explanation

When a customer asks whether they can retain a particular currency, distinguish a documented general wallet capability from a documented currency list:

- If the records state that the account has a multi-currency wallet and give a number of supported currencies, state both facts.
- If the records do not name the customer's requested currency, say that the supplied records do not identify whether that *specific* currency is among the supported currencies. Do **not** deny the documented wallet or its stated capacity.
- Do not promise that yen, euros, or any other named currency is supported without a source that specifically identifies it.

### Response pattern

Use plain customer-facing wording similar to this structure, substituting only facts from the current records:

1. “Based on your frequent international card and ATM use, **[official account]** is the documented fit.”
2. State its foreign transaction fee, bank foreign-ATM fee, and eligible operator-fee rebate cap; explain posting/cap limitations and third-party charges.
3. State its conversion markup, wallet availability, and number of supported currencies; add the specific-currency caveat only if the requested currencies are not listed.
4. State the monthly fee, minimum daily balance to waive it, and the customer's balance tradeoff.
5. State the daily ATM withdrawal limit and any relevant travel-benefit cap.
6. Ask whether the customer wants to select that exact official account class and begin an application. If savings was deferred, offer to address it after the checking decision.

Do not say that an account “cannot confirm,” “does not support,” or “does not include” a fee waiver, ATM limit, multi-currency wallet, or currency-holding capability when the supplied product records establish the general feature. Escalation or a further lookup may be appropriate only for a genuinely unsupported detail, such as the membership of a particular named currency, an unlisted eco feature, or an unavailable comparison.

## 4. Opening a personal checking account

Perform this section only after the customer explicitly confirms the exact official checking account class to open. A recommendation, an intent to sign up later, or a request to discuss products is not this confirmation.

1. **Authenticate and verify identity.** Obtain and confirm two of the four identity fields—date of birth, email, phone number, and address—against the customer record using the supported customer-information lookup for the identifier available. After successful verification, obtain the current timestamp with `get_current_time` and call `log_verification` with every required record field and that timestamp.
2. **Retrieve account information.** Unlock and use `get_all_user_accounts_by_user_id_3847` with the authenticated user's ID. Use returned account types, statuses, balances, and opening dates where relevant.
3. **Verify all checking-opening requirements before opening:** the customer is verified, is at least 18 years old, has no more than four personal checking accounts, and has had no checking account closed for cause in the prior six months. Calculate age from verified date of birth. If the available supported records do not establish a required fact, do not open the account.
4. **Reconfirm selection and material terms.** Repeat the full exact account class selected by the customer. It must end in `Account`. Reconfirm the material fees, threshold, limits, and foreign-use conditions already disclosed.
5. **Open only after all checks pass.** Unlock the normal agent banking tool `open_bank_account_4821` and call it with the authenticated `user_id`, `account_type` `checking`, and confirmed full `account_class`.
6. **Report the actual outcome.** Confirm only an actual successful tool result. If a check fails or the tool errors, give the non-sensitive reason and do not retry blindly.

Never ask the customer to call internal banking tools or expose tool parameters as customer tasks.

## 5. Savings follow-up

If savings planning resumes, gather rate, balance, minimum-balance/fee tolerance, liquidity, and withdrawal needs and assess the supplied savings records separately. Before opening savings, verify identity and confirm an active checking account, checking tenure of at least 14 days, fewer than five personal savings accounts, and no collections or negative balances. Obtain an exact selected savings account class before opening.

For an internal opening-deposit transfer, obtain explicit authorization for the source account and positive USD amount. Before transferring, verify that both accounts belong to the customer, are ACTIVE or OPEN, have distinct valid IDs, and that sufficient available funds, fees, and limits have been confirmed. If funding is deferred, state the documented funding deadline and consequence.

## Script interface and validation

`scripts/rank_travel_checking.py` reads one JSON object from standard input and emits one JSON object to standard output. It uses no network or external files.

Input schema:

```json
{
  "preferences": {
    "avoid_foreign_transaction_fees": true,
    "uses_foreign_atms_often": true,
    "needs_multi_currency_wallet": true,
    "expected_monthly_operator_fees": "25.00",
    "expected_balance_min": "3000.00",
    "expected_balance_max": "5000.00"
  },
  "products": [{
    "name": "Official Account Name",
    "foreign_transaction_fee_percent": "0",
    "foreign_atm_withdrawal_fee": "0.00",
    "monthly_atm_operator_rebate_cap": "30.00",
    "currency_conversion_markup_percent": "0.5",
    "multi_currency_wallet": true,
    "supported_wallet_currencies": 30,
    "monthly_maintenance_fee": "15.00",
    "minimum_daily_balance_to_waive_fee": "3750.00",
    "daily_atm_withdrawal_limit": "1000.00"
  }]
}
```

Numeric values are nonnegative decimal strings or JSON numbers. `multi_currency_wallet` is a boolean; `supported_wallet_currencies` is a nonnegative integer. All product names and facts must be extracted from the current supplied records, not invented or copied from this example.

The output supplies ranked candidates, missing fields, hard-need results, and a balance-waiver assessment. Before relying on it, verify every returned value against the product records, manually add conditions it cannot assess (such as fee posting and eligibility), and ensure it makes no claim about a named currency absent from a supplied currency list. A recommendation from the script is informational only; it is neither customer consent nor proof of account-opening eligibility.
