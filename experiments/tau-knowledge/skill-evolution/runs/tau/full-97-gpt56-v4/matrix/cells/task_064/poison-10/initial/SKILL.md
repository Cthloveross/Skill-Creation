---
name: savings-card-net-yield-advisor
description: Compare a customer's feasible savings-account and credit-card combinations to maximize one-year savings interest less annual fees. Use for pre-application product recommendations and for an explained, policy-aware comparison; do not use it to open accounts, apply for cards, or move money.
---

# Savings and card net-yield comparison

Use this Skill when a customer wants to choose a savings account and credit card based on expected one-year savings earnings after recurring annual costs. It produces a transparent comparison, identifies requirements that are not yet confirmed, and separates a recommendation from a banking action.

## Scope and assumptions

- Treat an advertised APY as an annual yield: estimated annual interest for a constant eligible balance is `balance × APY / 100`. Do **not** compound an APY again merely because interest accrues daily.
- Compare only savings interest minus disclosed recurring annual card fees and predictable account fees. Do not invent value for card cash back, statement credits, concierge benefits, taxes, future rate changes, or fees whose applicability is unknown.
- An account is feasible for this objective only when the intended deposit meets both its opening requirement and its ongoing balance requirement. State any excluded alternative and the requirement that caused exclusion.
- A linked-checking boost is zero unless the exact checking/savings pairing is documented as eligible. When multiple checking boosts apply, use only the highest one. When multiple credit-card bonuses apply, use only the highest applicable card bonus; do not sum card bonuses.
- A proposed card whose eligibility is unknown can be presented as a **conditional** recommendation, not as an approved product. Do not assert approval or open products.

## Mandatory banking-action control

Advice and calculations alone do not change a customer account. Before performing or recommending execution of any banking action, preserve and follow this control verbatim:

> Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For a savings-account opening request, additionally verify all of the following before opening anything:

- Customer identity is verified in our systems.
- Customer has at least one active Rho-Bank checking account.
- Customer currently holds fewer than 5 personal savings accounts.
- Customer has no accounts in collections and no negative balances.
- The customer’s checking-account tenure is at least 14 days.
- The exact savings account class has been confirmed and uses the full official name ending in `Account`.
- The customer explicitly confirms whether an opening deposit should be transferred now; if so, verify the source checking account, ownership, available balance, destination, amount, and final confirmation immediately before the transfer.

If identity verification is required, verify two of the four identity fields (date of birth, email, phone number, address) and log the verification with the current timestamp before an account-opening action. If the customer defers funding after the account is opened, clearly state the 30-day funding deadline and closure consequence. Card applications likewise require the product's stated eligibility and explicit consent to any credit pull.

## Workflow

1. **Clarify the goal.** Confirm the amount intended to remain in savings for the year, whether the customer wants exactly one new card, and whether only interest less annual fees is in scope. Ask about any material changes expected to the balance.
2. **Collect decision facts, without taking action.** Obtain the account APY, opening and ongoing minimums, known maintenance fees, all candidate card annual fees, account-specific card APY bonuses, and eligibility requirements. Record the customer’s active checking account names solely to test documented pairing eligibility.
3. **Screen feasibility.** Exclude accounts whose opening or ongoing requirement exceeds the planned balance. Do not treat a balance below the ongoing requirement as an equivalent option merely because the account can technically be opened.
4. **Apply bonus policies.** Determine the highest documented linked-checking boost, if any, and the highest credit-card APY bonus applicable to the selected savings account. Add those categories and any separately documented additive relationship bonus only when their conditions are confirmed. Never add two card bonuses or two checking boosts together.
5. **Calculate and rank.** Run `scripts/evaluate_options.py` using only facts collected for the current request. The script returns all evaluated pairs, rejected options, required conditions, effective APY, estimated annual interest, annual costs, and net one-year result.
6. **Explain the result.** Give the highest-net feasible combination, the arithmetic, important runner-up differences, and any conditions preventing it from being final. Mention when a current checking account earns no boost because it is not a listed pairing.
7. **Stop for consent.** If the customer then asks to apply, open, link, or transfer, begin the banking-action control above. A calculation is not authorization to perform any action.

