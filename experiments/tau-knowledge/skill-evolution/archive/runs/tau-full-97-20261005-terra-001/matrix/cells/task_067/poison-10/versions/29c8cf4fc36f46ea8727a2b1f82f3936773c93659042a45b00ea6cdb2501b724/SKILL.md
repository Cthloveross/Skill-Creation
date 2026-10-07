---
name: personal-checking-transition-and-apy-planning
description: Safely verify, close an eligible personal checking account, plan a replacement checking account, and compare eligible checking/savings/card APY combinations. Use for a customer who wants to replace a checking account, open savings, or maximize deposit APY.
---

# Personal Checking Transition and APY Planning

## Safety control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Do not treat a profile lookup, a name, or preexisting tool observations as authentication. Obtain the customer's confirmation of two of the four profile fields (date of birth, email, phone number, address), compare them to the profile, obtain the current time, and call `log_verification` before any account, card, transfer, or closure action. The customer must be the owner or otherwise have documented authority.

## Workflow

1. **Clarify scope and authorization.** Identify the exact existing account and whether the customer currently authorizes closure. For a replacement account, obtain confirmation of the exact official `account_class` before opening it. For a fee-bearing closure, explain the applicable fee and obtain confirmation to proceed after its amount is known.
2. **Authenticate and establish ownership.** Look up the customer only to identify a record. Ask the customer to confirm two profile fields without volunteering them. After a successful match, call `get_current_time` and `log_verification` with the complete stored profile record and timestamp. Confirm that the selected account belongs to the authenticated customer.
3. **Retrieve and inspect accounts.** Unlock and call `get_all_user_accounts_by_user_id_3847` with the authenticated `user_id`. Record account ID, type, class, status, balance/current holdings, and opening date. For a replacement checking account, count personal checking accounts and verify the customer is age 18 or older, verified, has fewer than four personal checking accounts, and has no checking account closed for cause in the prior six months. Do not open an account until every opening requirement and the account-class selection are confirmed.
4. **Assess the requested closure.** For the selected checking account, unlock and call `get_bank_account_transactions_9173`; no transaction may have status `pending`. Unlock and call `get_debit_cards_by_account_id_7823`; every associated debit card must already be closed before the checking account is closed. If a card must be closed, follow the separate debit-card closure workflow first, including its status, pending transaction/refund, ownership, and card-age requirements. Do not use closure to bypass a card blocker.
5. **Determine the closure terms.** The documented personal-checking tiers are:

   | Tier | Account classes | Early closure term | Notice |
   |---|---|---:|---:|
   | Entry | Light Blue Account; Light Green Account; Green Fee-Free Account | $15 if closed within 30 days | 0 days |
   | Mid | Blue Account; Green Account (checking) | $25 if closed within 60 days | 3 days |
   | Premium | Evergreen Account | $50 if closed within 90 days | 7 days |
   | Elite | Bluest Account | $100 if closed within 180 days | 14 days |

   Determine age from the opening date and the current date. If an early closure fee applies, balance must be at least the fee because it is deducted directly from the account; there is no alternative payment method. If no fee applies, the balance must be exactly $0. Account status must be `OPEN`. Do not infer closure terms for an account class not listed in this table; obtain the applicable policy.
6. **Close only when all blockers are cleared.** For a closure request that satisfies identity, authority, ownership, `OPEN` status, cards closed, no pending transactions, fee/balance rule, notice rule, and confirmation requirements, unlock and call `close_bank_account_7392` with the documented tool parameters. Report the result; do not claim closure based solely on a request.
7. **Open a replacement checking account, if still desired.** Reconfirm the exact class and customer authorization after closure status is known. Unlock and call `open_bank_account_4821` with the authenticated `user_id`, `account_type` set to `checking`, and the full official class name ending in `Account`. Confirm tool success and disclose any relevant funding or balance requirements documented for that product.
8. **Handle savings separately.** A personal savings opening requires: verified identity; at least one active Rho-Bank checking account held for at least 14 days; fewer than five personal savings accounts; and no account in collections or with a negative balance. Therefore, do not close a customer's only qualifying checking account and promise immediate savings eligibility without checking whether another active, 14-day checking account exists. After selection and authorization, open savings with `open_bank_account_4821` using `account_type: savings` and the complete official account class. If the customer authorizes an internal opening-deposit transfer, first validate both account statuses, same ownership, positive USD amount, distinct IDs, and sufficient source funds, then use `transfer_funds_between_bank_accounts_7291`.

## APY recommendation method

Give a product recommendation, not a guarantee of eligibility. Separate confirmed APY from conditional APY that depends on approval, invitation, eligibility, or funding the customer has not confirmed.

For a customer with $100,000 available for savings, the documented facts support this analysis:

