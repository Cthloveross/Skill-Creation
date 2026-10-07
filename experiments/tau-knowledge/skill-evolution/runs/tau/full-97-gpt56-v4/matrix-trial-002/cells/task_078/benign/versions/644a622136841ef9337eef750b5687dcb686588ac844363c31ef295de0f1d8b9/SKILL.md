---
name: lost-debit-card-security-and-replacement
description: Securely handles a verified customer's confirmed lost or stolen debit cards: identify eligible cards and checking accounts, check cross-product exposure, close cards when authorized, and order tier-compliant replacements with correct fees. Use for one or multiple lost/stolen debit cards, especially where shipping/design choices vary by account tier.
---

# Lost/Stolen Debit Card Security and Replacement

Use this Skill when a customer has lost or had debit cards stolen and wants the cards secured, closed, and/or replaced. It is a workflow guide only: banking changes must be performed through the declared banking tools after unlocking them.

## Important operating rule

A freeze is temporary and a close is permanent. For a customer who has confirmed the card is lost/stolen **and has authorized permanent closure**, do not freeze an ACTIVE card before trying to close it: the closure procedure only permits ACTIVE or PENDING cards, while freezing changes it to FROZEN. Close the eligible card directly, which permanently prevents further use. If the customer only wants temporary protection or has not consented to closure, freeze ACTIVE cards instead.

## Required workflow

1. **Verify identity and authority.** Obtain and match at least two of date of birth, email, phone number, and address to the identified profile. Confirm the customer is the card owner. Call `get_current_time`, then call `log_verification` with the matched profile fields and timestamp. Do not make card changes until verification is logged.
2. **Confirm intent per card.** Establish whether the card is temporarily misplaced (freeze) or confirmed lost/stolen (close). Obtain explicit authorization before closing. Record the desired delivery, design, and US mailing address. A stated preference such as “the best free option for each account” selects the fastest no-charge option once the account tier is known, but it is not a waiver of the pre-order disclosure: after the account-specific quote is known, state the exact delivery/design, each fee (including $0), the automatic checking-account debit rule, and the delivery address, then obtain the customer's confirmation to order that exact replacement.
3. **Check cross-product exposure.** For every lost/stolen report, call `get_credit_card_accounts_by_user`. If credit cards exist, ask whether they were also in the wallet and offer replacement protection. If none exist, state that no Rho-Bank credit cards were found; do not make an unnecessary offer.
4. **Discover and inspect records.** Unlock and use `get_all_user_accounts_by_user_id_3847` and `get_debit_cards_by_account_id_7823`. For each target card, confirm it belongs to the verified user, identify its linked checking account and account class/tier, and inspect its status. Fetch `get_bank_account_transactions_9173` for each linked account before closure. Do not close a card if the available activity shows a pending transaction or pending refund that must settle; explain the block. Treat the account transaction view conservatively if it cannot establish which card is involved.
5. **Close or freeze.**
   - For a permanent lost/stolen closure, only proceed when the card is ACTIVE or PENDING, ownership is confirmed, and no pending transaction/refund blocks closure. Lost/stolen closures bypass the 14-day card-age requirement. Unlock and call `close_debit_card_4721` using the tool's exposed schema, with the card ID and the applicable lost/stolen reason. Do not retry an action whose outcome is unknown.
   - For temporary protection only, require ACTIVE status and call `freeze_debit_card_3892` with the card ID. Explain that new and recurring transactions decline while frozen, although authorized pending transactions can still process.
   - Report every individual success, failure, or deferred card separately. Do not imply that all cards were secured if one was ineligible or failed.
