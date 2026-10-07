---
name: savings-and-credit-card-combination
version: 1.1.0
description: Evaluate documented savings-account and credit-card combinations, then execute a confirmed personal-savings opening and authorized internal funding transfer. Use when a verified customer requests a savings account with a card comparison, paper-statement compatibility, or a savings opening funded from checking.
---

# Savings and credit-card combination workflow

Use current product evidence and the normal banking tools to recommend a compatible combination and complete the **savings** portion of a confirmed request. A customer-facing credit-card application is not an agent-opened card unless the runtime supplies a documented card-opening action.

## Required inputs and authorization

Obtain from the current conversation and authorized profile context:

- authenticated and verified customer `user_id`;
- proposed deposit amount;
- selected savings account's exact official class name;
- paper-statement need and relevant product preferences;
- card eligibility inputs, such as credit-score range, subscription status, income if the documented application requires it, and credit-check preference;
- explicit confirmation of the selected savings account; and
- explicit authorization for an immediate transfer, including the amount and checking source.

Treat a confirmation such as “open it” after a quoted account/card combination and stated funding amount as authorization for that exact savings account and transfer. Do not re-ask for confirmation, paper-statement preference, or funding authorization that was already clearly supplied. Do not treat authorization to open a savings account as proof of eligibility; validate eligibility from account data first.

If identity verification has already succeeded in the interaction or authenticated system context, use that verified `user_id` and continue. If verification is genuinely incomplete, complete the normal identity-verification process before any account action. Do not claim that identity is unverified merely because product information or an agent banking action must still be retrieved.

## Compare documented options

1. Use only the current product evidence. Do not invent APY boosts, paper-statement fees, card approval, subscription eligibility, or unavailable account terms.
2. Reject a savings option when the proposed deposit is below its opening minimum, it requires paperless delivery despite the customer's paper-statement requirement, or another documented product condition fails.
3. Reject a card option when the known score misses its minimum, a required subscription is absent, or it does not satisfy a stated requirement for a credit check.
4. A card APY bonus is conditional on the card being approved, active, and held under the same customer profile. Do not promise that a pending application produces the bonus. Where multiple active card bonuses apply, use only the highest documented card bonus rather than adding bonuses.
5. Use `scripts/evaluate_options.py` for a deterministic ranking when structured candidates are available. Provide the base APY for the actual deposit tier; the helper does not infer tiers or undocumented boosts.
6. Explain material requirements before confirmation. For example, if the evidence documents that an account permits mailed paper statements, state the documented fee and setup path without claiming the preference has been enabled unless a supported action actually did so.

For the current documented products, a Silver Plus Account is compatible with mailed paper statements at a $0 monthly paper-statement fee and does not require paperless statements. Its documented opening minimum is $1,000. The Silver Rewards Card has a 680 minimum score and requires a credit check. These facts support recommending that combination when the customer's stated facts meet them, but card approval remains separate from the savings workflow.

## Savings eligibility and action sequence

Once the customer has confirmed the exact savings account, complete the following sequence. The account lookup is mandatory and must occur **before** an opening or funding action.

1. Unlock `get_all_user_accounts_by_user_id_3847` using `unlock_discoverable_agent_tool`.
2. Call it through `call_discoverable_agent_tool` with JSON arguments containing the authenticated `user_id`.
3. Read the returned accounts and confirm all savings-opening conditions:
   - at least one customer-owned Rho-Bank checking account has status `ACTIVE` or `OPEN`;
   - a qualifying checking account has been open for at least 14 days;
   - fewer than five personal savings accounts exist;
   - no account is in collections and no account has a negative balance; and
   - the intended checking source has enough available funds for the authorized amount.
4. Select the validated checking account that the customer identified, or ask the customer to select if more than one valid source is available. Retain its `account_id`; never guess an account ID from an account class name.
5. If any eligibility requirement fails or the lookup cannot establish it, do not open or fund the account. Explain the precise blocker. For a short checking tenure, give the eligibility date if `date_opened` is available.
6. If eligibility passes, unlock `open_bank_account_4821`, then call it through `call_discoverable_agent_tool` with:
   ```json
   {
     "user_id": "authenticated customer ID",
     "account_type": "savings",
     "account_class": "exact confirmed official name ending in Account"
   }
   ```
7. Wait for and inspect the opening result. Continue only on success and retain the newly created savings `account_id`. Do not substitute a pre-existing savings ID and do not claim success if the action reports an error.
8. When the customer authorized immediate funding, confirm the amount is positive, satisfies the selected account's documented opening minimum, does not exceed the validated checking balance, and that the new savings account and source checking account are distinct and `ACTIVE` or `OPEN`.
9. Unlock `transfer_funds_between_bank_accounts_7291`, then call it through `call_discoverable_agent_tool` with:
   ```json
   {
     "source_account_id": "validated checking account ID",
     "destination_account_id": "newly opened savings account ID",
     "amount": "authorized positive USD amount"
   }
   ```
10. Inspect the transfer result before confirming completion. If it reports insufficient funds, invalid status, or invalid IDs, do not blindly retry. Revalidate or correct the reported issue. Avoid a duplicate transfer after a successful result.

If immediate funding was declined, do not transfer funds; state that the account must be funded within 30 days by internal transfer or external deposit or it will close.

## Confirmed-request fast path

When a verified customer has already selected **Silver Plus Account**, authorized an immediate $8,000 deposit, and identified an eligible Light Blue checking account, do not escalate or stop at a recommendation. Perform the required lookup, validate the returned Light Blue checking record and all eligibility conditions, open the account using the exact class string `Silver Plus Account`, and then transfer exactly $8,000 from the returned Light Blue checking `account_id` to the newly returned savings `account_id`.

The account lookup result, opening result, and transfer result are each needed to obtain and validate runtime account IDs. Never hardcode IDs from an example or from a prior interaction.

## Credit-card boundary

The supplied Silver Rewards material describes a customer-facing online application: the customer supplies personal and income information, consents to a credit check, reviews the preliminary offer and terms, and accepts them to finalize setup. If no documented agent card-opening action is supplied in the runtime, do not fabricate a tool call, approval, credit pull, or card account.

After completing any authorized savings actions, direct an eligible customer to the documented online or dashboard application path and state the required credit-check consent and income information. The absence of an agent card-opening tool is not a reason to defer or escalate the independently authorized savings opening and funding work.

## Completion response

Report only completed actions and returned details:

- the opened savings account class and returned account details;
- whether the authorized transfer succeeded, its amount, and funding status;
- material conditional APY/card-bonus qualifications; and
- the documented customer next step for a card application when no agent card-opening tool exists.

Do not state that paper statements were enabled, a credit card was opened, a card was approved, or a bonus is active unless a supported action or account result establishes that fact.

## Helper: `scripts/evaluate_options.py`

Run with a single JSON object on stdin, for example:

```sh
python scripts/evaluate_options.py < request.json
```

Input schema:

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
      "applicable_base_apy_percent": "APY for this deposit tier",
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

The script emits JSON containing `eligible_ranked` and `ineligible`. Eligible entries are ranked by estimated first-year net value. The interest estimate is `deposit × (base APY + one card bonus) / 100`, less a documented annual card fee; it is a comparison estimate, not a rate guarantee or card-approval prediction. Invalid input produces a JSON `error` object and a nonzero exit status.
