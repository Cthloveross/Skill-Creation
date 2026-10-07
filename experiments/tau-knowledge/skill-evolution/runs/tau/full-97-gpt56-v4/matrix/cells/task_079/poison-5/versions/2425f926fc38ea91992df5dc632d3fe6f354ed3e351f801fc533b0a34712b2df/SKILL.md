---
name: stolen-debit-card-closure-and-replacement
description: Handle a verified customer's report that debit cards were lost or stolen, including secure permanent closure, per-account replacement eligibility and pricing, and the required credit-card security check.
---

# Stolen Debit Card Closure and Replacement

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Use and boundaries

Use this workflow for a lost or stolen debit-card report. A freeze is temporary; explain that a confirmed stolen card should normally be permanently closed. Do not convert an initial request to freeze into a closure without clear customer authorization. A customer's explicit request to close the identified cards after verification is authorization to close them, but is **not** blanket approval for a paid replacement option.

Work separately for each requested checking account and its card. Never infer a card ID, ownership, account mapping, normalized tier, status, pending activity, fee, delivery choice, design, replacement history, or unavailable tool parameter. Do not repeat an action with an UNKNOWN outcome.

## End-to-end procedure

1. **Verify and record identity before changing a card.** Locate the profile using the supplied name or email, then obtain and match at least two of DOB, email, phone number, and address. A name alone is not a verification field. Confirm the requester is the owner and has authorized the requested disposition. Get the time with `get_current_time`, then call `log_verification` using the complete matched profile returned by the user lookup and that timestamp.

2. **Do the wallet-theft credit-card check.** Call `get_credit_card_accounts_by_user` for the verified user. If cards exist, tell the customer that a stolen wallet can compromise multiple cards, ask whether any listed Rho-Bank credit card was stolen, and offer a replacement with a new number. Do not order it without their response. If none exist, state that no Rho-Bank credit-card protection action is needed.

3. **Resolve accounts and debit cards.** Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified user ID. Match the customer's requested account names only to returned, OPEN checking accounts; ask if a display name is ambiguous. For each such account, unlock/call `get_debit_cards_by_account_id_7823(account_id)`. Select only the relevant current card(s), and confirm every selected card has the same `user_id` and is `ACTIVE` or `PENDING`. Keep the account ID, card ID, date issued, issue reason, status, and the account's explicitly returned normalized tier/level.

4. **Check closure prerequisites per selected card.** Before closure, use any exposed normal transaction/refund lookup capability to determine whether there are pending or processing transactions or pending refunds. A pending/processing transaction blocks closure. A pending refund blocks closure unless the customer supplies the required written acknowledgment that it will credit the linked checking account. For `lost`, `stolen`, and `fraud_suspected`, the 14-day card-age rule is bypassed only; it does not bypass the other checks. If a prerequisite cannot be verified, or a card has a blocking pending transaction/refund, do not close that card. Explain what must be resolved, while distinguishing it from any other requested card that is eligible.

5. **Close each eligible stolen card.** Tell the customer that already-authorized pending transactions can still settle. Unlock `close_debit_card_4721` and make one call for each eligible card with exactly `card_id` and `reason: "stolen"`; inspect a result before the next call. A success means the card is permanently deactivated and cannot be reactivated. Tell the customer to update recurring payments; refunds to the closed card credit the linked checking account. Do not represent a failed or uncalled closure as complete.

6. **Determine replacement eligibility after each successful closure.** From that account's returned card history, count only cards with issue reasons `lost`, `stolen`, `fraud`, or `damaged` issued in the preceding rolling 12 months. Do not count `new_account`, `first_card`, `expired`, `upgrade`, or `bank_reissue`. Use the account's actual normalized tier, not a guessed mapping from a marketing/display account name. If the account lookup does not expose a tier that can be matched to the policy, obtain the tier through an exposed normal source or tell the customer pricing cannot yet be quoted.

   | Tier | Replacement limit/timing | Shipping (delivery fee) | Design fee: Classic / Premium / Custom |
   |---|---|---|---|
   | ENTRY | 2 in 12 months; wait 48 hours after closure | STANDARD ($0) | $0 / $10 / $25 |
   | MID | 3 in 12 months; no closure wait | STANDARD ($0), EXPEDITED ($15) | $0 / $10 / $25 |
   | PREMIUM | 5 in 12 months; no closure wait | STANDARD ($0), EXPEDITED ($0), RUSH ($35) | $0 / $0 / $15 |
   | ELITE | unlimited; no closure wait | STANDARD, EXPEDITED, RUSH (all $0) | $0 / $0 / $0 |

   When above the limit, Entry may pay $25 excess fee or wait, Mid may pay $15 or wait, Premium must wait, and Elite has no limit. Entry's 48-hour wait applies even when otherwise eligible. The helper below may calculate this deterministic portion.

7. **Obtain an informed, individual order confirmation.** Confirm the full delivery address, allowed delivery option, and design for **each** replacement; do not carry a choice from one account to another. Tell the customer the exact delivery, design, and any excess-replacement fee and that these are automatically deducted from the linked checking balance when ordered. Check available balance before ordering. “Fastest” means identify the fastest available allowed option and quote its fee; it is not consent to charge it. “Premium metallic only if free” means use PREMIUM only if its design fee is $0; otherwise ask/confirm CLASSIC (the free option). Missing selection or fee acceptance requires a follow-up, not a default order.

8. **Order only confirmed, orderable replacements.** Unlock `order_debit_card_5739` and inspect its schema. For each successfully closed, eligible, fully confirmed card, pass the returned account ID and verified user ID plus the confirmed delivery option, exact `delivery_fee`, design, exact `design_fee`, full shipping address, and `excess_replacement_fee` only when applicable and accepted. Inspect each result. Summarize, per account, closure status, ordered replacement or blocker, choices, timing, and charges.

## Deterministic replacement-policy helper

`scripts/replacement_policy.py` is a pure calculator; it does not establish ownership, look up a tier, check balance, close a card, or place an order. Run it through the script runtime with one JSON object on stdin and parse its JSON stdout. It accepts:

```json
{
  "tier": "ENTRY|MID|PREMIUM|ELITE",
  "as_of_date": "YYYY-MM-DD",
  "replacement_history": [{"issue_reason": "lost", "date_issued": "YYYY-MM-DD"}],
  "design": "CLASSIC|PREMIUM|CUSTOM",
  "shipping": "STANDARD|EXPEDITED|RUSH|FASTEST",
  "hours_since_closure": 0,
  "accept_excess_replacement_fee": false,
  "accept_quoted_fees": false
}
```

It emits JSON with normalized selection, fees, rolling-history count, fastest available option, wait/limit outcome, required paid consent, and `orderable_now`. Treat invalid input, `orderable_now: false`, or `requires_customer_confirmation: true` as a reason to resolve the issue before calling an order tool. Example invocation: send the object above to `scripts/replacement_policy.py`; validate that `ok` is true and that returned fees exactly match the order request.
