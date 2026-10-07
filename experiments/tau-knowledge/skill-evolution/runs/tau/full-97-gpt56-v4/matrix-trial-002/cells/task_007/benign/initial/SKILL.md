---
name: personal-card-signup-bonus-advisor
description: Answer a customer asking about personal credit-card cash-back or points sign-up bonuses using the documented offers, qualification terms, customer constraints, and offer dates. Use when the customer wants bonus comparisons or needs to know whether a documented bonus is attainable.
---

# Personal Card Sign-Up Bonus Advisor

Use this Skill to provide a precise, customer-facing answer about **personal-card sign-up bonuses in cash back or points**. It distinguishes sign-up bonuses from ongoing rewards and from non-reward promotions, and does not claim that an offer is the market-wide or bank-wide "best" unless complete comparable offer data has been supplied.

## Evidence boundaries

The packaged reference contains the available documented card facts. Treat an offer as available only when it is documented there and, where dates are available, the supplied current date falls within its offer window. Do not infer a sign-up bonus from an ongoing reward rate, an introductory APR, a waived fee, or the absence of a bonus in a document.

For the EcoCard, clearly distinguish `2,000 sustainability points` from `$2,000`: its documented redemption value is $0.01 per point, so 2,000 points have a stated redemption value of $20.00. Do not represent this as $2,000 cash.

## Runtime procedure

1. Collect or use the public conversation answers for:
   - whether the customer wants only a personal cash-back/points sign-up bonus;
   - whether they are a new customer where an offer requires it;
   - whether they can meet an offer's spend requirement; and
   - the current date/time.
2. Run `scripts/assess_signup_bonus.py` with JSON on stdin. Its input schema is:
   ```json
   {
     "current_time": "YYYY-MM-DD HH:MM:SS TZ or YYYY-MM-DD",
     "personal_bonus_only": true,
     "is_new_customer": true,
     "can_spend_5000_in_one_month": false,
     "spend_capacity_note": "optional customer statement"
   }
   ```
   Boolean fields may be omitted or `null` if unknown. The script emits JSON containing a `response` suitable for the customer, a list of evaluated `offers`, and `limitations`.
3. Present the returned `response` faithfully. If an input was unknown, ask only the indicated missing qualification question rather than asserting eligibility or ineligibility.
4. If the customer is unable to meet a documented threshold, say the bonus is not attainable under that offer; do not encourage ineligible spending, imply an exception, or promise another offer. They may still be able to apply for the card, but that is separate from qualifying for the bonus.
5. If requested, explain only documented ancillary terms that matter to the comparison (for example, the EcoCard annual fee). Do not perform account actions, applications, or identity lookups for this informational request.

## Output validation

Before sending the answer, verify that it:

- calls the EcoCard the only **documented** personal cash-back/points sign-up offer rather than claiming it is definitively the best;
- gives the active window and all material qualifying conditions when it discusses the EcoCard;
- states the value as 2,000 points (documented $20.00 redemption value), not $2,000 cash;
- does not label Silver Rewards or Platinum Rewards ongoing features as sign-up bonuses; and
- makes an explicit attainability conclusion when the customer has supplied spend-capacity information.

## Runnable example

```bash
printf '%s' '{"current_time":"2025-11-14 03:40:00 EST","personal_bonus_only":true,"is_new_customer":true,"can_spend_5000_in_one_month":false}' | python3 scripts/assess_signup_bonus.py
```

The script emits one JSON object on stdout and uses only the bundled `references/documented_offers.json` file.