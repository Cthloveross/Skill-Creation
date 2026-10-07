---
name: savings-card-net-return-advisor
description: Recommend and, only after authorization, support opening a personal savings account paired with a credit card when a customer wants to maximize one-year savings yield net of recurring card and subscription fees. Use for evidence-backed APY comparison, non-stacking bonus analysis, savings-opening eligibility, and controlled funding.
---

# Savings and Credit-Card Net-Return Advisor

Use this Skill to answer a customer who wants the best savings-account/credit-card combination for a stated deposit and period, especially where APY bonuses, annual card fees, subscriptions, and linked-account boosts may affect the result. It supports a recommendation and a subsequent savings-opening workflow; it does not independently apply for credit cards or make transfers.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Treat an informational recommendation as non-actionable advice. Opening an account, submitting a credit-card application, linking products, or moving funds is a banking action and requires the applicable controls below.

## 1. Establish scope and gather only necessary facts

1. Identify the customer profile only as needed to personalize advice. Do not treat a database lookup or a supplied name as identity verification.
2. Ask for or confirm:
   - deposit amount and intended holding period;
   - whether the customer requires a no-annual-fee card and whether paid memberships are acceptable;
   - expected minimum balance and whether the opening deposit and ongoing-balance requirements can be met;
   - any relevant linked checking account, existing cards, and whether products are under the same profile;
   - credit-score eligibility only where product documentation states a threshold. Explain that eligibility thresholds do not guarantee approval.
3. Gather current product facts from the task-supplied documentation: account base APY and tier thresholds, recurring account fees, opening/ongoing minimums, card annual fees, required subscription charges, APY bonuses, and eligibility/linking conditions.
4. Do not infer a bonus percentage from a document for a different savings account. Do not fill in unspecified fees, boost amounts, product availability, or card terms.

## 2. Evaluate candidates from documented terms

For a stable balance over a one-year period, compare each viable combination as:

`estimated net return = opening balance × (effective APY / 100) − known annual recurring costs`

APY is already an annualized yield. Use the formula as an estimate for a balance that remains constant; do not apply a second daily-compounding calculation to an APY. For a different term, prorate only when the relevant fees and terms permit it, and clearly label the result as an estimate.

Determine effective APY in this order:

1. Select the account's documented base APY or the documented balance tier that the stated balance qualifies for.
2. For all applicable active credit cards, apply **only the highest** documented credit-card APY bonus. Credit-card bonuses do not stack.
3. For all applicable qualifying linked checking accounts, apply **only the highest** documented checking-account APY boost. Checking boosts do not stack.
4. Add documented relationship, direct-deposit, or account-tier bonuses only if their own terms say they are eligible and additive. Do not assume a relationship bonus is available merely because the customer holds multiple products.
5. Subtract every known recurring annual cost required to obtain or maintain that result, including card annual fees and required memberships. Separately disclose any possible maintenance fee or transaction fee whose occurrence depends on behavior.

Exclude candidates that violate a stated customer constraint, such as a nonzero annual card fee or a paid subscription the customer refuses. If two candidates tie within the stated precision, present both rather than inventing a preference. If documentation is incomplete, state which fact is missing and provide a conditional comparison rather than claiming a maximum.

Use `scripts/rank_combinations.py` for deterministic arithmetic after translating the current documented facts into its input schema. The script is a calculation aid, not a source of product terms.

## 3. Give the recommendation

Provide a concise, auditable answer containing:

- the selected account and card, conditional on application approval and all ongoing eligibility/linking requirements;
- the base APY, applied card bonus, any applied checking/other bonus, and effective APY;
- the estimated interest, each known recurring cost, and estimated net return for the stated balance and period;
- material account requirements, including opening deposit, ongoing minimum balance, paperless requirement, and relevant withdrawal/maintenance terms when documented;
- why alternatives with a higher headline APY did not win (for example, a fee, subscription, tier minimum, unavailable boost, or non-stacking rule);
- a request for explicit selection before beginning any account-opening workflow.

Never claim a card has been opened, approved, linked, or that a bonus is active unless an applicable execution tool has confirmed it. If there is no supported credit-card application tool, direct the customer to the documented application channel and do not simulate an application.

## 4. Controlled savings-account opening workflow

Run this section only after the customer explicitly selects the savings account and authorizes opening it.

1. **Verify identity and authority.** Have the customer confirm at least two profile fields (date of birth, email, phone number, or address) against the profile record. Obtain the current time, then call `log_verification` with the required complete profile fields and timestamp only after two fields match. Confirm the requester is authorized for the selected profile.
2. **Check savings eligibility before opening.** Confirm all of the following: the customer is verified; has at least one active Rho-Bank checking account; has held checking for at least 14 days; has fewer than five personal savings accounts; and has no accounts in collections or negative balances. Do not proceed if any condition fails. Obtain account/status information through available supported tools or ask for required confirmation when no lookup is available; do not fabricate a result.
3. **Confirm the product and funding terms.** Confirm the full official `account_class` name ending in `Account`, required opening deposit, ongoing balance requirement, applicable fees, and paperless requirement. Confirm the funding choice and, for a transfer, source checking account, destination, amount, available balance, ownership, limits, cutoffs, and final authorization.
4. **Open only the savings account.** Unlock `open_bank_account_4821`, then call it with the authenticated user ID, `account_type` set to `savings`, and the exact confirmed full `account_class`. Do not use an abbreviation or a guessed product name.
5. **Fund only with explicit authorization.** After a successful opening returns the destination account ID, ask whether the customer wants an immediate opening-deposit transfer. If yes, unlock and call `transfer_funds_between_bank_accounts_7291` with the confirmed owned source checking account, newly opened destination account, and authorized amount. If no, clearly state the documented 30-day funding deadline and closure consequence.
6. **Finish.** Report only confirmed new-account details and funding status. State any remaining customer action, including paperless enrollment or an unsupported card application.

If the customer has reached the five-account limit, has insufficient checking tenure, has collections/negative balances, cannot meet the opening minimum, declines a required prerequisite, or fails identity verification, do not open the account. Explain the relevant blocker and next step.

## Script interface

Run `scripts/rank_combinations.py` with JSON on stdin. It emits JSON on stdout.

Input schema:

```json
{
  "deposit": 5000,
  "term_years": 1,
  "constraints": {
    "max_card_annual_fee": 0,
    "allow_paid_subscription": false
  },
  "combinations": [
    {
      "id": "stable-runtime-label",
      "savings_account": "Full official account name",
      "card": "Card name or null",
      "base_apy_percent": 4.0,
      "card_apy_bonuses_percent": [0.45],
      "checking_apy_boosts_percent": [],
      "other_additive_apy_bonuses_percent": [],
      "annual_card_fee": 0,
      "annual_subscription_fee": 0,
      "other_known_annual_costs": 0,
      "notes": ["Documented eligibility condition"]
    }
  ]
}
```

All monetary amounts and percentage-point bonuses must be nonnegative numbers. Each candidate must already reflect only bonuses documented as applicable to that candidate and the customer's facts. The output lists eligible candidates ordered by estimated net return, rejected candidates with reasons, and the highest-return set. Validate that the candidate with the highest output `net_return` also satisfies every stated constraint; then cross-check each input term against the supplied documentation before communicating it to the customer.
