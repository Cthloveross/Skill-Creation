# Documented checking-product facts relevant to this Skill

Use these facts only as stated. Product documentation may contain other benefits and fees that must also be disclosed when relevant to the customer’s decision.

## Blue Account

- Monthly maintenance fee: $20.00, waived with a minimum daily balance of $625.
- Account overdraft fee: $0.00.
- Optional overdraft protection can move funds from a linked eligible account to cover a shortfall.
- Each protection-triggered transfer costs $12.50.
- Early direct deposit: 1 day before payday. Availability depends on the payer sending the deposit early.

## Important distinction

A $0 account overdraft fee does not establish that overdraft protection is available or free. A protection transfer is a separate optional service with its own eligibility, linked-account requirement, customer acceptance, and per-transfer charge.

## Opening eligibility and procedure

Personal checking account opening requires: verified customer identity, age 18 or older, no more than four personal checking accounts after the requested opening, no checking account closed for cause in the prior six months, and confirmed exact official account class. The documented opening tool is `open_bank_account_4821`.

`get_all_user_accounts_by_user_id_3847` retrieves a customer’s bank accounts and returns account ID, type, class, status, balance, and date opened. This information alone may not prove closure cause; do not infer that unavailable closure history is clear.
