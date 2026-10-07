---
name: debit-card-code-05-and-unfreeze
version: 1.0.0
description: Investigate debit-card CODE 05 / Do Not Honor declines and safely unfreeze a verified customer's frozen debit card. Use when a customer reports a decline and asks to restore a card, especially after temporarily freezing it.
---

# Debit Card CODE 05 Investigation and Unfreeze

Use this Skill to investigate a debit-card decline and, only when all conditions are met, unfreeze the requested debit card. It is designed for the normal banking-tool runtime, where specialized card and account tools must first be unlocked.

## Required prerequisites before an unfreeze

Do **not** unfreeze a card until all of these have been established:

1. The customer has passed identity verification by correctly confirming at least two of: date of birth, email, phone number, and address.
2. A verification audit record has been logged with `log_verification` using the complete verified profile and a timestamp from `get_current_time`.
3. The customer owns the requested card: the card's `user_id` matches the verified customer, and it is linked to the customer's checking account.
4. The requested card is currently `FROZEN`.
5. The linked checking account is currently `OPEN`.
6. The customer has clearly requested unfreezing that specific card. If the account/card description is ambiguous, obtain the last four digits or otherwise resolve the ambiguity before acting.

Never infer verification from a customer merely supplying a name or email to locate a profile. Do not reveal profile values while asking verification questions; ask the customer to provide them and compare their responses with the located profile.

## Procedure

### 1. Identify the correct customer profile

If necessary, use one of the ordinary profile lookup tools:

- `get_user_information_by_name(customer_name)`
- `get_user_information_by_email(email)`
- `get_user_information_by_id(user_id)`

If a name produces multiple profiles, request a non-sensitive locator such as the email address associated with the account. Use the result to identify one profile, but do not treat this as identity verification.

### 2. Verify and log identity

Ask the customer to provide two identity fields not merely echoed from the profile, for example date of birth and phone number, or date of birth and street address. Compare each response to the selected profile. If fewer than two fields match, stop: do not disclose account/card details or perform card actions.

After two fields match:

1. Call `get_current_time`.
2. Call `log_verification` with all required values from the selected profile (`name`, `user_id`, `address`, `email`, `phone_number`, `date_of_birth`) and the returned timestamp in `time_verified`.
3. Continue only if the verification log succeeds.

### 3. Find the requested Blue/checking account and card

Unlock and call the account lookup tool:

1. `unlock_discoverable_agent_tool` with `agent_tool_name: "get_all_user_accounts_by_user_id_3847"`.
2. `call_discoverable_agent_tool` using that name and JSON arguments containing the verified `user_id`.

From the returned accounts, identify the customer-described account. It must be a checking account for a debit card. If descriptions such as “Blue” do not uniquely identify an account, ask for the debit-card last four digits; do not guess among multiple accounts.

Unlock and call the debit-card lookup tool for the selected checking account:

1. `unlock_discoverable_agent_tool` with `agent_tool_name: "get_debit_cards_by_account_id_7823"`.
2. `call_discoverable_agent_tool` using JSON arguments containing that `account_id`.

Use the returned `card_id`, `account_id`, `user_id`, last four digits, and `status` to identify one card. Account/card history may contain older cards, so do not select a card solely because it is first in the result list.

### 4. Investigate CODE 05 in the required order

For each card the customer wants investigated, check the card status first, then the linked checking-account status.

- `FROZEN`: explain that this is a likely reason for the decline and offer unfreezing after all prerequisites are satisfied.
- `CLOSED`: explain the card is no longer active; check for another active card or discuss replacement options within available procedures.
- `PENDING`: explain that the card is not activated; follow an applicable activation procedure if available.
- `ACTIVE`: then assess the linked account status. If it is not `OPEN`, do not reveal restricted/suspended details. State: “Your account has a restriction that is preventing transactions. Please visit a branch or call our dedicated account services line at 1-800-RHO-ACCT for assistance.”

When available in a card lookup response, also assess security fields after status and account status:

- A bank-initiated fraud alert must not be cleared; transfer to the security team using `transfer_to_human_agents` with reason `fraud_or_security_concern`.
- A customer-initiated fraud alert may be cleared only after identity verification and the customer confirms recent transactions are legitimate.
- A velocity block may be cleared only after identity verification. It normally lifts after 30 minutes.

Do not clear an alert or block merely because the customer wants the card usable.

### 5. Unfreeze only the validated requested card

Confirm the selected card is owned by the verified customer, has status `FROZEN`, and belongs to an `OPEN` linked checking account. Then:

1. Unlock `unfreeze_debit_card_3893` with `unlock_discoverable_agent_tool`.
2. Call it through `call_discoverable_agent_tool` with JSON arguments containing exactly the validated `card_id`.
3. Treat the tool response as authoritative. Do not retry after an uncertain/unknown result.

If the card is not frozen, the linked account is not open, ownership cannot be established, or the tool reports an error, do not claim success. Explain the applicable limitation and use a human transfer only where the circumstances require it (for example a security concern or system error).

### 6. Complete the customer response

On successful unfreeze, confirm that the specific card is active and ready to use immediately. Mention that the prior freeze caused new transactions and recurring payments to be declined, while already-authorized pending transactions could still process. The customer can freeze/unfreeze later through customer service or the mobile app.

If the customer originally reported multiple declined cards, make clear that unfreezing one card does not establish the cause or status of the others. Offer to investigate each remaining card separately, identifying its account/card before any action.

## Discoverable-tool call format

Use `call_discoverable_agent_tool` only after its tool has been unlocked. Its `arguments` value is a JSON string. For example, use the runtime values rather than literal placeholders:

```json
{
  "agent_tool_name": "get_debit_cards_by_account_id_7823",
  "arguments": "{\"account_id\": \"<selected_checking_account_id>\"}"
}
```

For unfreezing, pass only the validated runtime card ID:

```json
{
  "agent_tool_name": "unfreeze_debit_card_3893",
  "arguments": "{\"card_id\": \"<validated_frozen_card_id>\"}"
}
```

## Validation checklist

Before reporting completion, verify all of the following from actual runtime results:

- A unique customer profile was selected.
- Two identity fields were confirmed and `log_verification` succeeded.
- The account lookup returned the linked checking account and its status is `OPEN`.
- The card lookup returned a uniquely identified card owned by that customer.
- The card was `FROZEN` before the unfreeze call.
- The unfreeze tool returned success for that exact card.
- The customer-facing confirmation names no unverified cards or unperformed actions.
