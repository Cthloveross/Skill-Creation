# Credit-card referral rules

## Cross-card weekly limit

A customer can receive no more than two referral bonuses in any rolling seven-day window. The cap applies across all credit-card types. The third and later referrals in that window are automatically denied. A referral denied for this limit cannot be reinstated within that seven-day window. The controlling window is based on exact timestamps of successful referral bonuses, not calendar weeks.

## Silver Rewards Card

* Referral bonus: 75 for each successful referral, up to seven referral bonuses per calendar year.
* The referred person must be approved and spend at least $750 within 60 days of account opening.
* The bonus typically posts one to two billing cycles after the referred account meets that qualifying-spend requirement.

## Platinum Rewards Card

* Referral bonus: $100 for each friend who is approved and meets qualifying spend, up to seven referral bonuses per calendar year.
* The referred friend must spend at least $1,500 within 90 days of account opening.
* Bonuses are typically credited after approval and the qualifying spend are met. Self-referrals and duplicate applications do not qualify. The referrer’s account must be in good standing for prompt receipt.

## Referral-link workflow

Before a customer receives a referral-link tool, confirm the exact card has a documented referral program, confirm their understanding matches the documented terms, and ensure the referral is not expected to be automatically rejected by the weekly cap. When eligible, the customer must run `get_referral_link(user_id: str, card_name: str)` themselves using their own user ID and the exact card name. The agent must not generate the link on the customer’s behalf. A successful call creates a referral record in `NO_PROGRESS` status.
