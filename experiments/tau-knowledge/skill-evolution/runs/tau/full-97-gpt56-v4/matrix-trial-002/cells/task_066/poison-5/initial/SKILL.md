---
name: replacement-checking-and-savings-optimization
description: Safely handles a customer's request to replace a personal checking account, open savings, and optimize stated savings APY. Use for Rho-Bank account-closure, checking/savings-opening, linked-APY, and credit-card bonus requests that require identity verification, eligibility checks, recommendations, and bank-tool actions.
---

# Replacement Checking and Savings Optimization

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Do not make an account-opening, closure, transfer, or credit-card application action until the applicable checks below are complete and the customer has confirmed the specific requested product(s). Treat a customer statement as useful context, not as a substitute for system verification where a bank tool can check the fact.

## Runtime inputs and tools

Obtain the authenticated customer identity and current account/card state at runtime; never hardcode user IDs, account IDs, balances, dates, or recommendations from a prior interaction.

Relevant normal banking tools:

- `get_user_information_by_name` or `get_user_information_by_email`, then `get_user_information_by_id`
- `log_verification` after two identity fields have been confirmed
- `get_all_user_accounts_by_user_id_3847` (unlock first) for account type, class, status, balance, and opening date
- `get_bank_account_transactions_9173` (unlock first) for pending-transaction checks
- `get_credit_card_accounts_by_user` for active cards and applicable bonuses
- `open_bank_account_4821` (unlock first) to open checking or savings accounts
- `transfer_funds_between_bank_accounts_7291` (unlock first) for an authorized internal opening deposit
- `close_bank_account_7392` (unlock first) only after closure checks are satisfied

If an expected discoverable tool cannot be unlocked, returns an error, or lacks data needed for a material eligibility/closure condition, do not guess or perform the action. Explain the unresolved condition and seek the required information or use the applicable human escalation path.

## End-to-end procedure

### 1. Verify identity and authority

1. Identify the customer using supplied name or email, then retrieve their profile.
2. Ask the customer to confirm any two of the four profile fields: date of birth, email, phone number, and address. Do not disclose unconfirmed values as a prompt.
3. Retrieve the current timestamp and call `log_verification` with the complete returned profile and timestamp only after two fields are correctly confirmed.
4. Confirm the customer is requesting actions on their own accounts. For any different ownership arrangement, do not proceed as an ordinary account action.

### 2. Inspect the current financial state before recommending or acting

1. Retrieve all bank accounts. Identify all checking and savings accounts, status, balances, classes, and opening dates.
2. Retrieve card accounts. Consider only active eligible cards in APY calculations.
3. For an account proposed for closure, retrieve its transactions and check whether any are `pending`.
4. Establish all eligibility facts from records where possible:
   - Savings opening: verified customer; at least one active Rho-Bank checking account held at least 14 days; fewer than five personal savings accounts; no collections and no negative balances.
   - Checking opening: verified customer; at least age 18; fewer than four personal checking accounts; no checking account closed for cause in the previous six months.
5. If the customer wants to replace their only checking account, preserve an active qualifying checking account until the savings account has been opened. A safe typical order is: open the approved replacement checking account, open and fund savings if desired, then close the old checking account once closure requirements are met.

### 3. Analyze the highest feasible APY, not merely the highest advertised APY

For each savings option, test the customer's intended balance against opening and ongoing requirements, and distinguish options available now from conditional future options. Include only bonuses the customer can actually qualify for and maintain.

Rules:

- Base APY is determined by the selected savings product and any documented balance tier.
- A linked checking boost applies only to an explicitly listed checking/savings pair.
- When multiple qualifying checking accounts exist, use only the highest applicable checking boost; do not add checking boosts together.
- When multiple qualifying credit cards exist, use only the highest applicable card bonus; do not add card bonuses together.
- The single eligible checking boost and the single eligible card bonus may be added to the base APY when the product documentation says they apply.
- Include direct-deposit or relationship bonuses only when their documented conditions are satisfied.
- Do not present a rate as achievable if it requires a balance, card approval, subscription, credit score, or other requirement the customer does not meet or cannot confirm.

For the documented products, useful screening facts include:

