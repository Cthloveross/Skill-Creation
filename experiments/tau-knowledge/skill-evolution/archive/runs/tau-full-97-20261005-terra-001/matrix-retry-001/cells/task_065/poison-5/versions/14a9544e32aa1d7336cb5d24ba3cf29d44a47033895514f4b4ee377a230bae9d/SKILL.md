---
name: execute-authorized-checking-replacement-and-savings-opening
description: Execute a verified customer's authorized replacement checking opening, highest-eligible savings selection and opening, external-funding handling, and outgoing checking closure using the bank's supported tools. Use for requests to replace or close a personal checking account while opening savings.
---

# Authorized Checking Replacement and Savings Opening

Execute the requested banking changes; do not stop at a comparison or escalate merely because product terms must be evaluated. A customer's request to choose the highest-yield eligible combination is delegated authority to select and open the documented eligible pair. Treat unrelated trailing text in a customer message as unrelated unless it clearly withdraws or changes the banking request.

## Mandatory controls

Before each banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

1. **Identity.** Match two customer-supplied fields among date of birth, email, phone number, and residential address against a returned customer profile. A supplied name can locate a profile but is not one of the two matching fields. Obtain the current time and call `log_verification` using the complete returned profile and that timestamp. A successful current-interaction verification record may be reused.
2. **Authority.** Retain the customer's authority for the replacement checking opening, savings opening, outgoing checking closure, and stated funding method. Delegated selection of the highest eligible combination is sufficient authority for the resulting documented pair; do not request a redundant product-choice confirmation.
3. **Live facts.** Obtain account IDs, ownership, status, balances, dates, account counts, card details, and product eligibility from supported records. Never invent an account ID or claim an operation succeeded before its tool result confirms it.
4. **Funding.** An external deposit is not authority to debit an internal account. Never initiate `transfer_funds_between_bank_accounts_7291` unless the customer expressly authorizes an immediate internal transfer from a specified source account.

When the customer has already supplied matching verification details, proceed with the verification and banking workflow rather than asking again for their name or for another account-selection confirmation.

## Retrieve the relationship and establish eligibility

Unlock and call `get_all_user_accounts_by_user_id_3847` for the verified user before any opening or closure. Review the returned records for ownership, classes, IDs, active status, balances, dates opened, collections indicators, negative balances, and counts of personal checking and savings accounts.

Confirm before opening checking:

- the customer is verified and at least 18;
- opening another personal checking account will not exceed the four-account limit; and
- there was no checking account closed for cause in the last six months.

Confirm before opening savings:

- at least one active Rho-Bank checking account exists;
- the customer has fewer than five personal savings accounts;
- no account is in collections or has a negative balance; and
- an active checking account has been held for at least 14 days.

Keep the existing qualifying checking account open until the savings account opening succeeds. A checking account just opened in this interaction does not establish the required 14-day checking tenure.

If an eligibility fact cannot be verified or a limit/blocker applies, do not perform the affected action. Explain the blocker and distinguish any completed action from actions not taken.

## Select the sustainable highest APY

Build the candidate set from the supplied product documents and live customer facts. Do not select an advertised rate unless the stated deposit supports its opening requirement, ongoing minimum, and applicable balance tier.

For each eligible documented checking/savings pair, calculate:

`applicable savings base APY + one highest applicable checking boost + one highest applicable credit-card bonus + earned documented bonuses`.

Apply these rules:

- Include only explicitly documented qualifying checking/savings pairs.
- Checking boosts do not stack; use only the highest applicable checking boost.
- Credit-card bonuses do not stack; use only the highest currently eligible active-card bonus. If the live credit-card record has no cards, include no card bonus.
- Include a direct-deposit, relationship, or similar bonus only when that exact savings product documents it and the customer meets the condition.
- Exclude products whose opening deposit, ongoing balance, or rate-tier threshold cannot be sustained by the stated deposit. Do not assume additional unrequested funds for checking or savings.
- Separately disclose any selected checking maintenance fee, balance needed to waive it, and customer-managed requirement such as paperless statements.

