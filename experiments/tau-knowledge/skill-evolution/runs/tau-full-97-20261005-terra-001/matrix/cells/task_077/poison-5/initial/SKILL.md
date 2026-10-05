---
name: secure-lost-wallet-card-protection
description: Securely freeze debit cards that a verified customer has temporarily misplaced and, when a lost or stolen wallet also contained a Rho-Bank credit card, offer and process an approved replacement credit-card order. Use for lost-wallet or temporary debit-card-security requests; do not use it to reactivate cards reported stolen or permanently closed.
---

# Secure Lost-Wallet Card Protection

Use this workflow when a customer is looking for a debit card or wallet and requests a temporary freeze, including when the wallet may also contain a Rho-Bank credit card. A freeze is reversible; a closure is permanent. If the customer confirms a debit card is lost or stolen rather than merely misplaced, recommend closure rather than freezing and follow the debit-card closure procedure.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Runtime inputs and tool results

Work from the current conversation plus current runtime tool results. Never use identifiers, addresses, card details, or approvals from another customer or prior task.

Relevant normal banking tools documented for this workflow are:

- `get_all_user_accounts_by_user_id_3847(user_id)`
- `get_debit_cards_by_account_id_7823(account_id)`
- `freeze_debit_card_3892(card_id)`
- `get_credit_card_accounts_by_user(user_id)`
- `unlock_discoverable_agent_tool(agent_tool_name="order_replacement_credit_card_7291")`
- `call_discoverable_agent_tool(agent_tool_name="order_replacement_credit_card_7291", arguments=...)`
- `get_current_time()` and `log_verification(...)`

Use the runtime's normal banking-tool access for the documented debit-card and account lookups/actions. If the runtime exposes a documented tool through a discoverable-tool wrapper, comply with that wrapper's required unlock/call sequence; do not replace the documented action with a different tool.

## Procedure

### 1. Establish and record verification before any action

1. Locate the customer profile using customer-provided identifying information.
2. Match at least two of the four profile fields: date of birth, email, phone number, and address. A supplied name alone is not sufficient.
3. Obtain the current timestamp with `get_current_time` and call `log_verification` with the complete matched profile record and that timestamp.
4. Ensure the caller is the owner: later card lookups must show the same `user_id` as the verified profile. Stop if identity or ownership cannot be established.

Do not treat a previously displayed profile or a customer assertion as a substitute for verification logging during the current workflow.

### 2. Identify only the debit cards the customer requested

1. Call `get_all_user_accounts_by_user_id_3847` using the verified `user_id`.
2. Identify the requested checking accounts from the returned account information. Do not infer an account identifier from a nickname if the returned record does not establish the match.
3. For each identified checking account, call `get_debit_cards_by_account_id_7823`.
4. For every candidate card, verify all of the following before freezing it:
   - its `account_id` is one of the requested checking accounts;
   - its `user_id` equals the verified customer `user_id`;
   - its status is exactly `ACTIVE`; and
   - it is the card the customer intended to protect, using returned card details such as the last four digits if clarification is necessary.

A lookup can return old, closed, pending, or frozen card history. Do not freeze those cards. If there is more than one active card for a requested account and the request does not uniquely identify one, ask the customer to identify the card before acting. If a card is already frozen, explain that it is already protected; do not call the freeze tool again.

### 3. Disclose freeze effects and perform each eligible freeze

Before calling the action, explain that:

- new transactions and recurring payments/subscriptions will be declined while the card is frozen;
- already-authorized pending transactions may still process;
- the card can be unfrozen later through customer service or the mobile app; and
- freezing does not block ATM access for someone with the PIN; an ATM Block must be enabled separately in the mobile app.

The customer's explicit request to freeze the identified cards is the required action confirmation. Then call `freeze_debit_card_3892(card_id)` once for each eligible, verified `ACTIVE` card. Treat each result independently. Confirm only cards for which the tool reports success; if a call fails, state that the card was not confirmed frozen and follow the returned error or escalate when appropriate.