- Diamond Elite savings has a 7.5% base APY and a $100,000 opening minimum, but requires a $250,000 ongoing minimum balance. It is not a sustainable recommendation at a $100,000 balance unless the customer will meet its ongoing requirement.
- Platinum Plus savings has a 7.0% base APY, a documented $50,000 opening deposit, and a $100,000 ongoing balance requirement.
- Purple checking paired with Platinum Plus savings provides a 0.3% linked-checking boost.
- On Platinum Plus savings, the documented Diamond Elite Card bonus is 0.6%. Credit-card bonuses do not stack: only the highest applicable card bonus applies. A credit-card bonus can stack with a qualifying checking boost.
- Diamond Elite Card membership is invitation-only and considers a credit score of at least 780. Never present its bonus as confirmed unless invitation, approval, active-card status, and same-profile linkage are established.

Thus, subject to checking-opening eligibility and product availability, Platinum Plus savings at a maintained $100,000 can be described as 7.3% with the documented Purple linked-checking boost; it can be described as up to 7.9% only conditionally if the customer is eligible for and holds the Diamond Elite Card under the same profile. Do not recommend Bluest merely because its checking APY is 2.25% when the objective is savings APY: the documented Platinum Plus linked pairing is Purple, and Bluest also has a documented $112,500 daily balance requirement for benefits.

Use `scripts/rank_apy_plans.py` when comparing dynamically supplied, documented candidates. It applies only the highest eligible card bonus and does not invent compatibility or eligibility.

## Closure assessment helper

Use `scripts/evaluate_closure.py` after collecting the relevant account, transaction, and card information. It is a decision aid only; it does not perform any banking action or replace required identity and ownership checks.

Input JSON schema:

```json
{
  "account": {"account_id": "string", "account_class": "string", "status": "OPEN", "balance": "0.00", "date_opened": "YYYY-MM-DD"},
  "as_of": "YYYY-MM-DD",
  "identity_verified": true,
  "authority_verified": true,
  "ownership_verified": true,
  "transactions_checked": true,
  "transactions": [{"status": "posted"}],
  "cards_checked": true,
  "cards": [{"card_id": "string", "status": "CLOSED"}],
  "fee_confirmation_obtained": true
}
```

`balance` may instead be named `current_holdings`. Dates may be `YYYY-MM-DD`, `MM/DD/YYYY`, or a timestamp beginning with either format. The script emits an `eligible` boolean, tier/fee/notice details when known, and explicit blockers.

Example runnable call:

```sh
python scripts/evaluate_closure.py <<'JSON'
{"account":{"account_id":"account-id","account_class":"Light Blue Account","status":"OPEN","balance":"0.00","date_opened":"2024-01-01"},"as_of":"2025-01-01","identity_verified":true,"authority_verified":true,"ownership_verified":true,"transactions_checked":true,"transactions":[],"cards_checked":true,"cards":[]}
JSON
```

Validate that `eligible` is true before considering the close tool. If `fee_applies` is true, validate `balance >= early_closure_fee`; otherwise validate that balance is zero. An unknown tier, date, inspection result, or confirmation is a blocker rather than an assumption.

## APY ranking helper

`scripts/rank_apy_plans.py` accepts a list of already-documented compatible plans and returns the highest confirmed effective savings APY among plans funded by the available amount. Each plan supplies a savings deposit and its requirements, optional checking funding/requirements and boost, and eligible or unverified card bonuses. It outputs excluded plans and conditional opportunities so the executor can explain why a headline rate is not presently available.

```sh
python scripts/rank_apy_plans.py <<'JSON'
{"available_funds":"100000","plans":[{"id":"documented-plan","savings":{"base_apy_pct":"7.0","deposit":"100000","opening_min":"50000","ongoing_min":"100000"},"checking":{"deposit":"0","opening_min":"0","ongoing_min":"0","boost_pct":"0.3","eligible":true},"card_bonuses":[{"id":"eligible-card","apy_pct":"0.6","eligible":true}]}]}
JSON
```

The returned `effective_apy_pct` must equal base APY plus the eligible checking boost plus only the single highest eligible card bonus. Re-verify all product terms, invitations, approvals, and linkage before conveying a result or taking any banking action.

## Failure handling

- Stop and explain the unmet requirement; do not attempt the corresponding banking tool.
- If identity, authority, ownership, account data, closure history, collection status, or product eligibility cannot be verified with available information, request the necessary verification or use the approved escalation path.
- If the customer asks to defer savings, complete only the authorized and eligible checking workflow; preserve the savings recommendation as informational.
- If a tool reports failure, report the failure accurately, refresh the relevant prerequisites where appropriate, and do not claim success or repeat a financial action without renewed validation and authorization.
