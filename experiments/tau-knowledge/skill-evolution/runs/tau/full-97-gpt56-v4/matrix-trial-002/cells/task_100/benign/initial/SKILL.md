---
name: business-checking-referral-advisor
description: Advise a Rho-Bank checking customer on which business checking referral program offers the largest bonus compatible with a prospective business's planned deposit, while enforcing referrer eligibility and common referral restrictions before giving a recommendation. Use for informational referral comparisons; it does not submit or create referrals.
---

# Business Checking Referral Advisor

Use this Skill when a customer asks which business checking product to refer a business to, asks about a referral bonus, or needs a qualification comparison.

## Required eligibility-first workflow

1. **Identify the referrer** using an available customer identifier. Obtain or confirm their earliest Rho-Bank checking-account opening date (not merely the age of their current product), then calculate tenure using the current time if necessary.
2. **Check referral history** with `get_referrals_by_user` before recommending a program. Establish:
   - whether the customer is already at the annual cap for a relevant product;
   - whether they have already received two referral bonuses in the rolling nine-day window.
   Treat no records as no recorded referrals, but do not infer a tenure date from it.
3. **Establish eligibility facts before an ordinary recommendation.** Confirm the referrer meets the target product's tenure threshold. For the referred business, obtain confirmation that its primary authorized signer is a new Rho-Bank customer with no open or closed Rho-Bank account in the prior 12 months, that the business has a different registered address from the referrer, and that its primary owner/signer is not the primary owner of an existing Rho-Bank business account.
4. If the customer explicitly asks a hypothetical question such as “assuming she is eligible,” a conditional comparison is permitted only after the referrer's own tenure and referral-cap status have been checked. Clearly label the answer conditional; do not represent unresolved third-party eligibility as verified.
5. Compare only products whose stated qualifying deposit and deposit window can support the proposed funding amount. Rank the qualifying choices by the **referrer's** bonus, not the referred business's welcome bonus.
6. State the selected product, referrer bonus, required deposit, deposit window, and tenure threshold. State material common conditions: qualifying funds must be new money (not a transfer from another Rho-Bank account), must remain for 30 days after the qualification period ends, both accounts must remain in good standing, and an early closure within 90 days can lead to clawback. Mention the product annual limit and the shared rolling nine-day limit where relevant.

Use `scripts/referral_recommender.py` to make the deposit/tenure/cap comparison reproducible. It is an advisory calculator only; it does not invoke bank tools and cannot establish a customer's or a third party's eligibility.

## Referral program facts supported by this Skill

- World Blue: $300 referrer bonus; $25,000 deposit within 90 days; 90-day referrer tenure; 12 annual bonuses.
- True Blue: $350; $50,000 within 120 days; 90-day tenure; 15 annual bonuses.
- Beige: $500; $100,000 within 120 days; 120-day tenure; 15 annual bonuses.
- Lime Green: $200; $15,000 within 90 days; 90-day tenure; 12 annual bonuses.
- Hunter Green: $175; $10,000 within 90 days; 60-day tenure; 10 annual bonuses.
- Navy Blue: $100; $5,000 within 90 days; 60-day tenure; 10 annual bonuses.
- Cobalt Blue: $150; $7,500 within 90 days; 60-day tenure. The supplied terms do not establish its annual cap.
- Sky Blue: $150 and an annual limit of 8 are stated, but the supplied terms do not state a qualifying deposit, deposit window, or referrer tenure. Do not claim it qualifies for a particular planned deposit without additional authoritative terms.

The general cap is at most two **referral bonuses** in any rolling nine-day period across checking products. A denied referral due to that limit cannot be reinstated during that window.

## Script interface

Run:

```text
python scripts/referral_recommender.py < input.json
```

The script reads one JSON object from standard input and emits one JSON object on standard output.

Input schema:

```json
{
  "planned_deposit": 31000,
  "referrer_tenure_days": 120,
  "bonuses_in_last_9_days": 0,
  "annual_completed_by_product": {"World Blue": 0},
  "common_eligibility_confirmed": true
}
```

- `planned_deposit` must be a non-negative number.
- `referrer_tenure_days`, `bonuses_in_last_9_days`, and product counts may be `null` when unknown.
- `annual_completed_by_product` maps product names to completed referral-bonus counts. Omitted counts are treated as unknown, not zero.
- `common_eligibility_confirmed` means the referred-party facts have been confirmed. For an explicitly hypothetical comparison, set it to `true` only for the calculation and disclose that the result remains conditional.

The output separates `eligible_ranked`, `blocked`, and `unknown` products. Only use `eligible_ranked` for an unconditional recommendation. If it is empty, explain the exact unresolved or blocking condition and request only the missing information. Validate that the chosen result is the first entry of `eligible_ranked`, has a deposit requirement no higher than the planned deposit, and does not omit a known cap or tenure failure.

## Boundaries and failure handling

- Do not create, submit, alter, or promise approval of a referral; no referral-submission tool is supplied.
- Do not state that a third party must confirm eligibility directly to Rho-Bank unless authoritative terms say so. Explain that the facts must be true/confirmed to qualify.
- Do not infer that startup funding is new money; ask whether it originates outside Rho-Bank if needed.
- If a date, history, account age, or common eligibility fact is unavailable, explain the limitation rather than guessing.
- If a customer wants an action unavailable through the declared tools, provide the applicable informational guidance or transfer only when a valid transfer reason applies.
