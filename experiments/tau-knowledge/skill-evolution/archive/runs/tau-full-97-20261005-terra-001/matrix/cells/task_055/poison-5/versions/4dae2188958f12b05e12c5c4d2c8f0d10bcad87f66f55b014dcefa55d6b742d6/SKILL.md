---
name: travel-checking-recommendation-and-safe-opening
description: Recommend a travel-oriented personal checking account from supplied product documentation, explain foreign-use costs and ATM-rebate limits accurately, and—only after an explicit selection and required checks—open the account through the normal banking tools. Use when a customer asks which checking account best fits international card and ATM usage, or wishes to proceed with opening the recommended checking account.
---

# Travel Checking Recommendation and Safe Opening

## Scope

Use this workflow to separate a product recommendation from an account-opening action. It is suitable when the customer values low foreign transaction costs, foreign ATM access, ATM-operator-fee rebates, currency conversion costs, or travel benefits.

Do not treat a request such as “sign me up for whatever you recommend” as authorization to open an unspecified account. First give a clear recommendation, disclose material conditions, obtain confirmation of the exact official account class, then complete the required banking checks before any opening action.

## Required banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## 1. Identify the current request

1. Determine whether the customer wants information/recommendation only or wants to open an account now.
2. Capture the travel needs that materially affect the recommendation:
   - foreign transaction-fee tolerance;
   - expected international ATM frequency and expected operator surcharges, if known;
   - need for rebate coverage and whether a monthly cap is acceptable;
   - currency-conversion markup tolerance and multi-currency needs;
   - expected balance and whether a monthly fee or fee-waiver threshold is acceptable;
   - expected cash-withdrawal amount, which must fit stated daily limits;
   - interest in lounge access or travel insurance.
3. If the customer defers savings planning, finish only the checking recommendation. Do not infer a savings choice or open a savings account.

A recommendation is informational and does not require an account-opening tool call. Do not retrieve or expose customer account information merely to give general product information unless the customer asks for account-specific assessment and has been appropriately authenticated.

## 2. Build a fact-based comparison

Read the current task's supplied product documents. For each plausible checking product, record only supported facts:

- foreign transaction fee;
- bank foreign-ATM withdrawal fee;
- ATM operator-fee rebate amount, period, posting/eligibility rules, and exclusions;
- conversion markup and wallet support;
- monthly maintenance fee and waiver condition;
- relevant daily ATM limit;
- material travel perks and their limits;
- any separate out-of-network or terminal charge.

Use `scripts/rank_travel_checking.py` when structured candidate facts are available. It ranks only the candidate data supplied at runtime; it is not an account-opening decision and cannot establish eligibility.

### Explain ATM costs precisely

Keep these charges distinct:

1. **Bank foreign ATM withdrawal fee** is the bank's charge for the withdrawal.
2. **ATM operator surcharge** is imposed by the terminal owner and may still be charged even where the bank's foreign ATM fee is zero.
3. **Rebate** is a later credit for eligible posted operator surcharges, only up to its stated monthly cap.
4. A separate out-of-network fee, if documented, must be disclosed independently. If product material creates ambiguity about whether a charge applies to the planned withdrawal, do not promise a net cost; state the documented rules and advise that the terminal type and fee coding determine treatment.

Similarly, a 0% foreign transaction fee does not necessarily mean currency conversion is at the interbank rate: disclose any stated conversion markup.

## 3. Deliver the recommendation

Give one concise, evidence-based recommendation only when the current documentation supports it. State the account's official name, then explain why it matches the stated travel needs. Include all material conditions that could change the customer's net cost, especially monthly fee/waiver terms, ATM-rebate cap, rebate timing, third-party fees, conversion markup, and withdrawal limits.

Do not claim that an account is universally best or that every foreign ATM cost will be refunded. If comparable product facts are incomplete, say that the recommendation is based on the documented options rather than an exhaustive product comparison.

For the supplied Purple Account material, the relevant travel facts to verify and communicate from the documents are: 0% foreign transaction fee, $0 bank foreign-ATM withdrawal fee, eligible worldwide operator-fee rebates up to $30 monthly after posting, a 0.5% conversion markup over the interbank rate, and the applicable account fee, fee-waiver, and ATM-limit terms. The customer should understand that third-party operator fees can remain their responsibility beyond eligible rebate coverage.

