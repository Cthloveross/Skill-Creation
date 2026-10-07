---
name: banking-account-transition-and-yield-planning
description: Safely recommend and carry out a customer-requested checking-account transition, savings-account opening and funding, optional overdraft-protection setup, and APY comparison. Use when account closures, openings, transfers, card-linked APY bonuses, or product eligibility must be coordinated.
---

# Banking Account Transition and Yield Planning

Use this Skill for requests to replace or close a checking account, open a checking and/or savings account, fund savings, enable overdraft protection, compare APY options, or evaluate a card-linked savings bonus.

> Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Operating rules

- Treat a stated preference, a broad request to "swap," and a request for a recommendation as distinct from final authorization for each irreversible or financial action.
- Never infer an account ID, account status, balance, tenure, funding source, card approval, or that a product pairing supports an APY boost or overdraft transfer.
- Do not promise an APY bonus from a credit-card application. It is conditional on approval, activation/eligibility, and the card and savings account being held as the applicable product terms require.
- Use the current product documentation for account-specific opening deposits, ongoing minimums, APYs, tier thresholds, link bonuses, card bonuses, overdraft availability, fees, and closure rules. Product names must be passed exactly as documented.
- A checking-linked APY boost and a credit-card APY bonus are separate components. Where policy says only the highest bonus in a category applies, do not stack bonuses within that category.
- A savings account used as overdraft funding must be eligible to be linked to the selected checking account; an APY-boost pairing does not by itself prove overdraft-link eligibility.
- Never make a bank action merely because a local script recommends it. Scripts only organize public facts and identify blockers.

## 1. Verify and gather the actionable facts

Before any action:

1. Identify the customer using an approved lookup.
2. Verify identity by having the customer confirm two of the profile fields required by the runtime, compare them to the customer record, obtain the current timestamp, then create the required verification log. A statement that verification is "current" does not substitute for the runtime's required identity-verification procedure.
3. Confirm the customer has authority over every account being closed, funded, or linked.
4. Look up—not merely rely on a customer assertion—the relevant account IDs, owners, classes, statuses, available balances, holds/pending transactions, account-open dates, and existing account counts when the runtime provides a lookup. If a needed lookup is not available, do not guess; request the necessary identifier/details or explain that the action cannot yet be completed.
5. Record the requested target balance, source of funds, desired checking behavior (including whether automatic overdraft transfers are required), and whether the customer wants an immediate internal transfer or an external deposit.

## 2. Determine the best supported rate

Research only documented, currently applicable products. For each candidate, establish all of the following before presenting it as an option:

- the base APY applicable at the customer's intended balance and any tier threshold;
- the account's opening and ongoing balance requirements;
- whether the proposed checking account supports automatic overdraft-protection transfers and the per-transfer fee;
- whether that savings account can be the selected checking account's linked overdraft funding source;
- any documented checking/savings APY boost for that exact pairing;
- each applicable card bonus and the rule governing multiple cards or bonuses;
- relationship bonuses and their exact qualifications; and
- card eligibility/application requirements and the fact that approval is not guaranteed.

Use `scripts/select_apy_plan.py` to compare researched candidate data deterministically. Feed it facts extracted at runtime; do not hardcode customer IDs or an already-derived answer into the input. Treat its `conditional_on_card_approval` field as a required disclosure.

When telling the customer the outcome, show the arithmetic in percentage points, identify every condition, mention any overdraft-transfer fee, and distinguish a documented maximum from a rate that is only available after a card is approved and maintained.

## 3. Validate eligibility and sequence the actions

Run `scripts/preflight.py` with current, verified facts to identify missing conditions. A positive result is a checklist aid, not a replacement for the product-specific procedure.

For the standard personal-account rules documented for this workflow:

- Checking: verified customer, age requirement met, within the checking-account count limit, and no disqualifying closure history.
- Savings: verified customer, an active checking account with the required tenure, below the savings-account limit, and no collections or negative balances.
- Internal transfer: source and destination are distinct, owned by the customer, ACTIVE or OPEN, the amount is positive USD, the source has sufficient available funds, and the customer authorized the transfer.
- Checking closure: the account is OPEN, has no pending transactions, and satisfies the applicable early-closure fee/balance rule. If no applicable fee is due, its current holdings must be zero; if a fee is due, its balance must at least cover that fee.

