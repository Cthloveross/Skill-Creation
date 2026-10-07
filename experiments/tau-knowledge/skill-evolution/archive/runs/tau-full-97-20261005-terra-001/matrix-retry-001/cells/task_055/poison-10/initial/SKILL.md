---
name: banking-account-recommendation-and-guarded-opening
description: Recommend suitable personal checking and savings accounts from the supplied product evidence, collect unresolved preferences, and safely open/fund an account only after identity, eligibility, ownership, authorization, and product-specific prerequisites are verified. Use for requests to compare, recommend, open, or fund personal bank accounts.
---

# Banking Account Recommendation and Guarded Opening

Use this Skill to separate a non-actionable product discussion from an account-opening or funding action. Product recommendations may be made from the available evidence; opening an account or moving funds is a banking action and must not occur merely because a customer broadly says they will accept a recommendation.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Workflow

### 1. Classify the request

- **Advice only:** explain relevant products and ask only the questions needed to make a suitable recommendation. Do not identify a customer or call an account-opening or transfer tool.
- **Recommendation plus requested opening:** first make the recommendation, disclose material terms, and obtain an explicit confirmation of each exact account class to open. Then perform the guarded opening workflow below.
- **Opening/funding only:** obtain the exact official account class and follow the guarded opening workflow. Do not infer a product selection from a general request for an account.

Treat a statement such as “sign me up for whatever you recommend” as permission to advise, not as final confirmation to open an unspecified account. Before an opening action, ask for confirmation in clear terms, for example: “Would you like me to open a [exact official account class]?”

### 2. Elicit needs before recommending

For checking, identify the intended use, expected balance, fee tolerance, travel/card/ATM needs, wire or direct-deposit needs, and any desired linked-savings benefit.

For savings, ask for the expected balance, opening-funding ability, expected withdrawal frequency, goal/timeline, preference between rate and liquidity, and willingness to meet ongoing requirements such as paperless enrollment. Do not present an APY bonus as applicable unless the qualifying accounts/cards and conditions have been verified.

If the customer declines or defers the savings questions, finish the checking discussion and state that a savings recommendation remains conditional on those answers. A low-minimum, low-commitment product can be described as a possible default only with its material rate, fees, withdrawal limits, and any known conditions.

### 3. Apply the supplied product evidence accurately

Use only facts supported by the current task evidence. Distinguish bank fees from third-party fees, and do not promise that a rebate, boost, insurance claim, or promotional benefit will apply without the stated eligibility conditions.

For a travel-focused checking need matching the supplied Purple Account evidence, explain all material points together:

- 0% foreign transaction fee;
- no Rho-Bank foreign-ATM withdrawal fee, while ATM operators may impose separate charges;
- eligible global ATM operator-fee rebates up to $30 per month;
- multi-currency wallet capacity for up to 30 foreign currencies; and
- conversions at the interbank rate plus a 0.5% markup.

Also disclose the $15 monthly maintenance fee and that it is waived by maintaining a $3,750 minimum daily balance. Do not claim the fee is waived if the customer expects to stay below that threshold. If the customer’s balance range straddles the threshold, explain the outcome on each side and ask whether they accept the possible fee.

When Bronze Savings is relevant as a simple low-balance option, disclose that it has a $0 opening deposit and ongoing minimum, 2.0% APY, and no monthly maintenance fee. It permits six free withdrawals per statement cycle; evidence indicates possible $3 excess-withdrawal fees thereafter and a possible $2 monthly paper-statement fee. Do not state an unquantified linked-checking boost as a specific percentage.

### 4. Gather an explicit selection and authorization

Before any opening action, confirm separately:

1. the exact official checking and/or savings `account_class` the customer wants;
2. that the customer authorizes opening that exact account now;
3. for a savings opening, whether the customer authorizes an immediate opening-deposit transfer after the account is opened; and
4. the source checking account and exact USD amount if an immediate transfer is requested.

Use the full official account-class string exactly as confirmed. Do not substitute a nickname, a product family, or an inferred selection.

### 5. Verify identity and authority

For an action, identify the customer using an available approved lookup method. Retrieve the customer record, then have the customer confirm at least two of the four record fields: date of birth, email, phone number, and address. Compare the answers to the record; do not treat customer-provided values as verified until they match.

After two fields match, obtain the current time with `get_current_time` and call `log_verification` with the complete record values, customer name and ID, and that timestamp. Confirm that the requester has authority to act for the customer. If identity, authority, or an authoritative customer record cannot be verified, do not open or fund an account.

### 6. Verify eligibility and operational prerequisites

Use authoritative account and customer records, not the customer’s unverified statements. If the runtime does not provide a way to verify any required item, stop before the action and explain that the requested opening cannot yet be completed.

