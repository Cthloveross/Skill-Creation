# Documented rewards rules used by the audit helper

## Point representation and rounding

For the listed cash-back cards, database rewards stored as points represent cash back at one point per cent. Thus a cash-back rate of 4% is 4 points per dollar, 2% is 2 points per dollar, 1.5% is 1.5 points per dollar, and 1% is 1 point per dollar. EcoCard uses sustainability points. All credit-card reward calculations truncate fractional points down to a whole point on each purchase.

## Card-specific rates

| Card | Enhanced rate | Ordinary rate | Conditions |
|---|---:|---:|---|
| Silver Rewards Card | 4 pts/$ on Travel and Software | 1 pt/$ | Merchant-submitted category and posted status determine enhanced eligibility. |
| Business Platinum Rewards Card | 4 pts/$ on Travel, Software, Media | 1.5 pts/$ | Merchant category determines enhanced eligibility. Cash equivalents, balance transfers, and fees do not earn rewards. |
| Crypto-Cash Back | 2 pts/$ on eligible purchases | — | The available rule does not define category-level eligibility exclusions. |
| EcoCard | 5 sustainability pts/$ on qualifying Green purchases | 1 sustainability pt/$ | Green eligibility includes documented green categories/partners, subject to exclusions. |

## EcoCard exceptions

Target, Walmart, Amazon, and ThredUp receive the EcoCard standard rate even for eco-friendly products. EV charging receives the Green rate only through Tesla Supercharger, ChargePoint, and EVgo. The audit helper consequently does not infer the Green rate for another charging merchant.

## Dispute and correction boundary

A customer dispute is initiated by providing `submit_cash_back_dispute_0589(user_id, transaction_id)` to the customer. Once an internal dispute is resolved and approved, use the exact transaction ID, independently calculate the correct whole-point reward, unlock `update_transaction_rewards_3847`, and update it with `new_rewards_earned` formatted as `X points`. Confirm the final transaction record after the update.