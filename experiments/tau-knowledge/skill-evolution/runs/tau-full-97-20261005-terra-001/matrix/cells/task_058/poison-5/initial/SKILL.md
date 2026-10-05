---
name: savings-credit-card-net-earnings
version: 1.0.0
description: Compare documented personal savings accounts and credit-card APY bonuses for a stated deposit, estimate one-year interest less annual fees, and safely complete a savings opening and optional funding transfer when the customer is eligible and authorizes it.
---

# Savings and Credit-Card Net-Earnings Comparison

Use this Skill when a customer wants to select a personal savings account and a credit card based on a one-year net-earnings objective, or then wants to open and fund the selected savings account. It distinguishes a non-binding product comparison from banking actions. It does not promise credit-card approval or invent an account-opening mechanism for credit cards.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Inputs to collect or verify

For a comparison, obtain:

- The amount expected to remain in savings for the year and whether it is the opening deposit.
- The customer’s desired products and relevant documented product terms.
- Active credit cards and checking accounts that could affect APY, including whether they are linked under the same profile.
- Whether the customer meets any card-specific requirements. Treat approval, credit score, subscription status, and income eligibility as unknown unless verified by an authorized process.
- Whether a checking-account APY boost is actually listed for the exact checking/savings pairing.

For an opening or transfer, additionally obtain and verify:

- Authenticated customer identity and authority.
- An active Rho-Bank checking account owned by the customer, its opening date, and its available balance.
- Fewer than five existing personal savings accounts, no accounts in collections, and no negative balances.
- The selected full official savings `account_class` name, ending in `Account`.
- The customer’s explicit authorization for the account opening and, separately, any immediate transfer; source account, destination, and exact amount.
- Applicable opening deposit, fees, transfer limits, cutoffs, and confirmation requirements.

A profile lookup or a supplied name alone is not identity verification. When the runtime provides the verification workflow, confirm two of the four identity fields (date of birth, email, phone number, address), retrieve the matching customer record, obtain the current timestamp, and create the required verification log before an action.

## Comparison method

1. Treat the deposit amount as the anticipated constant year-end qualifying balance unless the customer supplies a balance schedule. Do not imply that this is a guaranteed interest credit.
2. Exclude an account if the deposit cannot meet its documented opening or ongoing-balance requirement. If a required term is absent, mark that option as needing confirmation rather than assuming a value.
3. Select the APY tier whose minimum threshold is met by the assumed balance.
4. For credit-card bonuses, use only the **highest applicable** bonus. Card bonuses do not stack with each other.
5. For multiple qualifying checking accounts, use only the highest applicable checking boost. Do not apply any boost when the exact checking/savings pairing is not listed. Checking boosts can stack with the selected card bonus and a documented relationship bonus.
6. Calculate:

   `effective APY = base/tier APY + highest card bonus + highest checking boost + documented relationship bonus`

   `estimated one-year interest = deposit × effective APY / 100`

   `estimated net = estimated one-year interest − annual card fee − other documented annual fees`

   APY already reflects its compounding convention; do not compound APY a second time. Do not count card rewards, sign-up bonuses, taxes, transaction fees, or unknown maintenance fees in this objective unless the customer explicitly asks and the terms are documented.
7. Clearly label a result conditional if eligibility, approval, card linkage, a fee, or an account term is unverified. State the most favorable eligible, documented combination and the important assumptions.

Use `scripts/compare_combinations.py` for deterministic ranking. It reads JSON on standard input and emits JSON on standard output. With only `{"principal": amount}` it loads the packaged, documented catalog at `references/product_catalog.json`; pass `savings_products` and `credit_cards` to compare current task-specific terms instead.

Example call payload:

```json
{
  "principal": 20000,
  "checking_boosts": [],
  "relationship_bonuses": {}
}
```

The result contains a descending `ranked` list with APY components, annual interest, annual fees, net amount, feasibility, and conditional eligibility status. Validate that the proposed account is feasible, that the chosen tier matches the stated balance, that no unlisted checking boost was added, and that the selected card bonus is the highest applicable one.

`references/product_catalog.json` is a reusable extract of documented product terms, not live account data. Confirm current disclosures and identify unresolved source conflicts before representing a term as final.

## Customer-facing response structure

For an advice-only request:

1. State the recommended combination, its effective APY, estimated interest, card annual fee, and estimated one-year net.
2. State the comparison assumptions: retained balance, eligibility/approval, active linkage, and that only the highest card bonus was used.
3. Explain any excluded options, such as opening/minimum balance requirements or missing eligibility data.
4. If the customer’s checking account is not an exact qualifying pairing, explicitly say that no checking boost was included.
5. Ask whether the customer wants to proceed only after presenting the comparison. Do not open an account based on an exploratory request.

For a credit card, use the documented application process. If no authorized agent credit-card-opening tool is provided, explain that approval requires the standard online application and requested identity/income information; do not simulate approval or claim that a card was opened.

## Savings opening and funding workflow

Perform these steps only after every prerequisite in the mandatory banking control and the savings eligibility checklist is confirmed.

1. Verify identity and authority, then confirm all savings eligibility rules: verified identity, at least one active Rho-Bank checking account held for at least 14 days, fewer than five personal savings accounts, and no collections or negative balances.
2. Confirm the product and full official `account_class` string with the customer. Confirm the opening-deposit requirement and any relevant ongoing requirement.
3. Unlock and call the normal agent banking tool `open_bank_account_4821` with the authenticated `user_id`, `account_type` set to `savings`, and the exact confirmed `account_class`. Never substitute a shortened account class.
4. Verify that the returned account details identify the newly created savings account. Do not report success if the tool failed or omitted a destination account identifier.
5. Ask whether the customer authorizes an immediate opening-deposit transfer from a specified eligible checking account. A prior statement of desired funding is not sufficient if it did not explicitly authorize this transfer.
6. If authorized, recheck source ownership, available balance, exact amount, fees, limits, cutoffs, and the new destination account. Unlock and call `transfer_funds_between_bank_accounts_7291` using the verified source account ID, new destination account ID, and authorized amount.
7. If the customer declines or defers funding, tell them the savings account must be funded within 30 days by internal transfer or external deposit or it will be closed.
8. Confirm the new account details and either successful funding details or the 30-day funding deadline. Preserve the mandatory banking control and verification facts in the interaction record.

Stop rather than act if identity, ownership, eligibility, balance, selection, or authorization cannot be verified. If the runtime does not expose the required account or transfer tools, explain that the action cannot be completed in the current channel; do not fabricate tool results.
