---
name: business-referral-bonus-advisor
description: Assess whether a checking-account customer may submit a business referral and recommend the highest referrer bonus that fits a proposed opening deposit. Use for informational referral-program questions; do not use to open an account, submit a referral, or move money.
---

# Business Referral Bonus Advisor

Use this skill to give a compliant, evidence-based referral recommendation. It evaluates the referrer's tenure and bonus limits, the proposed business's stated eligibility, and each product's qualification terms. It is intentionally product-agnostic: obtain the current program rules from the supplied task materials at runtime rather than embedding product rates or customer data in this package.

## Scope and safety

This workflow provides information only. A recommendation is not a referral submission, account-opening request, or promise that a bonus will be paid. Do not open an account on behalf of the prospective business, create a referral, alter customer data, or imply that an attestation is a verified fact.

Before discussing or recommending referral terms, check whether the referrer is eligible to submit referrals. If the referrer cannot be resolved, their tenure is unavailable, or recent/annual bonus history cannot be checked, explain that eligibility cannot yet be confirmed and request only the missing information.

For any later banking action, preserve this prerequisite verbatim with the action procedure:

> Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

No referral-submission tool is assumed by this skill. If an approved submission or relationship-manager workflow is supplied separately, use only that documented workflow after the relevant prerequisites and required confirmation have been obtained.

## Required information and checks

1. **Resolve the referrer for read-only review.** Ask for an allowed lookup identifier (for example, exact account-holder name, user ID, or email) and use the available read-only customer lookup. Retrieve the referral history for the resolved user ID.
2. **Determine referrer tenure.** Obtain the opening date of the *earliest* Rho-Bank checking account from an authoritative account record when available. If such a record is unavailable, ask for the date and clearly label the result as based on the customer's statement. Do not use the currently held product or a credit-card opening date as a proxy.
3. **Check limits before recommending.** Count only successfully paid/`COMPLETE` referrals as bonuses received, unless current program terms explicitly define another status as paid. Check:
   - the shared rolling-window cap across all checking products using the actual bonus timestamps when available;
   - the annual cap using the scope stated by the product program. Do not assume that a product-specific annual cap is shared across products unless the terms say so.
4. **Obtain prospective-business facts.** Confirm or mark as unverified: new-customer/no relevant accounts during the exclusion period, different registered address, different primary business owner/signer where required, intended deposit amount and timing, use of new money rather than an internal transfer, and whether another promotion is being used.
5. **Build current product rules.** For every candidate product, capture product key/name, referrer reward, qualifying-deposit threshold, deposit window, minimum referrer tenure, annual cap, and annual-cap scope. Also capture requirements to open that specific product and any stated good-standing or retention conditions.
6. **Evaluate and rank.** Run `scripts/evaluate_referrals.py` with the gathered facts and rules. It blocks products with a known unmet requirement, ranks the remaining products by referrer reward, and reports unknown checks separately. A global rolling-window block applies to every product.
7. **Respond accurately.** Lead with the highest-paying currently admissible product(s), the referrer's bonus, and the specific threshold/deadline that make it fit. Mention higher-paying products that are excluded by the proposed deposit or other known condition. State each remaining confirmation condition, including new-money, retention, good-standing, promotion-stacking, and possible clawback conditions when applicable. Do not state a bonus is guaranteed.

If the calculation returns `conditional`, it is acceptable to give a *conditional* best option only after the referrer-side checks above have been completed; clearly identify the prospective-business facts that still require confirmation. If it returns `blocked` or `unavailable`, do not name an ineligible product as a recommendation.

## Calculator

Run:

```text
python scripts/evaluate_referrals.py < input.json
```

The script reads one JSON object from standard input and emits one JSON object to standard output. It uses only the Python standard library.

### Input schema

```json
{
  "as_of": "ISO-8601 date or timestamp",
  "proposed_deposit": 0,
  "referrer_tenure_days": 0,
  "referrals": [
    {
      "date": "ISO-8601 date or timestamp",
      "status": "COMPLETE",
      "product_key": "optional product key",
      "referred_account_type": "optional product name"
    }
  ],
  "shared_rolling_limit": {"max_bonuses": 2, "window_days": 9},
  "eligibility": {
    "new_customer": true,
    "different_address": true,
    "different_primary_owner": true,
    "new_money": true,
    "no_promotion_stacking": true
  },
  "products": [
    {
      "key": "stable product key",
      "name": "display name",
      "referrer_bonus": 0,
      "qualifying_deposit": 0,
      "deposit_window_days": 0,
      "min_tenure_days": 0,
      "annual_cap": 0,
      "annual_cap_scope": "product",
      "requires_new_customer": true,
      "requires_different_address": true,
      "requires_different_primary_owner": true,
      "requires_new_money": true,
      "prohibits_promotion_stacking": true
    }
  ]
}
```

`eligibility` flags may be `true`, `false`, or omitted/`null`. Missing facts are returned as `unknown_checks`; a false required fact is a blocker. `annual_cap_scope` must be `product` (default) or `global`. Use stable product keys in both product rules and referral records where possible. If only product names are supplied, the script performs conservative case-insensitive normalized matching.

### Output interpretation and validation

The output includes `decision` (`eligible`, `conditional`, `blocked`, or `unavailable`), `shared_limit`, ranked `recommendations`, and every evaluated product with `blockers` and `unknown_checks`.

Validate before answering:

- `shared_limit.blocked` must be false for any recommendation.
- Every recommended product must have an empty `blockers` list.
- The top recommendation(s) must have the greatest numeric `referrer_bonus` among unblocked products.
- Confirm the product's account-opening, deposit-window, retention, good-standing, and bonus-payment terms against the current source materials; the calculator only evaluates fields supplied in its input.
- If any referral record is date-only rather than timestamped, heed `time_precision_warning` and obtain precise timestamps before relying on a rolling-limit boundary calculation.

## Response structure

Use a short, customer-readable result:

1. Eligibility status of the referrer, including tenure and applicable bonus-limit result.
2. Best qualifying account and the **referrer's** reward (not the prospective customer's welcome reward).
3. Why it fits the stated deposit; briefly contrast any higher reward that does not fit.
4. Outstanding conditions and timing, including that the account must be the specified product and the qualifying deposit must be new money.
5. Where supported by program terms, note retention, good-standing, annual-cap, rolling-limit, anti-stacking, and clawback constraints.

Never expose unnecessary personal fields retrieved during lookup. Do not make a referral or account-opening recommendation based solely on an unverified identity or an unexamined referral history.
