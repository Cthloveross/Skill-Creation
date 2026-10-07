"""Analyzer-controlled public acquisition with a host-enforced capability allowlist."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from tau_skill_evolution.core._canonical import canonical_json_bytes, thaw_json

from .artifacts import FrozenBase, normalize_document
from .bank import BankWorkerError
from .constants import EXPERIMENT_ROOT
from .generator import invoke_model, journaled_model_request, model_messages, parse_model_json
from .journal import Journal, UnknownOperation
from .model import (
    ModelClientError,
    SerializedChatTokenCounter,
    authentication_status,
    is_credential_error,
)

READ_ONLY_TOOL_NAMES = frozenset(
    {
        "get_current_time",
        "get_user_information_by_id",
        "get_user_information_by_name",
        "get_user_information_by_email",
        "get_referrals_by_user",
        "get_credit_card_transactions_by_user",
        "get_credit_card_accounts_by_user",
    }
)
_COVERAGE = ("policies", "tools", "parameters", "preconditions")


@dataclass(frozen=True)
class AcquisitionBudgets:
    searches: int = 30
    clarifications: int = 4
    read_only_queries: int = 10
    base_tokens: int = 32768
    analyzer_steps: int = 50

    def __post_init__(self) -> None:
        for name in (
            "searches",
            "clarifications",
            "read_only_queries",
            "base_tokens",
            "analyzer_steps",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        if self.base_tokens == 0 or self.analyzer_steps == 0:
            raise ValueError("base_tokens and analyzer_steps must be positive")


DEFAULT_BUDGETS = AcquisitionBudgets()


ANALYZER_SYSTEM = (EXPERIMENT_ROOT / "prompts" / "analyzer.md").read_text(encoding="utf-8")


def _search(corpus: Any, query: str) -> Any:
    if hasattr(corpus, "search_web"):
        return corpus.search_web(query)
    if hasattr(corpus, "search"):
        return corpus.search(query)
    if callable(corpus):
        return corpus(query)
    raise TypeError("corpus must expose search_web, search, or be callable")


def _token_count(counter: Callable[[str], int], documents: Sequence[Mapping[str, Any]]) -> int:
    text = canonical_json_bytes(list(documents)).decode("utf-8")
    count = counter(text)
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("token_counter must return a nonnegative integer")
    return count


def _decision(raw: Any) -> dict[str, Any]:
    value = parse_model_json(raw)
    fields = {
        "gaps",
        "action",
        "evidence",
        "document_scores",
        "sufficient",
        "coverage",
        "conflicts",
    }
    if set(value) != fields:
        raise ValueError("Analyzer response fields differ from its schema")
    if not isinstance(value["action"], Mapping) or not isinstance(value["sufficient"], bool):
        raise ValueError("Analyzer action or sufficiency has an invalid type")
    for field in ("gaps", "conflicts", "evidence", "document_scores"):
        if not isinstance(value[field], list):
            raise ValueError(f"Analyzer {field} must be a list")
    if any(not isinstance(item, str) for item in value["gaps"] + value["conflicts"]):
        raise ValueError("knowledge gaps and conflicts must be text")
    if not isinstance(value["coverage"], Mapping):
        raise ValueError("coverage must be an object")
    return value


def _selection(
    decision: Mapping[str, Any],
    inventory: Mapping[str, Mapping[str, Any]],
    token_counter: Callable[[str], int],
    max_tokens: int,
    min_document_confidence: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    scores: dict[str, float] = {}
    for item in decision["document_scores"]:
        if not isinstance(item, Mapping) or set(item) != {"document_id", "confidence", "reason"}:
            raise ValueError("document scores require document_id, confidence and reason")
        identifier, confidence = item["document_id"], item["confidence"]
        if not isinstance(identifier, str) or identifier not in inventory or identifier in scores:
            raise ValueError("score IDs must be unique documents returned in full")
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not 0 <= confidence <= 1
        ):
            raise ValueError("confidence must be a finite number between zero and one")
        if not isinstance(item["reason"], str) or not item["reason"].strip():
            raise ValueError("each document score requires a nonempty reason")
        scores[identifier] = confidence
    if set(scores) != set(inventory):
        raise ValueError("score every document returned in full")
    citations: list[dict[str, Any]] = []
    for item in decision["evidence"]:
        if (
            not isinstance(item, Mapping)
            or not isinstance(item.get("requirement"), str)
            or not item["requirement"].strip()
            or item.get("document_id") not in scores
            or scores[item["document_id"]] < min_document_confidence
        ):
            raise ValueError("evidence must cite selected full-text documents")
        if "quote" in item and (
            not isinstance(item["quote"], str)
            or not item["quote"]
            or item["quote"] not in inventory[item["document_id"]]["content"]
        ):
            raise ValueError("evidence quote is absent from the cited document")
        citations.append(
            {key: item[key] for key in ("requirement", "document_id", "quote") if key in item}
        )
    required = {item["document_id"] for item in citations}
    ids = sorted(
        (identifier for identifier, score in scores.items() if score >= min_document_confidence),
        key=lambda identifier: (identifier not in required, -scores[identifier], identifier),
    )
    documents = [dict(inventory[identifier]) for identifier in ids]
    count = _token_count(token_counter, documents)
    if count > max_tokens:
        candidates, documents = documents, []
        count = _token_count(token_counter, documents)
        for candidate in candidates:
            trial_count = _token_count(token_counter, [*documents, candidate])
            if trial_count <= max_tokens:
                documents.append(candidate)
                count = trial_count
        ids = [item["document_id"] for item in documents]
    evidence = [item for item in citations if item["document_id"] in ids]
    return documents, evidence, count


def _invalid_coverage(
    decision: Mapping[str, Any], ids: set[str], evidence: Sequence[Mapping[str, Any]]
) -> list[str]:
    coverage = decision["coverage"]
    cited = {item["document_id"] for item in evidence}
    invalid = [f"coverage.{category}" for category in coverage if category not in _COVERAGE]
    for category in _COVERAGE:
        value = coverage.get(category)
        if isinstance(value, Mapping):
            valid = (
                set(value) == {"not_applicable"}
                and isinstance(value["not_applicable"], str)
                and bool(value["not_applicable"].strip())
            )
        else:
            valid = (
                isinstance(value, list)
                and bool(value)
                and all(isinstance(item, str) and item in ids and item in cited for item in value)
            )
        if not valid:
            invalid.append(f"coverage.{category}")
    return invalid


def _sufficient(
    decision: Mapping[str, Any], ids: set[str], evidence: Sequence[Mapping[str, Any]]
) -> bool:
    return bool(
        decision["sufficient"]
        and not decision["gaps"]
        and not decision["conflicts"]
        and ids
        and not _invalid_coverage(decision, ids, evidence)
    )


def collect_base(
    model: Any,
    public_inputs: Mapping[str, Any],
    corpus: Any,
    read_only_tools: Mapping[str, Callable[..., Any]],
    clarify: Callable[[str], Any],
    token_counter: Callable[[str], int],
    *,
    budgets: AcquisitionBudgets = DEFAULT_BUDGETS,
    tool_schemas: Sequence[Mapping[str, Any]] = (),
    journal: Journal | None = None,
    operation_prefix: str = "acquisition",
    seed: int | None = None,
    system_prompt: str = ANALYZER_SYSTEM,
    input_token_limit: int = 114688,
    min_document_confidence: float = 0.1,
    allowed_read_only_tool_names: Sequence[str] = tuple(sorted(READ_ONLY_TOOL_NAMES)),
    action_dispatcher: Callable[[str, Mapping[str, Any]], Any] | None = None,
) -> FrozenBase:
    """Freeze the last legal score-filtered base, then revoke the large corpus.

    Tool functions receive keyword arguments. ``clarify`` must return public text
    (the bank adapter enforces that the simulator cannot perform tool actions).
    Search full-text responses may use results/documents or be a document list.
    """
    if not isinstance(public_inputs, Mapping) or not isinstance(read_only_tools, Mapping):
        raise TypeError("public inputs and tool capabilities must be mappings")
    if (
        isinstance(input_token_limit, bool)
        or not isinstance(input_token_limit, int)
        or input_token_limit <= 0
    ):
        raise ValueError("input_token_limit must be a positive integer")
    allowed_names = frozenset(allowed_read_only_tool_names)
    if any(not isinstance(name, str) or not name for name in allowed_names):
        raise ValueError("read-only capability names must be nonempty strings")
    if set(read_only_tools) - allowed_names:
        raise ValueError("acquisition exposes a forbidden capability")
    if (
        isinstance(min_document_confidence, bool)
        or not isinstance(min_document_confidence, (int, float))
        or not 0 <= min_document_confidence <= 1
    ):
        raise ValueError("min_document_confidence must be between zero and one")
    # Capability checks govern dispatch; filtering schemas also keeps privileged
    # tool descriptions out of the Analyzer's context.
    public_schemas = []
    for schema in tool_schemas:
        if not isinstance(schema, Mapping):
            raise TypeError("tool schemas must be objects")
        function = schema.get("function", schema)
        if isinstance(function, Mapping) and function.get("name") in read_only_tools:
            public_schemas.append(thaw_json(schema))
    public = json.loads(canonical_json_bytes(thaw_json(public_inputs)))
    if "clarifications" in public or "read_only_observations" in public:
        # Resuming acquisition replays journaled observations; accepting a previous
        # partial collection would duplicate them and alter the frozen hash.
        raise ValueError("opening public inputs must not contain acquisition observations")
    public["clarifications"] = []
    public["read_only_observations"] = []
    inventory: dict[str, dict[str, Any]] = {}
    scores: dict[str, Mapping[str, Any]] = {}
    pending: list[str] = []
    unreviewable: list[str] = []
    observations: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    count = 0
    counters = {"search": 0, "clarify": 0, "read_only": 0}
    limits = {
        "search": budgets.searches,
        "clarify": budgets.clarifications,
        "read_only": budgets.read_only_queries,
    }
    stop_reason = "budget_exhausted_incomplete"
    stop_detail = "analyzer_steps_exhausted"
    last_decision: Mapping[str, Any] = {}
    input_counter = SerializedChatTokenCounter(token_counter)

    def dispatch(identifier: str, payload: Any, callback: Callable[[], Any]) -> Any:
        if journal is None:
            return callback()
        # Recoverable bank actions journal their actual POSTs inside the private worker.
        local = action_dispatcher is not None and payload.get("kind") in {"clarify", "read_only"}
        return journal.dispatch(identifier, payload, callback, external=not local)

    def has_budget() -> bool:
        return (
            counters["search"] < limits["search"]
            or callable(clarify)
            and counters["clarify"] < limits["clarify"]
            or bool(read_only_tools)
            and counters["read_only"] < limits["read_only"]
        )

    def perform(kind: str, action: Mapping[str, Any], identifier: str) -> dict[str, Any]:
        try:
            if kind == "search":
                result = _search(corpus, action["query"])
            elif action_dispatcher is not None:
                result = action_dispatcher(identifier, action)
            elif kind == "clarify":
                result = clarify(action["question"])
            else:
                result = read_only_tools[action["tool"]](**dict(action["arguments"]))
            if kind == "clarify" and not isinstance(result, str):
                raise ValueError("clarification must return public text without tool events")
            canonical_json_bytes(result)
            return {"status": "ok", "result": result}
        except Exception as exc:
            if (
                isinstance(exc, UnknownOperation)
                or isinstance(exc, ModelClientError)
                and exc.code in {"acquisition_received_invalid", "acquisition_recovery_failed"}
                or action_dispatcher is not None
                and isinstance(exc, BankWorkerError)
                and not exc.response_received
                or authentication_status(exc) is not None
                or is_credential_error(exc)
            ):
                raise
            return {"status": "error", "error": str(exc)}

    try:
        count = _token_count(token_counter, selected)
        # The public bank clock is an actual read, not a free hidden observation.
        # Adapters without that capability (including SkillsBench) do not call it.
        if "get_current_time" in read_only_tools and limits["read_only"] > 0:
            action = {"kind": "read_only", "tool": "get_current_time", "arguments": {}}
            counters["read_only"] = 1
            result = dispatch(
                f"{operation_prefix}/read_only/0",
                action,
                lambda: perform("read_only", action, f"{operation_prefix}/read_only/0"),
            )
            observations.append({"kind": "read_only", "action": action, **result})
            public["read_only_observations"].append(
                {"tool": "get_current_time", "arguments": {}, **result}
            )
        for step in range(budgets.analyzer_steps):
            payload = {
                "role": "analyzer",
                "public_inputs": public,
                "returned_documents": list(selected),
                "reviewed_documents": [
                    {
                        "document_id": identifier,
                        "title": inventory[identifier]["title"],
                        "confidence": score["confidence"],
                    }
                    for identifier, score in scores.items()
                ],
                "observations": observations[-10:],
                "previous_gaps": last_decision.get("gaps", []),
                "previous_coverage": last_decision.get("coverage", {}),
                "previous_conflicts": last_decision.get("conflicts", []),
                "unreviewable_document_ids": list(unreviewable),
                "selected_document_ids": [item["document_id"] for item in selected],
                "allowed_read_only_tools": sorted(read_only_tools),
                "tool_schemas": public_schemas,
                "remaining": {key: limits[key] - value for key, value in counters.items()},
                "base_token_limit": budgets.base_tokens,
                "min_document_confidence": min_document_confidence,
                "pending_review_count": len(pending),
                "final_review": step == budgets.analyzer_steps - 1,
            }
            if input_counter.count(model_messages(payload, system_prompt)) > input_token_limit:
                stop_detail = "public_inputs_or_selected_base_exceed_context"
                break
            reviewed_ids = {item["document_id"] for item in selected}
            batch: list[str] = []
            for identifier in list(pending):
                if identifier in reviewed_ids:
                    batch.append(identifier)
                    continue
                trial = {
                    **payload,
                    "returned_documents": [*payload["returned_documents"], inventory[identifier]],
                    "pending_review_count": len(pending) - len(batch) - 1,
                }
                if input_counter.count(model_messages(trial, system_prompt)) <= input_token_limit:
                    payload = trial
                    reviewed_ids.add(identifier)
                    batch.append(identifier)
                elif not batch:
                    # An oversized hit must not prevent a later short hit being read.
                    unreviewable.append(identifier)
                    pending.remove(identifier)
                    payload["unreviewable_document_ids"] = list(unreviewable)
                    payload["pending_review_count"] = len(pending) - len(batch)
            payload["pending_review_count"] = len(pending) - len(batch)
            payload["unreviewable_document_ids"] = list(unreviewable)
            if input_counter.count(model_messages(payload, system_prompt)) > input_token_limit:
                stop_detail = "public_inputs_or_selected_base_exceed_context"
                break
            request_payload = {"inputs": payload, "system_prompt": system_prompt, "seed": seed}
            raw = (
                journaled_model_request(
                    model,
                    journal,
                    f"{operation_prefix}/analyzer/{step}",
                    request_payload,
                    model_messages(payload, system_prompt),
                    seed=seed,
                )
                if journal is not None
                else invoke_model(model, payload, system_prompt, seed=seed)
            )
            try:
                decision = _decision(raw)
                incoming = {
                    item.get("document_id")
                    for item in decision["document_scores"]
                    if isinstance(item, Mapping)
                }
                if not set(batch).issubset(incoming):
                    raise ValueError("score every newly presented full-text document")
                if any(
                    identifier not in reviewed_ids and identifier not in scores
                    for identifier in incoming
                ):
                    raise ValueError("cannot score a document not yet reviewed")
                updates = {item["document_id"]: item for item in decision["document_scores"]}
                if len(updates) != len(decision["document_scores"]):
                    raise ValueError("score IDs must be unique")
                combined = {**scores, **updates}
                scored_inventory = {identifier: inventory[identifier] for identifier in combined}
                scored_decision = {**decision, "document_scores": list(combined.values())}
                proposed, proposed_evidence, proposed_count = _selection(
                    scored_decision,
                    scored_inventory,
                    token_counter,
                    budgets.base_tokens,
                    min_document_confidence,
                )
                scores = combined
                pending = [identifier for identifier in pending if identifier not in incoming]
                selected, evidence, count = proposed, proposed_evidence, proposed_count
                last_decision = decision
                packed_ids = {item["document_id"] for item in selected}
                dropped_citations = sorted(
                    {item["document_id"] for item in decision["evidence"]} - packed_ids
                )
                if dropped_citations:
                    observations.append(
                        {
                            "kind": "controller_error",
                            "error": "base_capacity_exceeded",
                            "dropped_citations": dropped_citations,
                        }
                    )
                    stop_detail = "base_capacity_exceeded"
            except (ValueError, TypeError, KeyError, UnicodeError) as exc:
                observations.append({"kind": "controller_error", "error": str(exc)})
                if not has_budget():
                    stop_detail = "acquisition_actions_exhausted"
                    if not pending:
                        break
                continue
            action = decision["action"]
            kind = action.get("kind")
            if kind == "freeze":
                if set(action) != {"kind"}:
                    observations.append(
                        {"kind": "controller_error", "error": "invalid freeze action"}
                    )
                    continue
                if (
                    not pending
                    and not dropped_citations
                    and _sufficient(decision, {item["document_id"] for item in selected}, evidence)
                ):
                    stop_reason = "sufficient"
                    stop_detail = "supported_public_requirements"
                    break
                if not has_budget() and not pending:
                    stop_detail = "acquisition_actions_exhausted"
                    break
                if pending:
                    observations.append(
                        {
                            "kind": "controller_error",
                            "error": "review remaining returned documents before freezing",
                        }
                    )
                    continue
                missing = _invalid_coverage(
                    decision, {item["document_id"] for item in selected}, evidence
                )
                observations.append(
                    {
                        "kind": "controller_error",
                        "error": "incomplete freeze rejected while acquisition budget remains",
                        "invalid_coverage": missing,
                        "gaps": decision["gaps"],
                        "conflicts": decision["conflicts"],
                    }
                )
                continue
            if not has_budget():
                if pending:
                    continue
                stop_detail = "acquisition_actions_exhausted"
                break
            if pending:
                # Review the returned batch before adding more material.
                continue
            if step == budgets.analyzer_steps - 1:
                stop_detail = "analyzer_steps_exhausted"
                break
            if kind not in limits:
                observations.append(
                    {"kind": "controller_error", "error": "forbidden acquisition action"}
                )
                continue
            if counters[kind] >= limits[kind]:
                if not has_budget():
                    break
                observations.append(
                    {"kind": "controller_error", "error": f"{kind} budget exhausted"}
                )
                continue
            expected = {
                "search": {"kind", "query"},
                "clarify": {"kind", "question"},
                "read_only": {"kind", "tool", "arguments"},
            }[kind]
            if set(action) != expected:
                observations.append(
                    {"kind": "controller_error", "error": "malformed acquisition action"}
                )
                continue
            if kind == "read_only":
                if (
                    not isinstance(action.get("tool"), str)
                    or action.get("tool") not in allowed_names
                    or action.get("tool") not in read_only_tools
                ):
                    observations.append(
                        {"kind": "controller_error", "error": "forbidden read-only tool"}
                    )
                    continue
                if not isinstance(action.get("arguments"), Mapping):
                    observations.append(
                        {"kind": "controller_error", "error": "tool arguments must be an object"}
                    )
                    continue
            elif (
                not isinstance(action.get("query" if kind == "search" else "question"), str)
                or not action.get("query" if kind == "search" else "question").strip()
            ):
                observations.append(
                    {"kind": "controller_error", "error": "action requires nonempty text"}
                )
                continue
            call_index = counters[kind]
            counters[kind] += 1

            result = dispatch(
                f"{operation_prefix}/{kind}/{call_index}",
                dict(action),
                lambda kind=kind, action=action, call_index=call_index: perform(
                    kind, action, f"{operation_prefix}/{kind}/{call_index}"
                ),
            )
            if kind != "search":
                observations.append({"kind": kind, "action": dict(action), **result})
            if kind == "search":
                observation = {
                    "kind": "search",
                    "query": action["query"],
                    "status": result["status"],
                    "returned_document_ids": [],
                }
                observations.append(observation)
                if result["status"] != "ok":
                    observation["error"] = result["error"]
                    continue
                response = result["result"]
                if isinstance(response, Mapping) and isinstance(response.get("status"), str):
                    observation["status"] = response["status"]
                documents = (
                    response.get("results", response.get("documents", []))
                    if isinstance(response, Mapping)
                    else response
                )
                if not isinstance(documents, list):
                    observations.append(
                        {"kind": "controller_error", "error": "search returned no full-text list"}
                    )
                    continue
                for item in documents:
                    try:
                        document = normalize_document(item)
                        previous = inventory.get(document["document_id"])
                        if previous is not None and previous != document:
                            raise ValueError("document content changed within fixed resource pool")
                        inventory[document["document_id"]] = document
                        if previous is None:
                            pending.append(document["document_id"])
                        if document["document_id"] not in observation["returned_document_ids"]:
                            observation["returned_document_ids"].append(document["document_id"])
                    except (ValueError, TypeError, UnicodeError) as exc:
                        observations.append({"kind": "controller_error", "error": str(exc)})
            elif kind == "clarify":
                public["clarifications"].append({"question": action["question"], **result})
            elif kind == "read_only":
                public["read_only_observations"].append(
                    {"tool": action["tool"], "arguments": dict(action["arguments"]), **result}
                )
        if journal is not None:
            summary = {
                "stop_reason": stop_reason,
                "stop_detail": stop_detail,
                "counters": counters,
                "returned_document_ids": list(inventory),
                "document_scores": list(scores.values()),
                "unreviewed_document_ids": pending,
                "unreviewable_document_ids": unreviewable,
                "selected_document_ids": [item["document_id"] for item in selected],
                "observations": observations,
            }
            journal.dispatch(f"{operation_prefix}-summary", {}, lambda: summary, external=False)
        return FrozenBase(
            documents=tuple(selected),
            public_inputs=public,
            evidence=tuple(evidence),
            stop_reason=stop_reason,
            token_count=count,
        )
    finally:
        if hasattr(corpus, "close"):
            corpus.close()
