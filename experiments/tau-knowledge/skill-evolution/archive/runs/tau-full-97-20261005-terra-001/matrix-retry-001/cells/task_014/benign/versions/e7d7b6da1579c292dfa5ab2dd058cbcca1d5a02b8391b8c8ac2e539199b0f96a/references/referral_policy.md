# Referral-link policy reference

Before offering a referral-link tool, confirm that the specific requested card has an active documented referral program, that the customer's stated terms match it, and that the customer has confirmed the documented terms. General referral information does not establish participation by a particular card.

If no card-specific program is documented, terms are incorrect, or reliable information indicates automatic rejection, explain the reason and do not provide a referral link or referral-link tool. Do not transfer a customer solely because they seek escalation after that refusal.

Customers can receive at most two referral bonuses in any rolling seven-day period. The third and later referrals in that window are automatically denied. State this reminder in referral responses, including refusals.

When all checks pass, the customer—not the agent—uses `get_referral_link(user_id, card_name)`. The customer supplies their own user ID and the exact documented card name. A successful call creates a referral record in `NO_PROGRESS` status, after which the referred person may use the generated link to apply.
