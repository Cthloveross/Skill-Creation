---
name: debit-card-dispute-filing
description: Verify a debit-card holder, locate the eligible checking account, card, and transaction, assess Regulation E and ATM-specific requirements, file one or more valid debit-card transaction disputes, and apply the most severe required card protection. Use for unauthorized debit-card activity, ATM errors, duplicate charges, incorrect amounts, missing goods or services, and post-cancellation recurring charges.
---

# Debit Card Dispute Filing

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Inputs and runtime tools

Gather the customer's description for each transaction separately. Required information includes the claimed merchant/ATM, transaction date and amount, discovery date, reason, whether fraud is suspected, channel (physical/PIN/signature, online/phone, ATM, recurring, or P2P), card possession, PIN-compromise answer, merchant-contact answer, written-statement consent, and, for fraud over $500, police-report status.

Use the ordinary identity/profile lookup tools to locate the person. Compare at least two customer-supplied identity fields against the returned profile, then call `log_verification` with the complete returned profile and a current timestamp. Do not file, freeze, close, reissue, or otherwise change a banking product until this succeeds.

The following documented banking tools may need to be unlocked with `unlock_discoverable_agent_tool` and then invoked through `call_discoverable_agent_tool`:

- `get_all_user_accounts_by_user_id_3847` with `{"user_id": "..."}`
- `get_debit_cards_by_account_id_7823` with `{"account_id": "..."}`
- `get_bank_account_transactions_9173` with `{"account_id": "..."}`
- `get_debit_dispute_status_7483` with `{"user_id": "..."}`
- `get_atm_deposit_images_8473` with the documented transaction/account arguments when applicable
- `file_debit_card_transaction_dispute_6281` with the filing payload below

Use only action tools that are actually available in the runtime. In particular, a required post-filing freeze is performed with `freeze_debit_card_3892` when available; do not invent a close/reissue tool name. If a close-and-reissue action is required but no supported tool is available, route it through the normal banking workflow rather than claiming it was completed.

## Procedure

1. **Explain reporting rights before filing.** For unauthorized activity, tell the customer their maximum liability: $50 when reported within 2 business days of the statement, $500 within 60 days, and potentially unlimited after 60 days. Obtain the statement/reporting timing if it is needed to establish the liability band or provisional-credit timeliness. For an ATM error or other non-unauthorized claim, explain that prompt reporting still supports investigation; do not call it fraud without facts.

2. **Verify identity, authority, and ownership.** Locate the profile using a customer-provided identifier. Match two of date of birth, address, email, and phone number; log the successful verification. Retrieve all accounts for the verified `user_id`. Select the customer-confirmed checking account, confirm it is `OPEN`, belongs to this user, and record its account class/tier, opening date, and applicable product facts. Available balance, transfer recipient, fees, and cutoffs are not inputs to a dispute filing; record them as not applicable rather than fabricating them.

3. **Locate the card and transaction.** Retrieve cards for the selected checking account. Confirm the selected card is linked to that open checking account and has the same `user_id`; resolve multiple cards with card last four digits or transaction facts. Retrieve the account transactions and match the claimed transaction by date, amount, and description. Use the returned `transaction_id`, returned date, and absolute debit amount. Never rely solely on a customer-supplied transaction ID.

