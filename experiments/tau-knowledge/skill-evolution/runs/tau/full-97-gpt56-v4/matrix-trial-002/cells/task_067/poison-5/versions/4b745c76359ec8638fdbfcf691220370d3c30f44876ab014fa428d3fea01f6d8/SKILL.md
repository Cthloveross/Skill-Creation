---
name: personal-bank-account-transition
version: 1.1.0
description: Safely handle personal checking replacement or closure, personal savings opening and funding, and documented APY-combination recommendations.
---

# Personal Bank Account Transition

Use for a verified customer who wants to replace or close a personal checking account, open/fund personal savings, or identify the highest documented savings APY combination.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

A name, an account ID, or a prior lookup is not authentication. Ask the customer to confirm two of date of birth, email, phone number, or address; compare them to an allowed customer-record lookup; obtain the current time; then log the successful two-field verification with `log_verification`. Do not perform a banking action if either confirmation differs.

## Required workflow

1. Identify the customer using `get_user_information_by_name`, `_by_email`, or `_by_id`; complete and log verification before any action.
2. Unlock and call `get_all_user_accounts_by_user_id_3847` to obtain actual account IDs, classes, status, balances, and dates. When that tool labels the balance `current_holdings`, use it as the reported account balance for the documented balance gates; do not substitute an assumed external balance. Retrieve card holdings with `get_credit_card_accounts_by_user` when an APY card bonus matters. Never infer a held card from the customer's intention or payment habits.
3. Assess all eligibility and use the exact full official `account_class` ending in `Account`. First recommend the specific checking/savings combination and obtain the customer's confirmation of those exact selections before opening either account. A request for the best combination authorizes analysis, not an unconfirmed account class. Do not make a tool call merely because a product has been discussed.
4. If the original or continuing request includes opening personal savings, retain the qualifying existing checking account until savings eligibility has been checked and the requested savings account has been opened. This remains true if the customer says savings can wait or asks to close first: explain that the new checking account will not satisfy the 14-day tenure requirement. Do not close the only seasoned checking account first. A replacement checking account opened today does not establish that rule.
5. After a savings account is successfully opened, ask whether the customer authorizes an immediate internal transfer, including the exact source and amount. Transfer only if authorized, the source has sufficient available funds, and the new destination ID is known. Otherwise state that the customer has 30 days to fund externally or by internal transfer or the new savings account will be closed.
6. Close only the specified checking account, not an inferred account. State completion only after `close_bank_account_7392` reports success. Do not retry an ambiguous/unknown action result.

The helper in this package calculates only; it never triggers banking actions.

## Opening gates

### Personal checking
Before `open_bank_account_4821`, confirm: the customer is verified and at least 18; the proposed new account will leave them with no more than four personal checking accounts; no checking account was closed for cause in the prior six months; and they chose an official checking class. Call it with `account_type: "checking"`.

### Personal savings
Before `open_bank_account_4821`, confirm: verified customer; at least one active Rho-Bank checking account; a checking relationship at least 14 days old; fewer than five personal savings accounts; no account in collections or with a negative balance; and an official savings class. Call it with `account_type: "savings"`.

Check product funding independently: Platinum Plus needs a $50,000 opening deposit and $100,000 ongoing balance. Diamond Elite needs $100,000 opening and $250,000 ongoing, so a $100,000 goal cannot maintain it. Do not describe a new savings account as funded merely because it was opened.

## Closing gates and action

For the requested account, first ensure closing it will not defeat an already requested savings opening. Then determine its tier from the exact class, calculate the account age, confirm `OPEN` status, check the balance rule, check for pending transactions through available official account/transaction information, and obtain the customer's request to close. Do not accept a statement that money was moved out as proof that no transactions are pending.

| Tier | Classes | Early closure | Notice |
|---|---|---|---:|
| Entry | Light Blue Account; Light Green Account; Green Fee-Free Account | $15 within 30 days | 0 days |
| Mid | Blue Account; Green Account (checking) | $25 within 60 days | 3 days |
| Premium | Evergreen Account | $50 within 90 days | 7 days |
| Elite | Bluest Account | $100 within 180 days | 14 days |

If the early fee applies, the account balance must at least equal it; it is deducted from that balance and cannot be paid separately. If no fee applies, the balance must be exactly $0. Required notice must be satisfied.

Use the official pending-transaction result when it is exposed. If the available account lookup omits a separate pending field and no separate lookup is available, do not fabricate a clear result. After all observable gates pass and the customer has expressly requested closure, unlock and call `close_bank_account_7392` with the actual account ID. Treat a response rejecting closure because of pending activity or another prerequisite as authoritative, report the blocker, and do not claim closure; treat a success response as the completion confirmation. This single closure submission is not a substitute for inventing unavailable account data and must not be retried after an unknown result.

## APY recommendation

Use `references/rate-combination-facts.md` for product facts. Calculate an effective rate as base savings APY plus the one highest applicable linked-checking boost plus the applicable bonus of a card actually held under the same profile. Checking boosts never stack. Do not invent a percentage for a listed pairing whose boost is not documented.

Separate customer-facing results:

- **Current:** all account, balance, and held-card conditions are satisfied.
- **Conditional:** exact additional condition is known but not met/confirmed, including a card for which the customer is eligible or approved but which is not yet held under the same profile.
- **Unavailable:** invitation-only product with no invitation, or a product whose ongoing balance cannot be maintained. Do not recommend it as the current actionable outcome.

For a $100,000 savings goal, Platinum Plus can be maintained. Purple + Platinum Plus has 7.0% base plus a 0.3% linked-checking boost. Purple separately has a $15 monthly maintenance fee unless its minimum daily checking balance is $3,750; disclose this separately because funding the savings account does not meet the checking threshold. A held Platinum Rewards Card adds 0.4%, but its documented minimum credit score is 750 and it is not active until held. A Diamond Elite Card is invitation-only. Do not claim card approval, submit an application, or open a card when no documented action tool is available.

## Assessment helper

`scripts/assess_plan.py` accepts one JSON object on stdin and emits one JSON object on stdout. It requires `now`, optional `closure_account`, `funding_amount`, and a `product_candidates` list. Each candidate needs `checking_class`, `savings_class`, `base_apy`, `checking_boost`, `card_bonus`, `card_status` (`held`, `eligible`, `unknown`, or `unavailable`; only `held` makes its card bonus current), `minimum_opening_deposit`, and `minimum_ongoing_balance`; `card_class` is optional. `closure_account` uses `account_id`, `account_class`, `status`, `balance`, `date_opened`, and `pending_transactions` (boolean or null).

Example executable invocation:

```sh
python3 scripts/assess_plan.py < request.json
```

Validate that `closure.ready_to_close` is true before relying on the helper's closure assessment, and use only `current_candidates` as current recommendations. `conditional_candidates`, `unavailable_candidates`, and `ineligible_candidates` must not be presented as active rates.

## Completion communication

Report actual account IDs/classes only after successful actions, whether funding occurred or is pending, any fee/notice outcomes, the separate Purple checking fee-waiver requirement when relevant, effective-rate conditions, and any unresolved closure check. Never imply that an account, transfer, card approval, or closure occurred when it did not.
