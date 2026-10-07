---
name: personal-checking-account-closure
version: 1.0.0
description: Verify and process a customer's personal checking-account closure request using the documented account, transaction, debit-card, and closure tools. Use when a customer asks to close a checking account, including when the account ID must be located from a verified profile.
---

# Personal Checking Account Closure

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and assumptions

This Skill handles a requested closure of a personal checking account. It does not open a savings account or select a savings product: if the customer has deferred that request or has not selected a savings account class, complete only the closure workflow and invite them to discuss savings needs later.

Use normal banking tools for all reads, verification records, and state-changing actions. Never treat a script result as a banking action. Do not guess account IDs, account classes, dates, balances, transaction states, card states, or unsupported tool parameters.

## Required procedure

1. **Establish identity and authority before banking actions.**
   - Match the customer's supplied identity details to one user record. Confirm at least two of the four identity fields (date of birth, email, phone number, address) against that record.
   - Obtain the current timestamp with `get_current_time`, then create the audit record with `log_verification`, supplying all required fields from the matched record and that timestamp.
   - Treat the verified customer as authorized only for an account returned under that customer's `user_id`. If identity is ambiguous, fields do not match, or verification cannot be completed, do not inspect or change accounts.

2. **Locate the requested account.**
   - Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified `user_id`.
   - Select only an OPEN checking account whose account class clearly matches the account the customer named. Do not substitute another checking account merely because it is open.
   - If there is no matching account or more than one plausible matching account, explain the issue and obtain an unambiguous account identifier before proceeding.
   - Record the account ID, account type/class, status, balance/current holdings, and opening date. Confirm ownership from the lookup result.

3. **Collect closure prerequisites immediately before any closure action.**
   - Unlock and call `get_bank_account_transactions_9173` with the selected account ID. Any transaction whose status is `pending` blocks account closure, regardless of its amount.
   - Unlock and call `get_debit_cards_by_account_id_7823` with the selected checking account ID. All associated debit cards must already be closed before the checking account can be closed. A card with a status other than `CLOSED` blocks account closure.
   - If cards must be closed, follow the separate debit-card closure process. In particular, do not close a card without the customer's reason, card ownership/status checks, pending-card-transaction and pending-refund checks, and applicable card-age determination. Then recheck the account's cards before attempting account closure.

4. **Apply checking closure requirements.**
   - The following documented tier rules apply:

     | Tier | Account classes | Early fee | Fee period | Notice |
     |---|---|---:|---:|---:|
     | Entry | Light Blue Account, Light Green Account, Green Fee-Free Account | $15 | within 30 days | 0 days |
     | Mid | Blue Account, Green Account (checking) | $25 | within 60 days | 3 days |
     | Premium | Evergreen Account | $50 | within 90 days | 7 days |
     | Elite | Bluest Account | $100 | within 180 days | 14 days |

   - The account must be OPEN and have no pending account transactions.
   - Calculate account age from `date_opened` and the current time. If the applicable early-closure period has not elapsed, the available balance/current holdings must be at least the fee because the fee is deducted from the account balance and has no alternate payment method. If no early fee applies, current holdings must be exactly $0.
   - Apply the listed notice period. Do not claim that closure is immediate when a nonzero notice period applies. If the closure tool represents notice scheduling or exposes required parameters, use only the parameters documented by its actual tool schema.

5. **Assess deterministically, then execute only if eligible.**
   - Optionally run `scripts/assess_closure.py` on the retrieved facts to make the rule evaluation reproducible. Its output is advisory; it does not replace live tool reads.
   - If any prerequisite is unmet, do not call the closure tool. State the specific blocker: account status, pending account transaction, non-closed debit card, insufficient balance for an applicable fee, or nonzero balance when no fee applies.
   - If all prerequisites are met, unlock `close_bank_account_7392` and inspect its discovered schema. Call it using the selected account and only the parameters the schema requires. Do not invent a fee amount, notice-date field, confirmation field, or other argument.
   - Treat an `UNKNOWN`, failed, or incomplete action response as not confirmed. Do not repeat an action reported as `UNKNOWN`. Report the observed result and escalate or transfer according to the supported workflow if needed.

6. **Respond accurately.**
   - On confirmed success, identify the account that was closed, disclose the applicable fee (if any) and notice period, and state the observed closure result.
   - If savings was deferred or no product class was selected, do not open one. Offer to help compare savings options after the closure matter is resolved and ask about the customer's savings goals rather than recommending an unsupported product.

## Script interface

`scripts/assess_closure.py` accepts one JSON object on standard input and emits one JSON object on standard output. It performs no banking actions.

Input schema:

```json
{
  "account": {
    "account_id": "string",
    "account_type": "checking",
    "account_class": "Green Account (checking)",
    "status": "OPEN",
    "balance": "0.00",
    "date_opened": "MM/DD/YYYY or ISO date"
  },
  "as_of": "timestamp or date",
  "transactions": [{"status": "posted or pending"}],
  "debit_cards": [{"status": "ACTIVE, CLOSED, or other status"}]
}
```

Output includes the recognized tier, fee and notice rule, parsed account age, blockers, and an `eligible_to_submit_closure` boolean. If a date or balance cannot be parsed, the script returns a blocker so the executor can resolve the live data rather than making an unsafe assumption.

Example invocation in a runtime that exposes packaged scripts:

```text
run_skill_script(relative_path="scripts/assess_closure.py", input_json={...retrieved facts...})
```

Validate its result by checking that: (1) the returned account ID is the selected account ID, (2) no blockers are present before attempting closure, (3) the fee and notice tier match the retrieved account class, and (4) live tool data was retrieved immediately before the state-changing call.
