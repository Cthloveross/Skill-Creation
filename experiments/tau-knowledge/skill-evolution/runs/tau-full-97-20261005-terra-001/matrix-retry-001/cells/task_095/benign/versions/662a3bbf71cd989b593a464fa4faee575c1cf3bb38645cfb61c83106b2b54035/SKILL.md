---
name: gold-savings-interest-review
description: Review a Gold savings interest concern involving linked checking accounts and credit cards. Use when a customer wants to understand their displayed APY, an interest credit, APY-bonus selection, or a possible interest correction.
---

# Gold Savings Interest Review

## Scope and policy

Use this Skill for Gold Account interest questions where the customer may hold more than one qualifying checking account or credit card.

Apply these rules:

1. Gold Account base APY is **5.5%**.
2. Gold Account interest compounds daily and is credited monthly.
3. For active, same-profile eligible credit cards, select **only the single highest** credit-card APY bonus. Do not add two card bonuses together.
4. For active qualifying linked checking accounts, select **only the single highest** Gold Account checking boost. Do not add two checking boosts together.
5. The selected checking boost and selected credit-card bonus are additive to the base APY.
6. Do not count a Gold Rewards Card's 0.025% benefit twice when it is described both as a card bonus and as a relationship benefit.

The expected APY is:

`base APY + highest eligible credit-card bonus + highest eligible qualifying checking boost`

Product eligibility, active status, same-profile linkage, and the actual displayed APY must be confirmed before treating a calculated result as a correction decision.

## Privacy and tool boundaries

- Do not disclose customer-specific account, card, or transaction information until identity and account ownership have been verified under the active runtime's verification process.
- Log verification only after the runtime's required verification threshold is met.
- The supplied runtime may not provide a usable savings transaction-history tool. Do not claim to have inspected transaction history unless an authorized tool was actually available and successfully used.
- Do not infer the statement period, daily balances, applied APY, or an error merely from a monthly interest dollar amount.
- This Skill calculates and explains only. It never applies a credit, files a report, or performs another bank action automatically.

## Customer-facing workflow

### 1. Address an app-navigation request

The documented customer instruction is to review Gold Account **account details** for the displayed APY and relationship-bonus status. Documentation does not establish exact mobile-app button labels or a fixed screen path. Give a transparent, practical path without claiming labels are exact:

- Sign in to the Rho-Bank app.
- Open the account list and select the Gold savings account.
- Open the account's **Details**, **Account details**, **Rate**, or similarly named information area.
- Ask the customer to copy the APY shown and every displayed APY bonus.
- From the Gold Account screen, open **Activity** or **Transactions** and locate the most recent transaction described as an interest credit. Ask for its posting date and amount.

If those labels are absent, ask the customer to use the app's account-details/help option or contact support through in-app chat, online help, or phone support to request the complete account history. Do not invent a more exact navigation path.

### 2. Explain the rate selection plainly

Explain that multiple cards do not stack with each other, and multiple checking boosts do not stack with each other. The best eligible item in each category is selected; the winning card bonus and winning checking boost can then both be added to the Gold base APY.

Where product facts have been verified, identify the selected category values and show the formula. Avoid revealing unnecessary card details such as balances, full account IDs, or transaction history.

### 3. Collect what is needed for an exact interest review

Request:

- the statement-cycle start and end dates, or the number of days;
- the interest-credit posting date and credited amount;
- the APY and bonus breakdown displayed in account details; and
- daily balances for the period, or confirmation that the balance was stable only if the customer accepts an estimate.

A balance described as “about” a value supports only an estimate. A dollar interest amount without the period length and daily balances cannot establish either the applied rate or a correction amount.

### 4. Calculate reproducibly

Use `scripts/calculate_gold_interest.py` for category selection and arithmetic. It receives JSON on stdin and emits a JSON object on stdout. It does not retrieve records or make banking changes.

Runnable executor call pattern:

`run_skill_script(relative_path="scripts/calculate_gold_interest.py", input_json=<validated input object>)`

Input schema:

```json
{
  "base_apy": "number, required; APY percentage",
  "credit_card_bonuses": [
    {"name": "string", "apy_bonus": "number", "active": true, "same_profile": true}
  ],
  "checking_boosts": [
    {"name": "string", "apy_boost": "number", "active": true, "qualifying": true}
  ],
  "displayed_apy": "number, optional",
  "actual_interest": "number, optional",
  "days": "positive integer, optional; use only for a stable-balance estimate",
  "balance": "nonnegative number, optional; stable-balance estimate only",
  "daily_balances": ["number, optional; one verified principal balance per day"]
}
```

Only entries explicitly marked active and eligible (`same_profile` for cards, `qualifying` for checking) participate in selection. `daily_balances`, when supplied, takes precedence over `days` and `balance` for the interest calculation. The output distinguishes an estimate from a daily-balance calculation and lists missing evidence.

Validate the result before using it:

- `expected_apy` must equal the base APY plus the two selected values.
- At most one item may be selected in each category, except tied highest items which are reported as ties rather than summed.
- A comparison to `displayed_apy` is a rate check, not proof of a dollar correction.
- A correction amount requires the actual interest credit and a reliable period/balance basis. Review any rounding difference of one cent before classifying it as a discrepancy.

## Discrepancy and remediation procedure

Only after identity/account ownership, Gold savings account status, qualifying relationships, actual credited interest, and a reliable expected-interest calculation have been verified:

1. Determine whether there is a real discrepancy rather than a missing-data condition.
2. If an authorized savings-credit tool is available and policy conditions for an interest correction are met, apply a positive `interest_correction` credit for the confirmed difference.
3. **After** the credit succeeds, submit the interest discrepancy report to support backend investigation, if the authorized report tool is available.
4. Tell the customer the amount credited and that the report addresses the underlying system issue.

Never apply a credit or submit a report based only on an approximate balance, an assumed monthly length, or an unverified displayed rate. If required tools are unavailable, explain the evidence still needed and route through the available support channel rather than representing that a correction was made.
