---
name: business-credit-card-large-purchase-adviser
description: Advise a prospective business-card applicant which available card is most rewarding for a large planned purchase, while separating estimated rewards from merchant-category qualification and credit-limit approval. Use for informational card-comparison questions; do not use it to submit applications or change accounts.
---

# Business Credit Card Large-Purchase Adviser

Use this Skill to give an accurate, decision-oriented comparison for a proposed business purchase. It is informational only: do not imply approval, a guaranteed limit, a guaranteed merchant category, or that an application has been submitted.

## Required inputs

Collect or infer only what the user supplied:

- purchase amount and whether it is one charge;
- merchant and product/service description;
- likely rewards category, if supportable from the supplied card materials;
- relevant card reward rates, named exclusions, and credit-limit ranges;
- current date if a time-bounded promotion or fee waiver is being considered.

If the merchant category code (MCC) is unknown, state that the reward is conditional on the merchant submitting the transaction under the eligible category. Do not treat a product description alone as proof of qualification.

## Method

1. **Identify feasible cards.** A single charge is feasible only if the card can be approved with a limit at least equal to the amount. A published maximum is not an approval promise. Exclude cards whose stated maximum limit is below the purchase amount, and say why.
2. **Classify the purchase carefully.** Use the bank's category definitions and card-specific eligibility rules. Check every named merchant exclusion before applying a bonus. A named exclusion overrides a broader category assumption.
3. **Compute potential rewards.** Use `scripts/compare_cards.py` with the amount and card facts. Supply the expected category only when it is supported by the available information. The script returns conditional estimates and ranks cards that have enough published maximum capacity.
4. **Make the recommendation.** Lead with the highest-reward feasible option, then list practical alternatives only when they can support the charge. State both the estimated dollar cash back and the condition that makes it available.
5. **Disclose meaningful tradeoffs.** Include any relevant annual fee, promotional fee timing, credit standards, and important uncertainty about category coding. Promotions apply only if their stated account-opening and customer eligibility conditions are met.
6. **Give next steps.** Suggest confirming how the merchant will code/bill the charge, requesting a limit sufficient for the full single payment, and preparing the application information described by the card materials. Do not promise that a limit request or application will be approved.

## Answer structure

Use plain language and concise arithmetic:

- A direct recommendation with “up to” or “if coded as” language where appropriate.
- A short comparison of nonviable or lower-return cards.
- A compact caveat that rewards depend on the posting MCC and the approved line must cover the full charge.
- Application/fee details only when supported by the supplied materials and relevant to the decision.

For cash-back cards whose backend shows rewards as points, convert at 1 point = $0.01 when expressing a dollar estimate.

## Current card-fact application guidance

When the available materials describe the Business Platinum, Business Gold, Business Silver, and Business Bronze products:

- Business Platinum: travel, software, and qualifying media/advertising earn 4.0%; other purchases earn 1.5%. Its stated approval range is $75,000–$400,000. Media eligibility requires an advertising/media MCC.
- Business Gold: qualifying operations earn 2.5% and other purchases earn 1.0%; the stated range reaches $225,000. Entertainment is a non-qualifying operations example.
- Business Silver: qualifying travel/software earns 10.0%, otherwise 1.0%, but named exclusions (including Apple) receive the standard rate. Its stated maximum is $75,000.
- Business Bronze: its stated maximum is $50,000.

Apply these facts only if they are present in the supplied materials. Do not invent a category, a special merchant rule, or an approval result.

## Script interface

`compare_cards.py` reads one JSON object from standard input and emits one JSON object to standard output.

Input schema:

```json
{
  "amount": "decimal amount greater than zero",
  "merchant": "optional merchant name",
  "expected_category": "optional category such as media or software",
  "cards": [
    {
      "name": "card name",
      "max_limit": "optional decimal maximum published limit",
      "base_rate_percent": "decimal percentage",
      "bonus_rates_percent": {"media": "4.0"},
      "excluded_merchants": {"Apple": "1.0"}
    }
  ]
}
```

`excluded_merchants` maps a case-insensitive merchant name to the rate that overrides all category bonuses; use `"0"` where an exclusion earns no rewards. The output identifies capacity, applied rate, estimated cash back, and a descending ranked list of cards with sufficient published maximum capacity. A missing maximum is reported as `unknown`, not assumed feasible.

Example executable call (replace all values with the live task facts):

```bash
printf '%s' '{"amount":"2500","merchant":"Example Vendor","expected_category":"software","cards":[{"name":"Example Card","max_limit":"5000","base_rate_percent":"1","bonus_rates_percent":{"software":"4"},"excluded_merchants":{}}]}' | python3 scripts/compare_cards.py
```

## Validation before responding

- Confirm the amount is positive and calculate percentage rewards as `amount × rate / 100`.
- Confirm every recommended card has a published maximum at least equal to the single-charge amount; label actual approval as conditional.
- Confirm that an exclusion was applied before a category bonus.
- Do not label category qualification as certain unless an eligible MCC is actually known.
- Verify date-sensitive offers against the supplied current date and stated window.
