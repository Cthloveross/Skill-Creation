---
name: savings-interest-discrepancy-review
description: Review a Rho-Bank savings interest-credit concern by verifying identity, collecting the statement-period ledger and eligibility facts, applying non-stacking card and checking APY rules, and calculating an auditable provisional expected-interest range. Use for questions about Silver, Silver Plus, Platinum, and Diamond Elite savings interest.
---

# Savings interest discrepancy review

Use this Skill to investigate an interest-credit discrepancy without assuming that a customer's rough balance, estimated payment, or list of products proves an error. The exact review requires the statement start/end dates, end-of-day balances or a complete dated transaction ledger, actual interest-credit entries, and product eligibility during the period.

## 1. Protect the account and establish identity

1. Obtain two customer-provided identity fields among date of birth, email, phone number, and address. Do not treat a database lookup or an account identifier alone as customer verification.
2. Match those fields to the customer record. After two fields match, call `get_current_time` and then `log_verification` with the complete returned customer record and the timestamp.
3. Only after verification, retrieve the active credit-card list if it is relevant. Consider only cards whose status is ACTIVE and that are under the same profile as the savings account.
4. Do not change an account, promise an adjustment, or disclose more account information than necessary to investigate.

## 2. Collect facts that determine the calculation

Ask for or retrieve, using only normal declared banking tools:

- statement period start and end dates;
- each savings account's actual interest-credit amount and posting date;
- a complete daily end-of-day balance schedule, or statement opening balance plus every dated deposit, withdrawal, pending reversal, and interest credit;
- whether each checking account was active, linked, and under the same profile for the period;
- Silver Plus direct-deposit status for the period;
- whether the relationship-bonus criteria were met, if the account offers that bonus;
- status and same-profile qualification of every relevant credit card.

A rough current balance cannot substitute for daily balances. Do not infer that direct deposit, relationship eligibility, linkage, or same-profile ownership existed when the customer says they do not know.

If the declared tool set cannot retrieve savings-account statements, transactions, account linkage, or interest credits, explain that an exact verification cannot be completed with the available records. Ask the customer to provide their statement or offer a specialist review. If the customer requests escalation or a correction cannot be safely validated, transfer with `specialized_department_required` and summarize the missing records and facts already gathered.

## 3. Apply the policy correctly

For each day of the statement period:

- Determine the savings account's base tier from that day's end-of-day balance.
  - Silver: 2.5% below $10,000 and 4.0% at or above $10,000.
  - Silver Plus: 3.0% below $15,000 and 4.5% at or above $15,000.
  - Platinum: 6.5%.
  - Diamond Elite: 7.5%.
- Select the **single highest** applicable credit-card APY bonus. Never add bonuses from multiple cards.
- Select the **single highest** applicable linked-checking APY boost. A checking boost requires an active, linked checking account under the same profile and a qualifying checking/savings pairing. Never add multiple checking boosts.
- Add the selected card bonus and checking boost to the base rate. These categories may stack with each other and with a supported relationship bonus, account-tier rate, and Silver Plus direct-deposit bonus.
- Apply age eligibility before using Light Green: its primary holder must remain age 13 through 24. Do not use its boost if this prerequisite is not established.
- Do not automatically remove Diamond Elite interest merely because its balance is below the stated $250,000 ongoing balance requirement. Flag that requirement for review; the supplied policy does not say that falling below it changes the APY.

The available account documentation establishes daily compounding and monthly crediting. It does not, by itself, establish every ledger convention (such as leap-year day count, exact posting cutoffs, or treatment of unsettled items). Treat the ledger/system calculation as authoritative for a monetary correction.

## 4. Use the calculator

`scripts/apy_review.py` is a local, deterministic calculator. It reads one JSON object from stdin and emits one JSON object on stdout. It makes no bank changes and does not call banking tools.

Input schema:

```json
{
  "account_type": "Silver | Silver Plus | Platinum | Diamond Elite",
  "balance_days": [{"date": "YYYY-MM-DD", "balance": "decimal dollars"}],
  "credit_cards": [{"type": "card name", "status": "ACTIVE", "same_profile": true}],
  "checking_accounts": [{"type": "checking name", "status": "ACTIVE", "linked": true, "same_profile": true}],
  "profile_age": 20,
  "direct_deposit_active": true,
  "relationship_eligible": false,
  "days_per_year": 365
}
```

Supply one balance entry for every statement day, in chronological order. `profile_age`, `direct_deposit_active`, and `relationship_eligible` may be `null` when unknown. Unknown prerequisites are listed in `unresolved`; they are deliberately not assumed eligible. `days_per_year` defaults to 365 and should be replaced with the bank's documented statement convention when available.

Example runnable call in the supported Skill runtime:

```text
run_skill_script(relative_path="scripts/apy_review.py", input_json={...the schema above...})
```

The result includes daily rate-component records, selected highest bonuses, an estimated compounded interest amount, and unresolved prerequisites. Validate before relying on it:

1. `ok` must be true.
2. The number of `daily_rates` must equal the number of supplied daily balances.
3. Check `selected_card_bonus_pct` and `selected_checking_bonus_pct` are maxima, not sums.
4. `unresolved` must be empty before presenting an estimate as a fully qualified result.
5. Reconcile the calculated period and ledger assumptions against the actual statement credit before deciding whether escalation is appropriate.

The calculation converts the additive annual APY percentage to a daily effective rate using `(1 + APY/100)^(1/days_per_year) - 1`, then compounds daily. Label it an estimate unless the bank's precise ledger convention confirms this method.

## 5. Explain the outcome clearly

Give a concise account-by-account explanation: the applicable base tier, one selected card bonus, one selected checking boost, any supported direct-deposit/relationship component, missing eligibility evidence, and why the actual credit can or cannot be reconciled. Do not state that multiple checking accounts or multiple credit cards should have been stacked. If information is missing, specify exactly what is needed rather than asserting an underpayment.
