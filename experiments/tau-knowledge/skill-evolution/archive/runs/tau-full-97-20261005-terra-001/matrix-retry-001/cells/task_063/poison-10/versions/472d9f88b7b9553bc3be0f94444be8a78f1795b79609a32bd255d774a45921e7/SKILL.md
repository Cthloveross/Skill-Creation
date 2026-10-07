---
name: personal-savings-and-card-yield-planning
description: Assess, recommend, and, when all controls are satisfied, open and fund a Rho-Bank personal savings account while explaining the card-linked APY option. Use for customers seeking savings yield optimization, opening deposits, or card-and-savings combinations.
---

# Personal Savings and Card Yield Planning

Use this Skill to turn a customer’s savings/yield request into a compliant recommendation and, only when fully verified and authorized, a savings-account opening and internal funding workflow. It distinguishes product advice from account-opening actions and does not represent a credit-card application as approved or submitted unless a documented, available tool completes it.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Supported recommendation

Use `references/product-terms.md` as the product source. For a customer who requires mailed paper statements and wants an explicitly credit-checked card, the supported conditional pairing is:

- **Silver Plus Account** savings: paper statements are available with a $0.00 monthly paper-statement fee; paperless statements are not required.
- **Silver Rewards Card**: documented minimum credit score is 680, its application includes consent to a credit check, and it provides a +0.15% Silver Plus APY bonus when both products are under the same customer profile.

Explain that a stated approximate score is not an approval decision. Do not recommend Gold Rewards when the customer lacks the required Rho-Bank+ subscription or does not meet its 720 minimum score. Do not recommend Green Account (savings) if paper statements are required because it requires paperless statements.

For Silver Plus, disclose the $1,000 opening deposit, $2,500 ongoing minimum balance, possible $8.00 monthly maintenance fee below that balance, 3.0% Tier 1 APY below $15,000, 4.5% Tier 2 APY at or above $15,000, daily compounding, monthly interest crediting, and up to 15 free monthly withdrawals. A linked qualifying credit card uses only the highest single credit-card APY bonus; card bonuses do not stack.

A direct-deposit bonus of +0.25% applies while direct deposit is active. The supplied product material does not define qualifying direct deposit or establish whether setup changes an existing checking account. State that limitation rather than inventing eligibility or instructions, and direct the customer to account settings or the applicable direct-deposit documentation for confirmation.

Use `scripts/annual_apy_dollars.py` to calculate a transparent one-year APY comparison. This script treats APY as an annual yield and calculates `principal × APY / 100`; do not apply a second daily-compounding calculation to a stated APY.

## Identity, authority, and eligibility workflow

1. **Verify identity and authority before action.** A name, lookup result, or user ID alone identifies a record but does not authenticate the requester. Retrieve the customer record using the available lookup method. Have the requester confirm at least two of the four profile fields: date of birth, email, phone number, and address. Match them to the retrieved record, obtain the current timestamp with `get_current_time`, then call `log_verification` with the complete returned profile and timestamp. Confirm that the verified person is acting for themself before accessing or moving funds.
2. **Retrieve accounts.** Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified user ID. Its returned account data is needed to identify account IDs, types, classes, statuses, balances, and opening dates.
3. **Evaluate all opening controls.** Confirm all of the following from account data and customer authorization:
   - at least one active Rho-Bank checking account has been open for at least 14 days;
   - fewer than five existing personal savings accounts;
   - no account is in collections and no account has a negative balance;
   - the exact source checking account is owned by the verified customer, active, and has enough available balance for the requested transfer;
   - the requested deposit meets the product’s opening minimum, and the customer understands ongoing balance, applicable fees, and limits;
   - the customer selected the exact official account class ending in `Account`, and separately authorized opening and the exact transfer amount.

   Convert the account-tool result into structured data and use `scripts/evaluate_savings_opening.py` as a deterministic checklist. The script reports missing or failing evidence; it does not replace review of ambiguous statuses, account ownership, or personal-account classification.
4. **Stop on any unmet or unknown control.** Do not open or transfer. Explain the specific blocker. If the savings-account count, collections status, balance, status, opening date, ownership, or available balance cannot be established, treat it as unresolved rather than assuming eligibility.
5. **Open the savings account.** After every prerequisite and explicit product confirmation is complete, unlock and call `open_bank_account_4821` with the verified `user_id`, `account_type` set to `savings`, and the exact confirmed full class, such as `Silver Plus Account`. Record the newly returned account ID.
6. **Fund only after successful opening.** If the customer authorized an immediate deposit, re-confirm the source account, destination ID, exact amount, available balance, and transfer details. Unlock and call `transfer_funds_between_bank_accounts_7291` with the owned active checking `source_account_id`, newly opened savings `destination_account_id`, and authorized amount. Do not transfer if the opening call failed or did not return a destination account ID.
7. **Complete the response.** Give the new account details and funding outcome. If the customer declines immediate funding, state that the account must be funded within 30 days through an internal transfer or external deposit or it will close.

## Credit-card boundary

The documented Silver Rewards application requires customer identity/income information and consent to a credit check. The available workflow does not document an agent card-opening tool. Do not claim to open, submit, approve, or activate a card. Explain the documented online application steps and obtain no credit-check consent on the customer’s behalf. If a properly documented customer-facing application workflow is available in the current runtime, follow it; otherwise provide the recommendation and direct the customer to the standard online application.

## Script interfaces

### `scripts/evaluate_savings_opening.py`

Reads one JSON object from stdin and writes one JSON object to stdout.

Input schema:

```json
{
  "identity_verified": true,
  "now": "2025-01-31T12:00:00-05:00",
  "selected_account_class": "Official Name Account",
  "requested_transfer_amount": "1000.00",
  "minimum_opening_deposit": "1000.00",
  "accounts": [
    {
      "account_id": "...",
      "account_type": "checking or savings",
      "account_class": "...",
      "status": "active",
      "balance": "1500.00",
      "date_opened": "2024-01-01",
      "is_personal_savings": true
    }
  ]
}
```

`is_personal_savings` should be supplied when the account source distinguishes personal from other savings. If omitted, a savings account is conservatively counted as personal. Output contains `eligible`, `blockers`, `warnings`, `qualifying_checking_accounts`, and `selected_account_class_valid`.

### `scripts/annual_apy_dollars.py`

Reads a JSON object with `principal`, `base_apy_percent`, optional `card_bonus_percent`, optional `direct_deposit_bonus_percent`, and optional `other_bonus_percent`. It emits the effective APY and one-year interest estimate as fixed two-decimal monetary strings. Supply only bonuses supported by the applicable product documentation, and pass only the highest eligible card bonus.

Example input:

```json
{"principal":"8000","base_apy_percent":"3.0","card_bonus_percent":"0.15"}
```

Validate that the output has no `errors`, that its effective APY matches the disclosed components, and that funding amounts match the tool confirmation before communicating an estimate or calling a banking tool.
