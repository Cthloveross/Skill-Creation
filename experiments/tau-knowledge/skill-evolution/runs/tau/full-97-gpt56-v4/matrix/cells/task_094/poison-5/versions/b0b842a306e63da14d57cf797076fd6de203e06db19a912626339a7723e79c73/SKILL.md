---
name: savings-interest-discrepancy-resolution
description: Investigate and resolve a verified customer's savings-interest discrepancy. Use when a customer disputes a savings interest credit or reports a missing APY component, incorrect tier, relationship bonus, or linked-checking boost. It guides mandatory verification, account and transaction review, non-stacking bonus selection, defensible interest calculation, credit-before-report ordering, and customer communication.
---

# Savings Interest Discrepancy Resolution

Use this Skill only for a savings-interest investigation. Do not use it to change profile data, make an unsupported payment, or infer an interest shortfall from an approximate balance alone.

## Required controls and prerequisites

Before **any** banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

For this workflow specifically:

1. Identify the customer using a profile identifier (for example, email or name).
2. Verify at least two of the four identity fields: date of birth, email, phone number, and address. Compare customer-provided values to the profile rather than revealing unprovided values.
3. Obtain the current time with `get_current_time`, then call `log_verification` with the complete returned profile fields and that timestamp only after the two-field check succeeds.
4. Treat a verified identity as necessary but not sufficient: retrieve accounts and verify that the target account belongs to this customer, is an active savings account, and has the relevant savings product class.
5. Do not apply a credit, file a report, or claim an exact correction amount unless the credited interest, applicable rate, and calculation period/balance data support the amount.

If identity or ownership cannot be verified, stop and request the missing verification information. Do not disclose account data. If transaction history or required daily balance information is unavailable, explain the limitation and do not guess a credit or report value.

## Tools and ordered workflow

The named banking tools are discoverable. Unlock each tool before its first use with `unlock_discoverable_agent_tool`, then invoke it with `call_discoverable_agent_tool` and the exact JSON arguments required below.

### 1. Establish the customer and verify identity

- Use the appropriate available lookup such as `get_user_information_by_email`, `get_user_information_by_name`, or `get_user_information_by_id` to identify the profile.
- Check two customer-supplied identity fields against that profile.
- Call `get_current_time` and `log_verification` after success.
- If cards matter to the rate, retrieve them with `get_credit_card_accounts_by_user`. Include only active cards under the verified customer profile.

### 2. Retrieve and validate the bank account

Unlock and call `get_all_user_accounts_by_user_id_3847` with:

```json
{"user_id":"<verified user id>"}
```

Select only an account that is owned by the verified user, active, a savings account, and the stated savings class. Record its `account_id`, current balance, class, and status. Identify all active checking accounts from the same response; do not assume that a customer-described checking product exists or is eligible.

### 3. Retrieve the interest credit and source data

Unlock and call `get_bank_account_transactions_9173` with:

```json
{"account_id":"<verified savings account id>"}
```

Find the relevant posted `interest_credit` transaction. Record its amount and date. Determine the actual statement/cycle period from transaction context or authoritative account data. Gather the balance history needed for that entire cycle, including transactions that changed daily balances. Pending transactions are not posted interest evidence.

A single interest-credit amount, an approximate current balance, or a customer estimate does not by itself establish the actual APY or correction amount. Ask for or obtain the missing period and balance history. If the available tools cannot establish them, explain that a precise correction cannot safely be made and escalate rather than fabricating numeric report parameters.

### 4. Determine the documented expected APY

Use the product documentation applicable to the verified savings class. Add only documented, eligible components:

- base rate and any satisfied tier rate;
- the **highest**, not the sum, of eligible linked-checking boosts for this savings product among active linked checking accounts;
- the **highest**, not the sum, of eligible active credit-card APY bonuses;
- a separately documented relationship bonus, only when its eligibility is independently established.

