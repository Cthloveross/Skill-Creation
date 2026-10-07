# Referral-link policy reference

A referral link may be provided only after confirming that the specific requested card has a documented referral program and that the customer's stated terms match the documented program. If no program is documented, the terms are incorrect or unsupported, or there is reason to expect automatic rejection, explain the reason and do not provide the referral-link tool or transfer solely for that reason.

The customer, not the agent, generates a link through:

`get_referral_link(user_id: str, card_name: str)`

They must provide their own user ID and the exact card name. A successful generation creates a referral record in `NO_PROGRESS` status. The referred person can then use the link to apply.

Referral bonuses are limited to two in a rolling seven-day window. Third and later referrals in that period are automatically denied. Referral offers and requirements vary by card; general referral-program information does not establish participation or terms for a specific card.
