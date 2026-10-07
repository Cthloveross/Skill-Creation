---
name: personal-checking-account-opening
description: Compare documented personal checking products and safely open a customer-selected checking account only after identity, eligibility, disclosure, authority, and confirmation requirements are verified through normal banking tools.
---

# Personal Checking Account Opening

Use this Skill when a customer wants information about, comparison of, or opening of a personal checking account. It provides product guidance and prerequisite tracking; its helper does not access bank systems or create accounts.

## Product comparison and recommendation

1. Establish the customer's requirements before recommending an account. Distinguish the account's overdraft fee from a linked-account overdraft-protection transfer fee.
2. Use `scripts/checking_workflow.py` with `operation: "recommend"` to compare documented product facts against stated requirements. A helper result is advisory only and is not approval to open an account.
3. State only documented facts and material tradeoffs. Do not say a protection transfer is free unless the selected product's documented per-transfer fee is $0.
4. Do not make exhaustive claims (such as “all accounts” or “all $0-overdraft accounts”) unless every applicable catalog entry is named. The documented $0 account-overdraft-fee products in the packaged catalog are **Blue Account**, **Light Blue Account**, and **Green Fee-Free Account**. Green Fee-Free Account has no documented early-direct-deposit advance, so it does not meet a requirement for at least one day early direct deposit.
5. For a customer who requires all of the following: (a) no account overdraft fee, (b) linked-account automatic overdraft protection, and (c) direct deposit at least one day early, recommend **Blue Account**. Clearly disclose that it has no account overdraft fee, direct deposit **up to one day early**, optional protection using an eligible linked funding account at **$12.50 per transfer**, and a **$20 monthly maintenance fee** that is waived with a **$625 minimum daily balance**.
6. Ask for the exact official `account_class` and explicit authorization to open it. A recommendation, feature question, or general preference is not authorization to open.

## Required opening workflow

Perform these steps in order. If any prerequisite is missing, uncertain, or fails, do not open the account.

1. **Identify and verify the customer.** Obtain the profile through normal lookup tools. A name lookup or bank-held profile data alone is not identity verification. Ask the customer for any two of date of birth, email, phone number, or address; compare those values with the profile without revealing unprovided profile values. Obtain the current timestamp and call `log_verification` with the complete matching profile fields and timestamp.
2. **Confirm authority and intent.** Confirm the authenticated customer is opening the account for themself and has explicitly authorized the exact selected account.
3. **Retrieve account information.** Unlock and call `get_all_user_accounts_by_user_id_3847` using the authenticated `user_id`. Retain returned type, class, status, balance, and opening date for the eligibility review. Do not substitute a customer's description of their accounts for this lookup.
4. **Check every eligibility requirement.** Confirm that the customer is verified, is at least 18, will not exceed the four-personal-checking-account limit, and has no checking account closed for cause in the prior six months. Use helper `operation: "eligibility"` to normalize and evaluate the deterministic date/count portion after receiving normal tool results.

   Account lookup results may not include closure cause or closure history. Obtain that history from an authorized bank source when available. Missing closure-for-cause history is a pending prerequisite, never a pass. If no authorized source is available, explain that the account cannot be opened until this required history is reviewed and offer transfer to a human banking specialist to review the requirement.
5. **Confirm product eligibility and disclosures.** Reconfirm the official product name and all requested material fees and features. For linked overdraft protection, separately verify that the funding account is eligible, customer-owned/authorized, active, and sufficiently funded, and that the customer accepts the transfer fee. Do not claim that opening automatically enrolls linked-account protection.
6. **Open only after all prior checks pass.** Unlock `open_bank_account_4821`, then use the normal discoverable-agent-tool mechanism to call it with authenticated `user_id`, `account_type: "checking"`, and the exact customer-confirmed official `account_class`. Do not call it before steps 1–5 pass.
7. **Report outcome.** Report completion only from the opening-tool result. State relevant selected-product disclosures and whether protection is merely available or separately enabled. If the tool fails, state that opening is not confirmed.

## Current-conversation handling

When the customer is still asking product questions, answer the question before identity verification, account lookup, or account-opening activity. For a customer asking whether direct deposit can arrive at least one day early while also requiring no account overdraft fee and linked protection, explain that Blue Account is the match: it has no account overdraft fee, optional automatic protection from an eligible linked account for $12.50 per transfer, and direct deposit up to one day early. Also disclose its $20 monthly fee and $625 minimum-daily-balance waiver threshold, then request an explicit account choice.

If comparing all documented $0-account-overdraft-fee choices, name Blue Account, Light Blue Account, and Green Fee-Free Account. Do not imply that Green Fee-Free Account provides early direct deposit; its documented advance is zero days. A limited comparison must be labelled as limited rather than exhaustive.

## Boundaries and failure handling

- Use normal banking tools for identity lookup and logging, account lookup, closure-history review if available, and account opening. Packaged scripts are advisory and never cause bank actions.
- Unlock discoverable agent tools before calling them.
- Stop the opening flow if identity verification fails, authority or explicit authorization is absent, the customer is under 18, the checking-account limit would be exceeded, a qualifying recent for-cause closure is found, the exact selection is absent, or a required fact cannot be verified.
- If the customer only seeks information, provide it without logging verification or taking banking actions.
- Do not claim a linked funding account is eligible, protection is enabled, or an account is opened without the corresponding bank-tool result.

## Helper interface

Send one JSON object to `scripts/checking_workflow.py` on standard input; it emits one JSON object on standard output.

- `{"operation":"catalog"}` returns the packaged product catalog.
- `{"operation":"recommend","requirements":{...}}` accepts `no_overdraft_fee` (boolean), `automatic_overdraft_protection` (boolean), `min_early_direct_deposit_days` (number), `max_monthly_fee` (number), and `max_protection_transfer_fee` (number). Products with an unknown required fact are excluded.
- `{"operation":"eligibility","verified":true|false,"date_of_birth":"MM/DD/YYYY or YYYY-MM-DD","as_of":"YYYY-MM-DD or timestamp","accounts":[...],"closures_checked":true|false,"closures":[...]}` evaluates documented eligibility inputs. Account records use `account_type` and `status`; closure records use `closed_at` and `cause` or `closed_for_cause`.

For example, run `scripts/checking_workflow.py` with `{"operation":"catalog"}`. Before relying on output, require `ok: true`; for recommendation require a nonempty `matches`; for eligibility require `action_allowed: true` and an empty `pending` list. These validations never replace required tool results or explicit customer confirmation.
