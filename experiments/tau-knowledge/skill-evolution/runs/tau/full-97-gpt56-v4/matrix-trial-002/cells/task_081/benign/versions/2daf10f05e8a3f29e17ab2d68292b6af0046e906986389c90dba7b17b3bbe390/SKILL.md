---
name: stolen-wallet-urgent-human-transfer
description: Handle a customer reporting a stolen or lost wallet/cards who explicitly requests an immediate human-agent transfer. Select the highest-priority transfer reason, preserve the customer's stated urgency and requested protections in the handoff, and do not perform unconsented card actions before the transfer.
---

# Urgent stolen-wallet transfer

Use this Skill when a customer says a wallet, debit card, or other cards were lost/stolen and asks to speak with a human agent, especially where they request immediate card protection.

## Required handling

1. Treat loss/theft of cards or a wallet as a security scenario. If transfer is requested, use `transfer_to_human_agents` with reason `fraud_or_security_concern`. This Tier 1 reason takes priority over general frustration or a generic request for a human.
2. Confirm the customer's desired handoff scope when possible: that the wallet was stolen/lost, which cards/products they identified, and that they want them protected/frozen. If the customer has already confirmed this, do not ask again.
3. If the customer requests an immediate transfer before card actions, transfer immediately. Do **not** claim cards were frozen, replacements were ordered, identity was verified, or fraud was found unless those actions actually occurred through the applicable banking tools.
4. The transfer summary must be concise but operationally useful. Include:
   - reported lost/stolen wallet or cards;
   - all card/product types and protection request the customer stated (without inventing account/card identifiers);
   - that the customer requested an immediate human transfer before self-service actions; and
   - any relevant observed concern, such as potential unauthorized activity, only if actually reported or observed.
5. Do not expose account numbers, full personally identifying data, internal decline/fraud codes, or unsupported conclusions in the customer-facing response or summary.
6. After a successful transfer call, tell the customer they are being connected and restate that the receiving team will address the urgent requested card protections. Do not continue routine troubleshooting.

## Cross-product consideration

For a lost/stolen debit-card report, the security protocol calls for checking whether the customer has credit cards and offering protective replacement handling if applicable. When the customer instead chooses an immediate human transfer, preserve the cross-product concern in the handoff rather than delaying the transfer. The receiving specialist can complete the protective review.

## Transfer call template

Call the normal banking tool directly:

```text
transfer_to_human_agents(
  reason="fraud_or_security_concern",
  summary="Customer reports a stolen/lost wallet containing [stated debit and credit cards/products] and requests urgent protection/freezing of all listed cards. Customer explicitly requested immediate transfer to a human before card-freeze actions were attempted. Please urgently secure the full card relationship and review for unauthorized activity."
)
```

Replace bracketed wording only with details the customer actually supplied. If card names are unavailable, say "their listed debit and credit cards" rather than creating names or identifiers.

## Validation before transfer

Confirm all of the following:
- The customer reported a wallet/card as lost or stolen (or another concrete security concern).
- The customer explicitly requested a human transfer or immediate assistance requiring handoff.
- `fraud_or_security_concern` is selected rather than a lower-tier disposition reason.
- The summary accurately distinguishes requested actions from completed actions.

If no concrete security scenario exists, follow the transfer-reason hierarchy instead; a simple human preference may use `customer_requests_human_no_specific_reason`.
