# Referral policy reference

Use this reference only for the documented rules below.

## Shared rolling limit

A customer may receive no more than two referral bonuses in any rolling seven-day window. The limit applies across all credit-card types. A third and subsequent referral in that window is automatically denied and cannot be reinstated in that same window. The window is based on exact timestamps of successful bonuses, not calendar weeks.

## Silver Rewards Card

- Bonus: 75 for each successful referral.
- Referred person must be approved and spend at least $750 within 60 days of account opening.
- Bonus typically posts one to two billing cycles after the spend requirement is met.
- Annual cap: seven referral bonuses per calendar year.
- An `IN_PROGRESS` referral record does not establish approval or qualifying spend. Do not disclose or infer the referred person's account activity.

## Platinum Rewards Card

- Bonus: $100 per referral that is approved and meets qualifying spend.
- Referred person must spend at least $1,500 within 90 days of account opening.
- Annual cap: seven referral bonuses per calendar year.
- Self-referrals and duplicate applications do not qualify.

## Referral link procedure

The exact card must have a documented active referral offer and the customer must understand its documented terms before a link tool is provided. The customer, not the agent, runs `get_referral_link(user_id, card_name)` using their own ID and the exact card name. A successful call creates a `NO_PROGRESS` referral record. Do not provide the tool if the offer is undocumented, terms cited are wrong, or the referral would be automatically rejected.
