---
name: business-checking-recommendation
version: 1.1.0
description: Conduct a turn-by-turn business checking recommendation conversation and recommend one evidence-supported account only after the customer has stated their hard requirements. Applies to product-fit requests, including a current promotional priority.
---

# Business Checking Recommendation

Use this Skill for a customer asking which business checking account is right for them. It recommends a product; it does not open an account, make a product change, or establish a customer's eligibility to open one.

## Turn-by-turn conversation protocol

Treat only information the customer has actually sent in the active conversation as a customer requirement. Never assume an answer to an anticipated clarification before the customer has supplied it.

1. From the customer's current message, record only explicit hard requirements. “Most perks,” “easy to use,” and similar general preferences are not independently verifiable requirements.
2. If a needed preference is still vague, ask **one concise, focused question** before recommending. For example, after a customer names no overdraft fee but says there are “other requirements,” ask which additional features are must-haves (such as ATM rebates, monthly fee/balance tolerance, international access, support, rewards, or transaction limits). Do not recommend an account in that turn.
3. After the customer answers, combine the answer with previously explicit requirements. If the answer supplies enough requirements to make a supported choice, perform the selection and give the recommendation in the next assistant turn. Ask another question only if a material requirement remains unresolved or the supported result is genuinely tied.
4. If the customer later adds or makes a requirement more specific, reassess all requirements before confirming that the recommendation still fits. Do not rely on an earlier conclusion alone.
5. Do not infer a requirement just because it was offered as an example in the question. A stated threshold, such as “at least $X per month,” is a hard requirement with its stated units and scope.

## Evidence extraction and prerequisites

For the then-current requirements, read the supplied account materials and create structured input for `scripts/select_account.py`:

- `requirements`: each hard requirement as `field`, `operator`, and normalized `value`.
- `offers`: one object for each account considered. Include a fact only if current materials expressly establish it, and include a nonempty source identifier for that fact in `evidence`.
- `promotion_active`: true only when an observed current date is inside the stated promotion period and the promotion applies to this recommendation.
- `promotion_rank`: the stated rank for an offer, if applicable. Lower is better.
- `tie_breakers`: only customer-relevant, evidence-supported preferences, if needed to resolve valid choices.

For common fee, rebate, balance, and APY requirements, use the normalized fields and scope checks in `references/feature_normalization.md` before running the helper. Missing documentation is unknown, not proof an account meets a requirement. Preserve feature scope: for example, do not interchange domestic ATM fees, foreign ATM fees, ATM-owner surcharges, and a monthly fee-rebate cap. Do not use a product fact to claim personal account-opening eligibility.

## Selection procedure

1. Run `scripts/select_account.py` with the structured data. Its stdin and stdout are each one JSON object.
2. Use promotion rank only after every hard requirement is verified. An offer with an unknown or failed must-have cannot be selected because of a promotion.
3. Interpret the result:
   - `selected`: recommend the named account.
   - `no_verified_match`: explain that the available materials do not establish an account satisfying every must-have. Identify missing facts as missing, not as negative facts, and ask whether the customer wants to relax a requirement or obtain more information.
   - `ambiguous`: ask one focused question that distinguishes the remaining offers; do not invent a best account.
   - `invalid_input`: correct the evidence extraction before responding substantively.

## Customer-facing recommendation

When `status` is `selected`, give a consolidated recommendation: name **one** account and plainly connect it to **every hard requirement currently stated**, including numerical thresholds and their units. Do this again whenever a customer adds a requirement; do not merely say that an earlier recommendation “still fits.” Disclose material, documented tradeoffs relevant to the request, such as a maintenance fee and waiver threshold, balance requirement, or per-withdrawal fee. State caps as caps. Say a rebate is automatic only where that is documented. Do not describe an account as fee-free when evidence only shows a $0 overdraft fee or a limited rebate.

Avoid exposing internal promotion language; it can determine the selection but is not a customer benefit. Do not initiate opening unless the customer subsequently asks to do so.

## Opening the recommended account after customer consent

If the customer clearly asks to open the recommended business checking account, switch from recommendation to the account-opening procedure. Do not assume that a product recommendation itself is authorization to open an account.

1. Verify identity by matching at least two of date of birth, email, phone number, and address against a customer record. Obtain a customer identifier from the matched record. If details do not match or more than one record matches, stop and resolve identity before continuing.
2. After two fields match, obtain the current time and create the required verification log using the verified record values and that timestamp.
3. Check the opening prerequisites using the declared account records or opening workflow: the customer is verified; has at least one OPEN personal checking account; has no CLOSED account; has no more than six business checking accounts; and has at least $500 in the existing checking account. If the available workflow reports a prerequisite failure, do not open the account; explain the applicable limitation without exposing unrelated account details.
4. Confirm the selected class. If the account-opening capability is discoverable, unlock `open_bank_account_4821` first, then call it with the verified customer ID, `account_type` of `business_checking`, and the exact account-class name. Use only the declared normal banking tool; do not claim an account was opened until the tool reports success. Never retry an operation whose outcome is unknown.
5. On success, tell the customer the account class, that it is open, and any returned account details appropriate for the customer. On failure, accurately explain that it could not be opened and the tool-reported reason if available.

## Helper interface and example

Input schema:

```json
{
  "requirements": [
    {"field": "overdraft_fee", "operator": "equals", "value": 0},
    {"field": "atm_rebate_cap", "operator": "at_least", "value": 15}
  ],
  "offers": [
    {
      "name": "Account name from current materials",
      "facts": {"overdraft_fee": 0, "atm_rebate_cap": 25},
      "evidence": {"overdraft_fee": "source title", "atm_rebate_cap": "source title"},
      "promotion_rank": 2
    }
  ],
  "promotion_active": true,
  "tie_breakers": []
}
```

Run `python3 scripts/select_account.py` and send this object on standard input. The helper writes a JSON object with `status` of `selected`, `no_verified_match`, `ambiguous`, or `invalid_input`. Before sending the customer-facing answer, confirm every claimed must-have appears in `matched_requirements`, each of those matches has evidence, and any stated product term is supported by the current materials.
