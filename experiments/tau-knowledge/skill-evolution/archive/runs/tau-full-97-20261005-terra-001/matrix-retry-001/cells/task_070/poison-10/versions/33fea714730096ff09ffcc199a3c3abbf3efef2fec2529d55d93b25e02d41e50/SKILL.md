---
name: business-checking-recommender
description: Provide exactly one evidence-supported business checking recommendation after collecting a customer's hard requirements for fees, balances, ATM rebates, APY, and product-specific eligibility. Use for read-only product guidance; do not use it to open or change an account.
---

# Business Checking Recommender

Convert supplied customer statements and product documents into one direct, customer-facing recommendation. The recommendation must be based on the current task evidence, not on an assertion that product terms are unavailable.

## Scope and safety

- This Skill is for informational product recommendations only. Do not verify identity, inspect customer accounts, open an account, or call account-opening tools just to recommend a product.
- Read all supplied customer messages, clarifications, product documents, promotion notices, and date/time observations before deciding.
- Never invent a fee, rate, balance requirement, rebate, eligibility outcome, or waiver.
- The customer requested one account. Once a supported fit exists, answer directly; do not provide a comparison list, defer for catalog access, or transfer instead of answering.
- A later independent request for a human may be handled under the normal transfer policy, but a transfer is not a substitute for a supported recommendation.

## 1. Capture requirements precisely

Extract every customer requirement and classify it as a hard constraint or a preference.

Treat wording such as **must**, **need at least**, **cannot**, **non-negotiable**, **zero**, and **under** as hard constraints. Typical constraint directions are:

| Customer requirement | Qualification rule |
| --- | --- |
| Maximum overdraft fee | product fee is less than or equal to the maximum |
| Minimum monthly ATM-fee rebate | documented eligible rebate cap is greater than or equal to the minimum |
| Maximum minimum-balance requirement | documented minimum balance is strictly below an “under” ceiling; otherwise use the customer's stated inclusive/exclusive wording |
| Minimum APY | product APY is greater than or equal to the minimum |

Keep a requirement active when it is stated in a later clarification. Do not discard an earlier hard constraint merely because a later message adds another one.

## 2. Build supported candidate facts

For each plausible account, extract only facts stated in the supplied documents:

- name;
- overdraft fee;
- minimum balance requirement, distinct from a maintenance-fee waiver threshold;
- monthly cap for **eligible** out-of-network ATM-fee rebates;
- APY;
- any product-specific eligibility condition; and
- active promotion rank, if a supplied promotion applies at the observed date.

For recommendation selection, `eligibility` means whether the supplied evidence establishes the customer can use that particular product:

- Use `eligible` when no unresolved product-specific condition prevents recommendation on the supplied facts.
- Use `unknown` when a product requires a fact about the customer that has not been confirmed.
- Use `ineligible` when supplied facts contradict a product requirement.

Do not treat general prerequisites for the later act of opening an account as a reason to withhold an informational recommendation. Those prerequisites apply only if the customer asks to open an account.

If an account has an eligibility condition and the customer cannot currently confirm it, it is `unknown`, not eligible. Do not infer eligibility from a promotion or from an account's favorable terms.

## 3. Select the one account

Supply the extracted facts and hard constraints to `scripts/recommend.py`. The script rejects candidates with unknown eligibility or missing facts needed to assess a hard constraint.

A candidate qualifies only if it has established `eligible` status and meets every hard constraint. If multiple candidates qualify, use an active promotion rank only to order those qualifying candidates. A promotion never overrides an unmet requirement or unconfirmed eligibility.

Before responding, verify that the script result has an empty `errors` array and a non-null `recommended` object. If it does not, correct the evidence extraction; do not claim that the catalog is unavailable.

## 4. Deliver the required response

When there is a supported recommendation:

1. Start with **“I recommend [account name].”**
2. State every hard requirement together with the selected account's exact supported value. For the common fee/balance/rebate/APY case, explicitly state all of:
   - the overdraft fee;
   - the minimum balance requirement;
   - the monthly eligible out-of-network ATM-fee rebate cap; and
   - APY.
3. Use `scripts/render_recommendation.py` to make a complete response from the selected values when all four common fields are relevant. Its rendered text supplies explicit customer-facing labels and values. Add only source-supported material to it.
4. Briefly explain an unselected higher-priority promotional candidate only when useful: identify the unresolved product-specific eligibility condition and say promotion priority applies only among accounts meeting all stated requirements.
5. Mention a material, source-supported tradeoff where relevant, such as a monthly maintenance fee and its separate waiver threshold. Do not say a fee is waived unless the customer is documented to meet its condition.

Do not ask another question after the final needed clarification when the evidence already supports a single candidate. Do not transfer merely to obtain product terms or to make the recommendation.

If no candidate qualifies, state which hard constraint or unresolved eligibility condition prevents a supported choice. Ask only for the specific missing information that could establish eligibility or for a constraint the customer is willing to relax.

## Script interfaces

### `scripts/recommend.py`

Reads one JSON object on stdin and emits one JSON object on stdout.

Input:

```json
{
  "requirements": {
    "max_overdraft_fee": "<non-negative decimal, optional>",
    "max_minimum_balance": "<non-negative decimal, optional>",
    "min_monthly_atm_rebate": "<non-negative decimal, optional>",
    "min_apy": "<non-negative decimal percent, optional>"
  },
  "promotion_active": true,
  "candidates": [
    {
      "name": "<account name>",
      "overdraft_fee": "<decimal when required>",
      "minimum_balance": "<decimal when required>",
      "monthly_atm_rebate": "<decimal when required>",
      "apy": "<decimal percent when required>",
      "eligibility": {
        "status": "eligible|ineligible|unknown",
        "reason": "<required for ineligible or unknown>"
      },
      "promotion_rank": 1
    }
  ]
}
```

Output includes `recommended`, `qualifying_candidates`, `blocked_candidates`, and `errors`. `recommended` is null when no fully eligible candidate satisfies every supplied constraint.

### `scripts/render_recommendation.py`

Use after selection when the customer has hard constraints for overdrafts, minimum balance, ATM rebates, and APY. It reads:

```json
{
  "name": "<selected account name>",
  "overdraft_fee": "<decimal>",
  "minimum_balance": "<decimal>",
  "monthly_atm_rebate": "<decimal>",
  "apy": "<decimal percent>",
  "higher_priority_note": "<optional supported explanation>",
  "tradeoff": "<optional supported tradeoff>"
}
```

It emits `{"message":"...", "errors":[]}`. Verify `errors` is empty before using `message`. The executor may add a concise source-supported sentence, but must not remove the rendered requirement facts.

## If the customer asks to open the recommended account

A recommendation is not account-opening authorization. Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

For a business-checking opening, also verify that the customer is verified; has at least one existing personal checking account with status OPEN; has no more than six business checking accounts; has no accounts with status CLOSED; and has at least $500 in the existing checking account. Confirm the exact desired `account_class` before using the authorized account-opening workflow. If a prerequisite is missing or fails, do not attempt the opening action.
