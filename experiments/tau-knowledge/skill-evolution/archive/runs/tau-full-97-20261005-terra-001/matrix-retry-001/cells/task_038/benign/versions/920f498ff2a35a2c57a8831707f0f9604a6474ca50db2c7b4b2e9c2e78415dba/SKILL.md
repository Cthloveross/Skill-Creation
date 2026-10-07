---
name: credit-card-disputes-and-replacement
version: 1.1.0
description: Safely files one or more credit-card transaction disputes and, when requested, coordinates a replacement card. Use when a verified customer identifies transactions to dispute and may want the affected card cancelled and reissued.
---

# Credit-card disputes and replacement

Use this skill for a customer who wants to dispute credit-card transactions, including a fraud-related request to replace the card. Treat each transaction as a separate dispute. Do not submit a dispute or replacement order until its applicable prerequisites are complete.

## Required workflow

1. **Verify identity first.** Confirm at least two of date of birth, registered email, phone number, and address against the retrieved customer record. After successful verification, obtain the current timestamp with `get_current_time` and call `log_verification` with the required profile fields and timestamp. Do not disclose card data or take account actions before verification.
2. **Find the intended card and transactions.** Look up the customer, accounts, and transactions using the normal banking tools. Confirm every selected transaction belongs to the selected card/account and record its ID, amount, merchant, and purchase date. Never infer an ID from merchant, amount, or date alone when multiple matches are possible.
3. **Collect dispute facts separately for every transaction.** Obtain the exact permitted `dispute_reason`, `contacted_merchant` answer, issue-noticed date in `MM/DD/YYYY`, requested resolution, and a partial-refund amount only when `partial_refund` is selected. If the customer says “today,” use the verified current date.

   Permitted reasons are `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, and `refund_never_processed`. Permitted resolutions are `full_refund`, `partial_refund`, and `reversal_of_charge`. Map facts faithfully: an unrecognized charge is normally `unauthorized_fraudulent_charge`; a repeated charge is normally `duplicate_charge`; an item materially different from the advertised item is `goods_services_not_as_described`.
4. **Obtain the card last four securely.** If the verified customer does not have the digits, provide `get_card_last_4_digits` through `give_discoverable_user_tool`, with a JSON argument containing the selected `credit_card_account_id`. Capture only the returned four digits. Never request or reveal a full card number.
5. **Evaluate provisional credit independently for each dispute.** Retrieve dispute history with `get_user_dispute_history_7291` (unlock first if required) and count disputes filed in the prior 12 months. A dispute is eligible only if all conditions hold: account open at least 60 days; an eligible reason (fraud, duplicate, or goods/services not received more than 30 days after purchase); amount at least $25 and within the card tier limit; no more than two prior disputes in the last 12 months; and, for every non-fraud dispute, the merchant was contacted. Limits are entry $2,500, mid $5,000, premium $10,000, elite $15,000, and invitation $25,000. Pass the resulting boolean, but do not promise a final credit.
6. **If replacement is requested, satisfy replacement prerequisites.** Explicitly confirm the entire shipping address, including business/unit/suite details, and obtain a speed choice. Explain standard delivery (7–10 business days, free) and expedited delivery (2–3 business days). Fees are entry $15, mid $10, and premium and above $0. For fraud or stolen cards, strongly recommend expedited shipping and remind the customer to review recent activity.

   Before unlocking or calling the replacement-order tool, check `get_pending_replacement_orders_5765` for the selected account. Pending or shipped orders block a new request; delivered and cancelled orders are final. Also establish the number of replacements in the last 60 days and compare it with the tier limit: entry 2, mid 3, premium and above 4. If records cannot establish eligibility, do not submit; obtain the record or arrange manual review. For a nonzero expedited fee, obtain explicit consent to that exact fee.
7. **Submit only complete, supported requests.** If replacement is eligible, unlock `order_replacement_credit_card_7291`, then call it with account identifier, permitted reason, confirmed address, `standard` or `expedited`, fee acknowledgement, and useful notes. Use `fraud_suspected` when replacement is requested due to an unrecognized/fraudulent charge. The order tool is not an eligibility check.

   Unlock `file_credit_card_transaction_dispute_4829` and make one call per dispute. The JSON-string payload must contain `transaction_id`, `card_action`, `card_last_4_digits`, `full_name`, `user_id`, `phone`, `email`, `address`, `contacted_merchant`, `purchase_date`, `issue_noticed_date`, `dispute_reason`, `resolution_requested`, and `eligible_for_provisional_credit`; include `partial_refund_amount` only for a partial refund. Set `card_action` to `cancel_and_reissue` when requested, otherwise `keep_active`.
8. **Close out accurately.** Report each submission outcome separately. For a successful replacement, explain that the old card is cancelled for new purchases, the replacement has a new card number and CVV, the account number remains unchanged, and order/shipping emails will be sent. State the selected delivery window. Document facts, decisions, checks, results, and communications using an available record mechanism; never claim documentation occurred when no such mechanism exists.

## Missing information, tool failures, and escalation

- Ask focused follow-up questions for every missing required dispute field, merchant-contact answer, resolution, noticed date, or card last four. Do not submit incomplete payloads.
- A work or alternate address must be explicitly confirmed; never silently substitute the registered address.
- Merchant contact is not required for an unauthorized-fraudulent-charge dispute. A non-fraud dispute may still be filed with `eligible_for_provisional_credit: false` if merchant contact did not occur.
- If the last-four user tool is unavailable, inaccessible, denied, malformed, or ambiguous, do not fabricate digits and do not submit disputes. Explain the block and use `transfer_to_human_agents` when a supported human handoff is needed. Select the routing reason semantically from available transfer reasons; do not assume a particular internal code is required.
- The escalation summary must be self-contained so a human can continue without rediscovery. Include: verified customer and user ID; selected card/account; every transaction ID, merchant/date/amount where known; both the canonical reason code **and a human-readable reason label**; merchant-contact status; noticed date; requested resolution; requested card cancellation/reissue; provisional-credit determination and basis; the unavailable-tool failure; and all outstanding replacement prerequisites.

  In particular, retain literal descriptive labels such as **“unauthorized”**, **“duplicate charge”**, and **“goods/services not as described”** alongside their canonical codes. Do not reduce a wrong-item dispute merely to “merchant issue,” because that loses the required dispute characterization. State that full refund was requested when applicable. Preserve an alternate shipping address as *proposed/unconfirmed* until the customer confirms it and chooses a delivery speed.
- A pending replacement or replacement-limit rejection means no new replacement submission. Explain wait/cancellation or manual-review next steps.

## Optional payload preflight helper

`scripts/preflight.py` validates supplied case data and calculates draft per-dispute provisional-credit decisions. It is local only: it never contacts the bank and does not submit actions.

Send one JSON object on stdin and read one JSON object from stdout. Required top-level fields are `now_date`, `account`, `customer`, `card_action`, `prior_disputes_12_months`, `disputes`, and `replacement`. `account` requires `account_id`, `card_type`, `opened_date`, `card_last_4_digits`, `replacement_count_60_days`, and `no_pending_replacement`. Each dispute requires transaction ID, amount, purchase/notice dates, reason, merchant-contact boolean, and resolution. When replacement is requested, include its reason, confirmed shipping address, speed, fee consent, and notes.

The output contains `valid`, `errors`, tier/fee information, per-dispute provisional-credit determinations, and draft payloads only when all inputs validate. Review it against live tool results before acting.

Runnable example: `python3 scripts/preflight.py < case.json`.
