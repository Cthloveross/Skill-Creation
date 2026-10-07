---
name: business-account-selection-and-safe-opening
description: Recommend a single business checking account and/or business savings account from supplied product evidence based on stated requirements, then safely handle an explicitly requested account-opening workflow. Use for business account selection, comparison, or opening requests where account limits, fees, eligibility, and promotions must be evaluated.
---

# Business Account Selection and Safe Opening

## Scope and operating boundary

Use this Skill to identify the best-supported account recommendation from the current task's product documents and customer requirements. A recommendation is not an account-opening action. Do not access customer data, verify identity, open an account, or transfer funds merely because the customer asks which account fits.

Read the current task inputs and product evidence at runtime. `references/account_facts.md` is a compact index of facts available in this knowledge set; it is not evidence of any fact absent from the source documents. Do not infer unlisted limits, APYs, account fees, account classes, availability, or eligibility.

If the customer has not stated a required feature, do not treat a product difference as a requirement. In particular, do not describe an account as "better overall" unless every comparison being made is supported and relevant to the customer's stated needs.

## Recommendation workflow

1. **Separate the requested product types.** Create distinct requirement sets for checking and savings. Normalize each stated need into a testable constraint, such as:
   - `mobile_deposit_daily_limit >= requested amount`
   - `overdraft_fee == 0`
   - `same_day_ach == true`
   - an eligibility constraint such as a product's maximum company age covering the customer's stated company age.
2. **Build candidate records from evidence.** Include only facts explicitly documented for each candidate. Missing information is `unknown`, not a pass. Keep the document identifier with each material fact for traceability.
3. **Screen candidates.** Use `scripts/rank_product_options.py` when inputs can be represented as structured candidate attributes and constraints. A candidate qualifies only when every stated requirement passes; an unknown required fact disqualifies it pending clarification or evidence.
4. **Apply a documented promotion only after qualification.** Check the reliable current/as-of date against the promotion's inclusive effective dates. If multiple candidates meet all requirements while the promotion is active, use its stated ordering to break the tie. Never use a promotion to override a customer requirement. Do not disclose internal promotional prioritization unless the customer specifically asks.
5. **Handle incomplete comparison evidence honestly.** If no candidate is fully supported, state which requirement lacks a matching product fact or needs clarification. Do not substitute an account merely because it has a favorable promotion.
6. **Give a direct, concise result.** For each requested account type, name one recommendation, explain how it meets the stated requirements, and identify any eligibility or opening prerequisites that remain unverified. Mention only material caveats supported by evidence. Do not overwhelm a customer who asked not to compare many options.

For a replacement-account request, comparison to the current account must be narrow and factual: identify the particular requested capacity or fee policy that is met or improved. Do not imply that the replacement improves every feature.

## Ranking helper

`scripts/rank_product_options.py` reads one JSON object from stdin and emits one JSON object to stdout. It performs no banking actions and does not read customer data itself.

### Input schema

```json
{
  "candidates": [
    {
      "name": "string",
      "product_type": "checking or savings",
      "attributes": {"attribute_key": "number, boolean, or string"}
    }
  ],
  "requirements": [
    {"key": "attribute_key", "operator": "gte|lte|eq|true|false|exists", "value": "required except for true, false, exists"}
  ],
  "as_of_date": "YYYY-MM-DD (optional)",
  "promotion": {
    "active_from": "YYYY-MM-DD",
    "active_through": "YYYY-MM-DD",
    "priority_order": ["candidate names in priority order"]
  }
}
```

All requirements apply to every supplied candidate; call the helper separately for checking and savings when their requirements differ. Numeric comparisons accept JSON numbers or numeric strings. The helper preserves source order when no active promotion establishes a tie-breaker.

### Output schema and validation

On valid input the script emits:

```json
{
  "ok": true,
  "promotion_active": false,
  "qualifying": [{"name": "...", "product_type": "...", "attributes": {}}],
  "rejected": [{"name": "...", "failures": [{"key": "...", "status": "failed|unknown", "reason": "..."}]}]
}
```

Validate that `ok` is `true`, every recommended product appears in `qualifying`, and each stated customer constraint is represented in the requirement list. Check the final narrative against the underlying documents, because the helper only evaluates normalized attributes and cannot judge whether an attribute was extracted correctly.