Sequence actions so that an existing eligible checking account remains open until all savings-opening conditions that depend on its active status and tenure have been satisfied. In particular, do not close the customer's only sufficiently tenured checking account before opening a savings account that requires such an account.

Before each action, obtain specific final confirmation of: account to close, selected checking and savings classes, funding amount and source/destination, overdraft-link enrollment and fee, and any card-application step. If the customer declines immediate funding, clearly provide the documented funding deadline and closure consequence for an unfunded new savings account.

## 4. Perform only supported bank actions

1. Unlock and call only the documented internal account-opening tool after the relevant eligibility checks pass. Set the account type and exact official account class required by the product procedure.
2. If the customer explicitly authorizes immediate funding and all transfer preconditions pass, unlock and call the documented internal transfer tool with the verified account IDs and a positive USD amount. Confirm the result and guard against duplicate transfers.
3. Enable overdraft protection only through the documented procedure or available settings workflow, after the customer accepts the fee disclosure and the linked funding account is verified eligible. If no agent tool exists for enrollment, explain the documented self-service path rather than inventing a tool call.
4. Close the old account only after its specific closure prerequisites are verified and the new-account/funding sequence is safely complete. Use the documented closure tool if it is available.
5. If a card application has no available agent action, provide the documented application requirements and direct the customer to the supported application route. Do not claim that a card was opened, approved, or linked.

After every tool call, inspect the returned status. Do not repeat an operation whose result is unknown. Confirm the created account details, funding status, any linked-service status, applicable fees, and any remaining customer step.

## Script interfaces

### `scripts/select_apy_plan.py`

Reads one JSON object from stdin and writes one JSON object to stdout.

Input schema:

```json
{
  "balance": 10000,
  "require_overdraft_transfer": true,
  "savings": [
    {
      "account_class": "Official Savings Account Name",
      "base_apy": 0.0,
      "eligible_for_balance": true,
      "minimum_opening_deposit": 0,
      "minimum_ongoing_balance": 0,
      "relationship_bonus": 0.0,
      "relationship_bonus_eligible": false,
      "card_bonuses": {"Official Card Name": 0.0}
    }
  ],
  "checking": [
    {
      "account_class": "Official Checking Account Name",
      "eligible": true,
      "supports_overdraft_transfer": true,
      "overdraft_transfer_fee": 0.0,
      "overdraft_link_eligible_savings": ["Official Savings Account Name"],
      "savings_bonuses": {"Official Savings Account Name": 0.0}
    }
  ],
  "cards": [
    {"card_class": "Official Card Name", "eligible": true, "approval_required": true}
  ]
}
```

All APY fields are percentage points, such as `0.45` for +0.45%. Include only researched and currently valid candidate data. A wildcard `"*"` in `overdraft_link_eligible_savings` is allowed only if product documentation explicitly establishes it. The output contains ranked eligible combinations, APY components, and a `conditional_on_card_approval` flag.

Example invocation in a supported runtime:

```sh
python3 scripts/select_apy_plan.py < researched_options.json
```

Validate that `ok` is true, the selected candidate contains every requested feature, and its components correspond to the current documentation before relying on it.

### `scripts/preflight.py`

Reads one JSON object from stdin and writes a JSON checklist to stdout. It checks generic account-opening, transfer, and closure conditions from supplied verified facts.

```json
{
  "identity_verified": true,
  "authority_confirmed": true,
  "ownership_confirmed": true,
  "checking_open": {"eligible": true},
  "savings_open": {"eligible": true},
  "transfer": {"requested": true, "source_open": true, "destination_open": true, "distinct_accounts": true, "sufficient_available_funds": true, "amount_positive_usd": true, "authorized": true},
  "closure": {"requested": true, "status_open": true, "no_pending_transactions": true, "current_holdings": 0, "applicable_early_closure_fee": 0, "final_confirmation": true}
}
```

An omitted or non-true prerequisite is a blocker. Check `ready` and each action's blockers, then perform the product-specific review described above.