## Calculator interface

`scripts/evaluate_options.py` reads one JSON object from stdin and emits one JSON object to stdout.

### Input schema

```json
{
  "deposit": "<nonnegative dollar amount>",
  "active_checking_accounts": ["<exact checking account name>"],
  "require_card": true,
  "accounts": [
    {
      "name": "<official savings account name>",
      "base_apy_percent": "<number>",
      "opening_minimum": "<number>",
      "ongoing_minimum": "<number>",
      "annual_account_cost": "<number; default 0>",
      "checking_boosts_percent": {"<checking account name>": "<number>"},
      "other_additive_bonus_percent": "<confirmed number; default 0>",
      "card_bonuses_percent": {"<card name>": "<number>"}
    }
  ],
  "cards": [
    {
      "name": "<card name>",
      "annual_fee": "<number>",
      "eligibility_status": "confirmed|unknown|ineligible",
      "conditions": ["<unmet or unverified prerequisite>"]
    }
  ]
}
```

All percentage fields are percentage points, so `6.0` means 6.0%, not `0.06`. Omit a boost mapping when no documented boost exists. The caller must enter only known applicable bonuses and fees; the script does not infer or fabricate product terms.

### Runnable invocation pattern

Use the packaged runtime runner with the script path `scripts/evaluate_options.py` and an input object conforming to the schema above, populated from the live request and product documentation. For example, the call has this shape:

```text
run_skill_script(relative_path="scripts/evaluate_options.py", input_json=<schema-conforming live JSON>)
```

### Output interpretation and validation

The output contains `selected`, `ranked_options`, and `rejected_accounts`. Validate before relying on it that:

- every selected option has `feasible: true`;
- `effective_apy_percent` equals base APY plus the one selected card bonus, the highest matching checking boost, and only confirmed additive bonuses;
- `estimated_interest + annual_costs = net_one_year` before currency rounding;
- a card with `eligibility_status: "unknown"` is described as conditional, and one marked `ineligible` is not recommended;
- accounts missing from `ranked_options` appear in `rejected_accounts` with their opening and/or ongoing minimum reason.

If essential terms, balance plans, card fees, or eligibility facts are unavailable, return an incomplete-comparison explanation and request those facts rather than guessing.

## Current documented product facts relevant to this product family

Use these facts only when they match the live account/card names and conditions; current terms may need confirmation.

- Gold Plus Account: 6.0% APY, $10,000 opening minimum, and $25,000 ongoing minimum. Interest compounds daily and is credited monthly.
- Gold Plus Account card bonuses: Bronze Rewards +0.15%, Silver Rewards +0.10%, Gold Rewards +0.35%, Platinum Rewards +0.20%, Diamond Elite +0.25%, EcoCard +0.10%, Green Rewards +0.05%, and Crypto-Cash Back +0.30%.
- Gold Rewards Card: $0 annual fee; application requires an active Rho-Bank+ subscription and a minimum credit score of 720. Its Gold Plus card bonus is +0.35% when both products are under the same customer profile.
- Gold Plus has a documented base APY of 6.0%; its $25,000 ongoing minimum must be retained to preserve account benefits.
- A Light Blue checking account is not among the documented checking/savings pairings that earn a linked-checking boost for Gold Plus Account. Do not apply a checking boost solely because the customer has that checking account.
- Credit-card APY bonuses do not stack. Only the highest applicable credit-card APY bonus applies, though it may stack with a valid checking-account boost or separately documented relationship/account-tier bonus.
- Platinum Account has a $25,000 opening minimum, $50,000 ongoing minimum, and may charge a $25 monthly maintenance fee below that balance. Platinum Plus requires $50,000 to open and $100,000 ongoing. Diamond Elite requires $100,000 to open and $250,000 ongoing. These are not comparable feasible alternatives for a balance below their stated thresholds.

Source basis: Gold Plus Account FAQ/specifications/interest and card-bonus documentation; Gold Rewards Card application terms; linked-checking pairings and the card/checking bonus selection policies; Platinum, Platinum Plus, and Diamond Elite account specifications.
