---
name: open-personal-checking-with-product-fit
version: 1.0.0
description: Handle a request to open an additional personal checking account: explain the relevant Blue and Green checking features accurately, obtain an explicit official account-class choice, verify identity and eligibility, and use the authorized banking workflow to open only an eligible, consented account.
---

# Open Personal Checking With Product Fit

Use this Skill for customers who ask to open a personal checking account, including when they are deciding between **Blue Account** and **Green Account (checking)**. Do not treat a product-information question as authorization to open an account.

## Product facts relevant to overdraft protection and early pay

Present the tradeoff precisely:

| Account class | Account overdraft fee | Automatic linked-account protection | Early direct deposit |
|---|---:|---|---|
| Blue Account | $0.00 | Available from an eligible linked account; each protection-triggered transfer costs $12.50 | Can arrive 1 day before payday, depending on when the payer submits the deposit |
| Green Account (checking) | $0.00 | Not available; transactions exceeding available funds are declined | Up to 1 day early, depending on payer submission |

Important distinctions:

- “No overdraft fees” does **not** mean Blue protection transfers are free. Blue has no account overdraft fee, but its optional protection service charges $12.50 per triggered transfer.
- Green has neither overdraft coverage nor protection transfers, so a linked savings account cannot automatically cover a shortfall. Explain that a declined transaction may still occur.
- Do not guarantee that a deposit will post on a particular weekday. Early availability depends on the payer’s submission timing.
- Blue’s monthly maintenance fee is $20 and is waived with a $625 minimum daily balance. Mention this only when it is relevant to the customer’s decision or they ask.

## Conversation and consent workflow

1. Identify the customer using the supplied full name or email with the appropriate customer lookup tool. Resolve ambiguous or missing lookup results before discussing account-specific actions.
2. Answer the customer’s current question directly. If the customer asks whether Blue provides early direct deposit, say that it can post **1 day early**, subject to payer timing.
3. If they have not made a final selection, summarize the Blue/Green tradeoff and ask a single explicit choice question. Require the complete official name exactly as one of:
   - `Blue Account`
   - `Green Account (checking)`
4. Do not open an account merely because the customer expressed a preference or asked a follow-up product question. Obtain an unambiguous affirmative instruction, for example: “Please open Blue Account.”
5. If the customer selects Blue for linked-account protection, explain that opening Blue does not itself enroll protection. After account opening, direct the customer to account settings → Overdraft Protection to choose an eligible funding account and accept the $12.50-per-transfer disclosure. Do not imply that a savings account has already been linked.

## Required identity verification

Before any account-opening action, independently verify the customer by having them confirm **two of four** profile fields: date of birth, email, phone number, and address.

1. Retrieve the profile by the resolved user ID if needed.
2. Ask the customer to provide or confirm any two fields; do not reveal profile values just to obtain confirmation.
3. Compare the customer-provided values to the profile. If fewer than two match, or the identity cannot be resolved, do not continue with opening.
4. Obtain the current time using `get_current_time` and call `log_verification` only after two fields match. Supply the complete profile record and the timestamp required by that tool.

A name lookup or knowledge of an account is not identity verification.

## Eligibility and account-opening workflow

After verification and explicit selection, perform all eligibility checks required for personal checking:

1. Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified user ID.
2. Confirm that the customer is at least 18 years old using their date of birth and the current date.
3. Count the customer’s personal checking accounts and confirm they do not exceed the limit of 4.
4. Confirm there is no personal checking account closed for cause in the prior 6 months. Inspect the returned account status/details for this condition; do not infer eligibility solely from the customer’s statement about an existing account.
5. If the account data cannot establish a required condition, do not open the account. Explain the unresolved prerequisite and use the institution’s supported escalation path if one is available.
6. Once every condition passes, unlock and call `open_bank_account_4821` using the verified customer and the exact selected `account_class` official name. Use only parameters required by the discovered tool schema.
7. Report the result returned by the opening tool. Do not claim success unless that tool confirms it.

## Handling failures and changes of mind

- If verification fails, eligibility fails, the selected name is not an official option, or account opening returns an error, make no substitute account-opening action.
- If the customer wants zero-cost automatic protection transfers, explain that neither option provides that: Blue charges $12.50 per triggered transfer and Green does not offer transfers.
- If the customer changes account class before opening, restate the final exact selection and use only that selection.
- Never fabricate account eligibility, a new account number, a linked funding account, direct-deposit timing, or a successful enrollment.

## Completion response

For a completed opening, state the exact account class opened and any account identifier/status returned by the tool. For an informational turn, answer the question and ask only for the next missing decision or verification item. Keep product disclosures separate from account-opening confirmation.