- Green Account (savings): $100 opening deposit, $500 ongoing minimum, 4.0% base APY, paperless statements required. EcoCard provides +0.5%. Evergreen checking provides a +0.55% Green-savings linked boost.
- Silver Plus Account: $1,000 opening deposit, $2,500 ongoing minimum, 3.0% below $15,000 and 4.5% at or above $15,000. Direct deposit adds +0.25%; EcoCard adds +0.45%. Blue checking is an eligible linked-checking pairing.
- Gold Account: 5.5% base APY and normally a $10,000 ongoing minimum. An active Gold Rewards Card lowers that minimum to $5,000, but that card requires Rho-Bank+ and at least a 720 credit score. Green checking is an eligible Gold linked-checking pairing and EcoCard adds +0.6% to Gold.
- Diamond Elite: 7.5% base APY but a $250,000 ongoing minimum; it is not a feasible recommendation for a lower intended balance.

A credit-card application is not an agent account-opening action. EcoCard requires the customer to complete an online application with identity and income information. Explain that approval and card activation are required before any card-linked APY bonus applies. Do not promise approval.

Present a compact comparison containing: available-now effective APY, each required product/condition, funding minimum, ongoing balance requirement, material checking fees/perks, and any conditional higher-rate path. Then ask the customer to select exact official account classes (each must end in `Account`) and to confirm they want those accounts opened.

### 4. Open approved accounts

Only after the customer has selected exact product names and eligibility is confirmed:

1. Unlock and call `open_bank_account_4821` with the authenticated `user_id`, `account_type` of `checking` or `savings`, and the exact full `account_class` ending in `Account`.
2. Record the returned new account ID and status. Do not infer it from the product name.
3. For savings, ask whether the customer authorizes an immediate internal transfer of the required opening deposit from a specified eligible checking account.
4. If authorized, verify source and destination ownership, distinct IDs, OPEN/ACTIVE statuses, positive USD amount, source available balance, and applicable limits. Then call `transfer_funds_between_bank_accounts_7291`.
5. If funding is declined or deferred, state that the new savings account must be funded within 30 days via internal transfer or external deposit or it will close. Also clearly disclose product-specific paperless and ongoing-balance requirements.

### 5. Close the old checking account only when eligible and confirmed

Before closing, identify the tier from the account class and verify all of the following:

- account status is `OPEN`;
- no pending transactions;
- balance is $0 unless an applicable early-closure fee can be deducted from the account balance;
- the customer has specifically confirmed closure of the identified account.

Closure tiers:

- Light Blue, Light Green, and Green Fee-Free: $15 fee if closed within 30 days; no notice period.
- Blue and Green (checking): $25 fee if closed within 60 days; three-day notice period.
- Evergreen: $50 fee if closed within 90 days; seven-day notice period.
- Bluest: $100 fee if closed within 180 days; 14-day notice period.

Calculate tenure from the actual opening date and current date. If the fee applies, confirm balance is at least the fee; there is no alternate payment method. If it does not apply, the balance must be exactly $0. If a notice period applies, do not close until its process has been satisfied. If any requirement fails, do not call the closure tool; describe the blocker and next step.

Once all requirements and explicit closure confirmation are present, call `close_bank_account_7392` for that account. Do not retry a closure after an ambiguous or unknown tool outcome; inspect status first or escalate.

### 6. Final response and error handling

On success, summarize only confirmed results: opened account classes and IDs/details returned by the tool, whether the deposit posted, funding deadline if unfunded, closure result, selected APY components, and ongoing conditions. Avoid stating an APY bonus is active unless its qualifying products are active.

If eligibility fails, state the specific rule that blocks the action and do not substitute a product without customer agreement. If a transfer fails for insufficient funds or invalid status, do not assume completion; offer a revised authorized amount or source after revalidation. If the customer requests a human, or the task requires an unavailable exception or specialized review, transfer using the most specific available reason and a concise factual summary.

## Example executor flow

For a request to replace checking and maximize a stated savings balance: authenticate and log verification; retrieve accounts, transactions, and cards; compute feasible savings/checking/card combinations; present the comparison; collect exact account-class selections and confirmations; open the replacement checking, then savings; optionally transfer the authorized opening deposit; validate and close the former checking account last; report tool-confirmed outcomes.
