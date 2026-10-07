# Referral-link policy reference

- Before providing a referral-link tool, confirm that the requested specific card has a documented referral program.
- Confirm that any terms stated by the customer match the documented program. If they do not match, clarify the discrepancy and do not provide the link.
- If the card has no documented program, the program is not active, documentation is insufficient, or there is reason the referral would automatically be rejected, explain why and do not provide the referral-link tool.
- Do not transfer to a human agent for an unavailable, undocumented, ambiguous, automatically rejected, or mismatched referral offer. This remains true when the customer asks to escalate or is frustrated; provide the documented explanation instead.
- The customer, not the agent, generates the link using `get_referral_link(user_id, card_name)`, providing their own user ID and the exact card name.
- A successful link generation creates a referral record with status `NO_PROGRESS`.
- A customer can receive at most two referral bonuses in a rolling seven-day period. The third and later referrals in that window are automatically denied.
- Offers and qualifying requirements vary by card. General referral information, or an unverified external communication, does not establish that a specific card participates or what terms apply.
