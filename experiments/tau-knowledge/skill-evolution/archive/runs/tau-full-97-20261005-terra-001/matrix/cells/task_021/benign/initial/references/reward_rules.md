# Reward rules used by the audit

## Shared rounding and representation

- Credit-card rewards are truncated (rounded down) to a whole point on each purchase.
- Transaction databases store rewards as points. For Business Bronze cash back, 1 point equals $0.01. Thus 1.0% cash back on an eligible amount is stored as one point per dollar, with fractional points floored.
- EcoCard sustainability points also redeem at $0.01 per point, but their earn rates are points per dollar rather than cash-back percentages.

## Business Bronze Rewards Card

- Eligible net posted purchases earn 1.0% cash back.
- 0-point named merchant exclusions: WeWork, Regus, Industrious, Gusto, ADP, Paychex, and Rippling.
- Slack, Zoom, HubSpot, and Salesforce earn the base rate only during the first 12 months of the subscription. Subsequent subscription payments earn 0 points.
- Returns or credits reduce rewards. A transaction review must use the final net amount and should not guess the original earn rate for a stand-alone negative record.

## EcoCard

- Qualifying green purchases earn 5 points per dollar; other purchases earn 1 point per dollar.
- Amazon, Target, Walmart, and ThredUp always earn the standard rate, including environmentally marketed items.
- EV charging earns the high rate only at Tesla Supercharger, ChargePoint, and EVgo.
- Green qualification can come from a verified merchant/category designation. Marketplace processing, mixed carts, and unverified seller-of-record information may prevent a purchase from qualifying; do not infer eligibility from product descriptions alone.

## Dispute and correction boundary

A customer with a potential reward discrepancy should receive the customer-executed `submit_cash_back_dispute_0589(user_id, transaction_id)` process after the transaction ID is confirmed. Internal reward updates are for resolved and approved disputes only, must independently calculate the whole-point result, and require `update_transaction_rewards_3847` with `new_rewards_earned` formatted as `X points`.
