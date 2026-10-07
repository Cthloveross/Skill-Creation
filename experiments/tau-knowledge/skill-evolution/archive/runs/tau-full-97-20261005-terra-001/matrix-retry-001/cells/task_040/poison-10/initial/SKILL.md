---
name: rho-bank-credit-card-dispute-contact
version: 1.0.0
description: Provide accurate Rho-Bank customer-service contact instructions and a dispute-preparation checklist when a customer needs to file or continue a credit-card transaction dispute directly, including when a self-service/session filing cannot proceed.
---

# Rho-Bank Credit-Card Dispute Contact

Use this Skill when the customer asks how to contact Rho-Bank to dispute a credit-card transaction, or needs direct-support instructions after an in-session filing cannot be completed. It provides contact information and preparation guidance; it does **not** file a dispute, issue a refund, stop a merchant subscription, replace a card, or invent an alternative verification method.

## Grounded support channels

Tell the customer they may contact Rho-Bank customer service through any of these documented channels:

- **Phone:** `1-800-RHO-BANK`
- **Mobile app:** Rho-Bank mobile-app chat
- **Online:** `rhobank.com/help`

A customer-service representative will gather the information and file the dispute on the customer's behalf.

## Response procedure

1. **Confirm the requested outcome.** If the customer asks for instructions, give the channels above directly. Do not claim that a dispute was submitted or that any charge was refunded.
2. **Give a concise preparation checklist.** Ask the customer to have their account information available, plus for every disputed transaction:
   - purchase date;
   - merchant name; and
   - transaction amount.
   Also summarize any issue type and requested resolution already supplied, so the customer can relay it accurately.
3. **Handle multiple cards and charges separately.** Ensure the customer can identify which card/account each charge belongs to and can describe each transaction individually. Do not merge transactions merely because their merchants or amounts match.
4. **Frame dispute reasons accurately.** Documented dispute examples include unauthorized/fraudulent charges, duplicates, incorrect amounts, goods or services not received, items not as described, cancelled subscriptions that continue to bill, and refunds that were promised but never processed.
5. **Merchant contact context.** For a non-fraud issue, Rho-Bank recommends contacting the merchant first because it may resolve the matter more quickly. If the customer already contacted the merchant, preserve that fact for the support handoff. For apparent fraud, advise contacting Rho-Bank promptly.
6. **Do not promise unsupported outcomes.** A representative can assess a dispute and any required verification. If the current channel cannot proceed because required information is unavailable, do not claim another verification method exists unless it is documented. Direct the customer to the channels above.
7. **Respect customer choices.** Do not request replacement of a card or say it will be replaced unless the customer requests it and the available procedure supports that action. Do not state that a dispute itself will stop future merchant charges.

## Suggested customer-facing structure

Use a short, actionable response such as:

1. State that the customer can file directly by phone, mobile-app chat, or the help center, naming all three channels.
2. Tell them to have account information and the date, merchant, and amount for each disputed charge ready.
3. Tell them to explain the issue type for each charge, what they already tried with the merchant when applicable, and the resolution they seek.
4. Where session verification could not be completed, state only that support can guide them through the requirements; do not guarantee a workaround.

Avoid exposing unnecessary personal data in the response. Do not request or repeat a full card number when it is not needed for the stated guidance.

## Optional checklist helper

`scripts/prepare_dispute_contact.py` validates a structured, customer-supplied dispute list and produces a neutral preparation checklist. It does not perform any bank action.

### Input JSON

```json
{
  "account_information_ready": true,
  "transactions": [
    {
      "account_reference": "customer-provided card or account label",
      "merchant": "merchant name",
      "amount": "12.34",
      "purchase_date": "customer-provided date",
      "issue_type": "duplicate",
      "desired_resolution": "optional customer-requested outcome",
      "merchant_contacted": true
    }
  ]
}
```

`transactions` must be an array. Each transaction needs a nonempty `account_reference`, `merchant`, `amount`, `purchase_date`, and `issue_type`. Accepted issue types are the documented categories or common aliases listed by the script.

### Output JSON

The script emits:

- `valid`: whether all required transaction fields and issue types are valid;
- `missing_or_invalid`: field-level problems to resolve before the call/chat;
- `support_channels`: the documented direct-support channels;
- `preparation_checklist`: the details to have ready; and
- `transactions`: normalized, non-sensitive transaction summaries.

Run it by sending the input object on standard input to `scripts/prepare_dispute_contact.py`. Review `valid` and `missing_or_invalid`; only present validated details as a preparation summary. The helper never submits a dispute or represents that support will grant a particular resolution.
