---
name: credit-card-rewards-discrepancy-review
description: Review reported credit-card cash-back or rewards-points discrepancies, calculate published baseline awards with whole-point truncation, gather the required transaction evidence, and route a verified, customer-authorized investigation without making an unsupported adjustment. Use for questions about missing, incorrect, or unexpectedly low card rewards.
---

# Credit-Card Rewards Discrepancy Review

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and safety boundary

Use this workflow to investigate a possible rewards discrepancy. Do **not** credit points, alter a rewards balance, reverse a transaction, or state that an adjustment is approved unless a documented normal banking tool and its required approval result explicitly permit that action.

Treat account/transaction lookup results as evidence, not authentication. Do not disclose account balances, full contact details, reward balances, or transaction-specific information until identity is verified.

## Required procedure

1. **Identify the customer without disclosing account data.** Ask for an account locator such as full name, user ID, or email if none is available. Use the appropriate lookup tool only to locate a possible record.
2. **Verify identity before any account-specific review or case action.** Ask the customer to confirm at least two of these four fields and compare them to the located record: date of birth, email, phone number, and address. Do not read the values aloud as prompts. Obtain the current timestamp and call `log_verification` with the complete record fields after two fields match.
   - If two fields cannot be verified, explain that account-specific review and dispute submission require verification. Do not reveal records or create a case.
3. **Verify authority and ownership.** Confirm the verified customer is asking about their own card account. Retrieve card accounts and confirm that each reviewed card belongs to that user and that the card type matches the transaction record.
4. **Gather the claim details.** For each reported transaction, collect or retrieve: transaction ID, date, merchant, amount, card type, category/qualification indicator, completion status, rewards actually awarded, and the customer’s expected outcome. Confirm the transaction is completed and is the intended purchase. Obtain receipts, offer terms, or enrollment evidence when the customer claims a merchant-specific or limited-time offer.
5. **Check applicable terms and prerequisites.** Confirm the applicable card product and published reward rate, merchant/category qualification, exclusions, points representation, whole-point rounding, and whether a refund/return affects the award. For this rewards-dispute workflow, available balance/credit, transfer recipient details, payment cutoffs, and payment fees are normally not applicable; record them as not applicable rather than inventing a prerequisite. If a card, product, merchant, offer, qualification, fee, cutoff, or confirmation requirement is unknown, do not infer it.
6. **Calculate the published baseline.** Run `scripts/evaluate_rewards.py` with only the transaction facts and qualification status supported by the records. The script uses `Decimal` and floors to whole points. Interpret outputs as follows:
   - `status: "comparable"` with unequal `expected_points` and `awarded_points` is a documented baseline discrepancy suitable for investigation.
   - `status: "needs_review"` means eligibility, merchant qualification, offer terms, or an unsupported card rule prevents a reliable baseline calculation; it may still be included in an investigation with the missing evidence noted.
   - Cash-back-card transaction rewards stored as points represent cash back at 1 point = $0.01. EcoCard sustainability points also redeem at $0.01 per point, but its earning rate is determined separately.
7. **Explain findings accurately.** State the actual award, the published baseline calculation, and any uncertainty. A baseline mismatch does not prove an error when an offer, reversal, merchant classification, or qualification rule is unresolved. Never fabricate a promotional explanation.
8. **Obtain explicit confirmation.** Name each transaction proposed for investigation and ask the customer to confirm submission. Record the customer’s confirmation and the scope of each claim. Do not submit transactions the customer did not approve.
9. **Create or route the investigation.** Use an explicitly documented normal rewards-dispute/case-creation tool if one is available in the runtime, supplying only verified facts, calculation results, customer confirmation, and evidence gaps. If no such tool is available, transfer to a human/specialized department using `transfer_to_human_agents` with `specialized_department_required` and a concise factual summary. Do not claim the case was submitted when only a handoff was made.
10. **Close with next steps.** Tell the customer which transactions were routed or require more evidence, what documents would help (receipt, merchant details, or offer enrollment evidence), and that the bank will review merchant category and applicable rates. Use an appropriate official contact channel if a secure handoff is unavailable.

## Published-rate calculation assumptions

- **Gold Rewards Card:** 2.5% cash back on all purchases. Since one stored point represents $0.01 for cash-back cards, the baseline points are `floor(amount_in_dollars * 2.5)`.
- **EcoCard:** 5 sustainability points per dollar for a qualifying green purchase and 1 point per dollar otherwise. Baseline points are `floor(amount_in_dollars * applicable_points_per_dollar)`.
- **Rounding:** floor every transaction’s fractional points to the nearest whole point; never round to nearest.
- A record marked green can support a provisional qualifying-green calculation only when the record or other evidence establishes qualifying status. Known exclusions and nonpartner EV charging override a generic green assertion. When merchant qualification is not established, use `qualification: "unknown"` and route for review instead of asserting the higher rate.

## Script interface

Run from the package root:

```sh
python3 scripts/evaluate_rewards.py <<'JSON'
{"transactions":[{"transaction_id":"...","card_type":"Gold Rewards Card","merchant_name":"...","amount":"0.00","category":"...","qualification":"not_applicable","rewards_earned":0}]}
JSON
```

Input is a JSON object with a `transactions` array. Each transaction requires `transaction_id`, `card_type`, `amount`, and `rewards_earned`; `merchant_name`, `category`, and `qualification` are optional. `amount` may be a decimal number or string. `qualification` is one of `qualifying_green`, `non_green`, `unknown`, or `not_applicable`.

The script emits JSON with one result per input transaction and an `errors` list. Validate that every intended transaction appears exactly once, numeric values parse correctly, IDs are nonempty, and any `comparable` output has an expected/awarded comparison before using it in a customer explanation or handoff. Invalid records are returned as errors and must be corrected or documented as unavailable rather than silently omitted.

## Handoff summary template

Include the verified customer and card ownership confirmation, transaction identifiers and facts, calculated baseline and actual award, known qualification/offer uncertainty, documents available or missing, explicit customer consent, and the request for a rewards investigation. Do not include unnecessary full sensitive identifiers in customer-facing text.
