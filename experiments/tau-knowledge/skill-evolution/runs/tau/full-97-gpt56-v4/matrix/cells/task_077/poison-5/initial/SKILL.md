---
name: temporarily-freeze-multiple-debit-cards
version: 1.0.0
description: Safely locate and temporarily freeze debit cards for a verified customer who has misplaced a wallet or needs short-term protection, including account/card selection, eligibility checks, confirmation, and the required lost-wallet credit-card security offer.
---

# Temporarily Freeze Multiple Debit Cards

Use this Skill when a verified customer asks to temporarily protect one or more debit cards, especially after misplacing a wallet. A freeze is temporary and reversible; it is not the correct action when the customer confirms that a card is lost or stolen and wants permanent deactivation.

Do not use this workflow to close a card. If the customer confirms a card is lost/stolen or requests cancellation, explain the difference and follow the debit-card closure workflow instead.

## Required controls before a banking action

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For a debit-card freeze, apply those controls as follows:

- **Identity and authority:** verify the requesting customer against the profile using at least two of date of birth, email, phone number, and address, then create the required verification audit record.
- **Ownership:** confirm every selected card's `user_id` is the verified customer's `user_id`; only use accounts returned for that same user.
- **Product eligibility and card details:** identify the intended checking accounts and their cards; verify that each selected card is currently `ACTIVE`. The required product state for freezing is the card's `ACTIVE` status. Do not impose the separate unfreeze requirement that the checking account be open.
- **Available balance/credit, fees, limits, cutoffs, and recipient:** review account/card information returned by the normal lookup tools. These items do not alter the documented eligibility of a temporary debit-card freeze; no recipient, transfer cutoff, freeze fee, or balance threshold is specified by this workflow. Do not invent one.
- **Confirmation requirements:** the customer must be asking for temporary protection rather than permanent closure. Before performing the freeze, give the required effects disclosure below. If their request is ambiguous between freeze and closure, obtain a clear choice.

Never freeze a card merely because it appears in the customer's history. Select only the card(s) tied to the checking account(s) the customer named. If an account label is ambiguous, multiple active cards exist for one intended account, or ownership/status cannot be established, ask the customer for an identifying detail rather than guessing.

## Runtime tool workflow

Tool invocations are normal banking actions and must be performed by the executor using the declared banking tools. This Skill does not itself perform actions.

### 1. Determine the requested protection type

1. Listen for language such as “misplaced,” “might have lost,” “looking for it,” or “temporary protection.” These support a temporary freeze.
2. If the customer reports confirmed loss/theft or asks for irreversible cancellation, do not substitute a freeze without clarification. Route to the closure procedure.
3. If the customer asks to protect multiple cards but has not supplied identifiers, tell them that their verified profile and checking accounts can be used to locate eligible cards; do not require wallet information that they do not have.

### 2. Verify and audit identity

1. Obtain a profile locator (for example, name or email) and use the applicable user lookup tool.
2. Compare at least two customer-supplied identity fields with the returned profile: date of birth, email, phone number, and/or address. A mere name match is not enough.
3. Obtain the current timestamp using `get_current_time`.
4. After successful comparison, call `log_verification` exactly with the returned profile fields (`name`, `user_id`, `address`, `email`, `phone_number`, and `date_of_birth`) and the timestamp as `time_verified`.
5. If any supplied factor conflicts with the profile, if fewer than two factors match, or if the lookup is not unique, do not look up or freeze cards. Resolve identity first or use the appropriate human handoff when resolution is unavailable.

### 3. Locate the intended checking accounts

1. Unlock `get_all_user_accounts_by_user_id_3847` using `unlock_discoverable_agent_tool` and call it through `call_discoverable_agent_tool` with the verified `user_id`.
2. Inspect all returned accounts. Select only checking accounts whose returned type/class/display designation exactly corresponds to the customer-provided account names or other unambiguous descriptors.
3. Confirm the selected accounts belong to the verified customer through the user-scoped lookup and returned account details. Review the returned account status and balance as part of the prerequisite review.
4. If the named account designation is not present, is duplicated, is not a checking account, or cannot be mapped confidently to one account ID, stop and ask a focused clarification. Do not select by order, balance, or an assumed color/name mapping.

### 4. Locate and validate debit cards

For each selected checking `account_id`:

