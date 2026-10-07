---
name: bank-account-transition-and-apy-advice
description: Safely handle a verified customer's request to close or replace a personal checking account, open a personal savings account, fund it, and compare documented checking/savings/card APY combinations. Use for banking-servicing conversations requiring eligibility checks, account actions, or a highest-attainable-yield recommendation.
---

# Bank Account Transition and APY Advice

Use this workflow for personal checking closure/replacement, personal savings opening/funding, and APY-combination advice. Treat product documents and live tool results as the source of truth. Never infer an unobserved account status, balance, tenure, credit score, invitation, eligibility result, or customer authorization.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## First: identify and authenticate

1. Locate the customer only from the identifying information they supplied (for example, full name or email), using the corresponding customer lookup tool.
2. Obtain and confirm two of four profile fields—date of birth, email, phone number, and address—from the customer. Do not reveal profile values as prompts or use data lookup alone as authentication.
3. Once two fields match, get the current timestamp and create the required verification log using the complete verified profile and timestamp.
4. Record the authenticated customer ID and use it for all later ownership checks. If identity cannot be verified, do not reveal account details or take an action.

A request for general product information or hypothetical APY guidance does not itself require an account-changing action, but do not use private account data until authentication is complete.

## Gather live facts before recommending or acting

Establish the customer’s goal and constraints: money to be held, desired checking benefits, current and planned cards, stated credit-score range if relevant, willingness to meet opening/ongoing balances, and whether they authorize a particular account action.

Inspect only necessary customer/account records and document:

- each relevant checking and savings account, ownership, status, opening date/tenure, balance/current holdings, pending activity, collections/negative balances, and number of accounts;
- credit-card holdings and, where supported, application eligibility—not merely an assumed score;
- the applicable account product terms: base APY, minimum opening deposit, ongoing minimum, card APY bonus, linked-checking APY boost, fees, and any invitation/subscription/age requirements;
- closure tier, elapsed account age, early-close fee, notice period, and whether a closure is permitted; and
- transfer source/destination ownership, status, available balance, amount, and explicit authorization.

If a needed fact cannot be retrieved through an available supported tool, explain the limitation and ask for the fact or provide conditional advice. Never claim that profile data can reveal a credit score unless a supported eligibility/score result actually does so.

## Provide highest-attainable APY advice

Build recommendations from documented current terms rather than a vague claim that one product is best.

1. Enumerate savings products that can accept the requested balance, respecting opening and ongoing balance requirements.
2. For each, start with its documented base APY.
3. Identify qualifying linked checking accounts. A checking boost applies only for the exact documented checking/savings pairing and only when both products are on the same customer profile. Where several checking boosts apply, use only the highest checking boost; do not add checking boosts together.
4. Identify qualifying held or realistically available credit cards. Apply only the highest applicable card APY bonus unless the specific product documentation explicitly establishes a different stacking rule. Do not treat invitation-only cards as attainable without an invitation, or a score-gated card as attainable without a confirmed qualifying score/eligibility.
5. Add bonuses only where the product terms say they stack. Verify that the required balance and every condition for each component can be maintained.
6. Present each viable effective APY as base + selected checking bonus + selected card bonus, with the product names, prerequisites, and limitations. Clearly label conditional alternatives (for example, “if eligible/approved”) and distinguish them from currently attainable options.
7. If the customer asked for the absolute highest rate but eligibility is unknown, do not manufacture a definitive answer. State the highest confirmed attainable option and the condition(s) required for any higher conditional option. Offer to continue once the customer confirms the missing eligibility fact or expressly chooses a combination.

Use `scripts/rank_apy_options.py` for a transparent deterministic ranking when product terms have been entered into the described JSON format. The script is an advisory calculation only; it neither establishes eligibility nor executes a banking action.

### APY-ranking helper

Run with JSON on standard input and read JSON from standard output:

```sh
python3 scripts/rank_apy_options.py <<'JSON'
{
  "balance": 100000,
  "savings": [{"name":"...","base_apy":0,"opening_deposit":0,"minimum_balance":0}],
  "checking_boosts": [{"checking":"...","savings":"...","apy_boost":0,"eligible":true}],
  "card_bonuses": [{"card":"...","savings":"...","apy_bonus":0,"eligible":true,"held":true}],
  "require_held_card": true
}
JSON
```

Amounts are USD numbers and APY values are percentage points (for example `0.3` means +0.3 percentage points). `eligible` must be set from verified facts; use `false` for unknown or unavailable eligibility. When `require_held_card` is true, only bonuses marked both eligible and held are included. The result contains eligible ranked combinations, excluded combinations and reasons, and structured validation errors. Review the underlying product terms because the helper uses the documented general rule of highest checking boost plus highest card bonus and does not decide whether a product’s special terms override that rule.

