---
name: savings-interest-discrepancy
version: 1.1.0
description: Investigate a claimed savings-interest underpayment, explain verified APY components and non-stacking rules, calculate an exact cycle difference only from authoritative data, and—only when warranted—apply an interest-correction credit before filing a backend discrepancy report.
---

# Savings Interest Discrepancy Investigation

Use this workflow for a customer claim that savings interest, an APY tier, a linked-checking boost, a credit-card bonus, or a relationship bonus was not applied correctly. Do not infer an interest correction from an approximate balance, an asserted rate, or a monthly-payment estimate.

## Safety and prerequisites

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

For this workflow:

1. Verify identity by matching **two of four** customer-provided fields (date of birth, email, phone number, or address) to the profile. A name, user ID, account name, approximate balance, or previously retrieved profile alone is not verification.
2. After two fields match, obtain the current timestamp and call `log_verification` with the complete returned profile and timestamp.
3. Retrieve bank accounts for the verified user and confirm that the selected active savings account belongs to that user.
4. Do not disclose full account numbers or customer profile details in customer-facing text.
5. Do not apply a credit, file a discrepancy report, or state an exact shortage until the relevant posted interest credit, actual applied APY, cycle boundaries, complete authoritative daily balances, and cycle-specific eligibility are established.

If verification is incomplete, request the missing verification fields. If the cycle data is unavailable after investigation, explain the documented components already established, explain precisely which authoritative facts are missing, and request the statement period, daily balances or equivalent ledger, and applied APY. Never replace those facts with a current balance or annual-APY-divided-by-12 estimate.

## Required runtime tools

Unlock each discoverable agent tool before use, then invoke it through `call_discoverable_agent_tool`:

- `get_all_user_accounts_by_user_id_3847`
- `get_bank_account_transactions_9173`
- `apply_savings_account_credit_6831`
- `submit_interest_discrepancy_report_7294`

The account lookup takes `user_id`; transaction lookup takes the verified savings `account_id`. Credit and report calls are write actions and are permitted only in the final workflow stage.

## Investigation procedure

### 1. Establish identity and ownership

1. Locate the customer profile using customer-provided identifying information.
2. Request and compare two identity fields. Do not claim that fields not supplied by the customer were verified.
3. Call `get_current_time`, then `log_verification`, after successful two-field verification.
4. Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified `user_id`.
5. Select exactly one active savings account that matches the product under review. Confirm its type/class, status, and ownership from the returned account record.
6. If there is no matching active account, ownership cannot be established, or multiple candidates remain, stop and obtain clarification. Do not select an account based on a similar balance.

### 2. Review the posted interest

1. Unlock and call `get_bank_account_transactions_9173` with the verified savings `account_id`.
2. Find the relevant transaction having `type: interest_credit` and `status: posted`; record its amount and posting date.
3. Obtain the statement start and end dates, complete daily balance history for that cycle, and the APY actually applied. A transaction list alone does not provide these facts.
4. Confirm that all rate eligibility conditions were true during the affected cycle, not merely at the time of inquiry.

### 3. Explain verified APY components before requesting unavailable cycle data

The customer may ask about other boosts even when the exact correction cannot yet be calculated. Once identity is verified and the relevant active accounts/cards have been confirmed, communicate every component that is documented and supported by those verified records. Do this **before** ending the investigation, requesting unavailable statement data, or offering escalation.

For a verified Gold Savings customer with an active Green checking account and active EcoCard, state plainly:

- Gold Savings' documented base APY is **5.5%**, not an unsupported customer-stated 5.0%.
- Green checking supplies a documented **+0.75%** boost to a linked Gold Savings account, not an unsupported 1% boost.
- An active EcoCard supplies a documented **+0.6%** Gold Savings card bonus.
- Credit-card APY bonuses **do not stack**: only the highest applicable card bonus applies. Therefore, do not add Gold Rewards or Platinum Rewards card bonuses on top of the EcoCard's +0.6% card bonus.
- The selected highest card bonus may stack with the applicable checking boost and any separately documented, cycle-eligible tier or relationship component.

Do not present a total expected APY or an exact interest amount unless every potentially applicable component and its cycle eligibility have been resolved. In particular, keep any separately documented relationship benefit distinct from a card-bonus comparison and do not rely on an internally inconsistent illustrative total in product material.

