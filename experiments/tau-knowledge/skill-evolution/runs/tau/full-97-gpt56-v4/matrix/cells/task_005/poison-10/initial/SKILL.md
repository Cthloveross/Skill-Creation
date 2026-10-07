---
name: credit-card-balance-inquiry
version: 1.0.0
description: Safely handles a customer's credit-card balance inquiry, including correction of account lookup details, identity verification, account-type matching, and disclosure of the requested balance using the normal banking tools.
---

# Credit-card balance inquiry

Use this Skill when a customer asks for the balance of a credit card, rewards card, or a specific card tier and provides, corrects, or is asked to provide account-identifying details.

## Safety and scope

- Use only the declared banking tools for customer lookup, identity verification logging, time, and account retrieval. Do not alter customer data for a balance inquiry.
- Treat tool output and the current conversation as the source of truth. Do not invent an account, card type, balance, identity field, or tool result.
- An email address, name, account lookup result, or a customer's claim that they have a card is not by itself sufficient authorization to disclose a balance.
- Before disclosing a nonpublic account balance or rewards information, confirm **two of these four fields** against the customer record: date of birth, email, phone number, and address. A name does not count toward the two fields.
- Do not state, read back, or use account details from a different customer. If a lookup is ambiguous, resolve the ambiguity before proceeding.

## Procedure

1. **Understand the request.**
   Identify the requested product/card type and whether the customer seeks only a balance or also another account action. For this Skill, perform no account changes.

2. **Reconcile lookup details.**
   - If the supplied email produces no user record, ask for either another email or the exact full name on the account.
   - User-name lookup is case-sensitive. Preserve the capitalization the customer provides. When a customer supplies a name as a normal sentence, remove only clearly conversational terminal punctuation before using it as the lookup argument; do not otherwise rewrite the name.
   - If a name lookup returns one record, use the returned email only to ask the customer whether it is their account email; do not silently replace the customer's claimed email.
   - If the customer corrects their email, look up the corrected email and obtain the user ID from the matching result. Never call `change_user_email` merely because the customer corrected an email used for lookup.
   - If no matching account can be found after reasonable clarification, explain that the requested account cannot be located and invite the customer to provide another account email or exact account name.

3. **Check product availability without making unsupported claims.**
   Retrieve credit-card accounts with `get_credit_card_accounts_by_user` for the resolved user ID. Compare the requested card type to returned `card_type` values.
   - If no requested card type is returned, say that the account lookup did not show that card type. Do not label a different tier as the requested tier.
   - Do not disclose the balance, points, opening date, or other nonpublic fields until identity verification is complete.
   - If a card is present but the customer has not yet been verified, retain the account result only as internal context and continue to verification.

4. **Verify identity.**
   - Count only customer-confirmed matches among date of birth, email, phone number, and address. A corrected email may count if it matches the resolved user record.
   - If fewer than two fields are confirmed, politely ask for one additional field at a time from the remaining fields. Ask the customer to provide the value; do not reveal an unconfirmed value from the record in the question.
   - Compare each response with the resolved user record. If it does not match, do not count it; ask for a different verification field or clarify a likely formatting issue.
   - After two fields match, call `get_current_time`, then call `log_verification` once with the complete values from the resolved user record (`name`, `user_id`, `address`, `email`, `phone_number`, `date_of_birth`) and the returned timestamp. This creates the required audit record.
   - If verification cannot be completed, explain that identity verification is required before sharing the balance. Do not disclose account information.

5. **Provide the result after verification.**
   - Retrieve the card accounts again if needed to ensure the result is current.
   - For an exact card-type match, state the requested card type and its current balance clearly. Mention rewards points only if the customer asked for them.
   - If the verified account has no matching requested card type, clearly state that no such card was found on the verified account. If a different card type exists, it may be identified as a different card, but do not present it as the requested card. Offer to provide that different card's balance only if the customer wants it.
   - If several matching cards exist, distinguish them using only necessary non-sensitive account descriptors and ask which one the customer means before giving a balance, unless the request unambiguously identifies one.

6. **Close succinctly.**
   Confirm the requested outcome or the absence of the requested card. Do not expose full contact information, date of birth, or address in the final customer-facing response.

## Using prior observations

When the task includes read-only observations from earlier turns, treat successful lookup results, customer clarifications, and previously retrieved account lists as evidence. Avoid repeating an identical lookup merely to reproduce it. Still complete any missing identity-verification and audit-log steps before a balance disclosure. Re-query an account only when a fresh value is needed after verification or when prior results are incomplete.

## Failure handling

- If a tool reports no records, do not guess identifiers or retry with modified personal data that the customer did not provide.
- If lookup results contain multiple people or accounts that cannot be safely disambiguated, ask a focused clarifying question. Do not choose one based on partial similarity.
- If a required normal banking tool has a technical failure, tell the customer that the account information cannot currently be retrieved and offer appropriate follow-up; do not claim that no account exists.
- Use `transfer_to_human_agents` only when the request genuinely requires it or a supported transfer reason applies. Include a concise factual summary of lookup and verification steps already attempted.

## Example execution shape

For a request with an initially invalid email followed by a corrected email:

1. Look up the initial email and report that it did not locate an account.
2. Use the customer's exact-name clarification, if provided, to find a candidate record.
3. Ask the customer to confirm the candidate email; if they correct their email, look up that corrected email.
4. Retrieve that user's card accounts and determine whether the requested card tier exists.
5. Obtain enough customer-provided verification fields to make two confirmed matches, get the timestamp, and log verification.
6. Give the requested balance only for a matching card. If the requested tier is absent, say so and optionally offer the balance for a different verified card.
