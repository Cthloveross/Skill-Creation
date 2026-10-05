---
name: gold-savings-interest-review
description: Review and explain a Gold savings account APY or monthly-interest concern, including the highest-only selection of linked checking boosts and credit-card bonuses, app navigation, evidence collection, and escalation for a possible interest discrepancy.
---

# Gold Savings Interest Review

## Scope

Use this Skill when a customer asks why Gold Account interest was low, what APY should apply, whether checking/card benefits stack, where to find the rate and interest credit in the app, or asks for a review by a specialist.

This Skill can determine the documented **expected APY** from verified or supplied product facts. It cannot establish the exact amount of an interest correction without a statement period and reliable daily-balance or transaction-history evidence.

## Gold Account policy facts

Apply the following documented rules:

1. The Gold Account base APY is **5.5%**.
2. Interest compounds daily and is credited monthly as an interest-credit transaction.
3. For active eligible Rho-Bank cards on the same customer profile, card APY bonuses do **not** stack. Select only the highest card bonus.
4. For active qualifying checking accounts linked to the Gold Account, checking boosts do **not** stack. Select only the highest Gold checking boost.
5. The selected card bonus and selected checking boost are additive to the 5.5% Gold base APY.
6. Do not count the Gold Rewards Card's 0.025% benefit twice if it is described as either a card or relationship benefit.

Use this formula:

`expected APY = 5.5% + highest eligible card bonus + highest eligible Gold checking boost`

### Product rate table for Gold Account selection

| Product | Gold Account APY addition |
|---|---:|
| Gold Rewards Card | +0.025% card bonus |
| Platinum Rewards Card | +0.15% card bonus |
| EcoCard | +0.6% card bonus |
| Green Account checking | +0.75% Gold checking boost |
| Purple Account checking | +0.1% Gold checking boost |

Only use an addition when the available evidence establishes the relevant active/qualifying relationship. Do not invent a product status or bonus for an unsupported product.

## Mandatory explanation when the supplied evidence establishes the known products

Do not give only a generic non-stacking explanation when the runtime has already supplied the relevant card observation and checking-account information.

When the evidence shows active same-profile Platinum Rewards Card, Gold Rewards Card, and EcoCard, and establishes Green and Purple checking for the Gold Account review, state all of the following plainly:

- **EcoCard's +0.6%** is the highest applicable card bonus.
- Platinum's +0.15% and Gold Rewards Card's +0.025% do not add on top of EcoCard, because card bonuses do not stack.
- **Green checking's +0.75%** is the higher Gold checking boost.
- Purple checking's +0.1% does not add on top of Green, because checking boosts do not stack.
- The documented expected rate is **6.85% APY**, calculated as **5.5% + 0.6% + 0.75%**.

Phrase this as the expected documented policy rate based on the supplied account/product facts. Do **not** say that card names or the customer-confirmed checking types are insufficient to identify the documented bonus amounts when the policy table and observations establish them.

A suitable customer-facing explanation is:

> Based on the products confirmed for this review, the expected Gold Account rate is 6.85% APY: 5.5% base, plus EcoCard's 0.6% highest card bonus, plus Green checking's 0.75% Gold boost. Card bonuses do not stack, so Platinum and Gold Rewards do not add to EcoCard; checking boosts do not stack, so Purple's 0.1% does not add to Green's boost.

Do not disclose unnecessary sensitive details such as card balances, full account identifiers, or unrelated transaction activity.

## Privacy, verification, and tool boundaries

- Follow the active runtime's identity-verification process before disclosing customer-specific account, card, or transaction data or taking an account action.
- Log verification only after the runtime's required verification threshold has actually been met.
- Use only tools actually supplied by the runtime. A policy document naming a tool does not make that tool available.
- Never claim to have viewed savings transaction history, a displayed APY, a statement, or an interest credit unless an authorized tool was successfully used or the customer provided it.
- The supplied runtime may not offer a usable savings transaction-history tool. Do not request or unlock a nonexistent tool.
- This Skill does not automatically apply credits or submit discrepancy reports.

## Customer-facing workflow

### 1. Give the expected-rate explanation first

Where policy and supplied facts support it, give the complete component calculation before asking for missing statement evidence. The expected APY and a precise review of the posted dollar amount are separate questions.

For any other set of products, identify the highest eligible item in each category, explain that each category is non-stacking, and show the formula. If card or checking eligibility is genuinely unknown, say exactly which eligibility fact is missing rather than treating documented bonus amounts as unavailable.

### 2. Explain the limitation on the monthly dollar amount

