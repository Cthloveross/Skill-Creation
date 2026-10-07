---
name: business-credit-card-purchase-return-advisor
description: Advise a prospective business-card customer which documented card may provide the best cash-back return for a large planned purchase. Use when purchase amount, merchant/category certainty, direct billing, timing, fees, credit-limit capacity, promotions, and eligibility must be compared without applying for a card or promising approval.
---

# Business Credit Card Purchase Return Advisor

Use this Skill for an informational comparison of documented business credit cards. It calculates conditional reward outcomes and produces an auditable set of options; it does not submit applications, open accounts, alter accounts, or guarantee a credit line, merchant category, reward, promotion, or approval.

## Required banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

This advisory workflow normally performs no banking action. If the customer later asks to apply, open an account, or perform any account action, stop the comparison workflow and follow the applicable approved banking procedure and the control above. Do not treat a recommendation as an approved application or available credit.

## Inputs to collect or use

Obtain the following without inventing missing facts:

- `purchase_amount`: the planned net purchase amount in USD.
- `merchant_category`: known category/MCC interpretation, if any. For this package use `travel`, `software`, `media_advertising`, `operations`, or `unknown`.
- `directly_billed`: whether the provider bills the customer directly. Direct billing is helpful for qualification but does not establish the merchant category.
- `open_date`: planned or actual account-opening date in `YYYY-MM-DD`, if promotion timing is being evaluated.
- `current_date`: date of the inquiry, if known.
- Optional `personal_credit_score` and `business_paydex`: only for a preliminary threshold comparison, never an approval decision.

For a subscription or streaming service with an unknown MCC, preserve the uncertainty. The general category taxonomy describes streaming as entertainment, while card bonus rules are card-specific. Do not equate entertainment with software, operations, or media advertising merely because the merchant supplies a digital service or bills directly.

## Procedure

1. Confirm that this is a prospective, informational card comparison and not an account action.
2. Clarify the purchase amount and whether the merchant coding is known. Explain that the issuer uses the category submitted by the merchant/payment processor; direct provider billing does not guarantee the category.
3. Run the calculator with the available facts:

   ```text
   python scripts/card_return_options.py <<'JSON'
   {"purchase_amount":"100000","merchant_category":"unknown","directly_billed":true,"current_date":"YYYY-MM-DD","open_date":"YYYY-MM-DD"}
   JSON
   ```

   The script reads one JSON object from standard input and writes one JSON object to standard output. It does not access accounts or perform banking actions.
4. Check credit-line feasibility separately from rewards. A card can only accommodate the purchase if underwriting approves a sufficient line; a published maximum is not a promised line.
5. Present both the qualifying-category outcome and the non-qualifying outcome when coding is unknown. Rank only within the stated scenario. Do not claim that the highest possible outcome is likely or guaranteed.
6. Include annual fees only where documented. Do not infer a fee where no fee is provided in this package. If a documented fee waiver depends on opening dates, present it as conditional.
7. State the relevant preliminary credit thresholds and request the customer’s scores only if they want a threshold comparison. Do not solicit or record identity data merely for advice.
8. Recommend confirming the MCC/category with the merchant before a large charge and retaining the invoice/receipt. If a posted purchase appears misclassified, the customer may contact support for category review with transaction and merchant details.

## Interpretation rules and documented product facts

The calculator uses these rules:

| Card | Bonus / other rate | Published line range | Preliminary eligibility | Fee facts |
| --- | --- | --- | --- | --- |
| Business Silver Rewards | 10.0% for travel or software coding; 1.0% otherwise | $17,500–$112,500 | Personal score at least 700; established business PAYDEX at least 47 | No fee fact is used by this Skill. A new-customer double-rewards offer applies only to accounts opened from 2024-11-14 through 2025-11-14; it doubles the normal rate for the first 6 months after opening. |
| Business Gold Rewards | 2.5% for operations coding; 1.0% otherwise | $37,500–$225,000 | Personal score at least 735; PAYDEX at least 67 | $200 annual fee |
| Business Platinum Rewards | 4.0% for travel, software, or media-advertising coding; 1.5% otherwise | $75,000–$400,000 | Personal score at least 765; PAYDEX at least 77 | $450 annual fee; first-year fee is waived for new accounts opened 2025-11-01 through 2026-02-28 |

For cash-back cards, the transaction system may store rewards as points. Interpret 1 point as $0.01 when redeemed as a statement credit or checking-account credit; the calculator expresses results directly in dollars.

A Business Bronze Rewards card has a published maximum initial line of $50,000, so it should not be presented as able by itself to fund a single purchase above that amount. Its 1.0% rewards do not make it a superior option for a larger single charge.

## Customer-facing response structure

Use plain language and include:

1. A brief conclusion conditional on the merchant category and approval for a sufficient credit line.
2. A compact scenario table or bullets showing each feasible card’s reward dollars/rate under qualifying and non-qualifying coding, plus material annual-fee conditions.
3. A clear distinction between direct billing and qualifying coding.
4. Any time-sensitive promotion condition, including that account opening must occur during the stated offer dates and qualification/approval is not guaranteed.
5. The credit-score/PAYDEX thresholds and the need for a line large enough for the charge.
6. The next safe step: confirm how the merchant will submit the charge and then choose or apply through the normal approved application channel.

## Validation

Before relying on calculator output, ensure:

- `purchase_amount` is positive and is a valid decimal number;
- category is one of the supported values or `unknown`;
- dates, if supplied, use valid ISO `YYYY-MM-DD` form;
- a card marked `line_capacity_possible: false` is not recommended for the single purchase;
- unknown coding is described as a range/scenario rather than a single enhanced reward;
- promotional calculations are labeled conditional on opening within the supplied promotion window.

If needed data are missing, the script still returns category scenarios but sets time-dependent promotion status to `unknown`; tell the customer exactly what cannot yet be determined.