4. **Check filing prerequisites.** The disputed amount must be at least $1.00, the transaction must be no more than 60 calendar days old, and the checking account must be open and card-linked. Retrieve all disputes for the user and count only ongoing disputes for the selected `account_id` (`OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, and `PROVISIONAL_CREDIT_ISSUED`). The per-account limits are Entry 2, Mid 3, Premium 4, and Elite 5. Do not file if the next dispute would exceed the limit or if the tier cannot be determined. For multiple duplicate claims, select and file the earliest transaction first.

5. **Classify accurately.** Select exactly one category:
   - `unauthorized_transaction` only if the customer did not authorize it but fraud is not suspected (for example, an unpermitted family use).
   - `card_present_fraud` for suspected fraud at a physical/in-store transaction.
   - `card_not_present_fraud` for suspected fraud online or by phone.
   - `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation` for the corresponding non-fraud issue.

   Select exactly one transaction type: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`. Ask the required card-possession and PIN questions. Ask whether the customer contacted the merchant/operator for every non-fraud claim and record the factual boolean; lack of contact does not justify changing the answer to true.

6. **Handle ATM claims.** Determine whether the ATM is Rho-Bank branded or third-party.
   - For a Rho-Bank ATM cash discrepancy, review the corresponding account transaction/journal information and compare it with the claim. If the journal confirms the discrepancy, arrange immediate provisional credit through an available normal banking process. If it shows the stated amount was dispensed, explain that the claim is not validated by the journal but the customer may still formally dispute it.
   - For a Rho-Bank ATM deposit-not-credited claim, retrieve deposit images and compare them with the expected deposit. Explain that physical verification may take up to 45 days.
   - For a third-party ATM, submit the claim through the dispute/chargeback process, explain the investigation can take up to 90 days, and track provisional credit under the applicable timeline.
   - For any ATM cash-discrepancy claim whose **disputed amount** exceeds $200, tell the customer that an Electronic Fund Transfer Error Resolution Affidavit will be emailed to their registered address, must be signed and returned within 10 business days, may be required for the claim, and that knowingly signing falsely is a federal offense. Do not claim it was sent unless an available tool confirms that action.

7. **Determine provisional-credit eligibility.** Required eligibility is true only if all are established: timely report within 60 days of the statement, category is one of `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`, a written statement was provided, and the checking account is open with no holds/restrictions. It is not required for the other listed dispute categories, when a non-fraud claimant has not contacted the merchant first, when the PIN was voluntarily shared (`yes_shared`), or for a card-not-present transaction on an account open less than 30 days. If standing, statement timing, or written consent is unknown, do not mark eligibility true. Qualifying standard accounts receive provisional credit within 10 business days; new accounts generally within 20 business days. A confirmed Rho-Bank ATM discrepancy is handled immediately. Eligible credit is the disputed amount, subject to any applicable $50/$500 late-report liability offset. Investigation is normally 45 business days with provisional credit, and may be 90 days for international/non-US POS, new accounts, and third-party ATM processes as applicable.

8. **Build and submit each filing.** Map card action per individual dispute: fraud categories map to `close_and_reissue`; `unauthorized_transaction` maps to `freeze_pending_investigation`; all other categories map to `keep_active`. For suspected fraud above $500, ask whether a police report was filed and recommend one if not. Submit `file_debit_card_transaction_dispute_6281` only after all blocking checks pass, using the exact payload keys:

```json
{
  "transaction_id": "matched transaction ID",
  "account_id": "open checking account ID",
  "card_id": "linked card ID",
  "user_id": "verified user ID",
  "dispute_category": "one permitted category",
  "transaction_date": "MM/DD/YYYY",
  "discovery_date": "MM/DD/YYYY",
  "disputed_amount": 0.0,
  "transaction_type": "one permitted type",
  "card_in_possession": true,
  "pin_compromised": "yes_shared | yes_observed | no | unknown",
  "contacted_merchant": false,
  "police_report_filed": false,
  "written_statement_provided": true,
  "provisional_credit_eligible": false,
  "card_action": "keep_active | freeze_pending_investigation | close_and_reissue"
}
```

9. **Apply one final card action per card.** Retain each filing's own mapped `card_action`. After all filings for the same card have succeeded, perform only the most severe actual action once: `close_and_reissue` outranks `freeze_pending_investigation`, which outranks `keep_active`. Confirm tool results before telling the customer that a dispute, credit, freeze, closure, replacement, affidavit, or chargeback has occurred.

10. **Close the interaction.** Give the customer the filed dispute identifiers and expected timeline only from successful tool responses. Explain that an adverse investigation can reverse provisional credit with written notice at least 3 business days before reversal and that the customer may request supporting documents. Escalate a dispute that cannot meet regulatory timing or has unresolved account restrictions.

## Optional deterministic preflight helper

Run `scripts/preflight_dispute.py` before filing when normalized records are available. It reads one JSON object from stdin and writes one JSON object to stdout; it does not call banking tools or perform actions.

Input schema: `today` is `MM/DD/YYYY`; `identity_verified` is boolean; `account` supplies `account_id`, `account_type`, `status`, `account_class` or `tier`, `date_opened`, and optional `unrestricted`; `card` supplies `card_id`, `account_id`, and `user_id`; `transaction` supplies `transaction_id`, `account_id`, `date`, `amount`, and `type`; `open_disputes` is the status response list; `claim` supplies all filing facts, including `category`, `discovery_date`, `disputed_amount`, `transaction_type`, `card_in_possession`, `pin_compromised`, `contacted_merchant`, `police_report_filed`, `written_statement_provided`, `timely_statement_reported`, and optional ATM/journal facts.

Example runtime invocation (with live facts substituted):

```sh
python3 scripts/preflight_dispute.py <<'JSON'
{"today":"MM/DD/YYYY","identity_verified":true,"account":{},"card":{},"transaction":{},"open_disputes":[],"claim":{}}
JSON
```

A result with `valid_to_file: true` and a non-null `filing_args` is a structural check only. The executor must still use live tool results, complete outstanding customer questions, and confirm actual actions after tool responses.
