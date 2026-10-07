---
name: savings-card-net-return-advisor
description: Advise a customer who wants a personal savings account and credit card by verifying the mandatory savings-opening prerequisites, comparing supported savings/card combinations over a stated horizon, and safely completing only the actions supported by available banking tools. Use when the customer wants to maximize savings yield net of documented fees or open/fund a personal savings account.
---

# Savings and Card Net-Return Advisor

## Scope
Use this Skill for Rho-Bank personal savings recommendations, savings-account opening, and an optional immediate internal opening-deposit transfer. It also explains credit-card combinations when the documented card benefit changes savings APY. It does **not** approve or open a credit card unless a supported credit-card application tool is available.

Treat account opening and money movement as separate actions. A recommendation is not authorization to open an account, and authorization to open is not authorization to transfer funds.

## Required runtime inputs
Obtain at runtime:

- Authenticated customer identity and `user_id`.
- Identity verification: confirm any two of date of birth, email, phone number, and address against the customer record, then log verification with the current timestamp using `log_verification`.
- Customer’s desired savings balance, expected holding period, account-class choices, and whether all stated funds will remain on deposit.
- Card preferences and relevant application inputs (including income/identity information and any product-specific eligibility such as credit score or subscription).
- Whether the customer wants an immediate opening-deposit transfer, the source checking account, and the exact amount.

Do not expose account IDs, tool parameters, or internal tool instructions to the customer.

## Workflow

### 1. Retrieve and verify facts
1. Resolve the customer record using the provided name, email, or user ID. Do not treat a name lookup, a previous conversation, or a claimed account as identity verification.
2. Ask the customer to confirm two identity fields without unnecessarily disclosing them. Retrieve the authoritative profile, compare the two supplied fields, get the current time, and call `log_verification` only after two fields match.
3. Unlock and call `get_all_user_accounts_by_user_id_3847` with the authenticated `user_id`. Use its account type, status, balance, and `date_opened` fields to establish the eligibility facts below. If the lookup is unavailable or incomplete, say eligibility cannot yet be confirmed; do not open an account.
4. For an existing card-benefit calculation, retrieve card accounts with `get_credit_card_accounts_by_user`. Do not assume a card is active merely because the customer wants one.

### 2. Enforce savings-opening gates
All gates must pass before opening a personal savings account:

- identity has been verified and logged;
- at least one checking account is active;
- at least one qualifying checking account has been held for at least 14 days;
- fewer than five existing personal savings accounts exist;
- no customer account is in collections or has a negative balance.

Use the system account data rather than an uncertain customer answer for status and balances. If a condition fails, explain the specific blocker and do not call the account-opening tool. For a checking account younger than 14 days, provide the date it reaches 14 days if the opening date is known. For five savings accounts, state that the maximum has been reached.

### 3. Compare only documented, feasible products
Construct candidate savings/card combinations from the supplied product documents. Do not infer a rate, fee, or bonus from an undocumented product.

For each candidate:

- Require that the customer can meet the opening deposit and continuing-balance requirements with the stated plan. Clearly flag products whose ongoing required balance exceeds the planned balance.
- Use the applicable base APY tier for the assumed balance.
- Apply a card APY bonus only if the customer holds or is approved for the relevant card under the same profile and the product documents explicitly list that bonus.
- If several eligible credit cards apply, use only the highest card APY bonus; card bonuses never stack.
- Add an eligible checking-linked boost only for an explicitly listed checking/savings pairing. If several qualifying checking accounts exist, only the highest boost applies. Do not invent a boost for an unlisted pairing.
- Add permitted non-card bonuses only when their requirements are satisfied (for example, direct deposit).
- Subtract documented annual card fees and predictable account maintenance fees from projected interest. Do not claim an unspecified fee or waive a documented fee.
- Keep distinct customer goals separate: cash interest net of fees, rewards from spending, welcome offers, and nonfinancial features. Do not treat a spending reward as interest on savings or assume the customer will meet a spending threshold.

Use `scripts/compare_net_return.py` to perform transparent annualized comparisons after you have assembled evidence-backed candidate values. The helper is arithmetic only; the executor remains responsible for selecting accurate inputs and explaining assumptions.

If documentation contains an arithmetic inconsistency, use the stated component values and show the addition. For example, a 4.0% base APY plus a 0.5% bonus is 4.5%, not 4.75%.

### 4. Present a recommendation
Give a compact comparison that includes:

- the feasible recommended savings account and any card pairing;
- assumed deposit, APY components, estimated interest, known annual fees, and net estimated return for the stated period;
- opening and ongoing balance requirements, plus material requirements such as paperless statements;
- caveats: variable balances, loss of eligibility, unguaranteed credit approval, and that rewards require qualifying spending;
- why alternatives were excluded or ranked lower.

For a customer who requires both a card and savings account, distinguish the best savings-only return from the best combined outcome after card fees. A card that increases APY may still lower one-year net interest after its annual fee at the customer’s deposit level.

### 5. Open only after an explicit selection
After all gates pass, the customer explicitly selects a savings product, and the exact official account class is known, unlock and call `open_bank_account_4821` with:

- `user_id`: authenticated user ID
- `account_type`: `savings`
- `account_class`: exact full official account name ending in `Account`

Do not shorten or normalize the official account-class string. Report the returned account details only after a successful tool result.

### 6. Handle opening funding
Ask after successful opening whether the customer authorizes an immediate transfer of the required opening deposit from a specified checking account.

- **Authorized immediate transfer:** validate that source and new destination accounts are distinct, both are `ACTIVE` or `OPEN`, belong to the customer, and that the source has sufficient funds. Validate a positive USD amount at least equal to the documented opening minimum. Then unlock and call `transfer_funds_between_bank_accounts_7291`.
- **Transfer declined or deferred:** do not transfer. State that the account must be funded within 30 days through an internal transfer or external deposit or it will be closed. This deadline applies even where the opening minimum is $0 if the product’s opening process requires funding; describe the product’s documented minimum precisely.
- **Transfer failure:** do not claim funding succeeded. Explain the returned issue (such as insufficient funds or invalid status), offer a different eligible source or amount if permitted, and revalidate before any retry.

### 7. Credit-card request
Explain documented application requirements and terms, including credit-score requirements only when documented. Obtain normal identity and income information as required by the product. If the available runtime exposes no credit-card application action, do not simulate an application, approval, activation, or card opening; provide the documented application path and state that approval is determined after submission.

## Helper interface
Run:

```json
{"horizon_days":365,"principal":5000,"candidates":[{"name":"Example candidate","base_apy_pct":4.0,"card_bonus_apy_pct":0.5,"checking_bonus_apy_pct":0,"other_bonus_apy_pct":0,"annual_fees":50,"one_time_fees":0,"minimum_opening_deposit":100,"minimum_ongoing_balance":500,"opening_requirement_met":true,"ongoing_requirement_met":true}]}
```

with `scripts/compare_net_return.py`. The script emits JSON with each candidate’s combined APY, simple projected interest for the horizon, fees prorated only for time-based annual fees, net return, feasibility status, and ranking. Amounts are estimates using APY as an annual yield; it does not simulate daily balance changes.

Validate that every numeric input is sourced from current product documentation and that `opening_requirement_met` and `ongoing_requirement_met` reflect the customer’s actual stated funding plan. Treat a helper error or missing numeric value as a reason to correct the inputs, not as financial advice.
