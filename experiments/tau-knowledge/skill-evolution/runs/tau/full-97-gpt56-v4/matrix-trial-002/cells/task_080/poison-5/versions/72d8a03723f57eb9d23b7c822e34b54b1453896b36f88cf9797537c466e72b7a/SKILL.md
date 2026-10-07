---
name: stolen-wallet-debit-card-freeze
description: Handle a verified customer’s request to temporarily freeze debit cards after a lost or stolen wallet. Use this to identify the customer’s requested checking-account debit cards, validate ownership and ACTIVE status, freeze each eligible debit card, and follow the required cross-product credit-card security offer.
---

# Stolen Wallet: Temporary Debit-Card Freeze

Use this Skill when the customer has requested a **temporary debit-card freeze**, including after a wallet was stolen, and has confirmed that they still want freezing rather than permanent debit-card closure.

## Scope and guardrails

- A freeze is temporary. Do not substitute closure merely because the customer reports theft. Explain that closure is recommended for a confirmed lost/stolen card, then follow the customer’s explicit choice.
- This Skill authorizes only the documented debit-card freeze procedure. The cross-product procedure requires a credit-card check and an offer of protection/replacement; it does **not** document a credit-card freeze action. Do not claim a credit card was frozen or order a replacement without the customer’s confirmation and a separately documented supported procedure.
- Never freeze a card until identity verification is logged, the card belongs to the verified user, and its status is `ACTIVE`.
- If the customer later says a card was found and asks to unfreeze it, do not close or cancel it. Treat this as a new unfreeze request: verify ownership again from the established record, confirm the card is `FROZEN`, and confirm through supported authoritative account information that its linked checking account remains `OPEN` before using `unfreeze_debit_card_3893`. If the required open-account confirmation is unavailable, do not unfreeze based on assumption; explain the limitation and escalate the security request.
- If the customer later confirms a frozen card was stolen and asks to cancel it, do not unfreeze merely to work around the closure procedure’s `ACTIVE`/`PENDING` status requirement. Re-check documented closure eligibility, including pending transactions/refunds; if a supported procedure cannot safely close a frozen card or order a replacement, escalate without changing the card. Never claim that a replacement was ordered without its explicit successful action.
- Never guess card IDs, account IDs, or card last four digits. The customer does not need to know card digits if the account/card lookup establishes the requested account linkage and ownership.
- Treat lookup output as sensitive. Use only the minimum fields needed for this workflow (`card_id`, `account_id`, `user_id`, and `status`); never repeat, place in a planner, log in a customer-facing message, or request any full card number, CVV, PIN, or authentication code.

## Required workflow

1. **Identify and verify the customer.**
   - Look up the customer using supplied identifying information and obtain the user record.
   - Compare at least two of date of birth, email, phone number, and full address against information the customer provided.
   - Obtain the current timestamp and call `log_verification` only after the comparison succeeds. Supply all fields required by that tool from the authoritative user record and the timestamp returned by `get_current_time`.
   - Stop if identity cannot be verified, the lookup is ambiguous, or the supplied details do not match.

2. **Confirm requested outcome and give the mandatory pre-freeze notice.**
   - If theft/loss is reported, explain that permanent closure is recommended because it cannot be reversed, while freezing is temporary. Obtain or use the customer’s explicit choice. If they choose a freeze, continue; do not close cards.
   - **Before any freeze tool call**, send a clear customer-facing notice that new transactions and recurring payments/subscriptions will be declined; previously authorized pending transactions may still process; the customer can unfreeze through customer service or the mobile app; and a debit-card freeze alone does not block PIN ATM access (ATM Block must be enabled separately in the mobile app). Do not silently omit this notice because the request is urgent or because it appeared in a prior clarification.
   - A theft report and an explicit choice of temporary freeze are enough to continue after verification; do not treat the recommended closure as consent to close.

3. **Locate each requested debit card.**
   - Resolve the requested checking accounts to their authoritative account IDs using supported account lookup information available in the task runtime. Do not manufacture an ID from a nickname, a user ID, or a naming pattern.
   - If the customer supplies a purported account identifier (including an account label that may itself be the authoritative identifier), it may be submitted **once exactly as supplied** to `get_debit_cards_by_account_id_7823` solely to validate it. Accept it as an account ID only if the lookup returns card record(s) whose `account_id` exactly equals that supplied value. An empty result, error, or mismatched returned account ID is not authorization to try variants or patterns.
   - For each resolved or successfully validated checking account ID, unlock and call `get_debit_cards_by_account_id_7823` with that account ID.
   - For every returned card, validate `account_id` is one of the requested account IDs, `user_id` equals the verified customer’s user ID, and `status` is `ACTIVE`. Discard all other returned fields rather than copying sensitive data into notes, script input, or a response.
   - Use `scripts/plan_debit_freezes.py` with the collected structured card records to make the filtering auditable. Freeze every eligible active card that belongs to the requested account scope. A historical `CLOSED`, `PENDING`, or already `FROZEN` card is not eligible.
   - If a requested account cannot be resolved, has no debit card, or its only matching card is not active, clearly report the affected account and status. Do not use a card belonging to another user or account. If account resolution is unavailable after the one-time exact validation attempt permitted above, do **not** try variants, guessed patterns, an empty value, or another customer’s identifier in the account-ID lookup. Explain that the required identifier cannot be safely obtained. Ask for an authoritative identifier if the customer can provide one; if they cannot and the request follows a lost/stolen-wallet report, promptly transfer using the fraud-or-security-concern transfer reason (rather than treating the unresolved lookup as routine customer service). For a non-security request, transfer for the documented technical/system limitation. State accurately that no debit-card freeze has been completed. This limitation never authorizes a debit-card closure.