A runnable empty-set interface check is:

```sh
printf '%s' '{"candidates":[],"requirements":[]}' | python scripts/rank_product_options.py
```

It should return `ok: true` and empty `qualifying` and `rejected` lists. Any `ok: false` response means correct the JSON schema or unsupported comparison before using its result.

## Current evidence index usage

Use the facts in `references/account_facts.md` to normalize known product evidence. Important limits of this index:

- A same-day ACH capability does not establish that an account can be opened by this customer.
- A checking product's mobile-deposit limit does not establish branch availability, cash-deposit capability, wire pricing, or a transaction allowance unless the relevant fact is documented.
- Do not equate a fee waiver threshold, an account minimum balance, and an opening deposit; they are distinct conditions.
- Only use the November 2025 promotion when the verified date is within its effective range.

## Account opening: only after a clear request and confirmation

If the customer explicitly asks to open a recommended account, first obtain their confirmation of the exact account type and official account-class name. A recommendation alone is not confirmation. Do not assume an informal product label is the exact tool-required `account_class` value.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

### Verification and authorization

1. Identify the customer using approved normal banking tools and ask them to confirm two of the four identity fields: date of birth, email, phone number, and address.
2. After two fields match, use the current timestamp and create the required verification audit record with `log_verification` when that tool is available.
3. Confirm that the verified customer is authorized to open the requested business account. Do not use another person's details or account as the source of eligibility or funding.
4. Confirm the requested account class, material fees and limits that apply, and that the customer wants the account opened now.

### Business checking opening prerequisites

Before opening a business checking account, confirm all documented conditions:

- the customer is verified;
- the customer has at least one existing personal checking account with status `OPEN`;
- the customer has no more than six business checking accounts;
- the customer has no account with status `CLOSED`; and
- the customer's existing checking account has a balance of at least $500.

If all conditions and the exact class are confirmed, use the normal banking workflow documented for `open_bank_account_4821` with `account_type` set to `savings` only for a savings account and to the appropriate checking value for a checking account. The supplied checking procedure documents the account-opening tool but does not explicitly specify the checking `account_type` literal; obtain that required literal from the enabled tool's documented interface rather than guessing.

### Business savings opening prerequisites and funding

Before opening a business savings account, confirm all documented conditions:

- the customer is verified;
- the customer has at least one business checking account with status `OPEN`;
- the customer has fewer than four business savings accounts;
- the customer has no account with a negative balance; and
- at least one `OPEN` business checking account has been open at least 30 days and has a current balance of at least $2,500.

Use the qualifying checking account for an optional opening-deposit transfer. Once the customer confirms the exact savings class and all eligibility conditions are satisfied, the documented opening call is `open_bank_account_4821(user_id, "savings", account_class)`.

After successful opening, ask whether the customer authorizes an opening deposit now. Before any transfer, reconfirm the source and destination account ownership, available balance, transfer amount, fees, limits, cutoffs, and the customer's confirmation. If authorized, use the documented internal transfer workflow `transfer_funds_between_bank_accounts_7291(source_account_id, destination_account_id, amount)`. If the customer declines or a transfer fails, explain that the documented savings procedure allows 30 days to fund via internal transfer or external deposit, after which the account will be closed.

### Tool availability and failures

The opening and transfer tools are agent tools, not customer-facing instructions. Use them only when they are available through the runtime's normal discoverable-agent-tool process and only after all prerequisites above are verified. Capture the returned account ID before an authorized funding transfer.

If identity, authority, account status, tenure, balance, account counts, product eligibility, exact account class, confirmation, or a required normal banking tool cannot be verified, do not open an account or transfer funds. State what is needed next without claiming eligibility. If a tool reports failure, report the failure accurately and do not retry or invent a successful result.

## Final-response checklist

Before responding, verify that:

- each recommendation meets every explicitly stated requirement using documented facts;
- date-sensitive promotion ordering was used only when active and only among qualifiers;
- unsupported comparisons and invented product terms were omitted;
- unverified opening eligibility is clearly distinguished from product fit; and
- no banking action was performed without verification, authority, prerequisite checks, and explicit confirmation.
