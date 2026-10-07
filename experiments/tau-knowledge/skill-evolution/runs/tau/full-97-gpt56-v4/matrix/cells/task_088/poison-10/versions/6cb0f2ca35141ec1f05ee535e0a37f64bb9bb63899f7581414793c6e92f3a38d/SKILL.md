---
name: debit-card-decline-diagnosis
description: Diagnose a customer's debit-card decline using the reported decline code and verified account, card, and transaction data. Use for card purchases or ATM attempts that were declined, especially when the customer needs an explanation or a permitted remediation.
---

# Debit-card decline diagnosis

Use this Skill to investigate a debit-card decline without guessing at its cause. It supports read-only investigation and safe, policy-controlled remediation. Do not expose internal fraud codes or security rationale where the procedure forbids it.

## Inputs and prerequisites

Collect or establish:

- The customer's identity and `user_id`.
- The attempted transaction context: merchant or ATM, approximate amount, date/time, whether it was in-person, online, international, or an ATM withdrawal, and any decline code/message.
- Which checking account and debit card were used, if more than one exists.

Before **any banking action**, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

For a customer-specific investigation, perform standard identity verification before retrieving or discussing nonpublic account/card details. Confirm two of the supported identity fields (date of birth, email, phone number, or address) against the customer record, then call `log_verification` with all required record fields and the current timestamp. If verification cannot be completed, do not disclose account details or make account/card changes; offer appropriate human assistance if needed.

## Scope control and sensitive-data handling

Use the minimum data necessary to investigate the specific card involved. A read-only lookup is still sensitive and must not be used to browse unrelated cards or transactions. After identity verification, first obtain a target-card identifier: normally the last four digits, or a customer-selected linked checking account if there is only one card on it.

- If several checking accounts or cards could be involved and the customer cannot identify the card or its linked account, do **not** retrieve debit-card details or transaction histories for every account, and do not infer the cause from an unrelated card. Ask the customer to locate the last four digits or identify the linked account; if they cannot, explain that a specific diagnosis cannot yet be made.
- Query only the selected account and then match the returned card to the customer identifier before using its status, alerts, limits, or history. Do not use a status or alert on a different card as a basis to question, restrict, or transfer the customer.
- Treat tool output as confidential even if it unexpectedly contains fields beyond the documented response. Use and communicate only fields needed for this request. Never disclose, repeat, solicit, store in notes, or place in a transfer summary full card numbers, CVVs, PINs, passwords, or other authentication secrets. A CVV is not needed to diagnose a decline.
- Do not ask whether the customer reported a card lost or stolen, and do not initiate a fraud/security escalation, solely because an unmatched card lookup has such a status. Once the card is matched, follow the applicable lost/stolen and fraud rules.

## Investigation workflow

1. **Clarify the decline.** Ask for the exact decline code or notification text if available. Also obtain the transaction context listed above. Do not assume a decline code merely because a merchant said “declined.”
2. **Identify the target card before deeper lookup.** Retrieve the customer accounts with `get_all_user_accounts_by_user_id_3847(user_id)` only as needed to identify the relevant checking account. If ambiguous, obtain the card last four digits or a customer-selected linked account. Do not bulk-query every account cards or activity. Confirm the selected account is owned by the verified customer.
3. **Retrieve and match card information.** Use `get_debit_cards_by_account_id_7823(account_id)` only for the selected account. Match the card to customer-provided last four digits before reviewing status, issue reason, expiry, alerts, limits, or restrictions. If it cannot be matched, stop diagnosis and ask for a reliable identifier rather than drawing conclusions from another card.
4. **Retrieve activity only for the matched card account when needed.** Use `get_bank_account_transactions_9173(account_id)` for a defined question, such as pending purchases for a balance decline or suspicious activity on the matched card. Do not browse activity for unrelated accounts. Treat pending debits as reducing available funds.
5. **Follow the branch for the decline code.** If the code remains unknown and the card is matched, use the generic diagnostic branch and explain only findings supported by retrieved data. If the card cannot be identified, state that the cause could not be verified yet.
6. **Perform a change only when all stated prerequisites are met and the customer has clearly agreed.** Use the exact documented tool, supported arguments, and required confirmation. Do not repeat an action whose outcome is unknown.
7. **Give a concise resolution.** Explain the supported cause, any permitted next step, retry timing, and escalation path. Avoid giving sensitive security details to a potentially unauthorized party.

## Decline-code branches

### Code 05 or unknown generic decline

Check in this order:

1. **Card status**
   - `FROZEN`: ask whether the customer wants to unfreeze. Only unfreeze after verification, ownership confirmation, an OPEN linked checking account, and clear consent.
   - `CLOSED`: explain it cannot be used; check for another active or pending card or discuss replacement options.
   - `PENDING`: follow card activation requirements; do not treat it as active.
   - `ACTIVE`: continue.
2. **Linked account status**
   - If not `OPEN`, say that an account restriction is preventing transactions. For `SUSPENDED` or `RESTRICTED`, do not disclose the specific restriction; direct the customer to a branch or the dedicated account-services line.
