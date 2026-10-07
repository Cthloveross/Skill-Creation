---
name: savings-interest-reconciliation
version: 1.0.0
description: Reconciles a customer's posted savings interest using base APY, eligible linked-checking boosts, and eligible credit-card bonuses. Use for questions about savings interest that appears low, especially where the customer holds multiple checking accounts.
---

# Savings interest reconciliation

Use this Skill to explain an apparent savings-interest discrepancy without guessing at statement dates, daily balances, account eligibility, or unreported credit cards.

## Policy rules represented

1. A linked checking boost applies only when the checking/savings pairing is an eligible pairing.
2. Multiple qualifying checking boosts for the *same* savings account do not stack: use only the largest applicable boost.
3. Multiple eligible credit-card bonuses for the same savings account likewise do not stack: use only the largest applicable card bonus.
4. The selected checking boost and selected card bonus may be added to the savings account's base APY.
5. Interest may accrue daily and post monthly. An exact reconciliation therefore requires the posting/cycle dates and daily eligible balances. Do not treat a balance described as “about” or “around” a value as an exact daily balance.

## Conversation procedure

1. Acknowledge the concern and restate the relevant savings accounts, approximate balances, and posted interest.
2. Identify the base APY and daily-compounding/crediting terms from the supplied product evidence.
3. List every checking account the customer reports. For each savings account, retain only documented eligible pairings and their documented boost values.
4. Select the highest applicable boost independently for each savings account. Explain that lower eligible checking boosts are not added.
5. Ask whether the customer holds eligible same-profile credit cards when card bonuses may apply. Do not claim a card bonus or include one unless the card and its documented amount are known. If several eligible cards are known, retain only the highest card bonus.
6. Use `scripts/reconcile_interest.py` for an approximate or exact calculation. Supply actual daily balances where available. For approximate results, provide a reasonable day range rather than a single invented cycle length.
7. Explain whether the posted amount appears broadly consistent with the known information. If dates, daily balances, eligibility, or bonus application are missing, say an exact comparison cannot yet be made.
8. Escalate or follow the institution's correction procedure only when verified account facts show the system used a lower qualifying checking boost, omitted a documented eligible bonus, or otherwise calculated interest incorrectly. Do not promise or apply a correction based only on an estimate.

## Response standards

- Distinguish APY percentages from dollar interest and show the selected rate components.
- Say “approximately” for calculations based on average/constant balances.
- Never add checking boosts together.
- Never add multiple credit-card bonuses together.
- Do not infer that every checking account boosts every savings product; eligibility must be documented.
- Avoid requesting identity verification or accessing account data unless a separate authorized process requires it.

## Packaged calculator

Run:

```text
python scripts/reconcile_interest.py < input.json
```

The script reads one JSON object from stdin and emits one JSON object to stdout.

### Input schema

```json
{
  "balance": 60000,
  "base_apy_percent": 6.0,
  "checking_boosts_percent": [0.5, 0.35],
  "card_bonuses_percent": [],
  "days": 30,
  "posted_interest": 328,
  "daily_compounding": true
}
```

Required fields are `balance`, `base_apy_percent`, and `days`. Boost arrays may be omitted and default to empty. Values in boost arrays must already be limited to *eligible* products for the savings account. `balance` is a constant/average eligible daily balance for the modeled period. `days` must be a positive integer. `posted_interest` is optional. Set `daily_compounding` false only where the product does not accrue daily.

### Output interpretation and validation

The result reports the highest selected checking and card bonuses, total APY, modeled interest, and, if supplied, the difference from posted interest. It also returns validation errors instead of producing a calculation for invalid inputs. Confirm before communicating a conclusion that:

- the pairings submitted to the calculator are documented as eligible;
- the calculator selected a maximum rather than summed boosts;
- the modeled days match the statement period, or are plainly presented as an estimate; and
- the balance represents eligible daily balances rather than merely the current balance.

For an uncertain statement length, run the calculator once for each plausible number of days and report the resulting range.