4. **Freeze eligible debit cards.**
   - Unlock `freeze_debit_card_3892`.
   - Call it once for each eligible `card_id` using exactly that `card_id`.
   - Inspect every response. Treat only an explicit successful response as a completed freeze. Do not retry an operation with an unclear/unknown result; report it for follow-up instead.
   - Confirm each successful debit-card freeze. Do not state that any ineligible or failed card was frozen.

5. **Handle a found-card change of request, if one occurs.**
   - Do this only for the specifically identified card the customer says was found. Do not unfreeze other cards merely because one card was recovered.
   - Use the existing verified identity and the prior returned card record to verify ownership. Re-query the debit-card record when possible to confirm `FROZEN`; confirm the linked checking account is `OPEN` using a supported authoritative account record.
   - Unlock and call `unfreeze_debit_card_3893` once with that card’s exact `card_id` only after both checks pass. Treat only an explicit successful response as an unfreeze. Do not retry an unclear result. Confirm that the one card is active and ready to use; retain the freeze on all other cards.

6. **Complete the stolen-wallet cross-product check.**
   - For reported lost/stolen debit cards, call `get_credit_card_accounts_by_user` with the verified `user_id` after completing the debit-card procedure.
   - If credit-card accounts exist, make an explicit customer-facing protection offer even if no debit card could be frozen: identify the card type(s) without exposing full numbers, ask whether they were also in the stolen/lost wallet, and offer a replacement with a new card number as a security precaution. If the report/request already clearly establishes that every listed credit card was in the wallet, acknowledge that and offer replacement rather than asking a redundant question. If the customer declines, note that the offer was made when an account-note mechanism is available.
   - If the customer asks to freeze credit cards, explain that this Skill provides the documented debit-card freezes and the required credit-card replacement/protection offer; it has no documented credit-card-freeze action. Do not describe a replacement offer, transfer, or account lookup as a completed credit-card freeze. Use a credit-card action only if a separately supported, confirmed procedure is available.

7. **Handle a post-freeze closure or replacement request, if one occurs.**
   - A confirmed stolen card merits permanent closure only through the documented closure workflow and only when its current status/transaction/refund eligibility is satisfied. A frozen card is not listed as eligible for `close_debit_card_4721`; do not unfreeze it solely to attempt closure.
   - A debit-card replacement requires a separately supported ordering procedure. If unavailable, report that no replacement is ordered and escalate the confirmed stolen-card request.

8. **Give an accurate completion summary.**
   - Separate successful debit freezes, cards that were already frozen/not active, unresolved cards, and the credit-card protection offer. For an unresolved stolen-wallet request, explicitly state that it was escalated as a fraud/security concern. Reiterate the effects of a debit freeze and how to unfreeze.
   - Never say that “all cards” or all requested cards are protected unless every individual supported action has an explicit success result. If an account-ID limitation blocks lookup, say which requested debit-card accounts remain unprotected and that the transfer is for immediate resolution.

## Planner script

Run the planner after card lookup, for example:

```bash
python3 scripts/plan_debit_freezes.py <<'JSON'
{"verified_user_id":"<user-id>","requested_account_ids":["<checking-account-id>"],"cards":[{"card_id":"<card-id>","account_id":"<checking-account-id>","user_id":"<user-id>","status":"ACTIVE"}]}
JSON
```

The planner reads one JSON object from standard input and emits one JSON object to standard output. Required input fields are `verified_user_id`, `requested_account_ids`, and `cards`. Each card should include `card_id`, `account_id`, `user_id`, and `status`. Output contains `freeze_actions` (safe recommendations only, not executed bank actions), `ineligible_cards`, `out_of_scope_cards`, and `validation_errors`.

Validate the plan before using it: there must be no validation errors, every freeze action must refer to a unique nonblank card ID, and every action must have a card owned by the verified user in a requested account with exact `ACTIVE` status. The planner intentionally emits no actions when malformed or duplicate lookup data is detected. The executor must still perform and inspect the actual banking tool calls.
