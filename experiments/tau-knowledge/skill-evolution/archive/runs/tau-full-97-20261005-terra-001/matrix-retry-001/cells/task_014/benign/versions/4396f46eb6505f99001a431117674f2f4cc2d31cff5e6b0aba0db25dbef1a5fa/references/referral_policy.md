# Referral-link policy reference

Before offering a referral-link tool, confirm that the specific requested card has a documented referral program and that the customer's stated terms match that program. If no program is documented, terms are incorrect, or there is reason to believe the referral will automatically be rejected, explain why and do not provide a link or transfer solely for that issue.

When all checks pass, the customer—not the agent—must use `get_referral_link(user_id, card_name)`. The customer supplies their own user ID and the exact card name. A successful call creates a referral record in `NO_PROGRESS` status, after which the referred person may use the generated link to apply.

Customers may receive no more than two referral bonuses in a rolling seven-day period. The third and later referrals in that window are automatically denied. Card participation, bonus amounts, and qualification requirements vary by card; general referral information does not establish a specific card offer.
