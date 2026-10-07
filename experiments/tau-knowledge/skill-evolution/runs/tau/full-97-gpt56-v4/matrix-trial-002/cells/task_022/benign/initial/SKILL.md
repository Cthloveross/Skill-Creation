---
name: ecocard-rewards-audit-and-escalation
description: Audit an authenticated customer's EcoCard transaction rewards against published sustainability-point rules, distinguish confirmed discrepancies from eligibility-dependent items, and escalate when historical merchant or Green Account linkage records are unavailable. Use for requests to review EcoCard rewards, green-rate eligibility, or the linked-Green-Account 2% cashback prerequisite.
---

# EcoCard Rewards Audit and Escalation

Use this Skill for a careful, evidence-bounded review of credit-card rewards. It does **not** infer unpublished reward schedules for other card products, and it does not make account changes or reward adjustments.

## Published rules captured by this Skill

- EcoCard earns 5 sustainability points per dollar on qualifying green purchases and 1 point per dollar on other purchases.
- Rewards are stored as integer points; calculate expected points by truncating fractional points (for example, use `floor(amount × rate)`). EcoCard points redeem at $0.01 per point, but they remain sustainability points rather than ordinary cash-back points.
- Target, Walmart, Amazon, and ThredUp are always standard-rate EcoCard merchants, including variants such as eco-themed product lines and marketplace/order channels processed by those merchants.
- EV charging receives the higher rate only for Tesla Supercharger, ChargePoint, and EVgo.
- A transaction category such as `Green` is not, by itself, historical proof that a merchant was eligible. Green eligibility can depend on the seller of record, merchant directory status, item-level data, and the transaction date.
- The extra 2.0% EcoCard cashback at eco-certified merchants requires both a linked Green Account (savings) and an EcoCard in good standing. Do not calculate, promise, or correct that extra bonus until those historical conditions are verified.

See `references/policy.md` for the evidence-bounded decision rules.

## Required handling flow

1. **Authenticate before account-specific disclosure.** If the customer has not already been verified in the current interaction, identify the record from a name, email, or user ID, then ask the customer to confirm any two of date of birth, email, phone number, and address. Compare those values with the retrieved record. Do not recite sensitive values to solicit confirmation.
2. After two fields match, call `get_current_time`, then call `log_verification` with the canonical user record, all required identity fields, and the returned timestamp. Stop if verification fails or the customer cannot supply two matching fields.
3. Retrieve `get_credit_card_accounts_by_user` and `get_credit_card_transactions_by_user` using the verified user ID. Include completed EcoCard transactions in the audit period. Do not call an undocumented tool or invent a tool parameter.
4. If the documented bank-account lookup is actually available in the runtime, it may be used with the verified user ID to determine whether a savings account exists. Its documented fields do not establish historic EcoCard linkage or historical good standing. If it is not among the available tools, state that this lookup is unavailable rather than attempting it.
5. Convert the relevant EcoCard transaction results into the structured JSON schema below and run `scripts/audit_ecocard.py`. Provide only historically verified merchant eligibility in `historical_green_transaction_ids` or `historical_green_merchants`; do not populate those fields from a transaction's category or from its currently posted rewards.
6. Report the script's `confirmed_findings` as confirmed results. Report `needs_eligibility_verification` and `provisional_standard_rate` as unresolved/provisional, never as errors. Mention returned, refunded, reversed, pending, or otherwise non-completed records separately because point reversals must be evaluated at the original earn rate.
7. Review transactions on non-EcoCard products only if an authoritative rate schedule for those products is available in the supplied case materials. The supplied EcoCard policy does not authorize deriving other-card errors from observed points, merchant categories, or apparent patterns.
8. If historical Green Account linkage/good-standing evidence, the historical merchant-directory record, item-level qualification, or a product-specific rate table is unavailable, explain that the audit cannot settle that portion. Offer a specialist/records escalation. When the customer requests it or needs it to complete the audit, call `transfer_to_human_agents` with reason `specialized_department_required` and a concise summary of: verified status, audit period, affected transaction IDs, records needed, and that no reward adjustment was made.

## Script interface

Run from the package root:

```sh
python3 scripts/audit_ecocard.py <<'JSON'
{
  "transactions": [],
  "historical_green_transaction_ids": [],
  "historical_green_merchants": []
}
JSON
```

Input is one JSON object:

- `transactions` (required): list of objects with `transaction_id`, `credit_card_type`, `merchant_name`, `transaction_amount`, `status`, and `rewards_earned`. Amount may be a number or a dollar-formatted string. `transaction_date` and `category` are retained in output when supplied.
- `historical_green_transaction_ids` (optional): transaction IDs whose green eligibility was verified for the transaction date.
- `historical_green_merchants` (optional): merchant names whose green eligibility was verified for the audit period. Do not use a current directory list unless it is known to be historical for the period.

The script emits a JSON object with:

- `confirmed_findings`: only transactions whose required rate is established by a published exclusion, certified charging-network rule, or supplied historical evidence. A finding can be `correct` or `discrepancy`; `point_delta` is expected minus posted points.
- `needs_eligibility_verification`: EcoCard items that could be either 1x or 5x because the supplied data does not prove historic eligibility.
- `provisional_standard_rate`: transactions posted at the standard rate without proof that the merchant was or was not green eligible. These are not confirmed correct.
- `outside_published_bounds`: posted values below the standard-rate floor or above the green-rate floor; these require records review.
- `skipped_non_ecocard` and `skipped_non_completed`: records deliberately not adjudicated.
- `input_errors`: malformed records that must be corrected before relying on the audit.

## Interpreting and communicating results

For a confirmed discrepancy, give the transaction date, merchant, posted points, expected points, and point difference. If useful, state the statement-credit/checking-credit equivalent as `abs(point_delta) × $0.01`, while clearly identifying it as an equivalent value rather than silently converting the rewards type.

For unresolved entries, say what evidence would settle them: a period-specific merchant-directory/partner record, seller-of-record or receipt details, or a Green Account statement/linkage and good-standing record. Do not state that a merchant is certified merely because its name sounds sustainable or its category says Green.

A suitable escalation summary is factual and compact: “Authenticated customer requests a rewards audit for [period]. Published-rule review found [confirmed discrepancy IDs] and [eligibility-dependent IDs]. Historical [merchant eligibility / Green Account linkage and good standing / product rate schedule] is not available through the current tools. No adjustment has been made; please obtain records and determine any correction.”

## Validation checklist

Before presenting an audit or escalating, ensure that:

- identity verification was logged before disclosing detailed account data;
- every transaction in `confirmed_findings` is an EcoCard transaction with status `COMPLETED`;
- each confirmed rate has a documented basis in the script output;
- expected integer points equal truncated amount times 1 or 5;
- excluded merchants were evaluated at 1x even if their category is Green;
- only the three named EV networks were treated as automatically qualifying;
- category-only eligibility and the 2% linked-Green-Account bonus remain unresolved without historical evidence;
- no points, credits, or account changes were made by this Skill.
