---
name: credit-card-payoff-from-rho-checking
version: 1.0.0
description: Handle an authorized payment of a Rho-Bank credit-card balance from the same customer's Rho-Bank checking account, including prerequisite verification, account-ID collection, balance checks, tool execution, and safe handling when the checking account ID is unavailable.
---

# Credit-card payoff from Rho-Bank checking

Use this Skill when a customer wants to pay a credit-card balance using their Rho-Bank checking account, including when payoff is needed before a separate card-closure workflow can proceed.

## Required conditions before payment

Do not initiate a payment unless all of the following are true:

1. **Identity is verified.** Confirm any two of the customer's date of birth, email, phone number, and address against the customer record. Then call `log_verification` with all required customer-record fields and the current timestamp.
2. **Correct customer and accounts are identified.** Look up the authenticated customer's credit-card account and the Rho-Bank checking account selected by the customer. Do not infer an account ID from a card type, a name, or another account.
3. **The payment is authorized.** Confirm the amount and that the customer authorizes the debit from the selected checking account. Authorization for a payoff amount does not identify which checking account to debit.
4. **Both balances permit the payment.** The amount must be positive, no greater than the available checking balance, and no greater than the current outstanding credit-card balance.

A request to close a card is not itself authorization to debit checking. Treat the card-closure process as separate from the payment; continue it only if its own requirements are available and satisfied.

## When the checking account ID is missing

Do not guess, search for, or substitute a checking account ID. Explain that the customer can use Rho-Bank online banking at `rhobank.com` or the mobile app to view their accounts and balances. Ask them to locate the Rho-Bank checking account they want to use, obtain its account ID from the account information presented there, and provide that ID. They should also confirm it has enough available funds for the authorized amount.

If they have online or mobile access, give concise navigation-oriented help without claiming a particular screen label that has not been supplied: log in, open the relevant checking account/account information, and review the displayed account details and balance. Ask them to return with the checking account ID. Do not perform the payment merely because they confirm they have access.

If the customer cannot provide or locate an ID, cannot access digital banking, or requests help beyond the available process, explain that payment cannot be safely processed without the selected account ID and follow the applicable support/escalation procedure if one is available.

## Payment procedure

Once every required condition is satisfied:

1. Obtain the current time for the verification audit record if it has not already been obtained.
2. Look up the customer record and verify two identity fields supplied by the customer. Log verification using `log_verification`.
3. Look up the customer’s credit-card accounts and select only the account the customer identified. Record its `account_id` and current balance.
4. Look up or otherwise obtain the customer-selected Rho-Bank checking account ID and its current available balance. Confirm that it belongs to the authenticated customer.
5. Restate the selected checking account, target credit-card account, and exact payment amount, and obtain/confirm authorization.
6. Validate prerequisites with `scripts/validate_payment.py`. A `ready: false` result means do not unlock or call the payment tool; resolve the listed missing or invalid items first.
7. Unlock `pay_credit_card_from_checking_9182` using `unlock_discoverable_agent_tool`.
8. Call `call_discoverable_agent_tool` with `agent_tool_name` set to `pay_credit_card_from_checking_9182` and an arguments JSON object containing exactly:
   - `user_id` (string)
   - `checking_account_id` (string)
   - `credit_card_account_id` (string)
   - `amount` (positive number in dollars)
9. Read the confirmation. Report that the payment was completed only after the tool reports success, and communicate the returned balances. If the call fails, do not claim a payment occurred or retry blindly; refresh relevant balances and resolve the stated failure.

Bank actions are performed only through the declared normal banking tools. The helper script only evaluates supplied facts and never performs an account action.

## Helper interface

Run `scripts/validate_payment.py` with one JSON object on stdin and read one JSON object from stdout.

Input schema:

```json
{
  "identity_verified": true,
  "authorization_confirmed": true,
  "user_id": "string",
  "checking_account_id": "string",
  "credit_card_account_id": "string",
  "amount": 0.0,
  "checking_available_balance": 0.0,
  "credit_card_outstanding_balance": 0.0
}
```

All boolean fields are required. IDs may be omitted or empty when not yet known. Numeric balance fields and `amount` may be omitted when unknown. Output contains `ready`, `issues`, and, when inputs are numeric, `post_payment_balances` for a successful proposed payment. Validate that `ready` is true immediately before tool execution; its balance calculation is advisory and the tool response remains authoritative.

## Customer-facing response for the missing-ID case

Use a response such as: “You can find the checking account information by signing in to Rho-Bank online banking at rhobank.com (or the mobile app), opening the checking account you want to use, and reviewing its account details and available balance. Please send me that checking account ID and confirm it has enough available funds for the authorized payment. I’ll then verify the account and can process the payment.”

Do not disclose another account’s information, invent an ID, or state that a card has been closed when only the payment inquiry has been addressed.
