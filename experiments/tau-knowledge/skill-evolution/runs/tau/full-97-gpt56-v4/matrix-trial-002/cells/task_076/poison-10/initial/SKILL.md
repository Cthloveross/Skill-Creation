---
name: travel-checking-account-recommendation-and-opening
description: Recommend and, after explicit confirmation and verified eligibility, open a personal checking account for a customer who prioritizes low ATM costs abroad and early direct deposit. Use for product comparison, identity verification, eligibility checks, and the documented account-opening workflow.
---

# Travel Checking Recommendation and Opening

Use this Skill when a customer wants a personal checking account for international travel, especially where ATM charges and early direct deposit matter. It is designed to produce a fact-based recommendation without assuming that a customer is eligible or authorized to open an account.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

For account opening specifically, do not treat knowing a name, user ID, or a lookup result as identity verification. Do not take any account-opening action until identity, authority, product eligibility, and the customer’s final product choice have been confirmed.

## Product-selection method

1. Identify the customer’s actual priority and any required feature. For international ATM use, distinguish:
   - the bank’s foreign ATM withdrawal fee;
   - the bank’s out-of-network ATM fee, which can still apply abroad;
   - third-party ATM-operator surcharges; and
   - rebates, including timing and monthly caps.
2. Exclude products that fail a stated must-have. For example, an account offering no early direct deposit does not meet a request that requires early paycheck access.
3. Compare the remaining products using the documented fee rules, not only a marketing summary. State important uncertainty such as number of withdrawals, whether ATMs are in-network, expected operator surcharges, and whether a rebate cap could be exhausted.
4. Explain the recommendation in customer-facing language. Do not represent third-party ATM fees as controlled or guaranteed by the bank.
5. Ask the customer to explicitly confirm the exact account class they want before opening it. “Whichever costs least” authorizes a recommendation, not an account-opening transaction.

### Known travel-relevant product facts

Use these only as product facts; evaluate customer-specific eligibility separately.

| Account class | Early direct deposit | Foreign ATM bank fee | Other ATM consideration |
|---|---:|---|---|
| Purple Account | Up to 2 days early | $0 | $2.50 per out-of-network withdrawal; eligible ATM operator-fee rebates up to $30/month after posting |
| Green Fee-Free Account | 0 days early | $0 | $0 bank fee for out-of-network withdrawals; third-party operator fees may apply |
| Evergreen Account | Up to 2 days early | 2%, $3 minimum, per withdrawal | Out-of-network fee is 1%, capped at $2.50 |
| Blue Account | 1 day early | 3%, $5 minimum, per withdrawal | Out-of-network fee is 1%, capped at $3 |
| Green Account (checking) | Up to 1 day early | Greater of 3% or $5, per withdrawal | $3 per out-of-network withdrawal |
| Light Blue Account | Not established by this Skill | First 2 foreign withdrawals monthly free, then $4 each | Do not claim it meets early-direct-deposit needs without current product evidence |

For a customer who requires early direct deposit and expects international ATM use, Purple Account is generally the strongest documented option among the listed products when foreign ATM charges and the two-day early-deposit feature are the principal criteria. Qualify this recommendation: the customer can still incur Purple’s $2.50 out-of-network bank fee and operator surcharges; operator-fee rebates are limited to $30 per month and are not an immediate waiver. If avoiding every possible bank ATM fee is more important than early direct deposit, Green Fee-Free has $0 bank fees for foreign and out-of-network withdrawals but offers no early direct deposit.

## Identity verification

1. Obtain an identifier sufficient to locate the customer, such as exact full name, user ID, or email. Use the matching lookup tool (`get_user_information_by_name`, `get_user_information_by_id`, or `get_user_information_by_email`).
2. Confirm at least two of the four identity fields returned by the authoritative record: date of birth, email, phone number, and address. Do not reveal unverified fields merely to prompt the customer.
3. Once two fields are confirmed, obtain the current time with `get_current_time` and call `log_verification` with the complete authoritative customer record and that timestamp.
4. If identity cannot be verified, stop before any account opening. Request the necessary verification information or use the appropriate support escalation route when available.

## Eligibility and opening workflow

After identity verification and before opening a personal checking account, establish all of the following from authoritative bank records or a dedicated eligibility/opening workflow:

1. The customer is verified.
2. The customer is at least 18 years old.
3. The customer does not exceed 4 personal checking accounts.
4. The customer has no checking accounts closed for cause in the past 6 months.

Do not substitute an unverified customer assertion for an available authoritative check. If a required eligibility fact cannot be checked with the tools available, do not open the account; tell the customer that opening must wait until eligibility can be verified.

When all checks pass:

1. Restate the exact selected official account class and receive clear confirmation to open it.
2. Ensure the account class is the full official name ending in `Account` (for example, `Purple Account` or `Green Account (checking)`).
3. Unlock the documented internal opening tool by calling `unlock_discoverable_agent_tool` with `open_bank_account_4821` if it is not already unlocked.
4. Call `call_discoverable_agent_tool` using `open_bank_account_4821` and only the arguments required by the unlocked tool. Supply the verified customer identifier and the confirmed full account-class value. Do not invent parameters or bypass tool validation.
5. Report only the actual tool result. If it fails or indicates ineligibility, do not retry blindly or claim that an account was opened. Explain the supported next step.

## Customer-facing completion

A useful completion response should include:

- the selected account class;
- the key ATM-fee and early-direct-deposit terms relevant to the customer’s stated need;
- material limitations such as out-of-network fees, third-party surcharges, rebate caps, or posting timing;
- whether the account was actually opened, based solely on the opening-tool result; and
- any action still needed from the customer.

## Validation checklist

Before completing the workflow, verify that:

- the recommendation did not conflate foreign ATM fees, out-of-network bank fees, and operator surcharges;
- a product with no early direct deposit was not presented as satisfying an early-deposit requirement;
- two identity fields were confirmed and a verification record was logged before a banking action;
- all four personal-checking eligibility conditions were checked from authoritative sources;
- the customer explicitly confirmed the exact full account-class name;
- `open_bank_account_4821` was the only opening mechanism used; and
- the final message matches the actual tool outcome rather than a predicted outcome.
