---
name: banking-account-transition-and-apy-recommendation
description: Safely explain, compare, and, only after verification and authorization, process personal checking/savings account transitions while determining the highest documented APY setup for a stated balance. Use for account closure/opening requests, linked-checking APY boosts, savings-card APY bonuses, and eligibility-sensitive product recommendations.
---

# Banking Account Transition and APY Recommendation

Use this Skill when a customer wants to close or replace a checking account, open savings, or identify the best available savings APY. Distinguish a **conditional theoretical maximum** from the best setup the customer can currently qualify for. Never treat a recommendation as authorization to open, close, link, transfer, or apply for a product.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Core rules

1. **Verify before acting.** A name lookup or account information already visible to the agent is not identity verification. Obtain confirmation of two of the four profile fields (date of birth, email, phone number, address), retrieve the current time, and call `log_verification` only after the customer has correctly confirmed them.
2. **Read current account facts before an account action.** Unlock and use `get_all_user_accounts_by_user_id_3847` to obtain account IDs, classes, statuses, balances, and opening dates. Do not infer account status, tenure, ownership, counts, pending activity, or balance from the customer’s request alone.
3. **Keep recommendations separate from transactions.** Explaining rates is read-only. Opening, closing, transferring, or applying requires a clear, current customer authorization after all material terms are disclosed.
4. **Use the highest one within each bonus category.** Multiple eligible credit-card bonuses do not stack: apply only the highest applicable card bonus. Multiple eligible checking boosts also do not stack: apply only the highest applicable checking boost. The selected card bonus and selected checking boost may stack with the savings base APY and other separately documented bonuses.
5. **Evaluate the actual balance and conditions.** Check the savings account’s relevant balance tier and minimum balance. Evaluate card-specific minimum-balance overrides only if the qualifying card is active under the same customer profile. A card application, an unknown score, an inactive card, or an unavailable required subscription is not eligibility.
6. **Do not invent missing product terms.** If a needed APY tier, boost amount, application tool, pending-transaction status, or eligibility fact is undocumented or unavailable, say so and obtain the fact rather than assuming it.

## APY comparison method

1. List each candidate savings account that can accept the stated balance.
2. Determine the base APY for that balance tier and whether account minimums are met.
3. For each linked checking account candidate, use only a specifically documented eligible checking–savings pair and its documented boost.
4. For each card candidate, validate the application/holding requirements and select only the highest applicable card bonus for that savings account.
5. Add separately documented relationship or direct-deposit bonuses only when their conditions are confirmed. Do not use examples in product copy as a source of a rate when the explicit numeric terms conflict; show the arithmetic from the explicit base and bonus figures.
6. State each result in this form:
   - base APY;
   - selected checking boost;
   - selected card bonus;
   - any separately confirmed bonus;
   - total APY;
   - all conditions still required.
7. If the highest mathematical option depends on unmet or unknown eligibility, label it conditional. Then identify the best fully documented currently feasible option, if one exists.

Use `scripts/evaluate_apy.py` to consistently calculate and rank a set of candidate configurations. The script calculates from facts supplied at runtime; it does not determine product policy or authorize actions.

### Helper input and output

Provide JSON on stdin:

```json
{
  "balance": "<USD amount>",
  "candidates": [
    {
      "id": "<descriptive candidate name>",
      "base_apy": "<percentage points>",
      "minimum_balance": "<USD amount>",
      "minimum_balance_overrides": [
        {"minimum_balance": "<USD amount>", "eligible": true, "label": "<condition>"}
      ],
      "requirements": [
        {"name": "<condition>", "status": true}
      ],
      "checking_boosts": [
        {"label": "<source>", "apy": "<percentage points>", "eligible": true}
      ],
      "card_bonuses": [
        {"label": "<source>", "apy": "<percentage points>", "eligible": true}
      ],
      "additional_bonuses": [
        {"label": "<source>", "apy": "<percentage points>", "eligible": true}
      ]
    }
  ]
}
```

`requirements[].status` must be `true`, `false`, or `"unknown"`. The helper emits JSON containing each candidate’s effective minimum, applied highest checking/card boosts, total APY, eligibility (`true`, `false`, or `"unknown"`), reasons, and a ranking. Invoke it as `python scripts/evaluate_apy.py < request.json`. Validate that all amounts and APYs are documented numeric values, every applied bonus has `eligible: true`, and any conditional option is not represented as currently available.

## Product-specific reasoning covered by the supplied knowledge

When the relevant products are being compared, use these documented facts:

