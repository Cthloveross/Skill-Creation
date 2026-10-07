---
name: savings-card-combination-advisor
description: Recommend a compatible personal savings account and credit card combination when a customer prioritizes savings yield, subject to card eligibility, credit-verification preferences, statement-delivery needs, and APY bonus rules. Use before taking account-opening actions.
---

# Savings and credit-card combination advisor

Use this Skill to give an evidence-based recommendation for a customer who wants a savings account plus a credit card, especially where card-linked APY bonuses may affect the savings yield. It distinguishes a recommendation from opening an account: do not perform an application, account opening, funding transfer, or identity verification merely because the customer asks for options.

## Runtime inputs

Read the current conversation and any supplied public task inputs for:

- available cash, desired deposit, and savings horizon;
- the customer's credit score range, subscription status, invitation status, and preference for a credit-verifying card;
- non-negotiable savings requirements, such as mailed paper statements;
- products already held and whether they are under the same customer profile; and
- explicit selection, funding authorization, and identity-verification information.

Use `references/product_rules.json` for the documented product facts in this package. Do not assume facts that are absent from the current customer record or conversation. In particular, do not infer that a checking account with a similar name is a documented qualifying pairing.

## Method

1. **Convert statements into constraints.** Mark a product unavailable if it conflicts with a stated hard requirement. Examples include a required subscription the customer lacks, an invitation-only product without an invitation, a score minimum above the stated score, a savings product requiring paperless statements when mailed statements are required, or a no-credit-check card when the customer requires credit verification.
2. **Apply card eligibility before comparing yields.** Distinguish “meets stated published minimums” from approved; card underwriting can still decline an application.
3. **Check account funding and tier eligibility.** Compare the planned deposit with the opening deposit, ongoing balance, and APY tier threshold. Do not describe a higher tier as applicable when the balance is below its threshold.
4. **Apply APY bonuses correctly.** A documented card bonus applies only when both eligible products are under the same customer profile. Credit-card bonuses do not stack: use only the highest applicable card bonus. Add separately documented relationship, direct-deposit, or qualifying linked-checking bonuses only when their conditions are actually confirmed. Multiple checking boosts likewise use only the highest applicable one.
5. **Calculate and explain the result.** Use the supplied calculator for a transparent estimate. Treat an APY as the one-year yield: for a stable balance, estimated annual interest is `balance × APY / 100`. State that actual interest may vary with daily balances, qualification changes, and account crediting practices. Round money only for presentation.
6. **Present the recommendation plainly.** Name the best documented compatible combination, its effective APY under confirmed conditions, approximate one-year earnings, the reason alternatives do not meet constraints, and any conditional upside that requires a fact not yet confirmed.
7. **Separate advice from execution.** If the customer wishes to proceed, obtain confirmation of the exact savings account and card application choice. For savings opening, follow the documented procedure: authenticate/verify the customer, confirm an active checking account held at least 14 days, fewer than five personal savings accounts, and no collections or negative balances; then use the designated normal banking opening tool with `account_type: "savings"` and the full official `account_class`. Only transfer an opening deposit after explicit authorization. If funding is deferred, communicate the documented 30-day funding deadline. Card applications should use the normal supported application flow only after required consent.

## Calculator

`scripts/yield_calculator.py` accepts JSON on stdin and emits JSON on stdout.

Input schema:

```json
{
  "balance": 8000,
  "base_apy_percent": 3.0,
  "bonuses_percent": [0.15],
  "days": 365,
  "relationship_bonus_percent": 0.025
}
```

- `balance` and `days` must be nonnegative numbers (`days` defaults to 365).
- APY and bonus fields are percentage points, not decimal fractions.
- `bonuses_percent` must already reflect non-stacking selection; the script rejects multiple nonzero card bonuses unless `allow_multiple_card_bonuses` is explicitly true for a non-card use case.
- Omit a conditional bonus unless its qualifying condition is confirmed.

Output includes the effective APY, estimated interest, ending balance, and a calculation note. Example runnable call:

```sh
printf '%s' '{"balance":8000,"base_apy_percent":3.0,"bonuses_percent":[0.15]}' | python3 scripts/yield_calculator.py
```

## Validation checklist

Before replying or acting, verify that:

- every hard customer requirement has been addressed;
- no card was recommended as guaranteed approval;
- no unconfirmed checking, direct-deposit, relationship, invitation, subscription, or profile-link benefit was counted;
- only one card bonus and one checking boost were counted where selection policies apply;
- dollar estimates use the actual planned balance and disclosed effective APY;
- paper-statement requirements and account funding requirements are explicit; and
- no banking action is proposed as already completed unless the normal banking tool reported success.

If facts needed to determine eligibility or a bonus are unavailable, state the limitation, show the recommendation based on confirmed facts, and ask only the targeted follow-up needed to resolve it.
