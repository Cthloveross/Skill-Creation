---
name: savings-card-net-return-advisor
description: Compare savings-account and credit-card combinations by one-year interest minus annual card fees, while enforcing non-stacking APY rules and clearly separating confirmed, conditional, and unavailable options. Use for customer questions about choosing a savings account and credit card to maximize net annual return.
---

# Savings and card net-return advisor

Use this Skill when a customer wants a fact-based comparison of a savings account plus one or more credit cards, especially where cards or linked checking accounts affect APY.

## Required facts to collect

From the task's supplied product documentation and the customer's statements, collect only facts applicable to the proposed account and card(s):

1. Savings account base APY, balance requirements, and opening-deposit requirement.
2. Each card's APY bonus for that *specific* savings account, annual fee, and stated application requirements.
3. Whether the customer meets each stated requirement. Do not infer a credit score that the customer cannot confirm.
4. Any linked-checking APY boost and whether the customer's checking/savings pairing is explicitly listed as qualifying.
5. Any separately documented relationship or tier bonuses that apply to the same profile.
6. Account-opening prerequisites before offering to open an account.

Do not treat similarly named accounts as the same product. In particular, a linked-checking boost applies only to an explicitly documented checking/savings pairing.

## APY policy and calculation method

Apply the policies in `references/apy_rules.md`:

- Among multiple eligible credit-card bonuses, use **only the single highest** one; never sum card bonuses.
- Among multiple eligible checking boosts, use **only the single highest** one; never sum checking boosts.
- The selected card bonus, selected checking boost, and separately documented additive bonuses may be added to the base APY when their documents say they stack.
- For a stable balance over one year, calculate estimated APY earnings as `balance × effective_APY / 100`. Because APY is already an annualized yield, do not compound it again in this comparison.
- Net one-year return is estimated APY earnings minus the card's annual fee. Clearly label this as an estimate and exclude unprovided fees, taxes, spending rewards, changing balances, and approval uncertainty.

Use `scripts/compare_options.py` for arithmetic and transparent ranking. It receives JSON on standard input and emits JSON on standard output. See the script's module documentation for its schema and example.

## Eligibility and recommendation protocol

1. Build one option for every documented account/card combination that is relevant to the customer's goal. Include a no-card option if it is meaningful.
2. Classify requirements truthfully:
   - **eligible**: all stated requirements relevant to the comparison are confirmed met.
   - **conditional**: a required fact, such as the customer's score, is unknown. State the exact missing fact and do not present it as available.
   - **ineligible**: a confirmed requirement is not met.
3. Recommend the highest estimated net return among confirmed eligible choices. If a higher-return choice is conditional, show its exact condition and its estimated difference from the confirmed recommendation.
4. If the customer asks what is best if they do not qualify for one named card, compare the remaining alternatives rather than assuming they fail every other card. If another option has a lower credit-score threshold, state that threshold; if no score is known, keep it conditional. A card with no stated score requirement may be presented as not score-gated, but approval is never guaranteed.
5. State the annual fee explicitly. A smaller APY bonus can be economically better after fees, so rank by net dollars rather than APY alone.
6. Mention balance and opening requirements. Do not say a customer qualifies merely because they have funds unless the documentation makes that conclusion valid.

## Customer response structure

Give a concise response containing:

- the recommended confirmed combination and the estimated effective APY, gross annual interest, annual fee, and net one-year return;
- the important next-best conditional or alternative combination(s), including their requirements and net-return difference;
- the non-stacking explanation when more than one card or checking boost could otherwise be counted;
- a caveat that product approval and unprovided conditions can change the outcome; and
- the next step: offer to check account-opening eligibility or begin the authorized application/opening flow, rather than opening accounts or applying without authorization.

Do not claim that an existing checking account creates a boost unless its exact pairing is listed. Do not claim a card is approved. Do not invent reward income, promotional value, rate changes, or fees.

## Opening-account safeguards

If the customer elects to open a personal savings account, follow the supplied bank procedure before any account-opening action. The procedure requires identity verification, an active qualifying checking account, required checking tenure, fewer than the allowed maximum personal savings accounts, and no collections or negative balances. Confirm the exact official savings account class. After the account is opened, obtain authorization before transferring an opening deposit. If the customer declines an immediate transfer, communicate the documented funding deadline.

This advisory Skill itself does not authorize, apply for, open, or fund accounts.

## Runnable calculation example

Create an input JSON object from current product facts, then run:

```text
python3 scripts/compare_options.py <<'JSON'
{"balance":"30000","profile":{"credit_score":null,"has_subscription":true},"options":[{"name":"Option A","base_apy_pct":"5.0","annual_fee":"0","card_bonus_pct":"0.2","minimum_credit_score":700,"requires_subscription":true},{"name":"Option B","base_apy_pct":"5.0","annual_fee":"50","card_bonus_pct":"0.1","minimum_credit_score":0}]}
JSON
```

Interpret `confirmed_ranked` as the set whose documented requirements are known met. Interpret `conditional_ranked` only as scenarios that require clarification. Verify that the selected bonus fields correspond to the correct savings account and that no unsupported checking boost or relationship bonus was entered.
