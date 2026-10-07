---
name: business-referral-bonus-advisor
description: Provide an informational, evidence-based recommendation for the highest-paying documented business-checking referral compatible with a prospective business's intended deposit and eligibility facts. Use for referral-program questions only, not to submit referrals, open accounts, or move funds.
---

# Business Referral Bonus Advisor

Give the customer a direct recommendation after the necessary read-only review and supplied eligibility answers are available. This Skill is informational only: it does not submit a referral and does not guarantee payment of a bonus.

## Authoritative policy source

Before assessing candidate products, read `references/business_referral_policy_catalog.md`. It is the packaged catalog of documented referral terms. Do **not** say that account-level referral terms are unavailable when this catalog supplies them. If the available policy source genuinely lacks a required product term, exclude that product from the ranking rather than guessing.

## Scope and safety

- Do **not** open an account, submit a referral, change customer data, make a payment, or promise a bonus.
- Use read-only customer and referral-history tools only when relevant and available.
- Do not disclose unnecessary personal data returned by a lookup.
- Treat prospective-business statements as customer attestations unless an authoritative source verifies them. A missing non-disqualifying fact makes the result conditional; it does not justify withholding an otherwise supported recommendation.
- If a later workflow performs a banking action, preserve this prerequisite verbatim with its procedure:

> Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Required review sequence

1. **Identify the referrer for read-only review.** Obtain a permitted identifier (exact name, user ID, or email), resolve it, then retrieve referral history with the resolved user ID. A lookup is not authority to take an action.
2. **Get current time** with the supplied current-time tool when available.
3. **Establish tenure.** Tenure is measured from the earliest Rho-Bank checking-account opening date, not the account product currently held. Prefer an authoritative account record. When the supplied conversation gives the customer's answer about their first checking relationship, use that duration as customer-reported evidence.
4. **Obtain or use eligibility facts.** Determine whether the referred business is a new eligible customer with no applicable existing or recently closed account, has a different registered address, and has a different primary owner/authorized signer. Establish the intended deposit. Also identify whether new money and non-stacking of promotions remain to be confirmed.
5. **Read the policy catalog and make a candidate table.** For each documented candidate, record referrer reward, deposit threshold and deadline, tenure minimum, annual cap, and product-opening requirements. Rank by the **referrer's** reward, never the referred business's welcome bonus.
6. **Apply limits correctly.** Count only `COMPLETE` referrals. The rolling nine-day cap is cross-product. Annual caps are product-specific unless a policy expressly says otherwise. Match historical referral account names to the recommended product; do not count referrals for other products against a product-specific annual cap.
7. **Respond now.** Once the relevant facts are present, give the recommendation in that response. Do not continue asking for facts that the customer has already supplied.

## Date-only referral histories

Referral tools can return a date without a time. Do not turn that limitation into a blanket refusal.

- A date plainly before the rolling-window boundary is conclusively outside the window.
- Request exact timestamps only when a date-only completed referral falls on the boundary date and could change whether the rolling limit has been reached.
- When the displayed history shows no referral for a product, its documented product-specific annual count is zero, regardless of completed referrals for other account types.
- State a limit as conditional only if an actually relevant boundary ambiguity remains.

Use `scripts/parse_referral_observation.py` to parse the numbered history response when useful. Use `scripts/evaluate_referrals.py` to make repeated comparison and limit calculations consistent.

## Calculator

Run:

```text
python scripts/evaluate_referrals.py < input.json
```

The calculator reads one JSON object on stdin and writes one JSON object on stdout. It has no network access and performs no bank action.

### Input schema

```json
{
  "as_of": "ISO timestamp, ISO date, or MM/DD/YYYY tool date",
  "proposed_deposit": 0,
  "referrer_tenure_days": 0,
  "referrals": [
    {
      "date": "ISO timestamp, ISO date, or MM/DD/YYYY",
      "status": "COMPLETE",
      "product_key": "optional stable key",
      "referred_account_type": "optional display name"
    }
  ],
  "shared_rolling_limit": {"max_bonuses": 2, "window_days": 9},
  "eligibility": {
    "new_customer": true,
    "different_address": true,
    "different_primary_owner": true,
    "new_money": null,
    "no_promotion_stacking": null
  },
  "products": [
    {
      "key": "stable key",
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

Eligibility flags can be `true`, `false`, `null`, or omitted. A required `false` fact is a blocker. An omitted required fact is listed in `unknown_checks`, making an otherwise best option conditional. `annual_cap_scope` defaults to `product`; use `global` only when policy supports it. Product matching falls back to normalized account names when a record has no stable key.

### Output validation

The output contains `decision` (`eligible`, `conditional`, `blocked`, or `unavailable`), `shared_limit`, `recommendations`, and `evaluated_products`.

Before responding, confirm that:

- the rolling limit is not blocked or is accurately described as a blocker;
- every selected recommendation has no blockers;
- the chosen product has the greatest referrer reward among unblocked documented products;
- a date precision ambiguity is material before seeking timestamps or declining a limit conclusion;
- a product-specific annual count was calculated from that product's history only; and
- unmodeled documented terms, such as account opening, deposit retention, good standing, payment timing, and clawbacks, are stated accurately.

## Response requirements

Lead with the answer, not the research process. Use this structure:

1. **Recommendation and reward.** Name the recommended product and explicitly state the referrer's dollar bonus.
2. **Why it fits.** State the qualifying-deposit threshold and deadline, then state whether the reported earliest-checking tenure meets the product minimum. If a product has a higher nominal reward but needs more than the proposed deposit, briefly name it and state its threshold.
3. **Eligibility and limits.** State the result for the rolling limit and the selected product's annual cap. Accurately reflect supplied attestations concerning new-customer status, distinct registered address, and distinct primary owner/authorized signer.
4. **Remaining conditions.** State that the business must open the recommended product, make the qualifying deposit with new money, retain it for the required post-qualification period, avoid promotion stacking, and keep both accounts in good standing. Mention any documented early-closure clawback.

Use clear conditional wording for unconfirmed new-money source or promotion use, but still make the supported recommendation. Never characterize other-product referral history as a bar to a selected product's annual cap. Never claim documented policy terms are unavailable after consulting the catalog.
