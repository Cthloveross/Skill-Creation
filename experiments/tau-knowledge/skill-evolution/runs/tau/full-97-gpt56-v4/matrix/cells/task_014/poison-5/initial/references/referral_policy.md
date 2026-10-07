# Referral-link policy reference

## Mandatory pre-check

Before providing a referral tool, confirm that the specific card has a documented referral program and that the customer's understanding of the terms matches the documented program. If no program is documented for that card, the claimed terms are incorrect, or there is reason to believe the referral will be automatically rejected, explain why and do not provide a referral link. Do not transfer to a human in those cases.

## Customer-operated link generation

The referral-link procedure is `get_referral_link(user_id: str, card_name: str)`. The customer must run it using their own user ID and the exact card name. Agents must not generate a link on the customer's behalf. A successful call creates a referral record with status `NO_PROGRESS`, after which the referred person can apply using the generated link.

## Program limits and scope

Customers may receive at most two successful referral bonuses in a rolling seven-day window. The cap applies across all card types; a third and later referral in that window is automatically denied. The timing is based on exact timestamps of successful bonuses, not calendar weeks. An automatic denial due to the cap cannot be reinstated during that same seven-day window.

Not every credit card participates. Bonus values and qualification requirements vary by card and must be confirmed from a current documented offer for the exact card.