## Evaluating whether an APY bonus offsets a card fee

For a card already known to be eligible for the savings account, compare the *incremental* card bonus—not the total savings yield—to the annual fee. The annual gross incremental interest is `qualifying savings balance × card APY bonus / 100`; subtract the annual fee to state the annual result before tax. This is an estimate: it assumes the documented APY applies to the full qualifying balance throughout the year, the card and savings remain eligible, and the fee is charged for the year. Do not represent an unapproved card's bonus as guaranteed.

Use `scripts/compare_apy_fee.py` for currency-rounded arithmetic. It reads JSON from standard input with nonnegative `balance`, `bonus_apy` (percentage points), and `annual_fee` values, and emits `gross_incremental_interest`, `annual_fee`, `net_before_tax`, and `errors` on standard output. Supply values from the current customer request and current product terms; if `errors` is nonempty, correct the inputs before quoting the calculation.

## Opening a personal checking account

Do not open an account based solely on a preference to “swap” or a request for a recommendation. Obtain the exact selected official account class and explicit authorization to open it.

Before opening, verify all documented checking-opening requirements:

- verified customer identity;
- customer age is at least 18;
- no more than four personal checking accounts; and
- no checking account closed for cause in the prior six months.

Also verify any product-specific eligibility and funding requirements. Use supported account records to check the account-count and recent-closure conditions. If all requirements are met, unlock the documented internal account-opening tool and call it with the authenticated user ID, `account_type` set to `checking`, and the exact full official `account_class` ending in `Account`. Confirm the result, including the new account identifier/status and any funding obligation. Do not silently close the old account merely because a replacement was opened.

If the account-opening service is the only supported mechanism that can evaluate a documented eligibility condition, do not guess that condition. With verified identity and explicit authorization, submit the exact requested opening once; report the service's actual approval or eligibility failure and never retry an uncertain outcome. This does not authorize closure of any other account.

## Opening and funding a personal savings account

Get the exact savings product selection and explicit authorization before opening. Confirm all personal-savings requirements:

- identity verified;
- at least one active Rho-Bank checking account;
- fewer than five personal savings accounts;
- no accounts in collections or with negative balances; and
- at least 14 days of checking-account tenure.

Verify the product’s required opening deposit and the chosen source’s available balance. Then unlock and call the documented internal account-opening tool with `account_type` set to `savings` and the exact official `account_class` ending in `Account`.

After a successful opening, ask whether the customer authorizes an immediate internal transfer of the required opening deposit. If yes, verify both accounts are ACTIVE or OPEN, owned by the customer, distinct, and that the source has sufficient available funds; then unlock and use the documented internal transfer tool. Confirm a successful posting and do not duplicate a transfer. If the customer declines, explain the documented 30-day funding deadline and closure consequence.

## Closing a personal checking account

Closing is a separate, consequential action. Obtain explicit confirmation that identifies the exact account to close and, if applicable, confirms that any required notice/fee is accepted. Do not interpret a request to “swap” as sufficient confirmation after discussing recommendations.

Before closure, verify account ownership, status is OPEN, no pending transactions, current holdings, account tier, date opened, early-closure fee, and notice period. If an early closure fee applies, confirm the balance can cover it; otherwise the account balance must be zero. Ensure the customer has a suitable destination for remaining funds before closure where applicable. If any prerequisite fails, do not close the account; explain the blocker and a safe next step.

When all conditions, timing, and confirmation requirements are satisfied, unlock and call the documented internal closure tool. Confirm only the actual reported outcome. Never repeat an action that returned an unknown outcome; instead escalate or investigate with supported tools.

## Handling errors and communication

- If an account-opening limit, tenure, balance, product eligibility, or card eligibility fails, do not bypass it. Explain the specific documented condition and available alternatives.
- If a transfer fails for insufficient funds or invalid status, do not retry unchanged. Recheck live balance/status and obtain a revised authorization when needed.
- For unknown card score or invitation status, provide conditional comparisons and the highest confirmed option; do not submit a card application without a separate supported workflow and consent.
- When a user asks to close an account but policy/system conditions prevent safe completion, offer the required remediation or transfer to a human agent using the applicable closure reason if a human is needed.
- Summarize completed actions, account/product selected, funding or closure status, material fee/deadline information, and uncompleted prerequisites. Do not expose full sensitive identifiers or unnecessary personal information.
