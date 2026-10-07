---
name: close-personal-checking-account
version: 1.0.0
description: Safely process a verified customer's request to close an eligible personal checking account. Use for Entry, Mid, Premium, or Elite checking-account closures when account information, identity verification, pending-transaction status, and required customer confirmation can be obtained.
---

# Close Personal Checking Account

Use this Skill for a customer-requested closure of a personal checking account. It supports account-tier fee and notice calculations, but does not itself perform bank actions.

## Preconditions and safety controls

Before **any** banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

For a closure specifically:

1. Identify the customer from a customer-provided identifier, then obtain a second identity factor. Verify at least two of date of birth, email, phone number, and address against the customer record.
2. Call `log_verification` only after the two-factor comparison succeeds. Include the complete retrieved customer details and a current timestamp from `get_current_time`.
3. Retrieve the customer's accounts with `get_all_user_accounts_by_user_id_3847` (unlock it first through the discoverable-agent-tool workflow if necessary). Select the requested account by its returned account ID and product/class; do not select solely from a product name if multiple accounts match.
4. Treat an account returned for the verified user as evidence of ownership, but ensure it is a checking account and the intended account before proceeding.
5. Obtain reliable current pending-transaction status using the supported account/transaction workflow. A customer assertion alone is not enough when an internal status source is available. If no supported method can establish this, do not close the account.
6. Explain the applicable fee and notice period, and obtain clear confirmation to submit the closure/notice after that disclosure. A prior general request can establish intent but should not substitute for a final confirmation when fees, timing, or account selection have just been determined.

Never infer an account ID, opening date, status, balance, pending status, identity factor, or customer confirmation. Do not open a savings account as part of this workflow unless the verified customer separately identifies a desired savings product and confirms that action.

## Tier rules

Map the returned account product/class to one of these tiers:

| Tier | Products | Early closure rule | Notice |
|---|---|---:|---:|
| Entry | Light Blue Account; Light Green Account; Green Fee-Free Account | $15 when closed within 30 days of opening | 0 days |
| Mid | Blue Account; Green Account (checking) | $25 when closed within 60 days of opening | 3 days |
| Premium | Evergreen Account | $50 when closed within 90 days of opening | 7 days |
| Elite | Bluest Account | $100 when closed within 180 days of opening | 14 days |

The account must be `OPEN`, have no pending transactions, and satisfy the balance rule:

- If the early-closure window applies, available/current holdings must be at least the fee because the fee is deducted from that account. There is no alternative payment method.
- If no early-closure fee applies, current holdings must be exactly $0.

Use calendar dates and treat an account as in the early-closure window through the listed number of days after opening. If the system provides a different authoritative fee calculation or processing-date interpretation, follow that system result and disclose it to the customer.

## Procedure

1. Identify the customer, collect and compare a second identity factor, retrieve the current time, and log successful verification.
2. Retrieve all accounts for the verified user. Confirm the target account ID, that it is a personal checking product, `OPEN`, and belongs to the customer.
3. Retrieve/verify the current balance and absence of pending transactions using supported bank tools. Capture the date opened and current processing date.
4. Run `scripts/closure_eligibility.py` with the selected account facts. The script reports the applicable tier, fee, notice, and blockers; it never initiates closure.
5. If any blocker is reported, explain only the blocker and the required remedy. Do not call the closure tool.
6. If eligible, disclose the fee (if any), that it will be deducted from the target account, and the notice period. Ask for explicit confirmation to submit the closure or notice now.
7. After receiving that confirmation, unlock `close_bank_account_7392` through the discoverable-agent-tool workflow if required. Call it only with the parameters documented by its runtime schema, using the confirmed target account. Do not invent parameters.
8. Report the tool result accurately. If closure is scheduled after notice rather than completed immediately, state the scheduled/notice status rather than claiming the account is closed.

## Handling unavailable or conflicting information

- Do not retry an action whose result is `UNKNOWN`.
- If identity cannot be verified, account ownership is unclear, pending status cannot be established, the product is unsupported, or a required closure action/tool is unavailable, do not perform closure. Explain the limitation and transfer to a human agent with the applicable closure or technical reason if further handling is required.
- If account data conflict with a customer statement, use current authoritative account data and ask for clarification where needed.
- If the account is empty but an early fee applies, it is ineligible until it has at least the fee amount; do not suggest an external payment method.

## Eligibility helper

`scripts/closure_eligibility.py` reads one JSON object from stdin and writes one JSON object to stdout. It is deterministic and performs no banking actions.

Input schema:

```json
{
  "account_product": "Green Account (checking)",
  "account_type": "checking",
  "status": "OPEN",
  "current_holdings": "0.00",
  "date_opened": "YYYY-MM-DD",
  "processing_date": "YYYY-MM-DD",
  "has_pending_transactions": false
}
```

`account_type` must identify a checking account. Monetary inputs are decimal strings or JSON numbers. The output contains `eligible`, `tier`, `early_closure_fee`, `notice_days`, `in_early_closure_window`, and a list of machine-readable `blockers`.

Example invocation in an executor that supports packaged scripts:

```text
run_skill_script(relative_path="scripts/closure_eligibility.py", input_json=<selected current account facts>)
```

Before calling the closure tool, validate that the helper reports `eligible: true`, its tier agrees with the retrieved product, the account ID is the specifically confirmed target, identity verification was logged, pending status was authoritatively checked, and final customer confirmation was received.