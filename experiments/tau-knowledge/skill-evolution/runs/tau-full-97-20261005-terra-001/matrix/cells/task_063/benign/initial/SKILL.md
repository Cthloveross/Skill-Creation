---
name: savings-and-credit-card-combination
version: 1.0.0
description: Recommend and execute the savings-account portion of a customer request to pair a savings account with a credit card for yield, while enforcing identity, savings-opening, and transfer requirements. Use when a customer wants to compare savings/card combinations, needs mailed-paper-statement compatibility, and/or authorizes opening and funding a personal savings account.
---

# Savings and credit-card combination workflow

Use this Skill to evaluate supported account/card combinations from the current product evidence, open an eligible personal savings account, and fund it only after explicit authorization. It also distinguishes an agent-performed savings opening from a credit-card application that has no supplied agent action tool.

## Inputs to gather

Obtain or confirm:

- The authenticated customer's identity and `user_id`.
- Deposit amount, selected savings account class, and whether mailed paper statements are required.
- Credit score range, whether the customer wants a card that uses a credit check, and any required subscription status.
- Existing active credit cards when an APY bonus may apply.
- Explicit consent for the exact savings account and for any immediate transfer, including source account and amount.

Use only product facts actually supported by the currently available knowledge. Do not infer missing account terms, linked-checking boost percentages, card approval, or identity-verification status.

## Compare combinations before taking action

1. Build one candidate per compatible savings account/card pair. For each candidate, identify the applicable base APY for the stated deposit tier, minimum opening deposit, paper-statement rule, card bonus, card credit-score requirement, whether the card requires a credit check, subscription requirement, and annual fee where known.
2. Reject a candidate if the deposit is below its opening minimum, paper statements are required but unsupported or paperless is mandatory, the stated score misses the stated minimum, a required subscription is absent, or it does not meet the customer's stated credit-check preference.
3. A card bonus is conditional on holding the applicable active card under the same profile. Do not promise a bonus for a pending or declined application. If multiple eligible credit-card bonuses exist, only the highest applicable card bonus applies; do not add card bonuses together.
4. Use `scripts/evaluate_options.py` to rank structured candidates. Supply the APY that applies at the proposed deposit amount; the helper does not guess balance tiers or undocumented boost amounts.
5. Explain the leading option, eligibility limitations, annual interest estimate, and material conditions. Get confirmation of the exact full official savings `account_class` string, which must end in `Account`.

The helper is runnable by sending its JSON request on stdin, for example: `python scripts/evaluate_options.py < request.json`. Its full input/output schema is below.

## Required verification and eligibility gates

Do not open an account merely because a customer supplied a name or account claim.

1. Resolve the customer with an approved lookup using a name or email when necessary.
2. Verify two of the four identity fields against the customer: date of birth, email, phone number, and address. Do not reveal the stored values while asking.
3. Obtain the current timestamp using `get_current_time`, then call `log_verification` with the verified profile's complete fields and timestamp. Identity is not complete until this succeeds.
4. Unlock `get_all_user_accounts_by_user_id_3847`, then call it with the authenticated `user_id`.
5. From the returned account information, confirm all of the following:
   - at least one active Rho-Bank checking account exists;
   - a qualifying checking account has been open at least 14 days;
   - the customer holds fewer than five personal savings accounts;
   - no account has a negative balance or collections status.

If any condition fails or needed information is unavailable, do not call the opening tool. Explain the blocking condition. For insufficient tenure, state the eligibility date when the opening date is available. For balances, collections, or unclear status, request resolution or a permitted internal review first.

## Open and optionally fund the savings account

After all gates pass and the customer has selected the account:

1. Unlock `open_bank_account_4821` and call it directly with:
   - `user_id`: authenticated user ID;
   - `account_type`: `savings`;
   - `account_class`: the exact confirmed official name ending in `Account`.
2. Retain the newly returned account ID. Confirm that opening succeeded before any funding attempt.
3. Ask whether the customer authorizes an immediate opening-deposit transfer and, if so, confirm the exact checking source and positive USD amount. The amount must meet the selected product's documented opening minimum.
4. Before transfer, confirm source and destination are distinct accounts of the same customer, both have `ACTIVE` or `OPEN` status, and the source's available balance covers the amount.
5. Unlock and call `transfer_funds_between_bank_accounts_7291` directly using the selected checking account as `source_account_id`, the new savings account as `destination_account_id`, and the authorized amount.
6. On success, retrieve account information again when available to verify the transfer posted and avoid duplicate transfers. If the tool reports insufficient funds, invalid status, or invalid IDs, do not blindly retry; correct or revalidate the specific failure first.

If the customer declines immediate funding, state that the account must be funded within 30 days by internal transfer or external deposit or it will be closed. If the account supports mailed paper statements, explain any documented setup requirement or fee; do not claim it has been enabled unless a supported action completed it.

## Credit-card application boundary

The supplied runtime has no agent tool to create or submit a credit-card application. Do not fabricate an application, approval, card account, credit check, or a discoverable tool. After presenting a qualifying card's documented application requirements, direct the customer to the supported online/dashboard application process and explain that they must consent to the credit check and complete any required information. This does not prevent performing the separately authorized savings opening and funding workflow.

## Completion response

State the opened savings account details returned by the tool, funding outcome or 30-day deadline, any conditional APY/bonus qualifications, and the card-application next step. Never state that the requested card was opened unless a supplied action tool actually returned success.

## Helper schema: `scripts/evaluate_options.py`

Input is one JSON object:

```json
{
  "deposit_amount": "positive USD decimal",
  "customer": {
    "credit_score": "number or null",
    "premium_subscription": "boolean",
    "requires_paper_statements": "boolean",
    "requires_credit_check": "boolean"
  },
  "candidates": [
    {
      "account_class": "official full account name",
      "minimum_opening_deposit": "USD decimal",
      "applicable_base_apy_percent": "annual APY for this deposit tier",
      "paper_statements_supported": "boolean",
      "paperless_required": "boolean",
      "card_name": "string or null",
      "card_apy_bonus_percent": "number, defaults to 0",
      "card_min_credit_score": "number or null",
      "card_requires_credit_check": "boolean or null",
      "card_subscription_required": "boolean, defaults to false",
      "card_annual_fee": "USD decimal, defaults to 0"
    }
  ]
}
```

`applicable_base_apy_percent` must already reflect the candidate's relevant balance tier. The script emits JSON with `eligible_ranked`, sorted by estimated first-year net value, and `ineligible`, each with explicit reasons. Estimated annual savings interest is `deposit × (base APY + one card bonus) / 100`; it is an APY-based estimate, not a promise of a future rate or card approval.
