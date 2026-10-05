---
name: savings-account-and-card-combination-advisor
description: Safely advises on a personal savings account and credit-card combination, compares APY without improperly stacking bonuses, and completes a savings opening only after identity verification and every documented eligibility check. Use when a customer wants to open, fund, compare, or optimize a Rho-Bank personal savings account, including a linked credit-card discussion.
---

# Savings Account and Card Combination Advisor

## Purpose and boundaries

Use this Skill to distinguish product advice from account-opening actions. A stated approximate credit score is only a preliminary screen, not an approval. Do not claim that a credit card is approved or opened unless a supported banking action completes it. Do not invent a credit-card application tool.

A savings account may be opened only after all required savings eligibility conditions are verified in bank records. Customer statements may explain intent, but they do not replace the account lookup for savings-account count, account status, balances, or checking tenure.

## Required workflow

1. **Authenticate and log verification.** Confirm two of the four identity fields (date of birth, email, phone number, address) against the authenticated customer record. Obtain the current timestamp and call `log_verification` with the complete record and timestamp. Do not expose the bank-record values as hints while asking for verification.
2. **Retrieve account records.** Unlock and call the documented agent tool `get_all_user_accounts_by_user_id_3847` with the verified user ID. If lookup cannot be completed, explain that eligibility cannot yet be confirmed and do not open or transfer funds.
3. **Check opening eligibility.** From the returned accounts, confirm all of the following:
   - at least one active Rho-Bank checking account exists;
   - at least one active checking account has been open for at least 14 days;
   - the customer has fewer than five personal savings accounts;
   - no account is in collections; and
   - no account has a negative balance.

   Pass normalized account data and the current date to `scripts/evaluate_opening_eligibility.py` if useful. Treat an unknown or malformed required field as unresolved, not as passing. If any criterion fails or is unresolved, do not call an opening or transfer action. State the specific known blocker; for a tenure failure, state the date eligibility is reached when the opening date is available.
4. **Discuss products without overpromising.** Capture the exact selected savings `account_class`; it must be the complete official name and end in `Account`. Verify product facts, opening-deposit requirements, statement-delivery needs, and card terms against the supplied knowledge. Respect customer constraints such as a requirement for mailed statements.
5. **Compare APY correctly.** For each viable candidate, include base APY/tier applicable to the planned balance, at most one highest applicable credit-card bonus, at most one highest applicable linked-checking boost, and separately documented additive relationship/direct-deposit bonuses. Credit-card bonuses never stack with one another; neither do multiple checking boosts. A pairing not listed as qualifying has no linked-checking boost. Use `scripts/rank_apy_candidates.py` with current candidate inputs to make a transparent static-balance annual APY comparison. This is an estimate based on published APY, not a guarantee of future earnings.
6. **Handle the credit card separately.** Explain preliminary card eligibility and required consent/credit check. If a supported card-application action is available in the runtime, obtain the required customer authorization and use it according to its schema. If no such action is available, do not fabricate one: explain the supported application channel or leave the card application pending while continuing only with permitted savings actions.
7. **Open the savings account only after confirmation.** Reconfirm the selected official account class. Unlock and call `open_bank_account_4821` with the verified `user_id`, `account_type` set to `savings`, and the exact `account_class`. Do not substitute an abbreviated product name. Record the newly returned account ID.
8. **Arrange funding after the account exists.** Ask whether the customer authorizes an immediate opening-deposit transfer from a specified checking account. If authorized, call `transfer_funds_between_bank_accounts_7291` using the selected checking account ID, the newly created savings account ID, and the confirmed required amount. Report any transfer failure accurately; do not say the deposit succeeded unless the tool says so. If funding is deferred, explicitly state that the account must be funded within 30 days by internal transfer or external deposit or it will close.
9. **Close the interaction.** Provide the new account details, statement-delivery status/next step if applicable, and either the confirmed funding result or the 30-day deadline.

## Known product-screening pattern

Use only facts established by the supplied knowledge for the particular products being discussed. For example, where a customer has about $8,000, needs mailed paper statements, requires a real credit check, and has a score around 700:

- Silver Rewards Card is a preliminary possibility because it requires a 680 minimum and a credit check; a score near 700 is not approval.
- Gold Rewards Card has a 720 minimum, so a score around 700 does not preliminarily meet its published minimum. EcoCard has no score requirement, which does not satisfy a customer who requires a card that checks creditworthiness.
- Silver Plus Account explicitly permits paper statements at a $0 monthly paper-statement fee, has a $1,000 opening minimum, and its published Tier 1 APY applies below its $15,000 Tier 2 threshold. Its Silver Rewards Card bonus is +0.15%.
- Green savings requires paperless statements and is therefore unsuitable when mailed paper statements are mandatory. Gold requires a $5,000 opening deposit but a $10,000 ongoing balance, so an $8,000 plan does not meet its published ongoing standard. Light Blue checking is not in the published linked-checking APY-boost list.

These are screening facts, not permission to bypass the account-record, identity, selected-product, or funding checks.

## Helper scripts

### `scripts/evaluate_opening_eligibility.py`

Reads JSON from stdin and emits JSON to stdout. It is a deterministic eligibility checker; it does not retrieve records or perform bank actions.

Input schema:
```json
{
  "identity_verified": true,
  "as_of": "YYYY-MM-DD or timestamp",
  "accounts": [
    {
      "account_id": "string",
      "account_type": "checking|savings",
      "status": "active",
      "balance": "1250.00",
      "date_opened": "YYYY-MM-DD",
      "is_personal": true
    }
  ],
  "account_class": "Silver Plus Account",
  "required_opening_deposit": "1000.00",
  "requested_deposit": "8000.00",
  "funding_authorized": true,
  "source_account_id": "optional checking ID"
}
```

The output reports `eligible_to_open`, individual check results, blockers, eligible checking IDs, and a separate immediate-funding assessment. It only evaluates the transfer if authorization, source account ID, and amounts are supplied. Validate that `eligible_to_open` is true before proceeding to the opening action and that `immediate_funding.ready` is true before an immediate transfer.

### `scripts/rank_apy_candidates.py`

Reads a balance and fully sourced candidate components from JSON and emits ranked results. For each candidate, provide `base_apy`, a list of applicable card bonuses, a list of applicable checking boosts, and any documented additive bonuses. The script selects the maximum card bonus and maximum checking boost rather than summing them. It estimates one year of interest as `balance * effective_apy / 100` for a constant balance. Verify that each provided component is applicable to the customer and planned balance before relying on the result.

## Failure handling

- Never open a savings account when identity is unverified, eligibility is unknown, the class is incomplete, or the tool lookup/action fails.
- Do not use a savings-opening action to solve a credit-card application request.
- Do not transfer before a successful opening has returned the destination account ID.
- Do not imply that approval, APY bonuses, linked pairing, paper delivery, funding, or account creation occurred unless the applicable records or tool result confirm it.
- If the customer requests an unavailable action after a clear explanation, offer an available next step or transfer according to runtime policy.
