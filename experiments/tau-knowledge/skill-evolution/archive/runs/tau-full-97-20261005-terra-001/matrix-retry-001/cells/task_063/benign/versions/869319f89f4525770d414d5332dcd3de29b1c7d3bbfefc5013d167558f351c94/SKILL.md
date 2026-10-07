---
name: savings-account-and-card-combination-advisor
description: Safely compare Rho-Bank savings and credit-card combinations, screen published APY and card criteria, and open/fund a personal savings account only after verified identity and documented eligibility checks. Use for requests to optimize savings interest, select a savings/card combination, open a savings account, or arrange its opening deposit.
---

# Savings Account and Card Combination Advisor

## Purpose and safety boundary

Separate product advice, credit-card pre-screening, savings-account opening, and funding. An approximate credit score supports only a preliminary comparison; it is not an application, credit pull, approval, or card opening. Do not claim any of those events unless a supported action actually completed them.

A customer statement of their account history does not replace the required account-record lookup. Open a personal savings account only after the bank record confirms every required condition. Never invent a credit-card application action or report that an external deposit was received without confirmation.

## Required workflow

1. **Verify identity and create the audit record.** Ask the customer to confirm two of the four identity fields (date of birth, email, phone number, address) without exposing bank-record values as hints. Retrieve the current timestamp and call `log_verification` with the complete matched customer record. Do not proceed with account actions until verification is logged.

2. **Retrieve account records before deciding eligibility.** Unlock `get_all_user_accounts_by_user_id_3847`, then call it with the verified user ID. This lookup is required to establish account IDs, account types, status, balance, opening date, account count, and good standing. If it is unavailable, fails, or is incomplete, explain that eligibility cannot be confirmed; do not open or transfer funds.

3. **Evaluate the savings-opening prerequisites.** Confirm from the lookup that all of the following hold:
   - at least one Rho-Bank checking account is active/open;
   - an active/open checking account has been held at least 14 days;
   - fewer than five personal savings accounts are held;
   - no account is in collections; and
   - no account has a negative balance.

   Use `scripts/evaluate_opening_eligibility.py` for deterministic evaluation when helpful. Unknown, malformed, or ambiguous required data is unresolved and therefore does not pass. If a condition fails or is unresolved, state the known reason and do not open or transfer. For a short tenure, provide the eligibility date if the opening date is available.

4. **Screen and explain products.** Identify customer constraints, including planned balance, required opening funding, statement preference, and whether a credit check is required. Use only supplied product documentation. Capture a confirmed savings selection using the full official `account_class` ending in `Account`; never substitute an abbreviation.

5. **Compare return estimates correctly.** For every viable candidate, determine the balance-appropriate base APY tier, select at most one highest applicable card bonus, select at most one highest applicable checking boost, and separately include only documented additive bonuses whose conditions are met. Card bonuses do not stack with one another, and checking boosts do not stack with one another. An unlisted checking/savings pairing receives no linked-checking boost. Use `scripts/rank_apy_candidates.py` with sourced current inputs for a transparent constant-balance annual estimate. Describe it as an estimate, not a promised return.

6. **Handle credit cards independently.** Explain preliminary eligibility, required score threshold, and credit-check consent. If the runtime offers a supported card-application action, obtain authorization and follow that action's schema. If it does not, state that the card has not been applied for, no credit check has occurred, and no approval has been given; provide the supported application channel if known. Do not block a permitted savings action merely because a card action is unavailable.

7. **Open only the confirmed eligible savings product.** Reconfirm the official account class. Unlock and call `open_bank_account_4821` using the verified `user_id`, `account_type: "savings"`, and the exact confirmed `account_class`. Retain the returned new account ID. If opening fails or does not return a destination account ID, report that accurately and do not attempt funding.

