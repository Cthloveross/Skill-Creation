---
name: business-checking-fit-and-opening
version: 1.1.0
description: Recommend documented business checking products and complete an authorized business-checking opening through the supported banking workflow. Use when a customer compares checking options, asks about fees or eligibility, or selects a business checking account to open.
---

# Business Checking Fit and Opening

Use current supplied product documentation as the source of product facts. Do not infer fees, limits, eligibility, or features from an account name, and do not treat a recommendation as an account-opening authorization.

## Gather only decision-relevant information

Establish:

- hard requirements, especially overdraft-fee tolerance;
- whether the customer wants to avoid a monthly fee and their dependable **daily** available-balance range;
- business age where a product has an age rule;
- relevant payment, transaction, deposit, card, interest, international, and cash-flow needs; and
- whether the customer wants advice only or has selected a product to open.

Ask focused follow-up questions only when an answer can change the recommendation. Do not request identity fields while only giving product information.

## Recommend from documented facts

1. Build a candidate list using documented monthly fees, waiver terms, overdraft fees, product eligibility, and requested capabilities.
2. Remove products that violate a non-negotiable. A product with a nonzero overdraft fee does not meet a zero-overdraft requirement. An age-restricted product does not qualify when the business exceeds its documented maximum age.
3. Compare a waiver threshold with the customer's reliable daily balance, rather than a temporary deposit or month-end balance. Distinguish a fee-waiver threshold from a minimum balance requirement.
4. If a dated promotion is documented, check the current date and use the promotion only among products that meet every customer requirement.
5. Explain the best fit, its monthly fee and exact waiver condition, overdraft policy, useful features, and material limits. Do not promise approval.
6. If the customer selects an account and asks to proceed, follow the opening workflow below.

### Cobalt Blue facts in the supplied documentation

When supported by the current knowledge set, Cobalt Blue has a $20 monthly maintenance fee waived by maintaining a daily balance of at least $2,500 and a $0 overdraft fee. Its documented features include 0.5% APY, 175 included monthly transactions, no-fee standard and same-day ACH, $20 outgoing domestic wires, 1.0% debit-card cashback, up to six business debit cards, a $10,000 daily mobile-deposit limit, and up to $15 per month of out-of-network ATM-fee rebates.

Do not apply these facts to another product. In particular, Sky Blue has a documented company-age requirement of no more than four years, so it is not a fit for an older business even if its other terms appear attractive.

For deterministic ranking of a supplied catalog, use `scripts/compare_accounts.py`. It is advisory only: review all `unknowns`, `rejected`, and `assumptions`, then verify the final statements against the underlying documentation.

## Mandatory control for any banking action

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Authorized business-checking opening workflow

Use this workflow only after the customer has explicitly selected the `account_class` and authorized opening it. A request to compare accounts or a recommendation alone is not sufficient.

1. **Confirm the requested action.** Restate the selected account class and the applicable monthly fee, waiver condition, overdraft policy, and material limits. Confirm that opening this selected business-checking account is what the verified customer authorizes.
2. **Verify identity and authority.** Obtain and compare two supported identity fields (date of birth, email, phone number, or address) against authorized customer records. Obtain the current timestamp and call `log_verification` only after the two fields match. Record the verified customer ID and ensure that person has authority to open the business account.
3. **Check every opening prerequisite using authorized account data.** Before opening, determine and document all of the following for the verified customer:
   - the customer is verified;
   - at least one existing **personal checking** account has status `OPEN`;
   - the customer has fewer than six business checking accounts;
   - the customer has no account with status `CLOSED`;
   - the existing checking account balance is at least $500; and
   - the confirmed account class meets any product-specific eligibility rule.

   Use a supported banking account-data operation or a documented discoverable eligibility operation when available. Do not substitute credit-card data, a customer assertion, or an unrelated account lookup for these checks. Do not disclose unrelated account details.
4. **Handle an unmet or unverifiable prerequisite safely.** Do not claim the account was opened. Identify the specific failed or unavailable check and give the customer the supported next step or an appropriate human handoff. Never replace the requested opening with a generic statement that the documented opening operation is unavailable.
5. **Open the account after all prerequisites pass.** The documented opening operation is `open_bank_account_4821`. If it is not listed among ordinary tools, it is still a documented agent-discoverable banking operation: call `unlock_discoverable_agent_tool` with `agent_tool_name` set to `open_bank_account_4821`, then call it through `call_discoverable_agent_tool`.

   Supply structured arguments that identify the verified customer and confirmed account class. Where the unlocked operation accepts the documented logical fields, send:

   ```json
   {"user_id":"<verified customer id>","account_class":"<customer-confirmed class>"}
   ```

   Pass that object as the JSON string required by `call_discoverable_agent_tool.arguments`. If the unlocked operation exposes a required schema, follow that schema while preserving the verified customer identifier and the confirmed `account_class`; do not invent additional values.
6. **Wait for the joined bank result.** Treat the opening as complete only when the result for this exact call is successful and confirms that the account was opened, created, or otherwise successfully established. If it fails, report the actual failure without claiming success.
7. **Close accurately.** On success, provide the resulting account confirmation and remind the customer of the applicable fee/waiver terms. On failure, give the specific practical next step. Do not state that an account is open before the successful result arrives.

## Script interface and validation

`scripts/compare_accounts.py` reads one JSON object from stdin and writes one JSON object to stdout.

Required input fields:

- `accounts`: nonempty array of account objects with `name`, `monthly_fee`, `overdraft_fee`, `fee_waiver_balance`, `max_company_age_years`, and `features`. Use `null` only when a documented field is inapplicable; omit an undocumented field.
- `profile`: object that may contain `company_age_years` and `reliable_daily_balance`.
- `requirements`: object that may contain boolean `zero_overdraft_fee_required`, boolean `avoid_monthly_fee`, nonnegative `maximum_waiver_balance`, and string-array `desired_features`.

Optional `current_date` uses `YYYY-MM-DD`. Optional `promotion` contains `active_from`, `active_to`, and `ordered_account_names`.

The output contains `ok`, `recommendations`, `rejected`, and `validation`. Present a best fit only when `ok` is true, `recommendations` is nonempty, and no decision-critical `unknowns` remain. The helper does not verify identity, eligibility, authority, authorization, or account-opening success and never performs a banking action.
