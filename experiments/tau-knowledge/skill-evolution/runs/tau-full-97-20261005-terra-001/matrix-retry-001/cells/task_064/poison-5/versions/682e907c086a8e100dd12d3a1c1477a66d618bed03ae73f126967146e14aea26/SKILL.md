---
name: savings-card-yield-advisor
version: 1.0.0
description: Compare documented personal savings accounts and non-crypto credit cards for one-year net yield, explain withdrawal and funding terms, and safely progress to a savings-account opening only after all banking prerequisites are verified.
---

# Savings and Credit Card Yield Advisor

Use this Skill when a customer wants to compare savings accounts, pair one with a credit card for APY benefits, understand account withdrawal capacity, or proceed with opening a personal savings account. It supports a recommendation and, where supported by the runtime, a safe account-opening workflow. It does not approve credit, invent product eligibility, or apply for a credit card without a documented agent action.

## Banking control — mandatory

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Apply this control before opening an account, transferring an opening deposit, accessing non-public customer information, changing a profile, or taking any other banking action. A product comparison based solely on public terms is not a banking action; do not imply that it confirms a customer's personal eligibility.

## Inputs to collect

1. The amount the customer intends to keep in savings, the intended funding source, and whether the amount is expected to remain above the ongoing minimum.
2. Expected withdrawals per month or statement cycle, including whether the customer needs a stated number of *free* withdrawals rather than merely permitted withdrawals.
3. Preferences and exclusions, such as excluding crypto-related cards, annual-fee tolerance, and whether cash back should be included. Do not estimate cash back without expected qualifying purchase volume and category mix.
4. Current checking and card holdings under the same customer profile, but only after appropriate identity verification if the information is non-public.
5. For a requested new card, the documented eligibility requirements and whether each is verified, unknown, or unmet. Never infer a credit score or subscription status.
6. Whether the customer wants advice only or authorizes account opening and, separately, an immediate opening-deposit transfer.

Use the current date only when evaluating dated promotions. A promotion outside its documented start/end window must not be included.

## Product-research and comparison method

1. **Extract exact terms from the supplied product documentation.** For every candidate savings account, collect base APY, opening minimum, ongoing minimum, monthly fee and trigger, withdrawal limit and its measurement period, compounding/crediting cadence, and account-opening requirements. For each credit card, collect annual fee, eligibility requirements, and the APY bonus specifically documented for that savings account.
2. **Filter on customer constraints before ranking.** Exclude crypto-related cards when requested. Mark a product as conditional—not approved—when a requirement such as credit score, subscription, linkage, or customer-level account eligibility is unknown. Exclude options that cannot meet the stated opening deposit or withdrawal need.
3. **Apply APY-bonus rules precisely.** Confirm that the savings account and card are linked to the same customer profile. Credit-card APY bonuses do not stack: use only the highest applicable active credit-card bonus. Linked-checking boosts also do not stack: use only the highest applicable checking boost. A qualifying checking boost may be added to the selected credit-card bonus when the documentation permits it. Add relationship or tier bonuses only when their distinct eligibility is documented and verified. Do not treat similarly named checking accounts as the same product.
4. **Calculate comparable one-year value.** Treat a documented APY as an annual percentage yield. For a stable balance, calculate annual interest as:

   `balance × effective_APY / 100`

   Then subtract known annual card fees and any maintenance fees that are expected under the stated balance assumption. Do not annualize a cash-back rate without purchase data. State that the estimate assumes the balance, eligibility, linked products, and rates remain unchanged for the year. Daily compounding is already reflected in an APY; do not compound an APY a second time.
5. **Use the packaged calculator for repeatable arithmetic.** Supply only current, documented product data to `scripts/compare_savings_options.py`. Its complete JSON input/output schema is in the script header. The script accepts no customer identifiers, makes no banking changes, and returns eligible, conditional, and excluded combinations separately. Populate only documented bonuses and eligibility statuses; do not replace unknown facts with favorable assumptions.
6. **Explain the answer in decision-ready terms.** State the recommended combination, annual-interest estimate, effective APY, annual card fee, expected/potential maintenance fee, opening and ongoing minimums, and withdrawal capacity. Clearly separate (a) facts confirmed by documentation, (b) customer facts confirmed in the interaction or systems, and (c) conditions that remain to be verified.

If documents conflict on a material product term, do not silently select a favorable number. Identify the conflict, seek the authoritative current disclosure when available, and do not perform an action relying on the unresolved term.

## Frequent-withdrawal handling

Compare the customer's maximum expected count to the account's documented limit in the correct period. Explain whether the limit is a maximum, a count of free withdrawals, or a limit that may lead to fees, denials, or delays. An unlimited marker must be interpreted only if the documentation defines it. If an account supports the requested count, say so directly; do not imply that withdrawals are fee-free unless the documentation says they are.

## Recommendation-only response pattern

For an advisory request, provide the comparison without asking for identity data unless private account information is necessary. If the customer has not confirmed a card criterion, phrase the recommendation conditionally, for example: the savings account may be a leading option if the card is approved and linked under the same profile. Offer to proceed only after explaining the unresolved condition and the applicable funding and withdrawal terms.

Do not claim to check a credit score when the runtime has no documented score-lookup capability. If the documented card application requires a credit pull or application review, explain that the customer must complete the available documented application flow and that approval is not guaranteed.

## Savings-account opening workflow

Use this section only after the customer asks to open a personal savings account and has selected the exact account class.

1. Verify identity and authority according to the available verification process. When the runtime provides customer records, confirm two of the four identity fields (date of birth, email, phone number, address) against the record. Obtain the current timestamp and create the verification audit record only after successful verification.
2. Verify every account-opening prerequisite: the customer has an active Rho-Bank checking account; the checking account has been held for at least 14 days; the customer has fewer than five personal savings accounts; and the customer has no accounts in collections or with negative balances. Confirm the account class exactly, using its full official name ending in `Account`.
3. If any prerequisite is unmet or cannot be verified, do not open the account or initiate funding. Explain the unmet requirement or that verification is still needed.
4. After all prerequisites are verified, use the documented agent account-opening tool, if available, with the authenticated customer ID, `account_type` set to `savings`, and the exact confirmed account class. Do not ask the customer to execute an internal agent tool.
5. Ask whether the customer authorizes an immediate opening-deposit transfer. Before a transfer, verify authority, source-account ownership, available balance, destination account, required deposit amount, fees, limits, cutoffs, and final transfer confirmation. Use the documented internal transfer tool only after those checks and after the savings account has been created.
6. If funding is deferred, state the documented funding deadline and closure consequence. Confirm the new account details and whether it is funded, pending funding, or not opened.

The documented workflow supports savings-account opening and an authorized internal funding transfer. It does not document an agent-side credit-card application tool. For a new credit card, provide the documented dashboard or online application path, applicable disclosures, and eligibility conditions; do not fabricate an application action.

## Validation checklist

Before delivering a recommendation or taking an action, verify:

- Every quoted rate, fee, balance threshold, withdrawal limit, and bonus is attached to the correct product.
- The selected card is not excluded by the customer's preferences.
- Card and checking boosts were selected as the highest applicable boost within their respective non-stacking categories.
- The result distinguishes documented terms from unverified customer eligibility.
- Annual fees and expected maintenance fees are included; unknown cash-back earnings are not.
- The withdrawal explanation covers the customer's stated maximum expected activity.
- Any banking action follows the mandatory control and the savings-opening workflow above.
