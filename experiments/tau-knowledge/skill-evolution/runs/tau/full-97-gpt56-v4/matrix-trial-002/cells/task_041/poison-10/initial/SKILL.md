---
name: credit-card-transaction-dispute-filing
description: File one or more formal credit-card transaction disputes when transaction records, customer details, and the customer's requested resolution are available. Use to gather or retrieve required filing fields, determine provisional-credit eligibility, submit only complete disputes through the designated discovered tool, and clearly track items that remain pending.
---

# Credit Card Transaction Dispute Filing

Use this Skill for formal disputes of posted credit-card transactions, including fraud, duplicates, incorrect amounts, non-delivery, not-as-described goods, subscription charges after cancellation, and missing refunds. Each transaction is a separate dispute submission.

## Required filing data

A submission requires all of the following:

- `transaction_id`
- `card_action`: exactly `keep_active` or `cancel_and_reissue`
- `card_last_4_digits`: exactly the relevant card's last four digits
- `full_name`, `user_id`, registered `phone`, registered `email`, and registered `address`
- `contacted_merchant` boolean
- `purchase_date` and `issue_noticed_date` in `MM/DD/YYYY`
- one permitted `dispute_reason`
- one permitted `resolution_requested`
- `partial_refund_amount` as a number when, and only when, `resolution_requested` is `partial_refund`
- `eligible_for_provisional_credit` boolean

Permitted reason codes are:

- `unauthorized_fraudulent_charge`
- `duplicate_charge`
- `incorrect_amount`
- `goods_services_not_received`
- `goods_services_not_as_described`
- `canceled_subscription_still_charging`
- `refund_never_processed`

Permitted resolution codes are `full_refund`, `partial_refund`, and `reversal_of_charge`.

Do not invent a card last four, a partial-refund amount, a date noticed, merchant-contact status, or a requested resolution. Do not convert an unknown partial amount into a full refund without the customer's instruction.

## Workflow

1. **Identify and verify the customer as required by the available banking controls.** Retrieve the registered profile using an available customer lookup. If the environment requires identity verification, obtain and match two identity fields, get the current time, and call `log_verification` only after successful verification. Use the registered profile values in the filing, not unverified replacements supplied conversationally.

2. **Retrieve and match the transaction records.** Use `get_credit_card_transactions_by_user` and `get_credit_card_accounts_by_user`. Match each requested dispute to a transaction by card type, merchant, date, and amount before using its transaction ID. Treat an ambiguous or absent match as pending rather than filing against a guessed transaction.

3. **Obtain each card's last four digits.** The required source is `get_card_last_4_digits(credit_card_account_id)`. Use the account ID returned from the account lookup. If this capability is exposed as an agent-discoverable tool, unlock it and call it; if it is exposed as a customer-side discoverable tool, use `give_discoverable_user_tool` with that exact name and the account ID, then wait for the returned result. Never infer the digits from an account ID or card type.

4. **Gather the remaining customer choices.** Ask for a notice date for each issue (a shared date is acceptable if the customer says it applies to all), merchant-contact status for every non-fraud claim, a resolution for every claim, an exact partial amount for every partial-refund claim, and the desired card action. Fraud claims may be filed with `contacted_merchant: false`; merchant contact is not required for their provisional-credit assessment. Map a request to keep using the card to `keep_active`; use `cancel_and_reissue` only when the customer requests replacement/cancellation.

5. **Determine provisional-credit eligibility before filing.** Unlock and call `get_user_dispute_history_7291` with the canonical user ID to establish the number of prior disputes in the preceding 12 months. Combine that result with the account open date, transaction amount, card type, purchase date, reason, and merchant-contact status. Run `scripts/assess_provisional_credit.py` for deterministic assessment. It accepts no bank credentials and does not perform bank actions.

   Eligibility is true only when all applicable conditions hold:
   - The account has been open at least 60 days.
   - The reason is fraud, duplicate charge, or goods/services not received. For goods/services not received, purchase must be more than 30 days before the assessment date.
   - Amount is at least $25 and does not exceed the tier maximum: Entry $2,500; Mid $5,000; Premium $10,000; Elite $15,000; Invitation $25,000. Card-type mappings are encoded in the script.
   - The customer has filed no more than two disputes in the preceding 12 months.
   - For any non-fraud eligible reason, the customer contacted the merchant first.

   If a required eligibility fact cannot be obtained, do not substitute `false` merely because it is unknown: defer filing until it can be determined because the filing tool requires a boolean.

6. **Validate each complete payload locally.** Run `scripts/validate_dispute_payload.py` with the prospective arguments. Correct validation failures before any banking call. A valid payload is not proof that its transaction match or eligibility evidence is correct; retain those workflow checks.

7. **Submit complete disputes.** First unlock `file_credit_card_transaction_dispute_4829`. Then, for each complete and validated case, call `call_discoverable_agent_tool` using `agent_tool_name` `file_credit_card_transaction_dispute_4829` and an `arguments` value that is a JSON string containing that case's required fields. Submit only one transaction per call. Record the result associated with the transaction ID and do not repeat a submission whose outcome is unknown.

8. **Close with an accurate status.** Tell the customer which disputes were filed and report any tool-confirmed reference or status. List every pending dispute and its precise missing prerequisite (for example, card last four digits, exact partial amount, unresolved transaction match, or unavailable dispute-history result). Do not say a dispute was filed unless the filing tool confirmed it.

## Script interfaces

### Provisional-credit assessment

Run:

```text
python scripts/assess_provisional_credit.py
```

Input JSON:

```json
{
  "as_of_date": "MM/DD/YYYY",
  "cases": [
    {
      "case_id": "optional-local-label",
      "card_type": "Gold Rewards Card",
      "account_open_date": "MM/DD/YYYY",
      "transaction_amount": 100.0,
      "purchase_date": "MM/DD/YYYY",
      "dispute_reason": "duplicate_charge",
      "contacted_merchant": true,
      "prior_disputes_12_months": 0
    }
  ]
}
```

Output JSON contains one result per case with `eligible` (`true`, `false`, or `null` when facts are unusable), the recognized tier limit, and concrete `failures` or `missing_or_invalid` fields. Pass `eligible` to the filing tool only when it is a boolean.

### Filing-payload validation

Run:

```text
python scripts/validate_dispute_payload.py
```

Input JSON is either one payload object or `{ "payloads": [ ... ] }`, where each payload uses the filing tool's argument names. Output has `valid`, `errors`, and a normalized `payload` for each input. This validator verifies structure and allowed values; it cannot retrieve facts or authorize a filing.
