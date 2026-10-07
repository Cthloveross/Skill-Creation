---
name: unverified-credit-card-promotion
version: 1.0.0
description: Handle a prospective or existing customer who asks to redeem a mailed credit-card promotion when the specific offer cannot be verified. Use this Skill to preserve the stated offer without honoring, applying, or inventing unverified terms, and to give an accurate explanation and escalation recommendation when appropriate.
---

# Unverified credit-card promotion handling

## Purpose and limits
Use this Skill when a customer cites a flyer, mailer, or other promotion but will not provide the identifiers needed to validate it, such as an offer code and expiration date. It is especially applicable where the available product information establishes eligibility limits but does **not** establish the advertised promotion.

Do not create an application, promise a statement credit, redeem a code, change an account, or represent that a flyer is valid unless a declared banking tool and verified offer details support doing so. Do not infer product type, invitation status, expiration, eligibility, or promotion terms from the customer's paraphrase.

The packaged reference establishes that Diamond Elite Card membership is invitation-only, invitations are time-limited, and an invitation review may consider a maintained Rho-Bank balance of at least $250,000. These facts do not verify any particular flyer or bonus.

## Runtime inputs
Read the current conversation and any supplied observations. Capture only facts actually supplied at runtime:

- whether the customer is found in the bank system;
- whether the promotion's offer code is supplied;
- whether its expiration date is supplied;
- whether the customer is insisting that an unavailable/unverified offer be honored after the limitation has been explained;
- whether the customer explicitly requests a human agent.

Use `scripts/promotion_decision.py` for a consistent recommendation. It reads one JSON object from stdin and emits one JSON object to stdout.

Input schema:

```json
{
  "customer_record_found": false,
  "offer_code_provided": false,
  "expiration_date_provided": false,
  "customer_demands_honor_after_refusal": false,
  "customer_requests_human": false
}
```

All fields are booleans. Omitted fields default to `false`.

Example runnable invocation in a supported executor:

```text
run_skill_script(relative_path="scripts/promotion_decision.py", input_json={"customer_record_found":false,"offer_code_provided":false,"expiration_date_provided":false,"customer_demands_honor_after_refusal":false,"customer_requests_human":false})
```

## Procedure

1. **Acknowledge the request without confirming it.** State that you understand the customer is asking to redeem the described promotion. Do not repeat it as a confirmed entitlement.
2. **Separate a customer record from an application.** If no customer record is found and the caller says they do not have an account, do not continue account lookup or ask for account-verification details. A lack of an existing account does not itself validate or invalidate a mail offer.
3. **State the verification boundary.** Explain plainly that the offer code and expiration date are necessary to check whether that specific promotion is valid and applicable. If either is absent, say that the bank cannot verify or honor it from the spend/credit description alone.
4. **Give only supported product context, if relevant.** If the flyer is represented as Diamond Elite, explain that Diamond Elite membership is invitation-only and invitations are time-limited. Do not characterize an unverified flyer as an invitation. If the customer asks how invitation consideration works, accurately say that maintaining at least $250,000 with Rho-Bank and requesting a review may support consideration; it does not guarantee an invitation.
5. **Offer the narrow next step.** Invite the customer to provide only the offer code and expiration date for verification. Do not request every flyer detail merely to pressure disclosure.
6. **If details remain unavailable, refuse narrowly and courteously.** Explain that the promotion cannot be honored or redeemed until it can be verified. Do not promise a substitute promotion or manually override the offer.
7. **Escalate only when indicated.** If, after this unavailable-offer refusal, the customer continues to demand that it be honored, call `transfer_to_human_agents` with reason `customer_demands_after_unavailable_offer_refusal`. If they instead explicitly ask for a human without that demand, use `customer_requests_human_no_specific_reason`. Include a factual summary: promotion described, code/expiration unavailable, offer could not be verified or honored, and the customer's request. Do not transfer merely because the customer is disappointed or asks why verification is needed.

## Suggested response structure

Use natural wording tailored to the conversation:

> I understand you want to use the promotion shown on your flyer. I cannot confirm or honor a specific mailed offer from its spending and credit description alone. I need the offer code and expiration date to verify whether it is valid and applies. Without those details, I cannot redeem or promise the offer. If you are comfortable sharing just those two items, I can have the promotion checked.

If product context is needed, append only the applicable supported fact about invitation-only Diamond Elite membership and time-limited invitations. Do not say that a caller qualifies, was invited, or can receive a credit.

## Validation

Before responding or transferring, verify all of the following:

- No claim says the unverified promotion will be honored, redeemed, applied, or matched.
- No unprovided offer code, expiry, card product, customer identity, or eligibility fact appears in the response or tool arguments.
- The response clearly identifies the minimum missing validation details: offer code and expiration date.
- Any Diamond Elite statement is limited to invitation-only membership and time-limited invitations, unless the customer specifically requests the supported consideration context.
- A transfer reason exactly matches the customer's demonstrated condition.
- No customer-affecting banking tool has been called merely to handle an unverified promotion.

The decision script's `validation` array should be empty before treating its recommendation as structurally valid. Script output is a recommendation only; the executor must make any permitted normal-tool call explicitly.