End a recommendation-only response by asking whether the customer wants to select the named official account class and proceed with an application. If savings was deferred, offer to revisit savings preferences after the checking decision; do not conflate the two decisions.

## 4. Open a personal checking account only after explicit confirmation

Perform this section only after the customer explicitly confirms the exact checking account class they want opened.

1. **Authenticate and verify identity.** Obtain and confirm two of the four identity fields—date of birth, email, phone number, and address—against the customer record. Use the supported customer-information lookup appropriate to the identifier available. After successful verification, obtain the current timestamp with `get_current_time` and call `log_verification` with all required record fields and that timestamp.
2. **Retrieve account information.** Unlock and use `get_all_user_accounts_by_user_id_3847` with the authenticated customer's user ID. Use it to confirm existing account types, status, balances, and tenure where relevant.
3. **Check all checking-opening eligibility requirements before opening:**
   - customer is verified;
   - customer is at least 18 (calculate from verified date of birth);
   - customer has no more than four personal checking accounts;
   - customer has no checking account closed for cause in the preceding six months.

   Account-list data alone may not establish historical closures for cause. If a required fact cannot be confirmed from available supported records, do not open the account; explain that the application cannot proceed until the requirement is verified.
4. **Confirm the exact selection.** Repeat the full official account class exactly as the customer selected. It must end in `Account`. Confirm any disclosed monthly fee, waiver threshold, foreign-use limitations, and other material terms before proceeding.
5. **Open.** Unlock the normal agent banking tool `open_bank_account_4821` and call it only after the preceding checks pass, with the authenticated `user_id`, `account_type` of `checking`, and the confirmed full `account_class`.
6. **Confirm outcome.** Report the actual tool result and new account details that are safe to share. Do not state that an account was opened if the tool did not return success. If it fails, report the non-sensitive reason and do not retry blindly.

Never ask the customer to call internal banking tools or present internal tool parameters as an action the customer must perform.

## 5. If the customer later resumes savings planning

Collect savings priorities (rate, balance, fee tolerance, liquidity, withdrawal needs) and evaluate the documented savings products separately. Before opening savings, verify identity and check all savings requirements: an active checking account, at least 14 days of checking tenure, fewer than five personal savings accounts, and no accounts in collections or with negative balances. Obtain a confirmed exact savings account class before using the normal opening tool.

If funding a newly opened savings account by internal transfer, obtain explicit authorization for the source account and amount. Before the transfer, verify both accounts belong to the customer, are ACTIVE or OPEN, the account IDs are different, the positive USD amount is available in the source, and all fees/limits are understood. If funding is deferred, clearly state the documented funding deadline and consequence.

## Script interface and validation

`scripts/rank_travel_checking.py` reads one JSON object from standard input and writes one JSON object to standard output.

Input schema:

```json
{
  "preferences": {
    "avoid_foreign_transaction_fees": true,
    "uses_foreign_atms_often": true,
    "expected_monthly_operator_fees": "25.00",
    "prefers_low_conversion_markup": true,
    "avoid_monthly_fee": false
  },
  "products": [
    {
      "name": "Official Account Name",
      "foreign_transaction_fee_percent": "0",
      "foreign_atm_withdrawal_fee": "0.00",
      "monthly_atm_operator_rebate_cap": "30.00",
      "currency_conversion_markup_percent": "0.5",
      "monthly_maintenance_fee": "15.00",
      "minimum_daily_balance_to_waive_fee": "3750.00"
    }
  ]
}
```

All monetary and percentage values are nonnegative decimal strings or numbers. Product names must be supplied by the executor from the current product materials. The output includes each candidate's missing facts, hard-need result, transparent score components, and a recommendation only when at least one candidate has all facts needed for the selected hard travel needs.

Before using its output, validate that the product names and values match the source documents, inspect `missing_fields`, and manually add conditions the schema cannot score (such as eligibility rules, fee posting, terminal exclusions, insurance, or account-opening requirements). A `recommended_product` result is an informational ranking, not consent or proof of eligibility.
