# Rewards rules used by this Skill

## Business Silver Rewards Card

- Eligible purchases posted under a travel or software merchant category earn 10.0% cash back.
- All other purchases earn 1.0% cash back.
- Eligibility depends on the merchant's transaction category, not merely the goods or service described by the merchant.
- Listed travel examples include airlines, lodging, car rentals, rideshare/taxis, passenger rail/buses/ferries, qualifying parking/tolls, and travel agencies or online travel platforms categorized as travel.

### Business Silver exclusions

These merchant groups earn the standard 1.0% rate rather than the 10.0% bonus rate, even if their posted category is Travel or Software:

- Corporate expense platforms: Concur, SAP Concur, Expensify, Navan
- Hardware/electronics: Apple, Microsoft, Dell
- Gaming subscriptions: Xbox Game Pass, PlayStation Plus, Nintendo Switch Online
- Online learning: Coursera, Udemy, LinkedIn Learning, Skillshare, Pluralsight

### Business Silver double-cash-back offer

New Business Silver customers who opened their account during 2024-11-14 through 2025-11-14 earn twice the normal cash-back rate on purchases during their first six months after account opening. The normal 10% Travel/Software rate becomes 20%; the normal 1% rate, including an exclusion's standard rate, becomes 2%. The script treats the six-month anniversary as the first date outside the window: a purchase dated before that anniversary is promotional.

## Consumer Silver Rewards Card

Eligible posted Travel and Software purchases earn 4.0% cash back. Other purchases do not receive that enhanced rate. Eligibility depends on the posted merchant category. The Business Silver offer does not apply to this card.

## Points representation

For these cash-back cards, database rewards labeled `points` represent cash back at 1 point = $0.01 when redeemed as a statement credit or checking-account credit. Rewards are calculated after a transaction posts. Returned or refunded purchases have rewards reversed when the credit posts.