For a temporarily misplaced card, do not close it merely because it was frozen. If the customer later confirms it is lost or stolen, recommend permanent closure because a closed card cannot be reactivated.

### 4. Apply the lost/stolen-wallet cross-product check

For a lost or stolen debit-card/wallet report, after protecting the eligible debit card(s), call `get_credit_card_accounts_by_user` for the verified user. If Rho-Bank credit cards exist, ask whether any were also in the wallet and proactively offer replacement protection. Explain that a replacement gives the customer a new card number and the old credit card will be cancelled.

Do not order a replacement merely because a card account exists. Obtain a clear replacement request and confirm which eligible credit-card account is affected.

### 5. Order an approved credit-card replacement

Before ordering, verify and record:

- verified customer identity and ownership of the selected credit-card account;
- current credit-card account lookup and replacement eligibility under the available knowledge base;
- exact replacement reason, one of `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`;
- confirmed shipping address, including unit or suite details where applicable;
- customer-selected shipping speed; and
- fee disclosure and acknowledgement if expedited shipping has a tier fee.

For standard delivery, disclose 7–10 business days and no fee. For expedited delivery, disclose 2–3 business days and determine the tier-specific fee before obtaining the required acknowledgement. Do not invent an eligibility rule, available-credit threshold, fee, cutoff, or limit that is not supplied by the available policy or tool result; if a required prerequisite cannot be checked, do not submit the order.

Only after all prerequisites are satisfied:

1. Call `unlock_discoverable_agent_tool` with `agent_tool_name` set to `order_replacement_credit_card_7291`.
2. Call `call_discoverable_agent_tool` with the same tool name. Supply a JSON arguments object containing the selected credit-card account identifier (or card identifier returned by the account lookup), `reason`, `shipping_address`, `shipping_speed`, any required `expedited_fee_acknowledgement`, and relevant `notes`.

For a standard shipment, do not claim an expedited-fee acknowledgement is needed. Notes should accurately state the reported lost/stolen-wallet context without adding unsupported allegations.

### 6. Finish and document accurately

Report the actual outcome of each debit freeze separately from the credit-card replacement result. For a successful credit-card order, state that the prior card is cancelled for new purchases, provide the selected delivery window, and advise the customer to watch for order and shipment emails. For suspected fraud or theft, remind the customer to review transactions and dispute unauthorized charges as appropriate.

Document the verified identity record, ownership checks, selected cards/accounts, card status checks, customer confirmations, freeze results, replacement reason, shipping selection/address confirmation, fee acknowledgement when applicable, and order result. Record unavailable/non-applicable control items rather than fabricating them.

## Optional deterministic preflight helper

`scripts/workflow_guard.py` checks structured facts already obtained at runtime. It does not access banking systems and does not perform, authorize, or simulate a banking action.

It reads one JSON object from stdin and writes one JSON object to stdout. Expected fields are:

- `user_id` and `verified_fields`: the verified profile identifier and a list containing the matched field names;
- `requested_account_ids`: the checking account IDs the customer identified;
- `accounts`: account lookup records with at least `account_id` and `account_type` when available;
- `debit_cards`: debit-card lookup records with `card_id`, `account_id`, `user_id`, and `status`;
- optional `credit_replacement`: an object with `requested`, `account_user_id`, `account_status`, `eligibility_confirmed`, `reason`, `shipping_address_confirmed`, `shipping_speed`, and, for a fee-bearing expedited selection, `expedited_fee_acknowledged`.

Example invocation pattern: pass the current lookup values as a JSON object to `scripts/workflow_guard.py`; use its `freeze_card_ids`, `blockers`, and `credit_order_ready` fields as a preflight checklist. The executor must still make the required runtime lookups, disclosures, verification log, and banking-tool calls.

Validation result meanings:

- `freeze_card_ids` contains only requested, owned `ACTIVE` debit cards associated with a returned checking account.
- `blockers` explains missing verification, ambiguous/mismatched records, or cards that cannot be frozen.
- `credit_order_ready` is true only for an explicitly requested, active, owned, eligibility-confirmed replacement with valid shipping prerequisites.
