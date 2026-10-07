---
name: credit-card-dispute-and-replacement-workflow
description: Handle one or more credit-card transaction disputes, including provisional-credit assessment and a requested replacement card. Use when a verified customer reports card charges and may want their card cancelled/reissued.
---

# Credit-card dispute and replacement workflow

Use this Skill to safely gather, validate, and submit formal credit-card disputes and (when requested) a replacement-card order. Treat each disputed transaction as a separate formal dispute. Never invent a required field or submit a tool call with incomplete information.

## 1. Verify and identify the correct account

1. Obtain enough customer-provided identity information to satisfy standard verification. In this runtime, successful verification requires confirmation of **two of four** fields: date of birth, email, phone number, and address.
2. Look up the customer and compare the two supplied fields to the customer record. Obtain the current timestamp with `get_current_time`, then call `log_verification` with all returned customer identity fields and that timestamp.
3. Retrieve the customer's card accounts and transactions. Match the reported transaction(s) to the correct transaction IDs and card account. Do not assume a transaction belongs to the desired card merely because merchant or amount match.
4. If last four digits are missing, use the documented `get_card_last_4_digits` discovered tool with the selected credit-card account ID. Follow the runtime's discoverable-tool access process (unlock it if it is agent-discoverable, then call it) and use the returned four digits. Do not substitute an account ID, guess digits, or require the customer to access their card when the documented tool is available.

If identity cannot be verified, do not reveal account information, order a card, or file a dispute. Ask for another identity field. If a documented tool is unavailable or returns an unresolved error, explain that the action cannot be completed yet and use the applicable escalation process; do not fabricate its result.

## 2. Gather and normalize dispute information

For every selected completed transaction, collect or confirm:

- transaction ID, purchase date, amount, and the selected card's last four digits;
- full name, user ID, registered phone, email, and home address from the verified record;
- when the issue was noticed, formatted `MM/DD/YYYY`;
- whether the customer contacted the merchant (`true` or `false`);
- exactly one allowed reason:
  `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, or `refund_never_processed`;
- requested resolution: `full_refund`, `partial_refund`, or `reversal_of_charge`; and a positive monetary `partial_refund_amount` only for `partial_refund`;
- card action: `keep_active` if the customer wants to retain the card, otherwise `cancel_and_reissue` if the customer wants it cancelled and replaced.

Do not characterize a customer complaint differently without confirmation. For example, an unrecognized charge is normally `unauthorized_fraudulent_charge`; the same authorized purchase posted more than once is normally `duplicate_charge`; a received wrong item is `goods_services_not_as_described`. A separate transaction still needs a separate reason and filing.

## 3. Determine provisional-credit eligibility before each filing

Retrieve dispute history with `get_user_dispute_history_7291(user_id)` and count disputes filed in the preceding 12 months as of the current date. Determine account age from the selected account, transaction amount from the actual transaction, and the card tier from the account.

A dispute is eligible only if **all** apply:

1. the account has been open at least 60 days;
2. reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`;
3. amount is at least $25 and no more than the tier maximum;
4. no more than two prior disputes were filed in the preceding 12 months; and
5. for a non-fraud reason, the customer contacted the merchant.

For `goods_services_not_received`, eligibility also requires the purchase to be more than 30 days old. Tier caps: Entry $2,500; Mid $5,000; Premium $10,000; Elite $15,000; Invitation $25,000. The script `scripts/assess_provisional_credit.py` can calculate the deterministic portion once dates, tier, amount, and history count are known; review its `failed_conditions` before setting the tool boolean.

A lack of provisional-credit eligibility does **not** itself prevent filing the formal dispute. Set `eligible_for_provisional_credit` to `false` and proceed if the other filing requirements are complete.

## 4. File every completed dispute

After verification and complete data, unlock `file_credit_card_transaction_dispute_4829`, then call it once per transaction through `call_discoverable_agent_tool`. Pass a JSON string containing exactly the required fields:

```json
{
  "transaction_id": "string",
  "card_action": "keep_active or cancel_and_reissue",
  "card_last_4_digits": "four digits",
  "full_name": "string",
  "user_id": "string",
  "phone": "string",
  "email": "string",
  "address": "string",
  "contacted_merchant": true,
  "purchase_date": "MM/DD/YYYY",
  "issue_noticed_date": "MM/DD/YYYY",
  "dispute_reason": "allowed reason",
  "resolution_requested": "full_refund, partial_refund, or reversal_of_charge",
  "eligible_for_provisional_credit": false
}
```

Add `partial_refund_amount` only when `resolution_requested` is `partial_refund`. Preserve the actual tool outcome for each call. Do not repeat a call whose outcome is unknown; report/escalate it instead.

## 5. Replacement-card workflow

Perform a replacement only when the customer requested cancellation/reissue and has completed the replacement prerequisites. Before unlocking or calling the ordering tool:

1. Verify identity and look up the correct card account.
2. Confirm the complete shipping address directly with the customer, including unit/suite information and whether it is primary or alternate. A stored address is not confirmation.
3. Record exactly one replacement reason: `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`.
4. Offer shipping. Standard is free and 7–10 business days. Expedited is 2–3 business days: Entry $15, Mid $10, Premium and above $0. For fraud or stolen cards, strongly recommend expedited delivery and remind the customer to review unauthorized activity.
5. If expedited carries a fee, obtain explicit consent to that fee. Do not treat selecting expedited as fee consent.
6. Confirm eligibility before ordering. Use `get_pending_replacement_orders_5765(credit_card_account_id)` and treat any non-final order (e.g. pending or shipped) as a blocker. Also verify the replacement count in the last 60 days from available replacement records: Entry maximum 2, Mid maximum 3, Premium and above maximum 4. If the needed history is unavailable, do not claim eligibility; obtain the relevant record or explain/escalate per process.

Only after passing these checks, unlock and call `order_replacement_credit_card_7291` with the account identifier, reason, confirmed shipping address, `standard` or `expedited` speed, fee acknowledgement (customer consent when a fee applies), and relevant notes. Do not order another card merely because dispute calls use `cancel_and_reissue`; the replacement ordering prerequisites still apply.

If blocked by a pending order or limit, do not submit. Explain that a pending request must be delivered/cancelled first, or that support can manually review a legitimate request beyond the tier limit.

## 6. Closeout

For a successful replacement, explain that the old card is cancelled for new purchases, the replacement has a new card number/CVV, and the account number remains unchanged. State the delivery window selected, and that emails are sent on order placement and shipment. For fraud/stolen cases, remind the customer to review recent transactions and dispute unauthorized charges. Document verification, transaction/dispute identifiers and outcomes, provisional-credit decisions, replacement eligibility checks, order details/outcome, customer confirmations, and any unresolved failures.

## Helper script

Run the deterministic eligibility helper by passing JSON on stdin:

```bash
python scripts/assess_provisional_credit.py <<'JSON'
{
  "current_date": "YYYY-MM-DD",
  "account_open_date": "YYYY-MM-DD",
  "purchase_date": "MM/DD/YYYY",
  "transaction_amount": 100.00,
  "card_tier": "mid",
  "dispute_reason": "duplicate_charge",
  "contacted_merchant": true,
  "prior_disputes_last_12_months": 0
}
JSON
```

It emits JSON with `eligible_for_provisional_credit`, `failed_conditions`, normalized tier cap, and age calculations. Its output is advisory validation; the executor must ensure the supplied history count and dates came from current runtime records.