- Silver Account pays 2.5% below its $10,000 higher-tier threshold and 4.0% at or above that threshold. Its listed EcoCard bonus is 2.2%.
- Green Account (checking) can boost an eligible linked Silver Account by 0.25%; it is not a documented linked-checking pairing for Green Account (savings).
- Green Account (savings) has a 4.0% base APY and a $500 minimum balance. An EcoCard adds 0.5% when held and linked under the same profile. Evergreen Account (checking) has a documented 0.55% boost for linked Green Account (savings). EcoCard has no minimum credit-score requirement, but approval and any normal application requirements remain unconfirmed until completed.
- Gold Account pays 5.5% but normally requires $10,000. A Gold Rewards Card reduces that account minimum to $5,000 and has a documented 0.025% Gold Account APY bonus. Green Account (checking) has a 0.75% documented boost for linked Gold Account. The Gold Rewards Card requires an active Rho-Bank+ subscription and a minimum credit score of 720.
- Silver Plus has a $2,500 ongoing minimum, 3.0% Tier 1 rate below $15,000, and a separately documented 0.25% direct-deposit bonus. Blue Account has a 0.35% boost for linked Silver Plus, and EcoCard’s listed Silver Plus card bonus is 0.45%.

For example, a setup that relies on Gold Account’s reduced minimum must not be described as available unless the customer both has the qualifying active Gold Rewards Card and meets that card’s subscription and score requirements. Conversely, simply changing to a lower-rate account because a premium card is unavailable is not necessarily optimal: compare every documented balance-compatible option and its actual pairing rules. A Green Account (savings) setup cannot receive a boost intended for a Green Account (checking).

## Responding to a changed recommendation

If an earlier recommendation changes after new eligibility information:

1. Acknowledge the change directly.
2. Show the original arithmetic and conditions, including why it is conditional or unavailable.
3. Explain exactly why the alternative differs (for example, a card requirement, a savings balance minimum, or an invalid checking–savings pair).
4. Recompute the alternatives using the non-stacking rules rather than relying on a prior conclusion.
5. Identify any remaining uncertainty, especially card approval, direct-deposit enrollment, card linkage, or account eligibility.
6. Ask the customer to choose only after the explanation. Do not perform any account action while they are asking for clarification.

## Opening workflow

Apply this workflow only after verified identity, account lookup, full eligibility checks, product disclosure, and explicit authorization.

### Opening personal checking

Verify all of the following:

- Customer is verified and at least 18.
- Customer will not exceed four personal checking accounts.
- Customer has no checking account closed for cause in the past six months.
- The selected `account_class` is the complete official name ending in `Account`.

Unlock `open_bank_account_4821`, then call it with the authenticated `user_id`, `account_type: "checking"`, and the confirmed official `account_class`. Confirm the resulting account details and applicable funding requirements.

### Opening personal savings

Verify all of the following:

- Customer is verified.
- Customer has at least one active checking account and qualifying checking tenure of at least 14 days.
- Customer has fewer than five personal savings accounts.
- No account is in collections or has a negative balance.
- The customer selected a complete official savings `account_class` ending in `Account`.

Unlock `open_bank_account_4821`, then call it with the authenticated `user_id`, `account_type: "savings"`, and the confirmed official class.

After opening, ask whether the customer authorizes an immediate opening-deposit transfer. If yes, verify both account statuses, same ownership, distinct account IDs, positive USD amount, sufficient available source funds, fees/limits/cutoffs, and transfer confirmation. Unlock and call `transfer_funds_between_bank_accounts_7291`. Confirm the posting and avoid duplicate transfers. If the customer declines, explain the 30-day funding deadline and the consequence that the account will close if it is not funded.

When a customer is replacing their only seasoned checking account, plan ordering carefully. Do not close the seasoned active checking account before confirming that savings-opening eligibility and any desired funding arrangements remain satisfied. This is especially important because a newly opened checking account may not satisfy the 14-day savings-opening tenure requirement.

## Closure workflow

Before closing a personal checking account:

1. Retrieve current account information and identify the exact account ID and tier.
2. Verify ownership, account status is `OPEN`, no pending transactions, current holdings, opening date, early-closure window, applicable fee, notice period, and explicit closure confirmation.
3. For a Light Blue Account, the entry-tier rule is a $15 early-closure fee if closed within 30 days, with no notice period. If a fee applies, balance must cover it because it is deducted from the account and cannot be paid another way. If no fee applies, current holdings must be exactly $0.
4. If prerequisites are satisfied and the customer has explicitly authorized closure, unlock and use `close_bank_account_7392`.
5. Confirm the closure result and any fee charged. If a prerequisite is absent, do not close the account; explain the missing item.

A customer statement that an account is open, has no pending transactions, or has a zero balance is useful but does not replace the required account lookup and verification.

## Boundaries and failure handling

- Do not submit a credit-card application unless a documented agent workflow/tool exists and the customer gives explicit authorization. A recommendation can explain eligibility and the customer may pursue the documented application process.
- If the customer has not selected among materially different account options, provide a ranked explanation and request a choice; do not choose and open an account solely because they asked for information.
- If account lookup, identity verification, pending-transaction review, or product eligibility cannot be completed, pause the banking action and state what is needed.
- If an eligible configuration requires an unknown credit score, subscription, approval, direct-deposit status, or linkage, mark it conditional rather than rejecting or approving it.
- If the user requests a human agent, transfer using the tool’s applicable reason after summarizing the verified facts, desired action, outstanding prerequisites, and actions not taken.
