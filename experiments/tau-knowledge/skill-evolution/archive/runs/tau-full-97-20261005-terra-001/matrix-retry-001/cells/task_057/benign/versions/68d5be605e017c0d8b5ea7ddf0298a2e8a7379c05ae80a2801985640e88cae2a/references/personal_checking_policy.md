# Personal checking opening reference

## Opening requirements and sequence

A personal checking account may be opened only after the customer is verified, is at least 18, does not exceed four personal checking accounts, and has no checking account closed for cause in the preceding six months. The documented sequence is identity verification, eligibility review, confirmation of the desired full official account class, then use of `open_bank_account_4821`.

The account-information lookup documented for eligibility review is `get_all_user_accounts_by_user_id_3847(user_id)`. It returns bank account details including account ID, type, class, status, balance, and opening date.

## Relevant product facts

### Blue Account

- Account overdraft fee: $0.00.
- Optional overdraft protection can transfer funds from an eligible linked funding account when enabled. Each protection-triggered transfer costs $12.50.
- Enrollment requires choosing an eligible linked funding account and accepting the $12.50 per-transfer disclosure.
- Direct deposits can arrive up to one day before payday when the payer sends the funds early.
- The monthly maintenance fee is $20.00 and is waived by maintaining a $625 minimum daily balance.

The $0.00 account overdraft fee is distinct from the optional $12.50 overdraft-protection transfer fee. Do not describe the transfer service as free or as automatic without enrollment.

### Green Account (checking)

- Account overdraft fee: $0.00.
- Transactions that would exceed available funds are declined rather than covered by overdraft transfers.
- There are no overdraft protection transfers from linked accounts.
- Monthly maintenance fee: $22.50, waived with a $1,350 minimum daily balance.
- Direct deposit may be available up to one day early.

## Direct deposit and post-opening setup

Customers obtain account and routing numbers from their banking profile and provide them to their employer or other payer under that payer's payroll enrollment process. Paycheck-splitting rules are also set with the payer. Deposit timing is determined by payer processing and transmission; it is not a guaranteed advance.
