# Personal Savings Opening Policy Reference

Before opening a personal savings account, verify and log customer identity, then retrieve the customer's accounts with `get_all_user_accounts_by_user_id_3847`. Confirm an active/open Rho-Bank checking account, checking tenure of at least 14 days, fewer than five personal savings accounts, no accounts in collections, and no negative balances.

After the customer confirms the complete official account class name ending in `Account`, call `open_bank_account_4821(user_id, 'savings', account_class)`. Funding can occur only after the opening succeeds and returns a destination account ID. An immediate transfer additionally requires customer authorization, a selected active checking source, and enough available balance for the complete amount. Never transfer a partial amount as a substitute.

If immediate funding is not completed, including because an authorized requested internal transfer exceeds the available balance, clearly state that no internal transfer was made. An external deposit may be offered, but it remains unreceived and unconfirmed unless a system result confirms receipt. State that funding is required within 30 days of opening by internal transfer or external deposit or the account will close.

For APY comparisons, use only listed linked checking/savings pairings. Multiple checking boosts do not stack; select the highest applicable one. Credit-card APY bonuses also do not stack; select the highest applicable card bonus. These selections may stack only with separately documented bonuses whose conditions are met.