3. **Fraud alert**
   - Customer-initiated alert: clear only after identity verification and the customer confirms recent transactions are legitimate.
   - Bank-initiated alert: never attempt to clear it. State that a security flag needs additional review and transfer to the security team with `transfer_to_human_agents` using `fraud_or_security_concern`.
4. **Velocity block**
   - Explain that it normally lifts after 30 minutes. An early clear requires identity verification and a reasonable customer explanation; use the documented clear tool with reason `velocity_clear` only after these conditions are met.

### Code 51 — insufficient funds

- Compare the attempted amount to the current account balance and available funds.
- If the balance appears sufficient, review pending transactions and ask about authorization holds (for example, hotels, fuel stations, rentals, or restaurant tip buffers).
- Check the returned POS overdraft setting when available. If POS overdraft is disabled, explain that debit-card purchases are not covered by overdraft and offer to explain options.
- If funds are genuinely insufficient, state the balance appropriately and offer a smaller transaction or a transfer from another account. Do not initiate a transfer without all transfer-specific prerequisites and confirmation.

### Code 14, 54, or 56 — invalid, expired, or no card record

- Code 14: verify the customer is using the correct card. Check card history for a newer active or pending replacement; advise updating a saved merchant card where applicable.
- Code 54: verify expiry and look for an `expired` replacement. Pending replacements need activation; active replacements should be used instead. If no replacement exists, discuss ordering one only after ordering eligibility and fees are checked.
- Code 56: confirm whether the customer is using a Rho-Bank card and compare the reported last four digits against cards on file. If none match, offer eligible replacement ordering rather than claiming a card record exists.

### Codes 19, 91, 92, or 96 — system/network issue

- Code 19: ask the merchant to retry immediately. If the retry also produces Code 19, advise waiting 10–15 minutes.
- Codes 91 or 96: explain this is usually temporary and retry in a few minutes; if it persists, wait 10–15 minutes and use another payment method if available.
- Code 92: explain that it is a temporary network-routing issue. Retry, then try a different merchant or ATM if it persists.

### Codes 55 or 75 — PIN issue or PIN locked

- If not locked, warn the customer when attempts are low and offer a PIN reset through the applicable documented procedure.
- If `pin_locked` is true, do **not** unlock immediately. Follow the full PIN-lock fraud-risk protocol: check automatic escalation triggers, review the required card/account/transaction history, calculate and apply the risk thresholds, ask required questions, and use the required post-unlock steps. Do not reveal internal scoring calculations.
- Escalate rather than unlock when the protocol requires it, including security hold, critical risk, or unresolved security concerns.

### Code 57, 58, 61, 62, or 65 — restrictions and limits

- Code 57: assess merchant-category, international, online, and parental restrictions. Never remove gambling or adult-content category restrictions by phone. Do not modify parental controls without guardian authorization.
- Code 58: explain that the terminal is flagged; recommend a different register or merchant. If it occurs at multiple unrelated terminals, perform the Code 05 diagnostic.
- Code 61: calculate remaining purchase or ATM allowance from the returned daily limit and amount used. A temporary increase requires an OPEN account at least 60 days old, no overdraft fees in the last 30 days, an ACTIVE card, no increase in the previous 24 hours, and a requested new limit no greater than 150% of the current limit. Confirm the 24-hour duration and customer consent before submitting a request.
- Code 62: assess geographic restrictions and recent card issuance. Do not promise changes without a supported card-control tool and required verification.
- Code 65: explain the daily transaction-count limit and that it generally resets at midnight; suggest another eligible payment method or card.

### Codes 04, 07, 34, or 59 — sensitive fraud/security codes

Do not disclose the code or state that fraud was detected. Use the approved neutral wording: the card cannot be used and the customer should visit a branch with valid ID; for persistent questions or a security concern, transfer to a human security specialist.

### Codes 41 or 43 — lost or stolen card

- Lost: a card reported lost cannot be reactivated. Check for a pending replacement and assist with activation only if eligible.
- Stolen: after matching the card, require enhanced verification including full name, date of birth, last four of SSN, and recent transaction verification before discussing the status or taking action. For the transaction-verification challenge, retrieve history only for the matched card account and use two or three recent transactions from that account—never another account. If any enhanced-verification element cannot be completed, disclose no further card-status details and transfer to security. A stolen card cannot be reactivated. If the customer says they did not report it stolen after enhanced verification, transfer to security; do not resolve it in chat.

### Code 82 or 87 — physical-card or cash-back issue

- Code 82: ask about damage. If damaged, discuss eligible replacement. If apparently undamaged, review recent activity after verification and ask the customer to confirm any suspicious transaction before treating it as fraud. If the customer confirms fraud and requests a dispute plus permanent replacement, collect dispute requirements, file the dispute, then close and reissue while the card remains eligible for closure; do not first freeze it solely as an interim action. If the customer instead wants only temporary protection while deciding, explain the effects and freeze only with consent. If a card is already frozen, never unfreeze it just to bypass closure eligibility; transfer to security to coordinate the permanent replacement safely.
- Code 87: explain that cash back was not permitted and advise retrying the purchase without cash back.