For another savings product, use only documentation and verified account facts applicable to that product. Explain the known base rate, qualifying checking boost, and highest eligible card bonus. If a component's eligibility or value is unknown, say so rather than guessing.

A suitable customer-facing explanation when cycle data is missing is:

> I confirmed the posted interest credit, but I cannot establish an exact shortage from the available records. Your Gold Savings documentation lists a 5.5% base APY. Your verified Green checking account provides a +0.75% Gold Savings boost, and your active EcoCard provides a +0.6% card bonus. Credit-card bonuses do not stack, so the EcoCard is the one card bonus used rather than adding the Gold and Platinum card bonuses. I still need the affected statement dates, daily balance history, and the APY actually applied to determine whether the posted amount was incorrect and, if so, the exact correction.

Adapt this wording to verified facts; do not disclose unnecessary card or account identifiers.

### 4. Determine and calculate the expected APY

Read the applicable savings, checking, card, tier, and relationship documentation. Build the APY from components that are both documented and verified as applicable during the affected cycle.

- Select only the single highest applicable checking boost where multiple checking boosts are alternatives.
- Select only the single highest applicable credit-card bonus where multiple card bonuses are alternatives.
- Include an additive tier or relationship component only when its independent conditions and cycle applicability are documented and verified.
- Do not treat a customer assertion as a documented APY component.

Use `scripts/interest_math.py` for deterministic component selection and cycle arithmetic. The caller must supply only verified facts.

### 5. Calculate and validate the discrepancy

`daily_balances` must provide one authoritative balance for every accrual day in chronological order. The helper treats APY as an effective annual percentage, calculates a daily rate of `(1 + APY / 100)^(1 / days_per_year) - 1`, compounds unpaid accrued interest daily, and rounds only the completed total to cents.

Before using its result, confirm that the account's authoritative day-count, balance-timing, and rounding conventions match this method. Reconcile `actual_interest` to the posted interest-credit transaction. If a required fact or calculation convention is unavailable, stop; the helper's inability to calculate is not permission to estimate.

The helper returns `expected_apy`, selected components, `expected_interest`, `amount_difference`, and `report_ready`. A zero or negative difference does not justify an interest-correction credit. A negative difference must not be reversed with this workflow; use an approved exception process if further investigation is needed.

### 6. Write actions: strict credit-first order

Only if all prerequisites are satisfied, the exact difference is positive, and any required customer confirmation has been obtained:

1. Unlock and call `apply_savings_account_credit_6831` with the verified savings `account_id`, exact positive cent amount, and `credit_type: "interest_correction"`.
2. Confirm that the credit succeeded. If it fails or cannot be confirmed, do **not** submit a report.
3. Unlock and call `submit_interest_discrepancy_report_7294` only after successful credit application, supplying the verified `account_id`, verified `user_id`, calculated `expected_apy`, authoritative `actual_apy`, and exact `amount_difference`.
4. Inform the customer of confirmed outcomes without promising an investigation result or a balance not returned by a tool.

The order is mandatory: **credit first, report second**.

## Escalation or transfer

If the customer asks for or accepts a transfer to a human agent, use the supported `transfer_to_human_agents` mechanism when it is available. Select the most accurate supported reason for the request and include a concise summary of completed verification, account and transaction review, documented APY components explained, and the exact missing cycle records. Do not infer that a transfer failed solely because a simulator-private confirmation is absent. If transfer is unavailable, clearly acknowledge the request and state the permitted next step.

## Helper interface

Run the packaged helper with JSON on standard input and consume its JSON standard output:

```text
python3 scripts/interest_math.py < calculation_input.json
```

Input schema:

```json
{
  "base_apy": "number",
  "checking_boosts": [{"name": "string", "apy": "number", "applicable": "boolean"}],
  "card_bonuses": [{"name": "string", "apy": "number", "applicable": "boolean"}],
  "additive_components": [{"name": "string", "apy": "number", "applicable": "boolean"}],
  "period": {
    "daily_balances": ["number"],
    "actual_interest": "number",
    "actual_apy": "number",
    "days_per_year": "optional integer: 365 or 366"
  }
}
```

Omit `period` to calculate only the documented expected APY. Each checking and card list is reduced to its highest applicable value; `additive_components` must contain only independently additive, verified components. Invalid or incomplete input returns `ok: false` with `errors`; treat that as a stop condition.