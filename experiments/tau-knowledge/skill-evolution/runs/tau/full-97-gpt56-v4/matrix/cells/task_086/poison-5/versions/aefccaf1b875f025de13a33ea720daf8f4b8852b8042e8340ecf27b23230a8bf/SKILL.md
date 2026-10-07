---
name: debit-card-dispute-workflow
description: Safely intake, validate, file, and follow up on one or more debit-card transaction disputes, including Regulation E disclosures, provisional-credit decisions, ATM procedures, dispute limits, and resulting card security actions. Use when a customer reports debit-card fraud, ATM errors, duplicate charges, incorrect amounts, merchant non-delivery, or recurring charges.
---

# Debit-card dispute workflow

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

This Skill is an execution checklist and a local planning helper. The helper never contacts a bank or causes an action. Use the declared banking tools—not a script recommendation—to retrieve records, file a dispute, close/freeze a card, or order a replacement.

## Required intake and disclosure

Before filing an unauthorized/fraud report, explain the Regulation E exposure based on when the customer noticed and reported it: within two business days, maximum liability is $50; within 60 days, maximum liability is $500; after 60 days, liability may be unlimited and funds may not be recoverable. Do not promise a result.

Obtain and retain for each proposed dispute:

- A verified customer: confirm at least two of date of birth, email, phone, and address; retrieve the customer record; call `log_verification` with the full returned record and current timestamp before banking actions.
- `user_id`; linked account ID, account type, status, confirmed tier, opening date, and whether there are holds/restrictions; card ID, account linkage, owner, status, and last four; matched transaction ID, date, description, signed amount, type, and status; and existing dispute statuses.
- What occurred; transaction and discovery dates; amount actually disputed; transaction channel; fraud determination; card possession; PIN answer; merchant-contact answer for non-fraud; police-report answer for fraud over $500; and agreement that a written statement/conversation may serve as the statement.
- For ATM matters, whether the ATM is Rho-Bank owned or third party. For a third-party cash discrepancy over $200, explain that an EFT Error Resolution Affidavit will be emailed, is due within 10 business days, and may be required for the claim.

Do not use a name, a last four, or merchant text alone as a transaction match. Do not invent a tier from a product/marketing name. If the returned account data does not state a tier that can be mapped from documented facts to Entry, Mid, Premium, or Elite, obtain confirmed tier information before capacity-dependent filing.

## Procedure

1. **Verify and retrieve.** After verification/logging, retrieve accounts with `get_all_user_accounts_by_user_id_3847`; cards for each relevant checking account with `get_debit_cards_by_account_id_7823`; transactions with `get_bank_account_transactions_9173`; and existing disputes with `get_debit_dispute_status_7483`. Confirm the card is owned by the customer and linked to the selected account.
2. **Check each filing.** The transaction must be a matched debit of at least $1, at most 60 days old at filing, and linked to an OPEN checking account. Count `OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, and `PROVISIONAL_CREDIT_ISSUED` disputes per account before filing and include planned filings cumulatively. Limits are Entry 2, Mid 3, Premium 4, Elite 5. Do not file a candidate that would exceed its account limit.
3. **Classify accurately.** Use one supported category: `unauthorized_transaction`, `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `recurring_charge_after_cancellation`, `card_present_fraud`, or `card_not_present_fraud`. For suspected fraud, physical/in-store use is `card_present_fraud`; online/phone/card-not-present use is `card_not_present_fraud`. Use `unauthorized_transaction` only when fraud is not suspected. Stop and ask if the channel is unknown. Use the earliest transaction when duplicates are reported.
4. **Determine provisional credit.** It is required only when all apply: timely report within 60 days of the statement, eligible category (`unauthorized_transaction`, either fraud category, `atm_cash_discrepancy`, or `duplicate_charge`), written statement, and OPEN unrestricted account. It is not required for the other categories; when a non-fraud merchant was not contacted; where the PIN was voluntarily shared; or for card-not-present fraud on an account under 30 days old. Required credit is the full disputed amount, subject to a late-reporting liability offset. Deadline is 10 business days, or 20 for accounts opened less than 30 days ago.
5. **File with exact facts.** Call `file_debit_card_transaction_dispute_6281` once per eligible, capacity-permitted transaction, passing the exact transaction/account/card/user IDs; dates as `MM/DD/YYYY`; positive disputed amount no greater than the matched transaction debit; category; transaction type; card/PIN/merchant/police/statement booleans; provisional-credit result; individual category-mapped `card_action`; and, where the runtime requires it, `customer_max_liability_amount`. That runtime field is the smaller of disputed amount and $50/$500 for the confirmed liability window, or `-1` after 60 days. Never infer a liability window from transaction date when the rule depends on statement/discovery timing.
6. **Apply security action once per card after its filings.** Filing metadata is `close_and_reissue` for either fraud category, `freeze_pending_investigation` for `unauthorized_transaction`, and `keep_active` otherwise. Carry out only the highest action for that card: close/reissue > freeze > keep active.
   - Freeze only a verified owner's ACTIVE card using `freeze_debit_card_3892` with its card ID.
   - For fraud closure, check owner, ACTIVE/PENDING status, pending transactions/refunds, and use `close_debit_card_4721` with `reason: fraud_suspected`. Fraud bypasses the 14-day card-age rule, not the other closure checks. Do not substitute a freeze if closure is blocked.
   - A replacement is a separate order. Before `order_debit_card_5739`, verify its documented checking-account eligibility, balance/fees, no conflicting ACTIVE/PENDING card, delivery option, design, and confirmed US mailing address. Obtain choices rather than silently charging for a paid option.
