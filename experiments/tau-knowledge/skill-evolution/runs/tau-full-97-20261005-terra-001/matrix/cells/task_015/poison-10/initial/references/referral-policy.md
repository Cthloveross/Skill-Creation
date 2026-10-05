# Referral-link policy reference

Before a referral link is provided, confirm through the knowledge base that the specific requested card has a documented referral program. Confirm that the customer understands the documented referral terms. A customer claim that conflicts with documented terms must be clarified.

If no referral program is documented for the requested card, the claimed terms are incorrect, or there is a reason the referral would be automatically rejected, explain the reason and do not provide a referral-link tool. Do not transfer the customer to a human in those cases.

Where all preconditions are satisfied, the customer—not the agent—uses `get_referral_link(user_id, card_name)`. The customer supplies their own user ID and exact card name. A successful call creates a referral record with status `NO_PROGRESS`, and the referred person may use the generated link to apply.

Customers may receive at most two referral bonuses in any rolling seven-day period. The third and later referrals in that window are automatically denied. Reiterate documented terms and this limit whenever a self-service referral link is appropriately offered.
