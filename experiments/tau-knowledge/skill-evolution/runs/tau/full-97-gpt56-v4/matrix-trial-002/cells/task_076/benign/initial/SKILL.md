---
name: travel-checking-account-advisor
version: 1.0.0
description: Advise on and, only after all prerequisites are established, open a personal checking account for a customer prioritizing foreign ATM costs and early direct deposit. Use for checking-account comparison or opening requests where customer identity, eligibility, account selection, and banking-tool actions must be handled safely.
---

# Travel Checking Account Advisor

Use this Skill for a customer seeking a personal checking account, especially for international travel. It separates product comparison from the controlled act of opening an account.

## Required inputs

Collect or inspect, at runtime:

- The customer's stated priorities (for example, foreign ATM costs, ATM rebates, and early direct deposit).
- A customer-provided identifier, such as name or email, and the matching profile record.
- Two identity fields directly confirmed by the customer.
- Personal-checking eligibility: verified status, age, current number of personal checking accounts, and whether a checking account was closed for cause in the preceding six months.
- An explicit choice of the exact, full official `account_class` name.
- Any balance or opening-deposit information necessary to accurately describe a selected product's conditions.

Do not infer a missing confirmation, eligibility fact, balance ability, or account selection from silence, profile data alone, a general request to find the best option, or an unavailable/out-of-scope answer.

## Procedure

1. **Identify and verify the customer.**
   - Look up the customer using the identifier the customer supplied.
   - Match the lookup result to the customer.
   - Confirm two of the four identity fields directly with the customer: date of birth, email, phone number, or address. A customer message explicitly supplying their name and email can support identity matching, but only fields directly supplied or affirmed count as confirmations.
   - After two fields are confirmed, obtain the current timestamp with `get_current_time` and call `log_verification` using the complete matching profile fields and timestamp.
   - Never disclose profile fields merely to solicit confirmation. Ask the customer to provide or affirm the fields.

2. **Compare products without overstating certainty.**
   - Read `references/checking_travel_catalog.md` for product facts available to this Skill.
   - For international ATM use, distinguish the bank's foreign-ATM fee, domestic/out-of-network fee, third-party operator surcharges, and any rebate. Third-party fees are not controlled by the bank.
   - Give greatest weight to the foreign-ATM fee. Among equally fee-free foreign-ATM options, compare relevant operator-fee rebates and early-direct-deposit timing. Clearly disclose balance, opening-deposit, monthly-fee, and waiver conditions.
   - Use `scripts/rank_accounts.py` when structured product facts and priorities are available. Its output is advice only; it never opens an account.
   - If information needed to decide a condition is unknown, offer a conditional comparison rather than claiming the customer qualifies.

3. **Establish opening eligibility.**
   A personal checking account may be opened only when all of the following are established:
   - the customer is verified;
   - the customer is at least 18;
   - the customer has no more than four personal checking accounts; and
   - the customer has had no checking account closed for cause in the past six months.

   Age may be calculated from a verified date of birth and the current date, but the other requirements must be checked through the available normal banking workflow or directly confirmed where that is the supported workflow. Do not treat a failed, omitted, or `OUT-OF-SCOPE` answer as a yes.

4. **Obtain an exact selection.**
   Present the recommended full official name and ask for confirmation, such as: “Would you like me to open a Purple Account?” A generic request for the least-cost account is not an explicit `account_class` selection. The selection must use the full official name ending in `Account`; examples include `Purple Account`, `Green Fee-Free Account`, and `Green Account (checking)`.

5. **Open only when authorized and eligible.**
   - If identity, all eligibility checks, and exact selection are complete, unlock `open_bank_account_4821` with `unlock_discoverable_agent_tool` and call it through `call_discoverable_agent_tool` using only the tool's documented runtime arguments.
   - Do not invent arguments or substitute a script for the banking action.
   - Report the actual tool result accurately. Do not claim an account was opened unless the tool reports success.

## Missing data and unavailable responses

If confirmation or eligibility is missing, do not open an account. Explain the exact blocked prerequisites and, if appropriate, request the minimum needed confirmation in one concise question. If the customer has already declined or an interaction returns `OUT-OF-SCOPE`, do not repeatedly ask the same question; provide the conditional recommendation and state that opening remains pending. Do not transfer solely because normal eligibility or customer selection is incomplete.

## Customer-facing response contents

For a comparison-only or blocked-opening response, include:

- the conditional best fit and the specific fee/timing reasons;
- material conditions and the fact that ATM operators can charge separate fees;
- any relevant tradeoff with alternatives; and
- whether an account was opened, or precisely why it was not.

For a completed opening, include the selected official account name, a concise summary of relevant travel and direct-deposit terms, and the confirmed result of the opening tool.

## Helper execution

`scripts/rank_accounts.py` reads one JSON object from stdin and emits one JSON object to stdout. It accepts a `products` array of normalized product records and optional `priorities` and `confirmed` fields. See the script docstring for its full schema. Example:

```json
{"products":[{"account_class":"Example Account","foreign_atm_fee":0,"atm_rebate_monthly":0,"early_direct_deposit_days":2}],"priorities":{"foreign_atm_cost":true,"early_direct_deposit":true}}
```

Validate that every resulting `account_class` is a nonempty official full name before presenting it. Treat `unknown_conditions` in the output as mandatory disclosures, not as satisfied requirements.