An approximate balance and a single monthly-interest amount do not prove which APY was applied or produce a reliable correction amount. Even after calculating the expected 6.85% policy rate, state that a precise validation of an interest credit requires:

- statement-cycle start and end dates, or an exact day count;
- the posting date and amount of the interest-credit transaction;
- the APY and listed bonus breakdown shown in account details; and
- daily balances for the period, or a clearly labeled stable-balance assumption for an estimate only.

Never assume a month has a particular number of days, infer the applied rate from an approximate balance, or promise a correction from an estimate.

### 3. Give practical app navigation

The documentation establishes that Gold Account details show the displayed APY and relationship-bonus status, but it does not establish exact mobile-app labels. Give a practical route without representing labels as exact:

1. Sign in to the Rho-Bank app.
2. From the account list, select the Gold savings account.
3. Open **Details**, **Account details**, **Rate**, or a similarly named account-information area.
4. Ask the customer to copy the displayed APY and every listed APY bonus.
5. Return to the Gold Account page and open **Activity** or **Transactions**.
6. Find the most recent interest-credit entry and obtain its posting date and amount.

If these labels are not present, direct the customer to the app help/account-details option or to in-app chat, online help, or phone support to request complete account history. Do not invent an exact screen path.

### 4. Calculate consistently

Use `scripts/calculate_gold_interest.py` after converting available facts into the documented input schema. The script reads one JSON object from stdin and writes one JSON object to stdout; it makes no network calls or banking changes.

Executor call pattern:

`run_skill_script(relative_path="scripts/calculate_gold_interest.py", input_json=<validated_input>)`

Input schema:

```json
{
  "base_apy": "number; required, APY percentage",
  "credit_card_bonuses": [
    {"name": "string", "apy_bonus": "number", "active": "boolean", "same_profile": "boolean"}
  ],
  "checking_boosts": [
    {"name": "string", "apy_boost": "number", "active": "boolean", "qualifying": "boolean"}
  ],
  "displayed_apy": "number; optional",
  "actual_interest": "number; optional",
  "daily_balances": ["number; optional, complete verified daily balances"],
  "days": "positive integer; optional, used only with balance",
  "balance": "nonnegative number; optional, stable-balance estimate only"
}
```

Output schema:

```json
{
  "expected_apy": "number",
  "components": {"base_apy": "number", "highest_credit_card_bonus": "number", "highest_checking_boost": "number"},
  "selected_credit_card_bonus": {"selected_names": ["string"], "tied_highest": "boolean", "eligible_count": "integer"},
  "selected_checking_boost": {"selected_names": ["string"], "tied_highest": "boolean", "eligible_count": "integer"},
  "apy_comparison": "object or null",
  "interest_calculation": "object or null",
  "discrepancy_status": "string",
  "missing_evidence": ["string"],
  "warnings": ["string"]
}
```

Validate the script result before relying on it:

- `expected_apy` equals base APY plus exactly one selected amount from each category.
- Multiple tied products are reported as a tie and are never summed.
- A displayed-APY comparison is a rate comparison, not proof of a dollar correction.
- A calculation based on `days` and one `balance` is an estimate only.
- A proposed dollar difference is actionable only when actual interest and a complete, reliable period/balance basis are present.

### 5. Remediate only after confirmation

Only after identity and ownership, Gold savings account status, relationships, actual interest credit, and a reliable expected-interest calculation are verified:

1. Determine whether a discrepancy actually exists.
2. If the authorized savings-credit capability is available and policy permits an interest correction, apply the confirmed positive difference as an `interest_correction`.
3. After the credit succeeds, submit the authorized discrepancy report, if available, to correct the underlying system issue.
4. Tell the customer what was completed and what remains under investigation.

Never apply a credit or submit a report based solely on an approximate balance, assumed statement length, or unverified rate.

### 6. Escalation

If the customer requests a human review, or a confirmed/possible system-rate issue requires specialist handling, use the runtime's normal human-transfer tool. Use the applicable provided reason code; `specialized_department_required` is appropriate for a specialist interest-calculation review when no more specific code applies.

The transfer summary must preserve the calculation and missing evidence. Include:

- Gold Account interest concern and the posted amount if supplied;
- expected policy APY and its components;
- the selected card and checking products;
- the non-stacking result; and
- what evidence or tool access is missing for an exact dollar validation.

For the documented Gold/Platinum/Eco and Green/Purple combination, explicitly include: **expected 6.85% APY = 5.5% base + 0.6% EcoCard + 0.75% Green checking; card and checking categories each select only their highest benefit.** State that statement dates, daily balances, and/or an interest-credit history are still needed to validate the dollar amount precisely.
