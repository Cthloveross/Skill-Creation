---
name: lost-stolen-card-security-escalation
version: 1.0.0
description: Handle a verified customer's lost or stolen debit-card report when they request a temporary freeze and/or a human agent. Use this for debit-card eligibility checks, required freeze disclosures, cross-product credit-card protection, and priority security escalation.
---

# Lost/Stolen Card Security Escalation

Use this workflow for a customer who reports that a debit card or wallet is lost or stolen, particularly when they request a debit-card freeze, report other cards at risk, or ask to speak to a human.

## Safety and prerequisite controls

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

1. Treat the report as a security concern. Do not reveal full card numbers or use an unverified identity to locate or change products.
2. Verify the customer using at least two identity fields from the profile (date of birth, email, phone, or address). Match supplied values to a single retrieved user record.
3. Get the current timestamp with `get_current_time`, then record a successful verification with `log_verification`, supplying all required profile fields and the retrieved timestamp. Do this before card actions or an escalation that depends on the customer's account details.
4. Confirm the customer is the cardholder by comparing each debit card's `user_id` with the verified user ID. Never act on a card belonging to another user.
5. If identity, ownership, or a required prerequisite cannot be confirmed, do not freeze or close the card. Escalate the unresolved security issue to a human with the most applicable reason.

## Decide between immediate escalation and card processing

A lost/stolen report is a `fraud_or_security_concern`, which is a Tier 1 transfer reason. It takes priority over a merely general request for a human or general frustration.

- If the customer asks for a human agent in connection with a lost/stolen card, promptly call `transfer_to_human_agents` with `reason: "fraud_or_security_concern"` after verification. Do not delay the requested escalation to pursue optional product actions.
- Put the verified customer ID (if appropriate), reported affected products, requested temporary freeze, identity-verification status, and any completed/blocked actions in the transfer summary. State that the report involves lost/stolen cards so the human agent can continue security handling.
- A transfer is not evidence that cards were frozen. Do not claim a freeze, closure, replacement, fraud dispute, or credit-card block occurred unless the corresponding banking tool reported success.
- If the customer does not request escalation, or explicitly wants the automated agent to continue, follow the debit-card workflow below.

## Debit-card temporary-freeze workflow

A freeze is temporary; it is not a closure. Use it when the customer wants short-term protection or is unsure whether the card is permanently lost. If the customer confirms the card is lost or stolen and wants permanent deactivation, explain that closure is irreversible and use the separate closure process rather than a freeze.

1. Ask for or identify the checking account(s) containing the debit cards. Retrieve the account's debit cards with `get_debit_cards_by_account_id_7823(account_id)`.
2. For each requested debit card, validate that it exists, belongs to the verified user, and is currently `ACTIVE`.
   - Do not freeze cards that are `PENDING`, `CLOSED`, or already `FROZEN`.
   - If the customer names several accounts, check every identified account independently; do not assume cards on one account represent all cards.
3. Obtain and record the customer's reason for the freeze. A lost/stolen wallet is an acceptable security reason.
4. Before freezing, tell the customer:
   - all new transactions will be declined while the card is frozen;
   - recurring payments and subscriptions will also be declined;
   - pending transactions already authorized may still process; and
   - the card can be unfrozen later through customer service or the mobile app.
5. Unlock `freeze_debit_card_3892` using `unlock_discoverable_agent_tool`, then call it through `call_discoverable_agent_tool` with the eligible `card_id` as documented by the unlocked tool.
6. Handle each card independently and confirm only successful freezes. Report cards skipped and the reason. Freezing does not affect ATM access for a customer with the PIN; ATM blocking requires the customer to enable the separate ATM Block setting in the mobile app.

## Lost/stolen cross-product protection

For every lost/stolen debit-card report, check the verified customer's credit-card accounts using `get_credit_card_accounts_by_user(user_id)`.

- If credit cards are found, tell the customer that wallet theft can affect multiple cards, ask whether each credit card was also in the wallet, and proactively offer a replacement card with a new number to reduce unauthorized-charge risk.
- Do not assert that a credit-card freeze, replacement, or closure was performed without a documented, available tool and successful result.
- If the customer has requested a human agent, include the credit-card findings and the need for this protection discussion in the transfer summary instead of making unsupported credit-card changes.
- If no credit cards are found, state only that no credit-card accounts were found for the verified user.

## Transfer call and user response

Use `transfer_to_human_agents` exactly once when escalation is selected. Use `fraud_or_security_concern` for a lost/stolen wallet or card; it outranks `customer_frustrated_demands_human` and `customer_requests_human_no_specific_reason`.

The summary should be factual and compact: verified status, lost/stolen report, debit accounts/cards identified or still needing review, completed freezes if any, credit-card accounts found, and the customer's request for human assistance. Do not include secrets beyond information needed for the handoff.

After the transfer reports success, tell the customer they are being connected to a human agent and summarize only actions confirmed by tool results. If a tool returns an error or an unknown outcome, do not retry an action whose outcome is unknown; disclose that it requires human review.

## Tool sequence examples

The executor invokes normal banking tools directly; no packaged script performs bank actions.

Typical requested-human sequence:

1. Retrieve/confirm profile fields, verify two fields, call `get_current_time`, and call `log_verification`.
2. Call `get_credit_card_accounts_by_user` when handling the lost/stolen cross-product requirement.
3. Call `transfer_to_human_agents` with `reason: "fraud_or_security_concern"` and an accurate handoff summary.

Typical automated debit-freeze sequence:

1. Complete verified-identity logging and retrieve debit cards for every requested checking account.
2. Make the mandatory freeze disclosures and validate each card is owned by the user and `ACTIVE`.
3. Unlock and call `freeze_debit_card_3892` once per eligible requested card.
4. Check credit-card accounts, offer the required protection, and accurately confirm results.

## Validation checklist

Before finalizing, verify that the recorded actions and customer-facing response satisfy all applicable items:

- Identity was matched to one user using two profile fields and `log_verification` succeeded before account-specific action.
- Every debit card acted on was retrieved from its account, belonged to that user, and was `ACTIVE`.
- Required freeze disclosures preceded every debit freeze.
- A temporary freeze was not described as closure or permanent deactivation.
- The lost/stolen report triggered a credit-card account check and protection offer or handoff note.
- A requested security escalation used `fraud_or_security_concern` and the summary did not overstate tool outcomes.
- No operation with an unknown outcome was repeated.
