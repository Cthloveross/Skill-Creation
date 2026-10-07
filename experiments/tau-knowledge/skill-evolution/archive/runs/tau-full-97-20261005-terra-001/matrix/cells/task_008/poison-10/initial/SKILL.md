---
name: credit-card-promotion-redemption-triage
description: Safely review a customer claim based on a mailed, emailed, or other external credit-card promotion; distinguish documented offers from unverified claims; transfer unverified external promotions using the correct reason; and, only when all controls are met, apply a verified promotional statement credit.
---

# Credit-Card Promotion Redemption Triage

Use this Skill when a customer asks to redeem, honor, explain, or receive a statement credit from a credit-card promotion, particularly a flyer, letter, email, or other customer-supplied offer.

> Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

A customer possessing or describing a flyer does not by itself establish that an offer exists, applies to their product, or is redeemable. Never infer a missing card name, promotion code, account, deadline, benefit amount, or eligibility result. Do not substitute a similar documented offer when a material term differs.

## Procedure

1. **Collect the claim without promising fulfillment.** Ask for the card/product name, offer or promotion code, offer expiration date/window, qualifying spend and period, benefit type and amount, and any mailer reference, URL/QR destination, phone number, or address. Record only facts the customer provides.

2. **Identify and verify the customer before account actions.** Obtain a usable user ID or a supported lookup identifier from the customer. To verify identity, confirm two of the four identity fields (date of birth, email, phone number, address) against the returned profile. Get the current time and call `log_verification` with the complete returned profile and timestamp only after two fields have been confirmed. Do not guess an identifier or inspect accounts for an unverified/unknown person.

3. **Search the supplied knowledge base and compare material terms.** Use only the current task's documented offers. Compare the claimed product, code, dates/window, required net posted spend, qualifying period, and statement-credit amount. A difference in any disclosed material term means the claimed external offer is not verified. Missing flyer identifiers also prevent treating the flyer itself as verified.

   The optional `scripts/assess_promotion.py` helper makes this comparison deterministic after the executor has entered the documented offers and customer claim. It does not search the knowledge base, authenticate a user, calculate qualifying spend, or authorize a credit.

4. **Handle an unverified external promotion correctly.** When the customer claims a specific external flyer/letter/email promotion and it cannot be verified after the knowledge-base search—including when it conflicts with the closest documented offer—explain that the offer cannot be confirmed or honored from the available information. Do not apply a credit. Transfer with:
   - `reason`: `unconfirmed_external_communication`
   - `summary`: a concise factual description of the claimed promotion, missing identifiers or material discrepancy, the completed KB comparison, and that no credit was applied. Do not include unnecessary full identity values.

   This Tier 2 reason takes precedence over general customer-request or catch-all transfer reasons for this scenario.

5. **For a documented offer, complete eligibility checks before any credit.** After identity verification, use `get_credit_card_accounts_by_user` to confirm the customer owns the applicable card and that the product and opening date fit the documented offer. Verify the offer window, account status, net qualifying purchases (posted purchases less returns/credits), qualifying-period cutoff, available credit/balance implications, fees, limits, and any other documented conditions. Use `get_credit_card_transactions_by_user` where transaction history is needed. Obtain explicit confirmation of the exact statement-credit amount to be applied.

6. **Apply only an authorized, verified credit.** If every prerequisite is satisfied, unlock `apply_statement_credit_8472`, then call it through `call_discoverable_agent_tool` with a JSON string containing the verified `user_id`, the confirmed `credit_card_account_id`, the positive documented amount, and `reason` set to `promotional_credit`. Never use a claimed amount that is unverified. Confirm the result by checking that the credit appears as a negative card transaction and reduces the statement balance.

7. **Communicate the outcome.** State only the verified terms and expected fulfillment timing. If qualification has not occurred, explain which verified requirement remains; do not promise an exception. If the customer later asks for a human after a completed action, choose the transfer reason based on the transfer-reason hierarchy rather than reusing the external-communication reason automatically.

## Classifier helper

Run with a real JSON request file containing current task facts:

```sh
python3 scripts/assess_promotion.py < promotion_request.json
```

### Input JSON schema

- `kb_search_completed` (boolean): whether the executor has searched the supplied KB.
- `external_promotion_claim` (boolean): whether the claim comes from a flyer, letter, email, or similar external communication.
- `account_identified` (boolean): whether an applicable customer account has been identified. This is not a substitute for identity verification.
- `identity_verified` (boolean): whether the required identity verification has completed.
- `claim` (object): supplied values among `card_name`, `product`, `promotion_code`, `offer_start`, `offer_end`, `spend_amount`, `qualifying_months`, `benefit_type`, and `benefit_amount`. Omit unknown fields or set them to `null`.
- `verified_offers` (array of objects): offers obtained from the current KB, using the same comparison fields and an optional internal `offer_id`.

### Output JSON schema and validation

The helper emits one JSON object with `ok`, `status`, `candidate_count`, `matching_offer_ids`, `conflicting_fields`, `transfer_reason`, and `next_step`. It emits `ok: false` with an `error` for malformed input. Review that `ok` is true, that the status agrees with the KB review, and that any transfer status has exactly `unconfirmed_external_communication` before using its recommendation. A matching candidate is only a comparison result; it is never authorization to access an account or apply a statement credit.
