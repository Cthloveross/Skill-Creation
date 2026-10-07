---
name: business-checking-referral-advisor
description: Safely screen a checking customer for eligibility before discussing referral terms, then compare documented business-checking referral programs against planned funding. Use for requests to maximize a business checking referral bonus or determine whether a business referral can proceed.
---

# Business Checking Referral Advisor

A referral recommendation or product-specific referral terms may be given **only after the referrer's eligibility has been screened**. This ordering is mandatory: do not name a referral product, bonus, qualifying-deposit amount, deposit window, or product tenure threshold while required referrer-eligibility facts are missing.

This Skill provides advice only. It does not submit a referral or open an account.

## Conversation and tool workflow

### 1. Screen eligibility before discussing products

First identify the referrer and use read-only tools to retrieve their referral history. Collect the following without naming product tiers or disclosing product-specific referral terms:

- The date of the referrer's earliest Rho-Bank checking account. Their current product does not determine tenure.
- Successful/COMPLETE referral-bonus events and timestamps, to assess the rolling nine-day limit and later annual limits.
- Whether the referred person is a new Rho-Bank customer, is registered at a separate address from the referrer, and is the primary owner of a business different from every existing Rho-Bank business account.

Ask for missing facts plainly and generically. For example, ask when the first checking account was opened and whether the prospective customer is new and separately registered; do **not** explain a particular program's reward or deposit requirement at this stage.

If the opening date is described only approximately, do not invent an exact date. A bounded statement may support a threshold when the entire stated range is safely beyond it, but explain that an exact account-opening date may still be needed for final operational processing.

Do not treat a customer's statement about another person's private account status as system verification. It may support a conditional discussion, but must be independently confirmed before an action.

### 2. Run the eligibility screen

Use `scripts/referral_advisor.py` with the facts collected so far. Before the screen is complete, its output intentionally contains no product names or product-specific referral terms.

Do not disclose, infer, or work around hidden catalog data from a screen result with `advice_permitted: false`. Ask the listed `next_required_facts` instead.

### 3. Compare programs only after the screen passes

Once `advice_permitted` is `true`, provide the planned **new-money** deposit amount and evaluate the returned products. The qualifying deposit cannot be transferred from another Rho-Bank account and must remain for at least 30 days after the applicable qualifying period ends.

For a request for the largest referrer reward, choose the largest documented reward among programs qualifying from known inputs and compatible with the planned funding. Do not assume qualification for programs with incomplete documented terms. A temporary promotional ordering applies only when multiple accounts meet every stated customer requirement; it does not make a non-qualifying or undocumented option suitable.

For a conditional product recommendation, communicate:

- the product and referrer reward;
- qualifying-deposit amount and deadline;
- referrer tenure requirement and whether the available timing supports it;
- documented annual cap and the general limit of two successful bonuses in a rolling nine-day window;
- new-money and post-qualification 30-day holding requirements;
- one referral code only and no stacking with other new-account promotions;
- good-standing requirement and possible clawback if the referred account closes within 90 days; and
- documented payment timing, if available.

Distinguish confirmed information from customer-reported facts and conditions still needing confirmation.

### 4. Keep account opening separate from referral advice

A prospective business owner may open business checking only after all of these are confirmed:

1. The customer is verified.
2. They have at least one OPEN personal checking account.
3. Their existing checking balance is at least $500.
4. They have no CLOSED accounts.
5. They have fewer than six business checking accounts.

Unknown conditions are not approval. A new customer may need to establish and fund a personal checking account first. If these facts remain unknown, present any otherwise suitable referral option as conditional and request confirmation from the prospective owner.

### 5. Do not take unrequested or unsafe actions

Never submit a referral or invoke an account-opening tool based only on this analysis. If a later request expressly asks for an action, use normal authorized banking tools only after all referral and account-opening requirements have been independently confirmed. No human handoff is required merely because an exact date or another customer's private status is unavailable.

## Helper interface

`scripts/referral_advisor.py` reads one JSON object from stdin and writes one JSON object to stdout. It loads `references/referral_programs.json` and makes repeatable screening, tenure, rolling-window, annual-cap, funding, and ranking calculations.

Input fields:

```json
{
  "now": "ISO-8601 datetime",
  "planned_new_money_deposit": "number; required only after eligibility screening",
  "referrer": {
    "first_checking_opened": "ISO-8601 date or datetime, if exact",
    "first_checking_opened_on_or_before": "ISO-8601 date or datetime, if only an upper bound is known"
  },
  "general_referral_facts": {
    "new_customer": true,
    "separate_registered_address": true,
    "different_business_primary_owner": true
  },
  "successful_bonus_events": [
    {"product": "program name", "credited_at": "ISO-8601 datetime"}
  ]
}
```

Supply only one of the two first-account fields. `first_checking_opened_on_or_before` means the customer became a checking customer no later than that date; the helper uses it as a conservative minimum-tenure calculation. `successful_bonus_events` must contain only successful/COMPLETE credited bonuses. Supply `[]` only when the referral-history lookup conclusively found none; omit the field when history is unknown.

A runnable invocation uses a runtime-supplied JSON file:

```bash
python3 scripts/referral_advisor.py < request.json
```

Output behavior:

- If screening facts are missing or blocked, output has `advice_permitted: false`, a generic `global_gate`, and `next_required_facts`; it deliberately omits product comparison and recommendation data.
- After screening passes, output has `advice_permitted: true`, product outcomes, `ranked_qualifying_products`, and a non-null recommendation only when known facts support one.
- `eligibility_status` values of `blocked`, `needs_confirmation`, or `catalog_terms_incomplete` are not final recommendations.
- `account_opening_prerequisites_not_evaluated` is a reminder that the helper cannot confirm the prospective owner's private eligibility.

Validate that `advice_permitted` is true and that the returned recommendation has `eligibility_status: qualifies_from_known_inputs` before presenting it as an option. If `tenure_basis` is `conservative_lower_bound`, disclose that the available timing supports the threshold while an exact date remains appropriate for final processing.

## Source basis

- `references/referral_programs.json`: documented business referral rewards, deposits, windows, tenure, caps, sources, and the November 2025 promotional ordering.
- General restrictions: Checking Account Referral Program Terms and Restrictions and FAQ: Checking Account Referrals.
- Account-opening rules: Internal: Opening Business Checking Accounts.
