# Referral-link policy reference

Use these rules when applying the Skill:

- The exact requested card must have a documented referral program before a referral-link tool may be offered.
- The customer's stated offer must match documented program terms. If the program is not documented or the terms are incorrect, explain why, do not provide the tool, and do not transfer to a human solely for that issue.
- Referral benefits and qualification requirements vary by card; not every card participates.
- Customers may receive no more than two referral bonuses in a rolling seven-day period across all card types. Later referrals in that window are automatically denied.
- Where permitted, the customer must run `get_referral_link(user_id, card_name)` themselves with their own user ID and the exact card name. An agent must not generate it for them.
- Successful generation creates a `NO_PROGRESS` referral record. The invitee can then use the link to apply.