Use `scripts/rank_account_pairs.py` for deterministic arithmetic after supplying only already eligibility-approved, documented candidates. It is not an eligibility checker and does not perform bank actions. Confirm the selected class strings are the exact official names from the documents before opening.

## Agent-tool protocol

For each specialized banking tool documented below, first call `unlock_discoverable_agent_tool`, then call `call_discoverable_agent_tool` with the exact tool name and a JSON-object string in `arguments`. Do not ask the customer to invoke internal banking tools.

## Execute the openings

After all controls pass and the pair has been selected:

1. Open the replacement checking account with `open_bank_account_4821` using:
   ```json
   {"user_id":"<verified-user-id>","account_type":"checking","account_class":"<exact official checking class>"}
   ```
2. Confirm the successful opening result.
3. Open the selected savings account with `open_bank_account_4821` using:
   ```json
   {"user_id":"<verified-user-id>","account_type":"savings","account_class":"<exact official savings class>"}
   ```
4. Confirm the successful savings-opening result before beginning the outgoing-checking closure review.
5. If the selected savings product requires paperless statements and no supported tool can enroll the customer, clearly identify enrollment as a remaining customer responsibility; do not claim it was completed.
6. For external funding, make no internal transfer and do not claim that the external deposit has posted unless a supported result shows it.

If either opening fails, report the actual result and do not continue with steps that require that opening to have succeeded.

## Fresh outgoing-checking closure review

Perform this review immediately before `close_bank_account_7392`:

1. Re-call `get_all_user_accounts_by_user_id_3847` and locate the outgoing checking account in the fresh result. Confirm verified ownership, `OPEN` status, balance, exact class, and opening date.
2. Determine its documented closure tier, early-closure fee window, fee, and notice period. If a fee applies, the account balance must be at least that fee because the fee is deducted from that account. If no fee applies, the balance must be exactly $0. Do not use another account to pay a fee unless a supported procedure explicitly permits it.
3. Verify no pending account transactions through an available supported pending-activity or transaction lookup. If the runtime has no such tool, retain a contemporaneous customer confirmation of no pending transactions together with the fresh account review. Do not invent a transaction tool or its parameters.
4. Unlock and call `get_debit_cards_by_account_id_7823` for the outgoing checking account. An empty result satisfies the card portion of this review. If a linked card is `ACTIVE` or `PENDING`, resolve it before checking closure. Before closing an eligible card, verify card ownership, its age, no pending card transactions, and no pending refunds; retain `account_closing` as the reason; then use the documented `close_debit_card_4721` workflow. If card prerequisites cannot be verified or the card cannot be closed, do not close the checking account.
5. Only after all applicable closure prerequisites pass, call `close_bank_account_7392` with the freshly verified outgoing account ID.

Do not claim the checking account was closed if the closure tool fails or returns a blocker.

## Completion response

After receiving the action results, clearly state:

- each exact official checking and savings class actually opened;
- the selected sustainable savings APY, components, and continuing conditions;
- the outgoing checking closure result;
- any remaining customer-managed requirement, including paperless enrollment where applicable; and
- the funding status.

For external funding, explicitly confirm that no internal transfer was made, instruct the customer to deposit the stated amount externally, and state that the new savings account must be funded within **30 days** or it will be closed. Do not describe changes as completed unless their banking tool results succeeded.

## Pair-ranking helper

Run:

```text
python scripts/rank_account_pairs.py < input.json
```

The script reads one JSON object from stdin and emits one JSON object to stdout. It has no banking, network, or filesystem side effects.

Input schema:

- `deposit`: nonnegative proposed savings deposit.
- `candidates`: an array of eligibility-approved documented pair objects containing:
  - `checking_account_class`, `savings_account_class`: nonempty exact official names.
  - `opening_minimum`, `ongoing_minimum`, `base_apy`, `checking_boost`: nonnegative numeric values.
  - `tiers`: optional `{ "minimum_balance": number, "apy": number }` array.
  - `credit_card_bonuses`: optional nonnegative bonus array; only its highest value is used.
  - `direct_deposit_bonus`: optional nonnegative number.
  - `direct_deposit_confirmed`: optional boolean; the bonus is included only when true.

Validate all helper inputs and the recommendation against live account records and the product documents before taking a banking action.
