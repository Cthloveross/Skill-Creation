---
name: business-card-purchase-return-comparison
description: Compare new business credit-card options for a planned large purchase. Use when a customer asks which card offers the best first-purchase return and the result depends on merchant-category coding, time-limited offers, fees, credit eligibility, or available credit.
---

# Business-card purchase-return comparison

Provide an accurate, conditional recommendation for a planned business purchase without representing approval, credit limits, merchant classification, or offer qualification as guaranteed.

## Scope and safety

- This Skill provides product information and a numerical comparison only. Do not apply for a card, access an account, promise approval, or perform a banking action.
- Use the product terms and current-time observation supplied with the live task. Do not reuse a prior customer's facts or a prior calculation.
- Do not infer a bonus merchant category merely from the customer's description of the item or business purpose. The processor-assigned merchant category code (MCC) controls whenever the product terms say it does.
- Do not treat an unconfirmed credit limit, an unconfirmed available-credit amount, or an unconfirmed eligibility credential as satisfied.

## Method

1. **Extract the decision inputs.** Identify the planned charge amount, purchase type, whether the customer is opening a new account, and the supplied current date. Record all relevant card terms: base and enhanced rates, annual fee (including a currently valid first-year waiver), new-account bonus conditions, stated credit standards, and credit-limit range or minimum.
2. **Check merchant-category uncertainty.** For each enhanced rate, state the exact MCC/category prerequisite. If it has not been confirmed, calculate separate outcomes for:
   - the charge receiving the enhanced rate; and
   - the charge receiving the base/non-bonus rate.
   Do not describe an operations-related truck as operations spend solely because it is used in the business.
3. **Evaluate promotions precisely.** A dated offer may be included only if the supplied date falls within its stated window and the customer can meet every stated condition. Distinguish account opening from application submission. For spend bonuses, require the charge to post in the stated period, remain a net purchase after returns/credits, and count toward the threshold. If the source gives only dates and the relevant account-opening cutoff is unclear, say that same-day eligibility must be confirmed rather than assuming it.
4. **Check feasibility before ranking.** For a charge of this size, the selected card needs an approved *available* line at least equal to the charge at authorization/posting. A stated possible maximum is not a promise. List unknown minimum personal/business credit requirements that the customer must meet.
5. **Calculate comparable first-year value.** For each viable scenario calculate:
   - purchase cash back = purchase amount × applicable rate;
   - plus a new-account bonus only when its conditions are met;
   - minus the first-year annual fee actually applicable.
   Keep annual travel credits and other non-cash purchase-adjacent perks separate unless the customer says they will use them; do not silently offset a fee with their nominal value.
6. **Respond directly.** Lead with the strongest conditional recommendation, then show the alternatives and their requirements. Because the customer specifically asks about coding, plainly explain the best option in both coding outcomes. Mention that the dealership can confirm the MCC before payment and that a documented review can be requested if terms provide one.

## Response structure

Use short currency amounts rounded to cents and make the qualification conditions visible:

1. A concise recommendation conditioned on approval, available line, and posting requirements.
2. A `If the dealership is coded as ...` comparison showing enhanced-rate versus base-rate outcome.
3. Other material alternatives, including only offers valid on the supplied date.
4. A short checklist: confirm dealership MCC, confirm approved available credit, and verify required credit/offer conditions before opening or charging.

When a welcome offer makes a lower ongoing-rate card best for this single purchase, say so explicitly. Also distinguish that one-time result from the ongoing rate after the promotion/bonus.

## Calculator

`scripts/compare_rewards.py` makes deterministic first-year comparisons after the executor has interpreted product terms and conditions. It does not decide merchant coding, promotion validity, or underwriting.

Input is JSON on standard input:

- `purchase_amount`: nonnegative decimal string or number.
- `cards`: nonempty list of objects with `name`, `earning_rate_percent`, and optional `annual_fee_first_year`, `new_account_bonus`, `conditions`, and `feasible`.
- `feasible` may be `true`, `false`, or omitted. `false` prevents a scenario from being recommended; omitted means its feasibility is still unconfirmed.
- `conditions` is a list of customer-facing strings, such as MCC, posting, eligibility, or available-credit prerequisites.

The script emits JSON on standard output with per-card cash back, first-year net value, conditions, feasibility status, and a ranking that places explicitly infeasible choices after feasible/unknown choices. Monetary outputs are decimal strings rounded to cents.

Run it with a dynamically prepared input file:

```sh
python3 scripts/compare_rewards.py < /path/to/comparison-input.json
```

Validate before relying on the result that every relevant scenario is represented, the rate is expressed as a percentage (not a decimal fraction), a waived fee is entered as `0`, and a bonus is entered only after its conditions have been assessed. The narrative must still disclose any unknown condition returned by the calculator.
