---
name: bank-account-switch-and-yield-recommendation
description: Safely recommend, open, fund, and/or close personal bank accounts when a verified customer wants to replace a checking account and maximize savings APY. Use for account comparisons and account-opening/closure workflows requiring eligibility, account-state, balance, and confirmation checks.
---

# Bank Account Switch and Yield Recommendation

Use this Skill to separate an informational yield recommendation from account-changing actions. A customer delegating product comparison is not, by itself, authorization to transfer money or close an account. Record the selected products explicitly and obtain the confirmations required below before each consequential action.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Inputs and available operations

At runtime, use the supplied customer conversation, account/product documentation, and banking tools. Do not assume that a customer-provided balance is held at a particular account, that an account is open, or that a previous account opening or transfer succeeded.

Relevant discoverable agent tools may include:

- `get_all_user_accounts_by_user_id_3847` for bank-account ownership, class, status, balance, and opening date.
- `open_bank_account_4821(user_id, account_type, account_class)` for an eligible, confirmed account opening.
- `transfer_funds_between_bank_accounts_7291(source_account_id, destination_account_id, amount)` for authorized transfers between the customer's distinct active/open accounts.
- `close_bank_account_7392` for a checking-account closure after all closure checks pass.

Unlock an agent-discoverable tool only when its supplied documentation identifies it. Invoke it only with documented parameters. Never tell the customer to invoke an internal agent tool.

## 1. Authenticate and establish authority

1. Identify the customer using the provided identifier (such as a profile email) and retrieve the matching customer record.
2. Before any state-changing tool call, verify **two of four** identity fields: date of birth, email, phone number, and address. A lookup result alone is not a second customer confirmation. Ask for missing confirmation(s) without exposing full values unnecessarily.
3. After two fields are confirmed, obtain the current timestamp and call `log_verification` with the complete returned customer record and timestamp.
4. Confirm the requesting customer is the primary/authorized owner of every affected account. Do not act on a third-party request.

If identity or authority cannot be verified, provide general information only and do not perform bank actions.

## 2. Build an eligible APY comparison

Use the current balance the customer intends to keep in savings and current product disclosures. For each candidate savings product:

1. Exclude products whose opening deposit, ongoing minimum, age/relationship condition, or required account eligibility is not met.
2. Apply the APY tier matching the stated balance. Do not advertise a higher tier that the balance does not reach.
3. Identify qualifying linked checking/savings pairs only. A checking boost is available only when the documentation explicitly lists that pairing.
4. Where multiple checking-account boosts apply, use only the highest applicable checking boost; do not add checking boosts together.
5. Where multiple credit-card bonuses apply, use only the highest applicable card bonus; do not add card bonuses together.
6. Add distinct bonus categories only when the disclosures say they stack. Check the customer’s actual active card accounts before claiming a card bonus.
7. Clearly distinguish the savings APY from a checking APY, fee waiver, rebate, or other perk.

Use `scripts/rank_apy_options.py` when the applicable base rates, tiers, and bonuses have been transcribed from the live disclosures. It performs deterministic ranking only; it does not prove product eligibility or initiate banking actions.

Explain the winning eligible combination, its effective APY calculation, material balance requirements, and assumptions. If facts are insufficient or disclosures conflict, state that a definitive highest-APY recommendation cannot yet be made and obtain the needed account/product facts.

### Calculator input/output

Run `scripts/rank_apy_options.py` with JSON on stdin (or through the Skill script runner):

```json
{
  "savings_balance": "6000.00",
  "options": [
    {
      "savings_account_class": "Official savings product name",
      "checking_account_class": "Official checking product name",
      "base_apy": "4.0",
      "minimum_opening_deposit": "100",
      "minimum_ongoing_balance": "500",
      "checking_boosts": ["0.55"],
      "card_bonuses": ["0.5"],
      "other_stackable_bonuses": ["0.025"],
      "eligible": true,
      "notes": ["optional disclosure note"]
    }
  ]
}
```

All APY values are percentage points (for example, `0.55` means +0.55 percentage points), not decimal rates. The script emits:

```json
{
  "eligible_ranked": [{"effective_apy": "...", "...": "..."}],
  "ineligible": [{"savings_account_class": "...", "reasons": ["..."]}],
  "winner": {"...": "..."}
}
```

An empty `winner` means no eligible option was supplied. Validate that each option uses official account names, balances are nonnegative, and every supplied bonus has already been confirmed as applicable. The output selects the greatest single checking and card bonuses, then adds distinct stackable bonuses.

## 3. Obtain actionable consent

After presenting a recommendation, ask the customer to confirm the exact official checking and savings account names to be opened. Separately obtain clear authorization for each of the following, as applicable:

- opening the checking account;
- opening the savings account;
- closing the identified existing account; and
- a specified internal transfer, including source account and amount.

Do not infer transfer authorization from approval to open an account. If the customer wants to keep funds externally or has not identified an eligible internal source, explain the funding deadline/process from the applicable disclosure and do not transfer.

## 4. Open accounts only after checks pass

### Checking account

Before opening a personal checking account, verify the customer is verified, at least 18, within the checking-account-count limit, and has no checking account closed for cause during the applicable lookback period. Confirm the exact full official checking `account_class` ending in `Account`. Then call the documented opening tool with `account_type` set to `checking`.

### Savings account

Before opening a personal savings account, retrieve current accounts and verify all documented requirements: verified identity, at least one active checking account, fewer than the maximum permitted personal savings accounts, no collections or negative balances, and minimum checking tenure. Also check the chosen savings product's opening deposit and ongoing balance requirements. Confirm the full official savings `account_class` ending in `Account`, then call the documented opening tool with `account_type` set to `savings`.

If a checking account is being replaced and savings eligibility requires an active checking account, open the approved replacement checking account first. Do not close the old account until the replacement and any required funding steps are complete.

Immediately read or retain the returned new account ID and status. If opening fails or returns ambiguity, stop and explain the result; do not assume an account was created or attempt a duplicate opening.

## 5. Funding transfer

Perform an internal funding transfer only after confirming:

- the customer explicitly authorized this exact transfer;
- the source and newly opened destination are distinct accounts owned by the customer;
- both have ACTIVE or OPEN status;
- the source has sufficient available funds after applicable restrictions; and
- the amount is a positive USD amount and meets the account's required opening deposit.

Call the documented transfer tool once. Verify the returned status and updated posting information before telling the customer it completed. On any uncertain, failed, or unknown result, do **not** retry automatically and do not create a duplicate transfer. Explain the outcome and offer safe next steps.

## 6. Close the former checking account last

A closure requires its own current account lookup and explicit customer authorization. Verify that the exact account is OPEN, has no pending transactions, and meets the tier-specific closure fee and notice-period requirements. For an early closure fee, verify the balance can cover it; otherwise verify the balance is zero as required. Confirm the account ID/class, applicable fee, notice period, and final disposition with the customer before calling the closure tool.

If a notice period applies, communicate that the closure cannot be represented as immediate. If preconditions fail, do not close the account; explain the blocker and retain the replacement account.

## Completion message

Report only actions that the banking tools actually confirmed. Include the official account classes opened, funding status or deadline, transfer amount/source/destination if completed, closure status (including any notice period), and key effective-APY assumptions. Never fabricate account IDs, final balances, eligibility, fees, or completion.
