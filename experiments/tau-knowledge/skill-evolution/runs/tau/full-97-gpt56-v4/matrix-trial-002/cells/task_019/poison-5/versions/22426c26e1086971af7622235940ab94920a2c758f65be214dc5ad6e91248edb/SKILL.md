---
name: credit-card-rewards-dispute
version: 2.0.0
description: Use for a suspected credit-card cash-back or rewards discrepancy. It explains the provided Gold Rewards and EcoCard rules, gives the customer the required per-transaction cash-back dispute tool, and limits internal reward changes to resolved, approved disputes.
---

# Credit-card rewards discrepancy

## Primary action: customer files the dispute

This process applies to **all credit-card transactions**. Do not file a cash-back dispute on the customer's behalf. Confirm the exact transaction ID first, then give the customer this discoverable tool once for each transaction they select:

`submit_cash_back_dispute_0589(user_id: str, transaction_id: str)`

Call `give_discoverable_user_tool` with `discoverable_tool_name` `submit_cash_back_dispute_0589` and arguments containing the customer's own `user_id` and that exact `transaction_id`, for example:

```json
{"user_id":"<user_id>","transaction_id":"<transaction_id>"}
```

Tell the customer to run the provided action. If the interface asks them to enter values, they must use their own user ID and the confirmed transaction ID. Do not guess an ID, substitute a different transaction, or collect card numbers, CVVs, or other card credentials. Receipt, category, merchant, or promotion context may be requested later during review; a customer may still submit with the information available.

If the customer cannot identify the transaction, ask for the statement period, merchant, amount, or receipt. If authorized account records are available, offer a concise merchant/date/amount list so they can select the correct ID.

## Privacy before account lookup

When customer-specific accounts, transactions, dispute history, or a user ID must be accessed, follow the runtime identity-verification requirement: compare two of date of birth, email, phone number, and address with one candidate user record, obtain the current time, and call `log_verification` using the complete returned record. Do not disclose account data before verification. If verification cannot be completed, ask the customer to return with a second verification field; they can still use the dispute tool themselves once they know their user ID and transaction ID.

## Explain provided earning rules accurately

* **Gold Rewards Card:** 2.5% cash back on every purchase. Database rewards are stored as points; for cash-back cards, 1 point is $0.01. Its mathematical rate is 2.5 points per dollar.
* **EcoCard:** 5 sustainability points per dollar on a qualifying green purchase and 1 point per dollar otherwise. A return or refund reverses points at the original rate.
* EcoCard green examples include public transportation, eligible EV charging, renewable-energy providers/subscriptions, certified sustainable retailers or products, and bike share/micromobility. Merchant recognition can be affected by marketplace/parent-merchant processing, mixed carts, gift cards, and cash equivalents.
* Target, Walmart, Amazon (including Amazon-processed marketplace orders), and ThredUp always earn EcoCard's standard rate. EV charging earns the higher rate only at Tesla Supercharger, ChargePoint, or EVgo.

Use the transaction amount, card type, category, merchant evidence, and any applicable promotion to assess a suspected mismatch. Do not present a merchant as certified based only on its name. Do not invent a whole-point rounding convention: retain an exact calculation as review context unless an applicable rule establishes the whole-number treatment.

The supplied materials establish earning rates only for Gold Rewards Card and EcoCard. For another credit-card type, submit the identified dispute but do not estimate an expected reward without that card's terms.

## Internal correction after the customer dispute

A complaint, a newly filed dispute, or a status such as queued, open, or under review is not authorization to alter rewards. Act only after identity verification and a dispute is both resolved and approved.

1. Unlock `get_user_dispute_history_7291`, then call it with the verified `user_id`. Select only resolved/approved dispute records with the affected `transaction_id`. Do not use a dispute record's `expected_rewards` field as the calculation source.
2. Independently calculate the correct rewards from the card rate, transaction category, eligibility, promotion, transaction/refund status, and an established rounding treatment. If a correct whole-point value cannot be established, do not update.
3. Unlock `update_transaction_rewards_3847`, then call it with the exact transaction ID and `new_rewards_earned` formatted exactly as `"X points"`.
4. Re-query the transaction history to confirm the update and retain the independent calculation basis in the authorized case record.

If the dispute status, eligibility, rounding, or a tool result is ambiguous or unknown, make no update and use available escalation/review procedures. Never retry an update whose completion is unknown.