1. Unlock `get_debit_cards_by_account_id_7823` and call it with that `account_id`.
2. Match returned cards to the linked `account_id` and verify that each selected card has `user_id` equal to the verified user.
3. Select the intended `ACTIVE` card. Cards in `PENDING`, `FROZEN`, or `CLOSED` status are not eligible to be frozen.
4. When the request concerns one card per named checking account, exactly one active card associated with each account is sufficient. If an account has multiple active cards, present safe non-sensitive distinguishing details such as last four digits and ask the customer which card to freeze.
5. If a requested card is already `FROZEN`, do not call the freeze tool again; explain that it is already protected. If it is not `ACTIVE`, explain the status-specific reason that no freeze can be performed.

### 5. Give the freeze disclosure and proceed

Before the first mutation, tell the customer:

- All new transactions will be declined while each card is frozen.
- Recurring payments and subscriptions will also be declined.
- Pending transactions that were already authorized may still process.
- The card can be unfrozen at any time through customer service or the mobile app.
- Freezing does not affect ATM access when the customer has their PIN; ATM blocking, if desired, must be enabled separately in the mobile app.

Where the customer has clearly requested temporary protection, this disclosure completes the required explanation and the executor may proceed. If the customer expresses uncertainty after the disclosure or has not chosen between freeze and closure, obtain explicit confirmation before mutation.

For each independently eligible, selected card:

1. Unlock `freeze_debit_card_3892`.
2. Call it through `call_discoverable_agent_tool` with the single required `card_id` argument.
3. Treat a successful tool result as the authoritative confirmation. Do not claim a freeze based only on intent.
4. If the tool reports failure, leave that card unconfirmed, explain the failure without fabricating a result, and use an appropriate human handoff for a technical/system problem if it cannot be resolved safely.
5. If the outcome of a mutating tool call is `UNKNOWN`, do **not** repeat it. Preserve the uncertainty and escalate/hand off so the card state can be determined safely.

Process each card separately so that one ineligible or failed card does not cause an unsafe action on another. Never use a script recommendation as a banking action.

### 6. Required lost-wallet cross-product security check

For a customer reporting a lost or stolen wallet/card, call `get_credit_card_accounts_by_user` with the verified `user_id` after identity verification. This is a lookup, not permission to change a credit card.

If one or more credit-card accounts exist, proactively tell the customer that a Rho-Bank credit card is on file, ask whether it was also in the missing wallet, and offer a replacement credit card with a new number as a security precaution. Explain that a lost wallet can expose multiple cards. Do not order a replacement unless the customer separately agrees and the applicable replacement workflow's prerequisites are met. If no credit-card account exists, do not make a false offer.

## Customer-facing completion

For every successfully frozen card, confirm only the safe identifying detail (for example, the last four digits or the associated named account), state that it is now frozen, and restate that new and recurring transactions will be declined while pending authorized transactions may still settle.

Clearly distinguish results for each requested card:

- **Frozen:** confirm success and how to unfreeze.
- **Already frozen:** confirm its existing protected state; no duplicate action was made.
- **Not frozen:** state the specific safe reason, such as non-active status, ambiguous selection, failed eligibility, or tool failure, and what information or follow-up is needed.

Do not disclose full card numbers, internal IDs, unrelated account details, or other customers' information. Do not state that a credit-card replacement was ordered unless it was separately authorized and successfully completed.

## Failure and escalation rules

- Do not freeze without a logged successful verification and verified card ownership.
- Do not attempt to freeze `PENDING`, `FROZEN`, or `CLOSED` cards.
- Do not convert a temporary-protection request into an irreversible closure.
- If a required lookup fails, produces ambiguous ownership/account selection, or the mutation result is unknown, do not guess or retry a potentially completed mutation.
- Use `transfer_to_human_agents` with `technical_system_error` for unresolved tool/system failures; use `fraud_or_security_concern` when the customer reports active fraud/security risk that cannot be safely completed through this workflow. Include the verification state, non-sensitive card/account context, attempted lookup/action, and known result in the summary.

## Tool interface reference

The executor uses the declared runtime interfaces, not local scripts:

- `get_current_time()` → timestamp for the verification record.
- Profile lookup by supplied customer identifier → authoritative profile and `user_id`.
- `log_verification(profile fields, time_verified)` → audit record after two matching identity factors.
- `get_all_user_accounts_by_user_id_3847(user_id)` → user accounts including account ID, type/class, status, and balance.
- `get_debit_cards_by_account_id_7823(account_id)` → cards including card ID, account ID, user ID, last four digits, and status.
- `freeze_debit_card_3892(card_id)` → temporary debit-card freeze.
- `get_credit_card_accounts_by_user(user_id)` → required lost/stolen-wallet cross-product check.

Discoverable agent tools must be unlocked before they are called. Pass JSON arguments matching the named parameter exactly, and preserve successful/failed tool responses in the execution record.