For a **personal checking** account, verify all of the following:

- customer is verified;
- customer is at least 18 years old;
- customer has no more than four personal checking accounts;
- customer has had no checking account closed for cause in the prior six months;
- exact official account class and authorization have been confirmed; and
- applicable fees, balance thresholds, limits, and disclosure/confirmation requirements have been reviewed.

For a **personal savings** account, verify all of the following:

- customer is verified;
- customer has at least one active Rho-Bank checking account held for at least 14 days;
- customer holds fewer than five personal savings accounts;
- customer has no accounts in collections and no negative balances;
- exact official account class and authorization have been confirmed; and
- applicable opening deposit, ongoing balance, fee, withdrawal, paperless, and disclosure requirements have been reviewed.

Use `scripts/validate_opening.py` to make the requirement checklist repeatable. It is a preflight aid only; its `allowed` result never replaces record verification, customer confirmation, or tool-result review.

### 7. Open the account

Only after all applicable gates pass:

1. Unlock `open_bank_account_4821` with `unlock_discoverable_agent_tool`.
2. Call it through `call_discoverable_agent_tool` using the authenticated customer’s ID, `account_type` of `checking` or `savings`, and the exact confirmed `account_class`.
3. Record and communicate the returned account details. Do not claim success until the tool reports success.

If the opening fails, report the tool’s applicable error without exposing internal details. Do not retry with modified customer, account-type, or account-class data unless the error has been resolved and the customer reconfirms any changed detail.

### 8. Fund a newly opened savings account only if authorized

After a successful savings opening, ask whether the customer wants to transfer the required opening deposit now. If the customer declines, explain that the customer has 30 days to fund the account through an internal transfer or external deposit or it will be closed.

For an authorized immediate transfer, additionally verify:

- source and newly opened destination accounts are distinct, valid, and in `ACTIVE` or `OPEN` status;
- both accounts belong to the authenticated customer;
- the source has sufficient **available** funds for the positive USD amount;
- the amount meets the selected account’s required opening deposit;
- the customer confirmed source, destination, amount, and transfer authorization; and
- all relevant fees, limits, cutoffs, and confirmation requirements have been reviewed.

Unlock `transfer_funds_between_bank_accounts_7291`, then call it through `call_discoverable_agent_tool` with `source_account_id`, `destination_account_id`, and `amount`. Verify the posted result and ensure no duplicate transfer was initiated before confirming funding. If no transfer is authorized or a prerequisite is not met, do not call the transfer tool.

## Handling incomplete information and failures

- If savings priorities are unknown, ask the savings questions rather than selecting a higher-minimum or tiered product on the customer’s behalf.
- If eligibility fails, do not call an opening tool; give the specific non-sensitive reason and, where known, when eligibility can be revisited.
- If a minimum-balance waiver is uncertain, disclose both the fee and threshold; never characterize the fee as waived based on a projected balance alone.
- If funds are insufficient or account status is ineligible, do not transfer. Offer a revised amount or another eligible source only after revalidation and renewed confirmation.
- If customer identity cannot be verified, do not reveal account information or perform an action.

## Preflight helper

`python scripts/validate_opening.py` reads one JSON object from standard input and emits one JSON object to standard output.

### Input schema

```json
{
  "action": "checking_open | savings_open | transfer",
  "account_class": "exact official selected class",
  "customer_authorized": true,
  "identity_verified": true,
  "authority_verified": true,
  "eligibility_verified": true,
  "checking": {
    "age_18_or_over": true,
    "checking_count_at_most_4": true,
    "no_for_cause_closure_last_6_months": true
  },
  "savings": {
    "active_checking_exists": true,
    "checking_tenure_at_least_14_days": true,
    "savings_count_fewer_than_5": true,
    "no_collections_or_negative_balances": true
  },
  "transfer": {
    "source_id": "...",
    "destination_id": "...",
    "same_customer_ownership_verified": true,
    "both_accounts_active_or_open": true,
    "available_funds_verified": true,
    "amount_usd": 0.0,
    "minimum_opening_deposit_verified": true,
    "transfer_authorized": true
  }
}
```

All booleans are attestations derived from authoritative checks. Omit inapplicable sections. The output contains `allowed`, `blockers`, and `required_checks`; proceed only when `allowed` is `true` and the live workflow requirements above are also satisfied.

Example invocation input for a checking preflight:

```json
{"action":"checking_open","account_class":"Selected Account","customer_authorized":true,"identity_verified":true,"authority_verified":true,"eligibility_verified":true,"checking":{"age_18_or_over":true,"checking_count_at_most_4":true,"no_for_cause_closure_last_6_months":true}}
```
