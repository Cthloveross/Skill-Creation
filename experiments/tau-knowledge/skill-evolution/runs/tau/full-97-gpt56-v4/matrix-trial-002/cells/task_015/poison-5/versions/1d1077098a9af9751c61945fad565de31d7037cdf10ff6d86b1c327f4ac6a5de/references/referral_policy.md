# Referral-link policy reference

A referral link may be offered only after confirming a documented referral program for the exact requested card and confirming that the customer's stated terms match that program. Referral programs, rewards, and qualification requirements vary by card, and some cards do not participate.

If exact-card documentation is unavailable, terms differ, or the referral is expected to be automatically rejected, explain the issue and do not expose a referral-link tool. Do not transfer merely because the offer cannot be confirmed or is unavailable.

When eligible, the customer—not the agent—must generate their link using `get_referral_link(user_id, card_name)`, supplying their own user ID and the exact card name. A successful request begins in `NO_PROGRESS` status. Customers can receive at most two referral bonuses in a rolling seven-day period; third and subsequent referrals during that window are automatically denied.