8. **Fund only after a successful opening and only when safe.** Ask for authorization to transfer a specified amount from a specified active checking account. Check the latest available source balance against the full requested amount before calling `transfer_funds_between_bank_accounts_7291`.
   - If authorization is absent, source selection is missing, funds are insufficient, or data is unavailable, do not call the transfer action.
   - When an authorized requested internal transfer exceeds the observed available balance, clearly communicate the limitation in direct language, for example: **"I cannot make an $[requested] internal transfer because the available balance is $[available]."** Substitute the actual requested transfer and available balance. Do not imply that a partial transfer was made.
   - Offer an external deposit for the needed amount when appropriate. A planned or requested external deposit is not received or confirmed. Say so explicitly until a supported confirmation exists.
   - When the account remains unfunded rather than successfully immediately funded, state that it must be funded within 30 days of opening by internal transfer or external deposit or the account will close. Calculate and provide the calendar deadline from the actual opening date when known.
   - If a transfer action is used, report success only if its result confirms it.

9. **Complete the response accurately.** Provide the opened-account details only when returned by the opening action, paper-statement availability or required servicing step, card application status, and the actual funding status. Do not state that a funding deposit, paper-delivery enrollment, APY bonus, or credit-card application occurred unless confirmed by the relevant system result.

## Product-screening rules

Apply these rules only when the supplied documentation establishes the facts for the products at issue:

- A savings product requiring paperless statements is unsuitable if mailed paper statements are mandatory. A product expressly permitting paper statements may meet that preference, subject to any documented fee.
- A card with no credit-score requirement does not meet a customer's stated requirement for a card that checks creditworthiness. A stated score that meets a published minimum remains a preliminary screen, not an approval.
- Evaluate both opening and ongoing balance requirements. A planned opening deposit does not make an account suitable when its ongoing minimum is not met.
- For Silver Plus, the base tier depends on the balance relative to its published tier threshold; its paper-statement availability and card bonus must be evaluated from current documentation. Do not assume a checking boost unless the exact checking/savings pairing is listed.

## Helper scripts

### `scripts/evaluate_opening_eligibility.py`

Reads one JSON object from stdin and emits one JSON object to stdout. It is advisory only: it never retrieves records or performs banking actions.

Input schema:
```json
{
  "identity_verified": true,
  "as_of": "YYYY-MM-DD or timestamp",
  "accounts": [
    {
      "account_id": "string",
      "account_type": "checking|savings",
      "status": "active|open|collections",
      "balance": "1250.00",
      "date_opened": "YYYY-MM-DD",
      "is_personal": true
    }
  ],
  "account_class": "Official Name Account",
  "required_opening_deposit": "1000.00",
  "requested_deposit": "8000.00",
  "funding_authorized": true,
  "source_account_id": "checking-account-id"
}
```

The result contains `eligible_to_open`, each prerequisite result, eligible checking IDs, blockers, and an independent `immediate_funding` assessment. Require `eligible_to_open: true` before opening. Require `immediate_funding.ready: true` before an immediate transfer. A source balance lower than the requested amount is a funding blocker, not permission to send a partial transfer.

### `scripts/rank_apy_candidates.py`

Reads one JSON object from stdin and emits ranked JSON results to stdout. Supply a balance and sourced components for each candidate:

```json
{
  "balance": "8000.00",
  "candidates": [
    {
      "name": "Official Name Account with Card",
      "base_apy": 3.0,
      "card_bonuses": [0.15],
      "checking_boosts": [],
      "additive_bonuses": []
    }
  ]
}
```

The script selects the maximum supplied card bonus and checking boost rather than summing either list. It estimates one year of interest as constant balance × effective APY / 100. Validate real-world applicability before using its output.

## Failure handling

- Do not open when identity, account eligibility, official class, or required tool result is missing or unresolved.
- Do not transfer before a successful savings opening returns a destination account ID.
- Do not execute an insufficient, unauthorized, unspecified-source, or partial substitute transfer.
- Do not turn a proposed external deposit into a confirmed deposit in the response.
- Do not describe preliminary card qualification as a submitted application, credit pull, or approval.
- If an unsupported action is requested, explain the limitation and offer a supported next step without fabricating a tool or outcome.