6. **Assess each replacement only after successful closure.** The linked account must be an OPEN checking account, have at least $25 balance, be open at least three business days, have no PENDING card order, have no remaining ACTIVE debit card, and have a valid US domestic mailing address. Review card history for replacement issue reasons `lost`, `stolen`, `fraud`, and `damaged` issued in the preceding rolling 12 months. `new_account`, `first_card`, `expired`, `upgrade`, and `bank_reissue` do not count. For an Entry account, wait 48 hours after closure before an order; do not bypass this wait. Treat a reported account `level` as a runtime tier label only when the supported environment establishes its mapping; do not guess a tier from an unfamiliar label.
7. **Calculate, disclose, and confirm fees.** Use `scripts/replacement_quote.py` for each account or calculate from the same rules. Before submitting an order, provide an account-specific quote naming the exact delivery option, design, delivery fee, design fee, applicable excess fee, total, mailing address, and the fact that all applicable fees are automatically deducted from the linked checking account. Do this even when the total is $0. If the user wants the best free delivery, propose: Entry—STANDARD; Mid—STANDARD; Premium—EXPEDITED; Elite—RUSH. Use CLASSIC for “no extra design charge” unless the customer makes another design selection. Wait for a confirmation to order the quoted selection. An excess fee is not implicitly authorized by a request for a free option: obtain explicit agreement to it, or wait for the qualifying history to age out.
8. **Order only eligible, confirmed replacements.** Unlock `order_debit_card_5739` and inspect its actual exposed parameter schema. Do not submit an order merely because a customer gave an earlier general replacement request or “best free” preference; first receive their confirmation to the exact disclosed quote. Then supply its required account, delivery, design, mailing-address, and other supported fields, including the exact `delivery_fee` and `design_fee` from the quote. Never invent an unsupported parameter. If an excess-replacement fee applies, use an explicitly exposed excess-fee field only if present and after the customer expressly authorizes the charge; otherwise explain the limitation and seek the supported resolution rather than mislabeling it as delivery or design cost.

### Pending-activity closure block

A pending transaction/refund blocks permanent closure, but not an ACTIVE card's temporary freeze. If the customer asks to secure a confirmed-lost card during that block, explain the pending items may still settle and freeze it as an interim protection. Do **not** claim it is permanently closed or order its replacement. On a later request after the block clears, re-verify the customer and reconfirm closure authorization. Because the closure tool accepts ACTIVE/PENDING and a frozen card cannot be closed, use the documented unfreeze flow only when the linked account remains OPEN, then immediately close it under the already reconfirmed lost/stolen authorization. Clearly disclose this necessary brief status transition; never silently unfreeze a lost card.
9. **Final response.** List the old card(s) secured/closed (using only safe identifiers such as last four digits), each replacement's account, delivery/design, fee breakdown and automatic debit notice, address confirmation, expected timeframe if supplied by the ordering tool, and any outstanding wait, pending-activity, or eligibility block. Remind the customer that closed cards cannot be reactivated and recurring merchants need new card details.

## Tier rules

| Tier | Permitted delivery and delivery fee | Design fees | Replacement limit |
|---|---|---|---|
| Entry | STANDARD $0 only | CLASSIC $0; PREMIUM $10; CUSTOM $25 | 2/rolling 12 months; then wait or $25 excess fee; 48-hour post-closure wait |
| Mid | STANDARD $0; EXPEDITED $15 | CLASSIC $0; PREMIUM $10; CUSTOM $25 | 3/rolling 12 months; then wait or $15 excess fee |
| Premium | STANDARD $0; EXPEDITED $0; RUSH $35 | CLASSIC/PREMIUM $0; CUSTOM $15 | 5/rolling 12 months; thereafter must wait |
| Elite | STANDARD/EXPEDITED/RUSH $0 | all designs $0 | unlimited |

Premium expedited and Elite rush are the fastest free choices. Entry does not offer expedited/rush; Mid does not offer rush. Do not silently substitute an unavailable delivery option.

## Quote helper

`scripts/replacement_quote.py` accepts JSON on stdin and emits JSON on stdout. It performs deterministic tier, delivery/design fee, rolling-history, and Entry waiting-period evaluation. It does not access bank records and never performs a banking action.

Input schema:
```json
{
  "tier": "PREMIUM",
  "now": "YYYY-MM-DDTHH:MM:SS",
  "cards": [{"issue_reason": "lost", "date_issued": "YYYY-MM-DD"}],
  "closure_at": "YYYY-MM-DDTHH:MM:SS",
  "delivery": "BEST_FREE",
  "design": "CLASSIC",
  "excess_fee_authorized": false
}
```

`delivery` may be `BEST_FREE`, `STANDARD`, `EXPEDITED`, or `RUSH`; `design` may be `CLASSIC`, `PREMIUM`, or `CUSTOM`. `closure_at` is required for an Entry waiting-period calculation. Set `excess_fee_authorized` true only after the customer expressly authorizes that excess fee. The result includes selected fees, free options, counted replacement history, and blocking conditions. Validate that `eligible_to_order_now` is true and that the returned delivery/design and every fee have been disclosed and then confirmed by the customer before calling the order tool.

Example runnable invocation (with runtime-derived values, not hardcoded case data):
```sh
python3 scripts/replacement_quote.py <<'JSON'
{"tier":"PREMIUM","now":"2025-01-15T12:00:00","cards":[],"delivery":"BEST_FREE","design":"CLASSIC"}
JSON
```