## Tool-use safeguards

- Retrieve accounts with `get_all_user_accounts_by_user_id_3847`, transactions with `get_bank_account_transactions_9173`, and cards with `get_debit_cards_by_account_id_7823`.
- Unlock a specialized tool only when the procedure explicitly names it. Call it only with documented required arguments.
- Before clearing a customer-initiated fraud alert or velocity block, verify identity and card ownership. Never use a clear operation for a bank-initiated fraud alert.
- Before freezing, unfreezing, activating, ordering, closing, raising a limit, or filing a dispute, independently re-check that operation's specific eligibility, account/card status, fees, balance, ownership, and confirmation requirements.
- Use `transfer_to_human_agents` for a bank-initiated alert or stolen-card claim only after confirming it belongs to the matched card, and for suspected fraud requiring escalation, security holds, or required PIN-risk escalations. Include a factual summary of checks completed, but do not include authentication secrets or unnecessary sensitive data.

## Completion checklist

Before concluding, ensure the response states:

- What was investigated and the supported reason for the decline, or that the cause could not be verified.
- Whether the customer may retry now, should wait, needs to add funds, needs activation/replacement, or was transferred.
- Any action completed and its result, without claiming success unless the tool confirmed it.
- Any customer action needed, such as using a replacement card or contacting the merchant.

## Per-execution discovery and dispute safeguards

Specialized agent tools are not assumed to remain unlocked between executions. In each execution, before the first use of a procedure-named specialized tool, call `unlock_discoverable_agent_tool` for that exact tool and wait for a successful unlock response. Only then call it through `call_discoverable_agent_tool`. If an attempted call reports that the tool is unavailable or not unlocked, do not treat that as a completed banking action; unlock it before proceeding. Never retry a banking action with an unknown outcome.

For an unauthorized debit-card transaction, do not file a dispute until the matched card and transaction are confirmed and all required dispute facts are collected. This includes transaction and discovery dates, amount, whether the physical card is in the customer's possession, PIN-compromise status, whether the merchant was contacted, a police-report response when applicable, and consent to use a written statement. Inform the customer of the applicable Regulation E liability timing before filing. Choose the fraud category and transaction type only from supported facts; do not guess whether a transaction was PIN, signature, online, or card-present.

The dispute tool may require `customer_max_liability_amount` in addition to the documented fields. Supply the maximum liability calculated from the applicable Regulation E reporting timing and the disputed amount (or `-1` only when liability is unlimited), after obtaining the timing facts. Do not invent provisional-credit eligibility: determine it under the applicable documented guidelines and the collected written-statement/timeliness facts. If a required eligibility rule or fact cannot be established, do not file a speculative dispute; explain the limitation and use the appropriate human escalation path.

When suspected card fraud requires a permanent close-and-reissue action, follow the closure prerequisites independently. If the card is already `FROZEN` and the documented closure procedure permits only `ACTIVE` or `PENDING` cards, do **not** unfreeze it merely to work around that condition. Preserve the freeze and transfer to the security team to coordinate the closure and replacement safely.

## Fraud disposition sequencing

For a confirmed, unauthorized transaction on the matched card, distinguish a temporary-protection request from a request to dispute and permanently replace the card. If the customer has agreed to the dispute and permanent close-and-reissue path, collect the dispute data, file it, and then perform the separately required closure action while the card satisfies the closure-status requirement. Do not create a preventable status conflict by freezing first. Explain that a fraud closure is permanent, the old card cannot be reactivated, and any recurring payments need new card information; obtain clear consent for closure and for the replacement order.

If transaction context establishes an in-person debit-card purchase and does not establish PIN use, record it as `card_present_fraud` with transaction type `signature_purchase`; if the context instead establishes PIN use, use `pin_purchase`. For online or phone activity, use the corresponding card-not-present/online classification. If neither channel can be established from transaction details or customer information, obtain clarification rather than guessing.

For a timely Regulation E fraud report with a customer-authorized written statement and no stated ineligibility, submit the documented provisional-credit eligibility value and communicate only the result returned by the dispute tool. Establish the discovery/reporting date before calculating `customer_max_liability_amount`; use the applicable $50, $500, or unlimited Regulation E outcome and never set a finite liability amount higher than the disputed amount.

After a successful fraud dispute whose `card_action` is `close_and_reissue`, the metadata alone does not close or replace the card. Separately use the documented close procedure, then obtain required delivery option, design choice, mailing-address confirmation, eligibility, fees, and balance before ordering a replacement. If prerequisites cannot be met or an action result is unknown, stop and explain or transfer rather than claiming the replacement was ordered.

## Enhanced-verification data isolation

When an applicable card status requires enhanced verification, first match the target card and retain that account identifier as the only permitted scope for the verification challenge. If recent-transaction verification is required, retrieve and use only recent transactions for that exact account; do not reuse transactions, merchant names, dates, amounts, or other observations from a prior card inquiry or any other account. Do not proceed to card changes or disclose the sensitive status if the required enhanced-verification factor is unavailable. Transfer with a neutral, factual summary instead.
