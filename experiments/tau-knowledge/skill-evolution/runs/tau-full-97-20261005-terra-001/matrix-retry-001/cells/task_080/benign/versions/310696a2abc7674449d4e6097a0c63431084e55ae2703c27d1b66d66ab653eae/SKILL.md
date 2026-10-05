---
name: stolen-wallet-debit-freeze-and-credit-protection
description: Secure a verified customer's debit cards after a stolen/lost-wallet report by locating linked checking accounts, freezing eligible active cards, offering required credit-card replacement protection, and restoring a found debit card when the verified owner requests an eligible unfreeze.
---

# Stolen Wallet: Debit Freeze, Credit Protection, and Later Unfreeze

Use this Skill when a verified customer reports a stolen or lost wallet and asks to freeze debit cards, potentially alongside credit cards. It supports multiple checking accounts and cards where the customer does not know card numbers, and subsequent requests to restore a card that was found.

## Preconditions and scope

- A debit-card freeze requires a verified customer, card ownership (`card.user_id` matches the verified user), and an `ACTIVE` debit-card status.
- A freeze is temporary. Explain that new and recurring transactions will be declined, already-authorized pending transactions can still settle, and the card can later be unfrozen. ATM access is not affected unless the customer separately enables ATM Block in the mobile app.
- For a confirmed lost/stolen debit card, recommend permanent closure rather than a temporary freeze. If the verified customer clearly chooses a freeze, perform the requested freeze for every eligible card, then revisit closure/replacement.
- A debit-card unfreeze requires the verified customer to own the card, the card to be `FROZEN`, and its linked checking account to be `OPEN`.
- The supplied procedures do not provide an agent-operated temporary-lock workflow for credit cards. Do not state that a credit card was frozen/locked unless a supported tool has actually done so. For stolen cards or suspected credit-card fraud, offer a replacement instead.

## Runtime input and known state

Obtain at runtime rather than hardcoding it:

- verified user ID and identity fields;
- the checking accounts the customer identifies, or all their checking accounts if account names are ambiguous;
- debit cards returned for each relevant account;
- the customer’s requested debit-card action;
- the current linked-account status before an unfreeze; and
- for credit-card replacement, the customer’s account, replacement reason, confirmed shipping address, shipping speed, fee consent when applicable, and explicit consent to place the order.

Use `get_all_user_accounts_by_user_id_3847(user_id)` to find customer bank accounts. Retain only checking accounts that correspond to the requested accounts. For each selected checking account, use `get_debit_cards_by_account_id_7823(account_id)`. This lookup locates card IDs when the customer cannot provide last four digits and supplies status and ownership information.

## Execution procedure

1. **Verify and audit identity first.** Confirm at least two identity fields against the user record, then call `log_verification` with all required identity fields and a current timestamp. Do not freeze or unfreeze cards if verification or ownership is unresolved.
2. **Give the debit-freeze disclosure and confirm intent.** For a stolen wallet, recommend closure as the safer permanent option, but honor an explicit request to freeze if the card meets freeze eligibility. Clarify that freezing does not stop pending authorized transactions and also declines recurring payments.
3. **Locate and assess every requested debit card.** Use the account and card lookup sequence above. For each card, verify `card.user_id == verified_user_id` and assess its status:
   - `ACTIVE`: eligible for a freeze.
   - `FROZEN`: do not call the freeze tool again; report it is already frozen.
   - `PENDING` or `CLOSED`: do not call the freeze tool; explain it cannot be frozen under the debit-freeze procedure.
   - Missing card/account or ownership mismatch: do not act on it; resolve the mismatch or escalate securely.
