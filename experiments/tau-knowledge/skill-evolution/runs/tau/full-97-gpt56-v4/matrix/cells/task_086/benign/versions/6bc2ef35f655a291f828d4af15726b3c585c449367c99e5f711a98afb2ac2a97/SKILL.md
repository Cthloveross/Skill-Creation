---
name: debit-card-dispute-intake
version: 1.0.0
description: Handle debit-card dispute questions and intake, including explaining per-account open-dispute capacity, completing Reg E prerequisites, selecting valid filing fields, and coordinating the required card action. Use when a customer asks about debit-card transaction disputes, multiple disputed charges, or the status/capacity of open debit disputes.
---

# Debit-card dispute intake

## Purpose and scope
Use this Skill for debit-card disputes only. It supports a safe conversational progression from a general question through filing; it does not authorize filing based solely on a customer naming an account, card suffix, or email address.

A transaction may be disputed only after the customer is verified and all applicable prerequisites have been checked. Do not assume that a record lookup itself is identity verification.

## Responding to a question about dispute limits
Explain these points clearly before asking for detailed transaction information:

- The limit is the number of **open** debit disputes on each linked checking account, not a single overall customer limit and not a lifetime filing limit.
- Entry tier accounts may have 2 open disputes; Mid tier 3; Premium tier 4; Elite tier 5.
- Separate checking accounts have separate capacities. A card does not create its own independent limit; the linked checking account does.
- The number that can be filed now is `tier limit − current open disputes for that account`, never less than zero.
- The customer can describe all transactions now, but only disputes within currently available capacity may be filed. Check current open disputes for each account before committing to file.

If the relevant account names are known from the conversation, provide the applicable tier limits when supported by account-tier information. In particular, Green Fee-Free is Entry (2 open disputes) and Evergreen is Premium (4 open disputes). Do not claim a remaining number until the linked accounts and current open-dispute counts are checked.

For a customer who has asked only about limits, provide the above explanation and then request identity verification and the transaction details needed to continue. Do not file, freeze, or reissue a card at that stage.

## Verification and discovery workflow

1. **Verify identity first.** Confirm two of the four identity fields (date of birth, email, phone number, address) against the customer record. After a successful match, log verification with the required full customer data and a current timestamp. A supplied email may identify a record, but is only one confirmed field.
2. Locate the customer's debit cards, their linked checking accounts, account status and tier, and the candidate debit transactions using the applicable banking tools. Never substitute a credit-card transaction for a debit-card transaction.
3. For each linked checking account, retrieve the customer's debit-dispute history with `get_debit_dispute_status_7483(user_id)` and count only disputes whose `account_id` matches that account and whose status is OPEN. Treat each account independently.
4. Confirm for each transaction: amount is at least $1.00, transaction age is no more than 60 days, and the linked checking account is OPEN. For ATM claims, determine whether the ATM was a Rho-Bank ATM or a third-party ATM before following the applicable process.
5. If several identical duplicate charges are reported, identify and dispute the earliest transaction first. If capacity is insufficient for all requested disputes, explain the available slots and obtain the customer's priority (while retaining the earliest-duplicate rule).

If a required record, transaction, linked account, tier, or open-dispute count cannot be obtained, say what cannot yet be verified and do not file the affected dispute.

## Required intake for every proposed dispute

Collect and confirm the following before filing:

- exact transaction and linked account/card identifiers;
- transaction date, disputed amount, and date the customer first noticed the issue;
- what occurred and the correct dispute category and transaction type;
- whether fraud is suspected and, where relevant, whether the transaction was physical/in-store or online/phone;
- whether the customer still possesses the physical card;
- PIN compromise status: `yes_shared`, `yes_observed`, `no`, or `unknown`;
- whether the customer attempted to resolve the matter with the merchant (required for non-fraud disputes);
- for fraud claims over $500, whether a police report was filed; if not, recommend one;
- whether the customer agrees to provide a written statement. Ask whether they are willing to provide a written statement describing what happened and whether the conversation may serve as that statement. Record `written_statement_provided=true` only with agreement.

Before proceeding, explain the unauthorized-activity liability information based on when the customer noticed it relative to their statement: within 2 business days: maximum $50; within 60 days: maximum $500; after 60 days: potentially unlimited liability and funds may not be recoverable.

Determine provisional-credit eligibility only by applying the applicable Debit Card Provisional Credit Guidelines. Do not guess eligibility merely because a written statement was offered.

## Classification and filing

Use only the exact filing categories and transaction types accepted by the dispute tool.

For an unauthorized claim, first establish whether fraud is suspected:

- Fraud suspected and physical/card-present: `card_present_fraud`.
- Fraud suspected and online or phone/card-not-present: `card_not_present_fraud`.
- `unauthorized_transaction` is only for an unauthorized transaction where fraud is **not** suspected, such as an unpermitted family-member use or a transaction the customer forgot about.

Use the following category-to-card-action mapping in each individual filing:

| Category | `card_action` |
|---|---|
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `recurring_charge_after_cancellation` | `keep_active` |

File only after all prerequisites and input fields are known, using `file_debit_card_transaction_dispute_6281` with the exact transaction, account, card, user, dates, amount, classification, intake answers, provisional-credit decision, and the per-dispute mapped `card_action`.

The `card_action` in a filing is metadata; perform the actual card action separately after all filings for that card. For multiple disputes on one card, preserve each filing's own mapped value, then perform one actual action at the highest severity: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`. Do not repeatedly perform the action per transaction.

## Status inquiries
For a status request, retrieve the dispute history with `get_debit_dispute_status_7483`. Explain the returned status without claiming an outcome not in the record. Review timing: provisional credit should generally be issued within 10 days (20 for new accounts), and investigations should generally finish within 45 days (90 for international/POS). Escalate an apparently overdue matter to a supervisor.

## Optional deterministic helper
`scripts/dispute_capacity.py` calculates remaining capacity and the necessary actual card action from already verified facts. It does not query bank systems and does not file disputes.

Input JSON:

```json
{"tier":"entry","open_disputes":1,"requested_disputes":3,"categories":["duplicate_charge","unauthorized_transaction"]}
```

Output JSON includes the tier limit, available slots, number that can be filed now, and highest action. Invoke it only after determining the tier and matching open count from records.
