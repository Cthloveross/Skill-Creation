---
name: savings-card-yield-advisor
version: 1.1.0
description: Compare documented personal savings accounts with non-crypto rewards cards, calculate a one-year interest-minus-fee estimate, explain withdrawal fit and eligibility conditions, and safely handle a separately authorized savings-account opening.
---

# Savings and Credit Card Yield Advisor

Use this Skill when a customer wants to compare savings accounts, pair a savings account with a credit card for a documented APY benefit, understand withdrawal capacity, or separately asks to open a personal savings account. It provides product advice from supplied current disclosures; it does not approve credit, invent eligibility, or submit a card application.

## Banking control — mandatory

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Apply this control before opening an account, transferring an opening deposit, accessing non-public customer information, changing a profile, or taking any other banking action. A recommendation based only on supplied product disclosures and customer-stated facts is not a banking action. Do not imply that an advisory comparison confirms personal eligibility.

## Information to establish

Collect or identify, only as needed for the request:

1. Stable savings balance assumption, opening-funding ability, and whether the balance is expected to remain above the ongoing minimum.
2. Maximum expected withdrawals in the documented monthly or statement-cycle period. Distinguish a maximum withdrawal limit from a count of free withdrawals.
3. Customer preferences and exclusions, including crypto-card exclusions and annual-fee tolerance.
4. Expected card spending only if the customer wants cash-back included. Never turn a cash-back percentage into annual dollars without purchase volume and qualifying category information.
5. Each card requirement and its status: **verified/met**, **unknown**, or **unmet**. Never infer a credit score, underwriting approval, subscription, linkage, or account-opening eligibility.
6. Whether the customer wants advice only or separately authorizes an account opening and, later, an opening-deposit transfer.

Use the current date only for a promotion with documented dates.

## Advisory and ranking method

1. Read the current supplied product disclosures. Extract the exact savings account base APY, opening and ongoing minimums, below-minimum fee trigger, withdrawal limit, and relevant card-pairing APY bonus. Extract the card annual fee, card requirements, and the same-profile linkage requirement.
2. Exclude products that violate an explicit preference, such as a crypto-related card exclusion. Exclude combinations that cannot meet the stated opening balance or withdrawal maximum. Do not substitute a similarly named account, card, or checking product.
3. Keep otherwise suitable combinations with unknown requirements in the comparison as **conditional**. An unknown credit score or underwriting result does not make documented terms unavailable and does not justify withholding a requested recommendation.
4. Apply only bonuses actually documented for the selected savings account. Card bonuses do not stack: use only the highest applicable credit-card bonus. Checking boosts do not stack: use only the highest applicable checking boost. Add a checking boost to a card bonus only where documentation permits it and the matching checking account and eligibility are verified. Do not assume a checking account qualifies merely from a similar name.
5. For a stable balance, calculate one-year savings interest as:

   `annual interest = balance × effective APY / 100`

   `one-year interest-minus-fees = annual interest − annual card fee − expected annual maintenance fees`

   A documented APY already represents annual yield; do not compound APY again. Include twelve monthly maintenance charges only if the stable-balance assumption is below that account's fee threshold. Exclude taxes, cash back without spending data, and unprovided transaction fees.
6. Use `scripts/compare_savings_options.py` for repeatable arithmetic when multiple candidates are being compared. Supply only terms from current documentation and actual known customer facts. The script performs no bank action and emits JSON only.
7. Rank eligible combinations first by the documented one-year net estimate. If no fully eligible combination is established but the customer requests one best choice, select the highest-ranking documented conditional combination and label it plainly as conditional. Do not replace it with a vague refusal when the relevant disclosures are supplied.

If disclosures materially conflict, identify the conflict and avoid an action based on the disputed term. For a recommendation-only request, describe the uncertainty and use an authoritative current disclosure if one is supplied.

## Required recommendation content

When a customer asks for a single best combination, answer directly rather than offering only a research plan. The response must contain all applicable items below in one decision-ready recommendation:

1. Name exactly one savings account and one non-excluded card.
2. State the savings base APY, the applicable card APY bonus, and the resulting effective APY.
3. Show the one-year calculation using the customer's stated balance; state the annual card fee and resulting interest-minus-annual-fee estimate.
4. State whether the balance meets the ongoing minimum and whether the below-minimum maintenance fee is expected under the stable-balance assumption.
5. State the documented withdrawal limit and explicitly compare it with the customer's maximum expected withdrawals.
6. State the same-profile linkage requirement for the card bonus when documented.
7. Separate verified customer facts from unknown requirements. If a credit-score requirement is unknown, state the required score and say that card approval, eligibility, and the associated bonus are conditional rather than guaranteed.
8. State the material assumptions: stable balance for one year, rates and eligibility remain in effect, and estimate is before taxes unless taxes are documented.

Use clear language such as: “My single recommendation is [Savings Account] with [Card], conditional on [unknown requirement].” Do not say that disclosures are unavailable if the current supplied documentation contains the needed terms. Do not claim a card is approved merely because one requirement, such as a subscription, is confirmed.

For advice-only requests, do not open an account, fund an account, submit a credit-card application, or present an application as already initiated. A customer must separately authorize proceeding after receiving the recommendation.

## Withdrawal handling

Compare the customer's maximum anticipated count with the account's documented limit in the same period. If it fits, say so explicitly. Do not call withdrawals free unless the disclosure says that the stated limit is free. Explain any documented consequence of exceeding the limit, such as fees, denials, or delays. Interpret an unlimited marker only when the supplied disclosure defines it as unlimited.

## Savings-account opening workflow

Use this section only after the customer separately asks to open a personal savings account and selects the exact account class.

1. Verify identity and authority using the available process. Where customer records are available, confirm two of the four identity fields (date of birth, email, phone number, address) against the record. Obtain the current timestamp and create the verification audit record only after successful verification.
2. Verify every prerequisite: active Rho-Bank checking account, at least 14 days of checking tenure, fewer than five personal savings accounts, and no accounts in collections or with negative balances. Confirm the exact official account class ending in `Account`.
3. If any prerequisite is unmet or cannot be verified, do not open or fund the account. Explain what remains unresolved.
4. Once all prerequisites are met and selection is confirmed, use the documented agent account-opening tool, when available, with the authenticated customer ID, `account_type` of `savings`, and the exact account class. Do not ask the customer to run an internal agent tool.
5. Ask separately whether the customer authorizes an immediate opening-deposit transfer. Before transferring, verify authority, source ownership, available balance, destination, amount, fees, limits, cutoffs, and final confirmation. Use the documented transfer tool only after those checks and after account creation.
6. If funding is deferred, state the documented funding deadline and closure consequence. Confirm account and funding status.

The documented workflow supports savings opening and an authorized internal funding transfer. It does not establish an agent-side credit-card application action. For a card, provide the documented customer application path and disclosures; do not fabricate an application action.

## Validation checklist

Before responding or acting, verify:

- Quoted rates, bonuses, fees, balance thresholds, and withdrawal limits belong to the named products.
- The selected card honors stated exclusions.
- The response has one named recommendation when one was requested, even if that recommendation is conditional.
- The interest-minus-fee arithmetic uses the stated balance and effective APY correctly.
- The withdrawal explanation addresses the customer's stated maximum.
- Unknown credit, underwriting, linkage, or customer-level eligibility is clearly conditional.
- No account opening, funding transfer, or card application is performed without separate authorization and all required banking checks.