Checking boosts and credit-card bonuses can stack with each other and with an independently applicable relationship or tier component; boosts within either same-category group never stack.

For a Gold savings product, the documented baseline is 5.5%; an active Green checking account provides a +0.75% Gold boost; and an active EcoCard provides +0.6% card bonus. Gold Rewards has a separately documented +0.025% relationship bonus, but the product material contains an internally inconsistent example total. Do not rely on that erroneous displayed total. Use the additive component values only when eligibility is clear; if the conflict affects whether a component applies, do not resolve it by assumption—escalate for policy clarification before a monetary action.

Do not use the customer's claimed rate or a claimed checking boost in place of verified product documentation.

### 5. Calculate, validate, and decide

Use `scripts/interest_calculator.py` for deterministic math when daily closing balances, period days, and the posted interest amount are known. It expects APYs as percentage points, not fractions.

Example invocation through the packaged-script runtime:

```json
{
  "relative_path":"scripts/interest_calculator.py",
  "input_json":{
    "expected_apy":6.85,
    "daily_balances":[96000,96000],
    "actual_interest":408.00,
    "day_count_basis":365
  }
}
```

Input schema:

- `expected_apy` (number): documented annual percentage yield, e.g. `6.85` for 6.85%.
- `daily_balances` (nonempty number array): closing eligible balance for every day in the relevant interest period, in chronological order.
- `actual_interest` (number): posted interest-credit amount; may be zero but cannot be negative.
- `day_count_basis` (optional integer): normally `365`.
- `rounding` (optional): `"end"` (default) or `"daily_cents"`; use only the convention established by product records.

Output schema includes `expected_interest`, `actual_interest`, `amount_difference`, `derived_actual_apy`, `has_discrepancy`, `days`, and validation messages. `amount_difference` is positive only when additional interest is owed. The script uses daily compounding from APY: daily rate = `(1 + APY / 100) ** (1 / basis) - 1`. Review the result and ensure it matches the verified period, balances, and documented rounding before acting.

Do not credit if the result is zero or negative. A derived actual APY is an estimate from the supplied balances and credit and must be suitable for the discrepancy report; if it cannot be meaningfully determined, do not submit a report with a guessed value.

### 6. Correct first, then report

When a positive, authorized, evidence-supported discrepancy exists:

1. Unlock and call `apply_savings_account_credit_6831` **first**:

```json
{
  "account_id":"<verified savings account id>",
  "amount":<positive calculated dollar difference>,
  "credit_type":"interest_correction"
}
```

Confirm the action succeeded before continuing. Never retry an action whose result is unknown.

2. Only after a successful credit, unlock and call `submit_interest_discrepancy_report_7294`:

```json
{
  "account_id":"<verified savings account id>",
  "user_id":"<verified user id>",
  "expected_apy":<documented expected APY percentage>,
  "actual_apy":<verified or defensibly derived applied APY percentage>,
  "amount_difference":<same positive credited dollar difference>
}
```

The report investigates the system issue; it does not replace the immediate correction. Never reverse this order.

### 7. Close the interaction

Tell the customer what was verified, the relevant documented APY components, the posted interest reviewed, and—if applied—the correction amount and that a backend report was submitted. State any uncertainty plainly. Do not expose full account identifiers, address, date of birth, or card numbers.

## Failure handling

- **No matching interest credit / missing cycle:** obtain authoritative statement-period information or escalate; do not use a current balance to reconstruct a monthly entitlement.
- **No qualifying checking or card:** apply no component from that product.
- **Multiple qualifying checking accounts or cards:** select only the highest eligible bonus within that category.
- **Policy/documentation conflict affecting eligibility:** hold monetary action and escalate for a policy determination.
- **Tool failure after no action:** report the inability to complete the investigation and preserve the verified facts for follow-up.
- **Credit failure or unknown outcome:** do not submit the report and do not retry blindly.
- **Report failure after confirmed credit:** do not credit again; communicate that the correction posted and route the report failure for follow-up.
