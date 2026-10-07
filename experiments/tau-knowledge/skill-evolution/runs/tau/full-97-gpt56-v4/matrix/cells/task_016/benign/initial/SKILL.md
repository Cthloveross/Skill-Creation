---
name: credit-card-referral-status-support
description: Assist a credit-card customer who has not received a referral bonus by locating the relevant referral, interpreting its status, explaining card-specific qualifying requirements and timing, and protecting the referred person's account privacy. Use for referral-bonus status questions when normal banking lookup tools are available.
---

# Credit-card referral status support

## Purpose and boundaries

Use this Skill to investigate a customer's own referral record and give an accurate status explanation. A referral record can establish its current status, but it does not authorize disclosure of another customer's account, card, or transaction details. Do not promise a bonus, manually grant one, or retry a referral merely because it is pending or rejected.

The referral offer and qualification rules are card-specific. Only state a reward amount, spending threshold, qualification window, payout time, annual cap, or weekly cap when the applicable card's documented terms support it.

## Workflow

1. **Identify the referrer and intended referral.**
   - Obtain a customer identifier, exact name, or email, then use the available user lookup and `get_referrals_by_user` tools.
   - If multiple referrals exist, ask which card or date is in question. If the customer says it is the most recent pending referral, confirm the matching record rather than guessing.
   - Treat the referral status returned by the system as authoritative.

2. **Observe verification requirements.**
   - Follow the runtime's identity-verification procedure before taking actions that require it. In particular, only call `log_verification` after the customer has confirmed two of the four required identity fields, and obtain the current time for its audit timestamp.
   - A lookup result alone is not customer confirmation of identity fields.

3. **Interpret the referral status.**
   - `COMPLETE`: say the referral has completed and the bonus is handled under the applicable offer terms.
   - `IN_PROGRESS`: say the referred person successfully opened an account and is still working toward the qualifying criteria. Do not imply that card use alone proves qualification.
   - `NO_PROGRESS`: explain that no application has started; the referrer may remind the invitee to apply using the referral link/code.
   - `APPLIED`: explain that the application decision is pending and no manual action is needed.
   - `REJECTED`: do not tell the customer to retry immediately. Explain that existing referral activity should be reviewed and that a weekly-cap denial cannot be reinstated inside the same rolling window.
   - `ERROR`: advise retrying later or internal escalation if it persists. Do not invent a cause.

4. **Apply the matching card terms.**
   - For a documented Silver Rewards Card referral, the invitee must be approved and spend at least $750 within 60 days after account opening. The referrer bonus normally posts one to two billing cycles after the threshold is met. The stated reward is 75 and the calendar-year maximum is seven bonuses.
   - Credit-card referrals are also subject to a cross-card rolling seven-day limit of two successful referral bonuses. It is based on exact bonus timestamps, not calendar weeks; later referrals exceeding it are automatically denied. Do not calculate compliance from dates alone when timestamps or bonus-posting facts are absent.
   - Other cards may have different terms. If the matching card's terms are not available, say that the specific requirements and offer need confirmation rather than applying Silver terms.

5. **Handle requested invitee-spend verification safely.**
   - Ask for a valid exact full name (including capitalization), email address, or user ID for the invitee if the available workflow permits a lookup. Use the supplied identifier with normal lookup tools.
   - If it produces no account/customer/transaction record, clearly state that it could not be matched. Ask for a valid exact name or email; do not search broadly, infer an identity, or reveal whether other possible customers exist.
   - If the customer cannot provide a valid identifier, explain that there is no alternate account lookup available through this workflow and that the invitee can check their own account or provide their accurate identifying detail. You may still explain the referral's visible status and published eligibility terms.
   - Do not reveal the invitee's transaction amounts, account-opening date, card balance, contact data, or other account details to the referrer. If the normal tools do not allow a privacy-safe determination, state that you cannot verify the invitee's qualifying spend from the information provided.

6. **Give a concise final response.** Include:
   - the confirmed referral card/date/status when available;
   - what that status means;
   - applicable published criteria and normal timing, qualified as not yet verified when appropriate;
   - the precise next step, if more identification or time is needed;
   - no unsupported promise that payment will post on a particular date.

Use a human transfer only when the customer requests one, a supported escalation condition applies, or the issue cannot be handled with the available normal workflow. Select only an available, applicable transfer reason.

## Optional deterministic helper

`scripts/referral_assessor.py` turns structured, already-authorized referral facts into status wording and next-step guidance. It never performs banking actions or accesses accounts. Send JSON on stdin and receive JSON on stdout.

Input schema:

```json
{
  "referral_status": "IN_PROGRESS",
  "card_type": "Silver Rewards Card",
  "referral_date": "optional display date",
  "invitee_lookup": "not_attempted|matched|not_found|unavailable",
  "has_invitee_identifier": false,
  "card_terms_known": true
}
```

Run example:

```sh
python3 scripts/referral_assessor.py <<'JSON'
{"referral_status":"IN_PROGRESS","card_type":"Silver Rewards Card","invitee_lookup":"not_found","has_invitee_identifier":true,"card_terms_known":true}
JSON
```

Validate that `status_meaning`, `customer_message_points`, and `next_step` match the tool-confirmed status and do not expose invitee data. The executor must still use normal banking tools for live lookup and compose the customer-facing response from authorized facts.