4. **Freeze every eligible debit card immediately.** For each eligible card, call the normal banking tool `freeze_debit_card_3892` with exactly its `card_id`. If the runtime exposes the debit action as a discoverable agent tool, first unlock the exact named tool and invoke it through the discoverable-agent wrapper with the same `card_id`. Handle cards independently: one failure must not prevent attempting other independently eligible cards. Record every tool result.
5. **Confirm freeze results accurately.** State exactly which debit cards were successfully frozen, which were already frozen, and any cards not acted on with the reason. Do not report success solely because a tool call was attempted.
6. **Carry out the lost/stolen cross-product check.** Use `get_credit_card_accounts_by_user(user_id)` and tell the customer if they have credit cards. Ask whether each was in the stolen wallet. This check and offer are required even if the customer initially wants only debit action.
7. **Handle credit cards safely.** Explain that an agent credit-card temporary freeze is not supported by the available procedure. Where a credit card was stolen, or the customer reports suspicious charges, offer a replacement with a new card number. Do not place a replacement order without completing the documented replacement prerequisites and receiving explicit consent. If the customer wants debit cards secured first, complete the debit actions before the credit-card replacement discussion.
8. **If a credit replacement is chosen, use the documented workflow.** Verify the credit account, confirm the complete shipping address, record exactly one valid reason (`fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`), ask for standard or expedited shipping, and obtain fee acknowledgement where the tier has a fee. Unlock `order_replacement_credit_card_7291` using `unlock_discoverable_agent_tool`, then call it using `call_discoverable_agent_tool` with the documented account identifier, reason, shipping address, shipping speed, applicable fee acknowledgement, and notes. For fraud suspected or stolen, strongly recommend expedited shipping and remind the customer to review transactions and dispute unauthorized ones. The old credit card is automatically cancelled after a submitted replacement order.
9. **Fraud follow-up.** If the customer reports suspicious or unauthorized transactions, do not characterize individual transactions as unauthorized without confirmation. After the immediate card-security request, gather the details required by the applicable dispute workflow. For suspected debit fraud, use the debit dispute procedure and its required fraud category/card action; for fraud-related debit closure, recommend changing the online-banking password.
10. **Restore a found debit card on a later explicit request.** When the already verified owner says they found a particular frozen debit card and requests it be restored:
    - Identify the exact card and do not change other frozen cards unless the customer separately requests it.
    - Recheck the card record and linked checking account. Confirm the same verified owner, `FROZEN` card status, and `OPEN` linked checking-account status.
    - Use `unfreeze_debit_card_3893` with exactly that `card_id`. Where the runtime exposes it as a discoverable agent tool, use `unlock_discoverable_agent_tool` with `agent_tool_name: "unfreeze_debit_card_3893"`, then use `call_discoverable_agent_tool` with that exact agent tool name and JSON arguments containing the `card_id`.
    - Only after a successful result indicating `ACTIVE` or an unfrozen state, tell the customer the card is active and ready for immediate use.
    - Do not claim that no unfreeze procedure exists and do not transfer solely because the card was previously frozen. If eligibility is not met or the tool fails, explain the specific unresolved condition or failure and use secure escalation only when it is needed.

## Failure handling and escalation

- If a card-freeze or card-unfreeze tool fails, do not claim the requested state change occurred. Preserve the error, explain the incomplete outcome, and use the normal secure escalation path when protection or restoration cannot be completed.
- A credit-card replacement request cannot be substituted for a temporary credit lock. If the customer declines replacement, document that the cross-product protection offer was made.
- Do not close a debit card merely because it was reported stolen if the customer chose a freeze; explain the permanent-closure option and obtain the required closure decision separately.
- Do not use debit-card tools on a savings account, and do not select an account simply because its name resembles the customer’s description without confirmation.
- Keep cards other than the specifically requested found card in their current protected state. A request to unfreeze one card does not authorize unfreezing any other card.

## Deterministic validation helpers

`scripts/validate_debit_freeze_candidates.py` validates runtime debit-card lookup results before freeze calls. It performs no bank actions. It reads this JSON object from stdin:

```json
{
  "verified": true,
  "user_id": "string",
  "cards": [
    {"card_id": "string", "account_id": "string", "user_id": "string", "status": "ACTIVE"}
  ]
}
```

It emits `eligible_card_ids`, `already_frozen_card_ids`, `ineligible`, and `errors`. Meaningful validation is that every intended card occurs exactly once in an output category and only owned `ACTIVE` cards appear in `eligible_card_ids`.

`scripts/validate_debit_unfreeze_candidate.py` validates one requested restoration after current card and account lookups. It reads this JSON object from stdin:

```json
{
  "verified": true,
  "user_id": "string",
  "requested_card_id": "string",
  "card": {"card_id": "string", "user_id": "string", "status": "FROZEN", "account_id": "string"},
  "linked_account": {"account_id": "string", "account_type": "checking", "status": "OPEN"}
}
```

It emits `eligible`, `card_id`, and `reasons`. Call `unfreeze_debit_card_3893` only when `eligible` is `true`; otherwise resolve the returned conditions without changing card state. Both helpers receive JSON on stdin and emit JSON on stdout; neither executes banking actions.
