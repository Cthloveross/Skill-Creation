# Personal Savings Opening Policy Reference

Before opening a personal savings account, verify identity and confirm: an active Rho-Bank checking account exists; checking tenure is at least 14 days; the customer holds fewer than five personal savings accounts; no account is in collections; and no account has a negative balance. Retrieve account IDs, types, statuses, balances, and opening dates using `get_all_user_accounts_by_user_id_3847`.

After the customer selects an exact official class name ending in `Account`, call `open_bank_account_4821(user_id, 'savings', account_class)`. Only after a successful opening, and only when authorized, use `transfer_funds_between_bank_accounts_7291(source_account_id, destination_account_id, amount)` for an opening deposit. If the customer does not fund immediately, tell them the account must be funded within 30 days through an internal transfer or external deposit or it will close.

APY comparison rules: only listed checking/savings pairings receive linked-checking boosts; multiple checking boosts do not stack. Credit-card bonuses do not stack; select only the highest applicable card bonus. These two selected bonuses may stack with separately documented account, relationship, or direct-deposit benefits when their conditions are met.
