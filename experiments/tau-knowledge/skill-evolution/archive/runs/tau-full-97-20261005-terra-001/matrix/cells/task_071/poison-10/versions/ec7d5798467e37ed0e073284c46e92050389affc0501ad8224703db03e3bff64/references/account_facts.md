# Product evidence index for business-account selection

Use this index only with the customer requirements and current date supplied to the task. All amounts and terms below are evidence summaries, not assumptions about customer eligibility.

## Checking products

### Sky Blue

Sources: `doc_business_checking_accounts_sky_blue_001`, `doc_business_checking_accounts_sky_blue_007`, `doc_business_checking_accounts_sky_blue_009`.

- Eligibility described for this startup offering: company within four years of formation; funding requirement shown as $0.
- Free period: six months. Monthly maintenance fee after that period: $25.00.
- Overdraft fee: $0.00.
- Daily mobile check-deposit limit: $25,000.
- APY: 1.25%; interest compounded daily.
- Mobile-deposit procedure: endorse the check, submit clear images in the mobile app, monitor deposit history, and retain the check until confirmation.

### Cobalt Blue

Sources: `doc_business_checking_accounts_cobalt_blue_001`, `doc_business_checking_accounts_cobalt_blue_006`, `doc_business_checking_accounts_cobalt_blue_008`, `doc_business_checking_accounts_cobalt_blue_009`.

- Daily mobile check-deposit limit: $10,000.
- No overdraft fee.
- Monthly maintenance fee: $20.00; the described waiver requirement is maintaining a daily balance at or above $2,500.
- APY: 0.5%; interest compounds daily.
- Included transaction allotment documented as 175 per month.
- The product documents do not establish that another checking account is superior on every Cobalt Blue feature.

### True Blue

Source: `doc_business_checking_accounts_true_blue_007`.

- Same-day ACH: available at no additional fee.
- Daily mobile check-deposit limit: $50,000.
- Maximum out-of-network ATM fee rebates: $30 per month.
- This source does not state its overdraft policy. Treat any zero-overdraft requirement as unknown for this candidate unless another current source establishes it.

## Savings products with documented same-day ACH availability

### Gold Saver Account

Sources: `doc_business_savings_accounts_gold_saver_account_006`, `doc_business_savings_accounts_gold_saver_account_002`.

- Same-day ACH: yes.
- Outgoing domestic wire fee: 15 (currency symbol is not specified in source).
- Automated sweeps are evaluated daily: checking balances above $1,000 may be transferred into savings.
- The cited sources do not provide a Gold Saver APY, minimum balance, opening deposit, or withdrawal allowance. Do not claim any of those terms.

### Silver Plus Saver

Sources: `doc_business_savings_accounts_silver_plus_saver_001`, `doc_business_savings_accounts_silver_plus_saver_002`, `doc_business_savings_accounts_silver_plus_saver_005`, `doc_business_savings_accounts_silver_plus_saver_006`.

- Same-day ACH: yes.
- Minimum balance to remain in good standing: $5,000.
- Base APY is 2.5% below the tier-2 threshold and 4.0% above it; the tier-2 threshold is $25,000. Eligible rewards cards can add a documented relationship bonus.
- Interest compounds daily.
- Up to 20 free withdrawals per month.
- Standard external transfer timing is typically two business days; outgoing domestic wire fee: 15 (currency symbol is not specified in source).

### Gold Plus Saver

Sources: `doc_business_savings_accounts_gold_plus_saver_001`, `doc_business_savings_accounts_gold_plus_saver_007`.

- Same-day ACH: yes.
- Base APY: 5.0%; documented eligible rewards-card boosts range from 0.22% to 0.7%.
- Minimum balance: $25,000. Monthly maintenance fee when minimum is not met: $15.00.
- The account includes configurable inbound and outbound investment sweeps.

### Diamond Vault

Source: `doc_business_savings_accounts_diamond_vault_006`.

- Same-day ACH: yes.
- Interest compounds daily.
- No APY, minimum-balance, opening-deposit, or fee term is stated in this source.

### Savings products not suitable for a same-day ACH requirement

- Emerald Saver: same-day ACH is explicitly unavailable (`doc_business_savings_accounts_emerald_saver_007`).
- Bronze Saver Account: same-day ACH is explicitly unavailable; standard ACH typically takes three business days and has a $5,000 daily outbound maximum (`doc_business_savings_accounts_bronze_saver_account_006`).

## Time-bound recommendation priority

Sources: `doc_bank_accounts_bank_accounts_(general)_013`, `doc_bank_accounts_bank_accounts_(general)_015`.

From 2025-11-01 through 2025-11-30 inclusive:

- If multiple business checking accounts meet all customer requirements, rank Sky Blue first, Lime Green second, then other qualifying accounts.
- If multiple business savings accounts meet all customer requirements, rank Gold Saver Account first, Silver Plus Saver second, then other qualifying accounts.

This ordering cannot make an account qualify and must not be applied outside the stated dates.

## Documented opening eligibility and tools

### Business checking

Source: `doc_bank_accounts_bank_accounts_(general)_003`.

To open business checking, the customer must be verified, have at least one `OPEN` personal checking account, have no more than six business checking accounts, have no accounts with status `CLOSED`, and have at least $500 in an existing checking account. The documented opening tool is `open_bank_account_4821`.

### Business savings

Source: `doc_bank_accounts_bank_accounts_(general)_004`.

To open business savings, the customer must be verified; have an `OPEN` business checking account; have fewer than four business savings accounts; have no negative account balances; and have an existing business checking account that has been open at least 30 days and has a balance of at least $2,500. The documented tool call is `open_bank_account_4821(user_id, account_type, account_class)` with `account_type` of `savings`. The optional authorized opening-deposit transfer uses `transfer_funds_between_bank_accounts_7291(source_account_id, destination_account_id, amount)` from the qualifying checking account.

If no opening deposit is made at opening, the documented process says the savings account must be funded within 30 days by internal transfer or external deposit or it will close.
