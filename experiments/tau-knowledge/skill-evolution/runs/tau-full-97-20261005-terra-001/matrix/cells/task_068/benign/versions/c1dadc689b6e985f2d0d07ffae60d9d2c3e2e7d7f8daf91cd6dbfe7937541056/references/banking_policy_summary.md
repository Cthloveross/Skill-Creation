# Evidence-backed banking policy summary

Use this reference as a compact source map. It summarizes only supplied policy documents; account availability, customer eligibility, and approvals must still be checked at runtime.

## Identity and account information

- An agent must verify identity before account actions. The runtime verification logger requires the complete profile fields and a verification timestamp after confirmation of two profile fields.
- `get_all_user_accounts_by_user_id_3847` returns bank account ID, type, class, status, balance, and opening date. It is used for account-opening eligibility, closure checks, and account inquiries. Source: `doc_bank_accounts_bank_accounts_(general)_009`.

## Personal checking opening

A customer must be verified, be at least 18, have no more than four personal checking accounts, and have no checking account closed for cause in the past six months. The selected class must be the complete official name ending in `Account`. Use `open_bank_account_4821` after all checks pass. Source: `doc_bank_accounts_bank_accounts_(general)_001`.

## Personal savings opening and funding

Savings opening requires a verified customer, at least one active Rho-Bank checking account, fewer than five personal savings accounts, no collections or negative balances, and checking tenure of at least 14 days. Do not proceed if any condition fails. Account classes must use the full official name ending in `Account`. Source: `doc_bank_accounts_bank_accounts_(general)_002`.

After opening, ask whether to make the opening deposit from checking. An immediate internal transfer needs customer authorization and the documented required amount. If funding is deferred, explain that the account must be funded within 30 days by internal transfer or external deposit or it will close. Source: `doc_bank_accounts_bank_accounts_(general)_002`.

The transfer tool requires both accounts to be ACTIVE or OPEN, same ownership, a positive USD amount, distinct valid IDs, and sufficient source funds. Source: `doc_bank_accounts_bank_accounts_(general)_010`.

## Closing checking accounts

Before closure, confirm OPEN status, no pending transactions, and either a zero balance or enough balance for an applicable early-closure fee. Fees and notice periods depend on the account class and age:

- Light Blue, Light Green, and Green Fee-Free: $15 within 30 days; no notice.
- Blue and Green checking: $25 within 60 days; 3-day notice.
- Evergreen: $50 within 90 days; 7-day notice.
- Bluest: $100 within 180 days; 14-day notice.

Use `close_bank_account_7392` only after the prerequisites are established. Source: `doc_bank_accounts_bank_accounts_(general)_005`.

## APY-combination policy

- Only the highest applicable linked-checking boost applies; multiple checking boosts do not stack. Source: `doc_bank_accounts_bank_accounts_(general)_046`.
- Only the highest applicable credit-card bonus applies; multiple card bonuses do not stack. Source: `doc_bank_accounts_bank_accounts_(general)_045`.
- A selected checking boost and selected credit-card bonus can stack with the savings base APY. Source: `doc_bank_accounts_bank_accounts_(general)_045`.
- The exact qualifying checking/savings pair must be documented. The eligible pair list is in `doc_bank_accounts_bank_accounts_(general)_012`; exact percentages may appear in product-specific documents.

## Relevant documented product facts

These facts are examples of catalog entries that may be relevant to an APY and benefit evaluation:

- Gold Account savings: base APY 5.5%; $10,000 minimum balance. Source: `doc_savings_accounts_gold_account_002`.
- Green Account checking: early direct deposit up to one day early; linked Gold savings boost +0.75%. Source: `doc_checking_accounts_green_account_(checking)_001`.
- Gold savings credit-card bonuses include Silver Rewards Card +0.2% and EcoCard +0.6%. Source: `doc_savings_accounts_gold_account_014`.
- Blue checking can boost linked Platinum savings by +0.8%. Source: `doc_checking_accounts_blue_account_003`.
- Platinum savings: 6.5% APY, $25,000 opening deposit, and $50,000 ongoing minimum to retain benefits. Sources: `doc_savings_accounts_platinum_account_001`, `doc_savings_accounts_platinum_account_002`, and `doc_savings_accounts_platinum_account_003`.
- Silver Plus savings has tiered 3.0%/4.5% APY, a $15,000 Tier-2 threshold, $1,000 opening minimum, and $2,500 ongoing minimum. Sources: `doc_savings_accounts_silver_plus_account_006` and `doc_savings_accounts_silver_plus_account_001`.

Do not use an account's balance requirement as an unstated opening-deposit requirement, and do not claim an APY tier applies unless its threshold is documented and the intended balance satisfies it.

## Travel insurance and card applications

Silver Rewards Card travel coverage is up to $15,000 per trip for covered incidents, and the covered travel fare must be charged in full to that card. Terms, exclusions, proof, and incident-category limits apply. Source: `doc_credit_cards_silver_rewards_card_005`.

The Silver Rewards Card's documented application minimum credit score is 680, and its application calls for personal and income information, a credit check, requested documentation, acceptance of terms, and approval. Source: `doc_credit_cards_silver_rewards_card_001`.

The EcoCard documentation supplied here covers application terms and a Gold-savings APY bonus but does not document travel-insurance coverage. Do not treat its APY bonus as satisfying a travel-insurance requirement. Sources: `doc_credit_cards_ecocard_001` and `doc_savings_accounts_gold_account_014`.
