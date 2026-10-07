---
name: stolen-debit-card-closure-and-replacement
description: Securely handle a verified customer's request to permanently close stolen debit cards and arrange eligible replacements across one or more checking accounts. Use for lost/stolen debit-card incidents where closure, replacement limits, shipping, design fees, and cross-product credit-card protection must be evaluated.
---

# Stolen Debit Card Closure and Replacement

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and safety

Use this procedure when the customer reports a debit card as lost or stolen and asks to freeze, close, or replace it. A freeze is temporary; for a confirmed stolen card, recommend permanent closure. Never treat a freeze request alone as authorization to close a card. A clear request to close after verification is authorization for closure, but ordering each replacement still requires complete delivery, product, fee, and confirmation details.

Do not guess account-to-card mappings, tiers, card IDs, card status, pending activity, fees, replacement history, or a tool parameter not exposed by the runtime. Do not retry an action whose outcome is reported as unknown.

## Required workflow

1. **Establish and log verification before an action.**
   - Obtain and match at least two of date of birth, email, phone number, and address against the customer profile. A supplied full name or email can be used to locate the profile but does not replace the two-field check.
   - Retrieve the current timestamp with `get_current_time` and call `log_verification` with the matched user's complete returned profile details and that timestamp.
   - Confirm the requester is asking about their own cards and record their requested disposition. If closure has not been clearly authorized, explain that closure is permanent and ask whether to freeze or close.

2. **Check the cross-product security requirement.**
   - For every lost or stolen debit-card incident, use `get_credit_card_accounts_by_user` for the verified user.
   - If any credit card is present, explain the wallet-theft risk and offer a replacement credit card with a new number. Do not order one without the customer's choice. If none are present, state that no Rho-Bank credit card protection action is needed.

3. **Identify only the relevant checking accounts and cards.**
   - Unlock and use `get_all_user_accounts_by_user_id_3847` with the verified `user_id`. Restrict card work to the requested, open checking accounts. Use returned account identifiers and account class/tier; if an account label cannot be matched unambiguously, ask the customer to identify it rather than assuming.
   - Unlock and use `get_debit_cards_by_account_id_7823` for each relevant checking account. Select the requested card(s) by returned account linkage and card details. Confirm each selected card's `user_id` equals the verified user ID.

4. **Perform every closure eligibility check separately for each card.**
   - The card must be owned by the verified user and have `ACTIVE` or `PENDING` status.
   - Retrieve the card's transaction and refund status using the applicable normal banking lookup tools available in the runtime. Do not close a card with a pending or processing transaction. Do not close a card with a pending refund unless the customer gives the required written acknowledgment that the refund will instead credit the linked checking account. Explain the applicable hold to the customer.
   - The ordinary 14-day active-age restriction does **not** apply to reasons `lost`, `stolen`, or `fraud_suspected`. It does not waive ownership, eligible status, pending-transaction, or pending-refund checks.
   - If a prerequisite cannot be verified, or any card is ineligible, do not close that card. Clearly distinguish it from any other requested card that is eligible.

5. **Close eligible stolen cards.**
   - Before the call, confirm that the customer authorized permanent closure and that `stolen` is the recorded reason. Inform them that authorized pending transactions may still settle.
   - Unlock and use `close_debit_card_4721` with exactly the selected `card_id` and reason `stolen` for each eligible card. Make one action per card and inspect the result before proceeding to the next.
   - Confirm a successful closure: the card is permanently deactivated and cannot be reactivated; recurring payments need updated payment details; refunds to the closed card credit the linked checking account; a new card must be ordered if needed.

6. **Evaluate replacement eligibility only after successful closure.**
   - Build replacement history from the account's cards. Count only cards issued within the prior rolling 12 months whose `issue_reason` is `lost`, `stolen`, `fraud`, or `damaged`. Do not count `new_account`, `first_card`, `expired`, `upgrade`, or `bank_reissue`.
   - Determine the linked checking-account tier from account data and apply the following policy:

     | Tier | Limit and timing | Allowed delivery and delivery fee |
     |---|---|---|
     | ENTRY | 2 replacements / rolling 12 months; wait 48 hours after closure | STANDARD only, $0 |
     | MID | 3 replacements / rolling 12 months; no closure wait | STANDARD $0 or EXPEDITED $15 |
     | PREMIUM | 5 replacements / rolling 12 months; no closure wait | STANDARD or EXPEDITED $0; RUSH $35 |
     | ELITE | Unlimited; no closure wait | STANDARD, EXPEDITED, or RUSH, all $0; same-business-day processing before 2pm EST |

     Entry and Mid customers above their limit may wait for the oldest counted replacement to age out or elect the applicable excess replacement fee ($25 Entry, $15 Mid). Premium customers above their limit must wait; Elite has no limit. Obtain customer consent before any paid option and use only the supported order workflow for any excess fee.

   - Apply design fees: Entry/Mid: CLASSIC $0, PREMIUM $10, CUSTOM $25. Premium: CLASSIC/PREMIUM $0, CUSTOM $15. Elite: all designs $0.
   - All delivery, design, and applicable excess fees are automatically charged to the linked checking-account balance. Quote exact applicable fees and confirm the customer accepts them before ordering. Confirm a complete delivery address, design, and allowed shipping choice for every individual replacement. A preference for the "fastest" option is a request to identify and quote that option, not consent to an unquoted paid charge.
   - If a requested metallic/PREMIUM design is conditional on being free, select PREMIUM only when its design fee is $0; otherwise offer/select CLASSIC after confirming that interpretation with the customer. If a card's design or shipping choice is absent, request it; do not infer it from another account.

7. **Order and confirm each authorized, eligible replacement.**
   - Unlock and use `order_debit_card_5739` only after closure, timing, limits, balance/fee, address, card details, shipping, design, and customer confirmation are all satisfied. Supply the exact `delivery_fee` and `design_fee` calculated for that account and the other parameters required by the exposed tool schema.
   - Inspect each result. Provide a per-account summary of closures, ordered replacements, design, shipping, charges, waits, and any cards that could not be acted on. Do not claim an order succeeded unless the tool reports success.

## Optional deterministic policy helper

`scripts/replacement_policy.py` calculates tier-based allowed shipping, design and delivery fees, and the rolling 12-month count from caller-supplied card history. It performs no bank action and does not establish eligibility by itself; the executor must still verify ownership, closure success, address, customer consent, available balance, and the actual order-tool schema.

Run it through the packaged script runtime with JSON on stdin. Input schema:

```json
{
  "tier": "ENTRY|MID|PREMIUM|ELITE",
  "as_of_date": "YYYY-MM-DD",
  "replacement_history": [{"issue_reason": "...", "date_issued": "YYYY-MM-DD"}],
  "design": "CLASSIC|PREMIUM|CUSTOM",
  "shipping": "STANDARD|EXPEDITED|RUSH|FASTEST"
}
```

It emits JSON containing normalized selections, exact `delivery_fee` and `design_fee`, counted history, limit state, timing requirement, and any validation errors. Treat errors or `orderable_now: false` as a stop condition until resolved.
