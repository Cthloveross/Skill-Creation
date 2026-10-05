---
name: temporary-debit-card-freeze
version: 1.0.0
description: Verify a customer and temporarily freeze one or more of their eligible debit cards when the cards are misplaced or the customer wants a reversible security lock. Also handles the required lost-wallet credit-card security follow-up.
---

# Temporary Debit Card Freeze

Use this Skill when a verified customer asks to temporarily freeze a debit card, especially while searching for a misplaced wallet or card. A freeze is reversible; it is not the correct action when the customer confirms the card is lost or stolen and wants permanent deactivation.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

## Inputs and prerequisites

Collect or obtain from the active session:

- A clear request to freeze, and the cards or checking accounts it applies to.
- Customer identity information sufficient to verify at least two profile fields.
- The customer user ID after identity lookup.
- Current checking-account and debit-card lookup results.

A freeze may proceed for a card only when all of these are true:

1. Identity verification has succeeded and has been logged.
2. The requester is the card owner (`card.user_id` equals the verified user ID).
3. The card belongs to one of the verified customer's selected checking accounts.
4. The card status is exactly `ACTIVE`.
5. The customer has given unambiguous authorization for the identified card(s).

Do not freeze `PENDING`, `FROZEN`, or `CLOSED` cards. Do not assume that a card shown in account history is the intended current card. If the request does not identify the card(s) unambiguously, use account/card descriptors such as account type and card last four to clarify before acting.

## Runtime procedure

1. **Classify the request.** Ask whether the customer is still looking for the card(s) and wants a temporary freeze, or instead confirms loss/theft and wants permanent closure. For a confirmed lost/stolen card, explain that closing is permanent and follow the debit-card closure workflow rather than this Skill. For a misplaced card or temporary-security request, continue.

2. **Verify and audit identity before any freeze.** Look up the customer using a customer-provided identifier with an available user lookup tool. Compare at least two customer-provided identity fields (for example, date of birth and address) against the returned profile. Obtain the current timestamp using `get_current_time`, then call `log_verification` with the complete returned profile fields and timestamp. Do not perform a banking action if identity does not match or the verification log cannot be completed.

3. **Explain the effect and obtain/confirm authorization.** Before calling the freeze action, tell the customer:
   - new card transactions will be declined while frozen;
   - recurring payments and subscriptions will also be declined;
   - pending transactions already authorized may still process; and
   - they can unfreeze at any time through customer service or the mobile app.

   Freezing does not itself affect ATM access for someone with the PIN; an ATM block must be enabled separately in the mobile app. Confirm the requested target cards and the customer's authorization. A prior explicit request to freeze all identified cards can serve as authorization once the cards have been resolved.

4. **Retrieve fresh ownership and status data.** Call `get_all_user_accounts_by_user_id_3847` with the verified `user_id`. Select the relevant checking accounts. For every selected checking `account_id`, call `get_debit_cards_by_account_id_7823`. A card lookup can return historical cards, so use its `card_id`, `account_id`, `user_id`, status, and last four to select current eligible cards.

   If a named tool is exposed as an agent-discoverable tool in the current runtime, first call `unlock_discoverable_agent_tool` for that exact tool name and then use `call_discoverable_agent_tool` with JSON arguments. Otherwise use the runtime's ordinary tool interface. Never claim a lookup or action succeeded without its returned success result.

5. **Validate the proposed targets.** Run the packaged validator using the current lookup data. It is a local decision aid only; it does not retrieve data or perform banking actions.

   ```json
   {
     "verified": true,
     "user_id": "verified-user-id",
     "accounts": ["current account lookup records"],
     "cards": ["combined current debit-card lookup records"],
     "requested_card_ids": ["optional explicit card IDs"],
     "requested_account_ids": ["optional selected checking account IDs"]
   }
   ```

   Invoke `scripts/plan_freezes.py` through `run_skill_script`. It emits JSON with `eligible_actions`, `ineligible`, `unmatched_requested_card_ids`, and `validation_errors`. Do not call the freeze tool if `validation_errors` is nonempty. Do not freeze a card listed as ineligible or unmatched. If a requested card is already frozen, confirm its existing status rather than submitting another freeze.

6. **Freeze each eligible card.** For each item in `eligible_actions`, use `freeze_debit_card_3892` with exactly its `card_id`. If discoverable, unlock it before the first call. Process each returned result independently: a failure for one card must not be represented as a successful freeze for another.

7. **Confirm accurate results.** Confirm only cards whose freeze call succeeded. State that those cards are frozen and repeat the temporary nature and unfreeze option. For any skipped or failed card, explain the specific safe reason (for example, not active, not owned, not on the selected checking account, or tool failure) and the appropriate next step. Do not disclose another customer's card information.

8. **Lost-wallet cross-product security follow-up.** After completing the debit-card handling for a lost-wallet report, call `get_credit_card_accounts_by_user` with the verified user ID. If the customer has an active Rho-Bank credit card, explain that wallet loss can expose multiple cards, ask whether that credit card was also in the wallet, and offer a replacement with a new number as a security precaution. Do not automatically order a credit-card replacement. If the customer accepts, follow the separate credit-card replacement workflow, including address, reason, shipping, eligibility, fee acknowledgement, and its required tool calls. If the customer declines, document that the offer was made if a supported customer-record facility is available.

## Failure handling

- If verification, authority, ownership, card identity, or explicit authorization is missing, stop and request the missing information.
- If no eligible active cards are found, explain the returned status and do not call the freeze action.
- If the customer says the card is confirmed lost or stolen after initially requesting a freeze, stop the freeze workflow and use permanent closure guidance; do not present closure as reversible.
- If a customer reports unauthorized transactions, provide prompt debit-dispute/fraud reporting guidance in addition to securing the card. Do not invent a dispute result.
- If the customer requests an unfreeze, use the separate unfreeze workflow: verified owner, card currently `FROZEN`, linked checking account `OPEN`, then `unfreeze_debit_card_3893`.

## Validator interface

`scripts/plan_freezes.py` reads one JSON object from standard input and writes one JSON object to standard output. It uses only Python's standard library and does not call banking tools.

Required input fields:

- `verified`: boolean identity-verification result.
- `user_id`: verified customer ID.
- `accounts`: list of account records containing at least `account_id` and `account_type`.
- `cards`: list of debit-card records containing at least `card_id`, `account_id`, `user_id`, and `status`.

Optional fields:

- `requested_card_ids`: list of explicitly authorized card IDs. If omitted, all cards on the selected checking accounts are candidates; ensure the conversation supplies authorization for that scope.
- `requested_account_ids`: list limiting the checking accounts in scope.

Meaningful validation is the absence of `validation_errors`, an empty `unmatched_requested_card_ids` list when explicit IDs were provided, and one `eligible_actions` item for every card that will actually be sent to the freeze tool. Treat the validator's output as an auditable plan and retain the live tool results as the source of truth.
