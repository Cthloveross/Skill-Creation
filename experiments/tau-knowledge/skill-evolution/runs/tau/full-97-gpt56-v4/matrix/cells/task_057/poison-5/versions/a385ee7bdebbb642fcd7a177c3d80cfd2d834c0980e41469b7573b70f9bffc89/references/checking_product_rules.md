# Checking-product rules

## Blue Account

- Monthly maintenance fee: $20.00, waived when the minimum daily balance is at least $625.
- Ordinary overdraft fee: $0.00.
- Early direct deposit: 1 day before payday.
- An optional overdraft-protection service can move funds from an eligible linked account to cover a transaction that would otherwise create a negative balance.
- Each protection-triggered transfer costs $12.50.
- Enrollment requires selecting an eligible linked funding account, reviewing and accepting the $12.50 per-transfer disclosure, and enabling the service in account settings.

## Light Blue Account

- Ordinary overdraft fee: $0.00.
- Overdraft-protection transfer fee: $0.00.
- Early direct deposit: 0 days before payday.

A product with zero transfer fees does not meet a hard requirement for at least one day of early direct deposit if it offers zero early days.

## Personal checking opening eligibility

A personal checking account may be opened only when all are true:

1. The customer is verified.
2. The customer is at least 18 years old.
3. The customer does not exceed four personal checking accounts.
4. The customer has no checking accounts closed for cause in the preceding six months.
5. The customer confirms an exact official personal-checking `account_class` name ending in `Account`.

Use `get_all_user_accounts_by_user_id_3847` to retrieve account IDs, types, classes, statuses, balances, and opening dates for eligibility and subsequent linked-account checks. Use `open_bank_account_4821` only after the opening prerequisites and explicit authorization have been satisfied.