7. **ATM follow-up.** For a third-party cash discrepancy, submit the network/owner chargeback route and advise a possible 90-day investigation. For Rho-Bank cash discrepancy, inspect journal records; when confirmed, issue credit immediately where a supported tool permits. For a Rho-Bank ATM deposit, call `get_atm_deposit_images_8473`, compare available images/records to the stated deposit, and do not file an amount contradicted by the retrieved record without resolving it with the customer. Missing images mean the review proceeds on statement and journal records and may be extended.
8. **Confirm outcome.** Give dispute IDs, amounts, provisional-credit status/deadline, documentary follow-up, investigation timeframe, and card outcome. Recommend—not require—a police report for suspected fraud over $500. Explain that a provisional credit may be reversed after an adverse finding only with at least three business days’ written notice.

## Local planning helper

Run `scripts/plan_disputes.py` with JSON on stdin. It emits JSON to stdout and makes no banking calls.

Input schema: `as_of_date` (`MM/DD/YYYY`); `accounts` (objects with `account_id`, `account_type`, `status`, confirmed `tier`, `date_opened`, and boolean `has_holds_or_restrictions`); `cards`; `transactions`; either `existing_disputes` (objects with account/status) or `open_dispute_counts`; and ordered `candidates`. Each candidate carries IDs, dates, category/type, `disputed_amount`, customer answers, `timely_reporting`, and `liability_window` (`within_2_business_days`, `within_60_days`, or `after_60_days`). The optional `reported_duplicate_group` makes the helper retain only the earliest transaction in a duplicate group.

Example:

```json
{"as_of_date":"11/14/2025","accounts":[{"account_id":"a1","account_type":"checking","status":"OPEN","tier":"Entry","date_opened":"01/01/2024","has_holds_or_restrictions":false}],"cards":[{"card_id":"c1","account_id":"a1","user_id":"u1","status":"ACTIVE"}],"transactions":[{"transaction_id":"t1","account_id":"a1","date":"11/10/2025","amount":-25.0,"status":"posted"}],"existing_disputes":[],"candidates":[{"transaction_id":"t1","account_id":"a1","card_id":"c1","user_id":"u1","transaction_date":"11/10/2025","discovery_date":"11/11/2025","disputed_amount":25.0,"dispute_category":"duplicate_charge","transaction_type":"online_purchase","card_in_possession":true,"pin_compromised":"no","contacted_merchant":true,"police_report_filed":false,"written_statement_provided":true,"timely_reporting":true,"liability_window":"within_2_business_days"}]}
```

Validate the helper output before acting: only `filable: true` entries may be filed; each includes a computed filing payload and individual card action. Review `blocking_reasons` and `followups`; then use live retrieved records and the procedure above to make the final decision.
