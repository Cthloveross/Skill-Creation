# Supplied business-checking evidence map

Use this map to locate and accurately state facts in the supplied frozen evidence. It does not authorize account opening and should not be treated as proof of a customer's individual eligibility.

## Recommendation facts

### Lime Green

- `doc_business_checking_accounts_lime_green_002`: Overdraft fee is $0.00. Monthly maintenance fee is $25.00; the stated fee-waiver balance threshold is $15,000. The document also describes a $5,000 minimum-balance requirement.
- `doc_business_checking_accounts_lime_green_007`: Eligible out-of-network ATM-fee rebates are available up to $25 per month. Domestic out-of-network ATM transactions are assessed $1.00. Foreign ATM withdrawals are 1.5% of the withdrawal amount, subject to a $2.50 minimum.
- `doc_business_checking_accounts_lime_green_003`: The account includes a dedicated manager, secure-message routing, and a priority support line with a stated maximum expected wait of 6 minutes; direct messages receive a response within 2 business hours.
- `doc_business_checking_accounts_lime_green_005`: APY is 1.5% and interest is compounded daily.

### Sky Blue

- `doc_business_checking_accounts_sky_blue_001`: Eligibility includes being within 4 years of formation and a funding requirement shown as 0. It states a 6-month free period, a $25 monthly maintenance fee after that period, and a $0.00 overdraft fee.
- `doc_business_checking_accounts_sky_blue_010`: States monthly out-of-network ATM-fee rebates up to 15. Preserve the document's monetary formatting and confirm the requested amount before treating it as satisfying a dollar-denominated requirement.

## Dated priority rule

- `doc_bank_accounts_bank_accounts_(general)_013`: From 2025-11-01 through 2025-11-30 inclusive, prioritize Sky Blue first and Lime Green second only if multiple accounts meet every customer requirement. The promotion never permits recommending an account that fails a requirement or has unconfirmed required eligibility.

Check the runtime date before applying this rule. Do not use expired promotions.

## If the customer asks to open an account after the recommendation

- `doc_bank_accounts_bank_accounts_(general)_003`: The general business-checking opening procedure requires customer verification; at least one existing OPEN personal checking account; no more than six business checking accounts; no CLOSED accounts; and an existing checking-account balance of at least $500. After confirming the desired account class, the documented opening mechanism is `open_bank_account_4821`.

These prerequisites must be established through the normal execution agent's approved banking tools and identity-verification process. A recommendation alone is not consent to open an account.
