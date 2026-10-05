#!/usr/bin/env python3
"""Solve or validate typed classical-PDDL plans declared by a JSON manifest.

Input is one JSON object on stdin.  In solve mode the program writes plans at
manifest plan_output paths; in validate-manifest mode it only replays files.
Output is one JSON result object on stdout.
"""
import collections
import heapq
import itertools
import json
import os
import re
import sys
import time

NUMERIC = {"increase", "decrease", "assign", "scale-up", "scale-down"}
LOGIC = {"and", "or", "not", "imply", "=", "forall", "exists", "when"}


def parse_sexpr(text):
    tokens = re.findall(r"\(|\)|[^\s()]+", re.sub(r";[^\n]*", "", text).lower())
    stack, root = [[]], None
    for token in tokens:
        if token == "(":
            node = []
            stack[-1].append(node)
            stack.append(node)
        elif token == ")":
            if len(stack) == 1:
                raise ValueError("unexpected closing parenthesis")
            stack.pop()
        else:
            stack[-1].append(token)
    if len(stack) != 1 or len(stack[0]) != 1 or not isinstance(stack[0][0], list):
        raise ValueError("malformed PDDL")
    return stack[0][0]


def typed(items, default="object"):
    answer, pending, i = [], [], 0
    while i < len(items):
        item = items[i]
        if item == "-":
            if i + 1 >= len(items) or isinstance(items[i + 1], list):
                raise ValueError("malformed typed list")
            answer.extend((name, items[i + 1]) for name in pending)
            pending = []
            i += 2
        else:
            if isinstance(item, list):
                raise ValueError("expression in typed list")
            pending.append(item)
            i += 1
    answer.extend((name, default) for name in pending)
    return answer


def action_fields(item):
    result, i = {}, 2
    while i + 1 < len(item):
        if isinstance(item[i], str) and item[i].startswith(":"):
            result[item[i]] = item[i + 1]
            i += 2
        else:
            i += 1
    return result


class Model:
    def __init__(self, domain_path, problem_path):
        domain = parse_sexpr(open(domain_path, encoding="utf-8").read())
        problem = parse_sexpr(open(problem_path, encoding="utf-8").read())
        if not (isinstance(domain, list) and isinstance(problem, list)
                and domain and problem and domain[0] == problem[0] == "define"):
            raise ValueError("expected PDDL define forms")
        self.types = {"object": None}
        self.actions = []
        changed = set()
        for item in domain[1:]:
            if not isinstance(item, list) or not item:
                continue
            if item[0] == ":types":
                self.types.update(dict(typed(item[1:])))
            elif item[0] == ":durative-action":
                raise ValueError("durative PDDL is unsupported")
            elif item[0] == ":action":
                fields = action_fields(item)
                if len(item) < 2 or not all(x in fields for x in (":parameters", ":precondition", ":effect")):
                    raise ValueError("incomplete action schema")
                schema = (item[1], typed(fields[":parameters"]), fields[":precondition"], fields[":effect"])
                self.actions.append(schema)
                self.effect_heads(schema[3], changed)
        if not self.actions:
            raise ValueError("domain has no action schemas")

        self.objects, initial, self.goal = {}, set(), None
        for item in problem[1:]:
            if not isinstance(item, list) or not item:
                continue
            if item[0] == ":objects":
                self.objects.update(dict(typed(item[1:])))
            elif item[0] == ":init":
                for atom in item[1:]:
                    if not isinstance(atom, list) or not atom:
                        continue
                    if atom[0] in NUMERIC:
                        raise ValueError("numeric PDDL is unsupported")
                    if atom[0] not in {"not", "="}:
                        initial.add(tuple(atom))
            elif item[0] == ":goal":
                if len(item) != 2:
                    raise ValueError("malformed goal")
                self.goal = item[1]
        if self.goal is None:
            raise ValueError("problem lacks a goal")

        self.by_type = collections.defaultdict(list)
        for obj, typ in self.objects.items():
            for ancestor in self.ancestors(typ):
                self.by_type[ancestor].append(obj)
        self.static_heads = {atom[0] for atom in initial if atom[0] not in changed}
        self.fixed = frozenset(atom for atom in initial if atom[0] in self.static_heads)
        self.initial = frozenset(atom for atom in initial if atom[0] not in self.static_heads)

    def ancestors(self, typ):
        seen = set()
        while typ is not None and typ not in seen:
            seen.add(typ)
            yield typ
            typ = self.types.get(typ)

    def effect_heads(self, expr, result):
        if not isinstance(expr, list) or not expr:
            raise ValueError("malformed effect")
        op = expr[0]
        if op == "and":
            for child in expr[1:]:
                self.effect_heads(child, result)
        elif op == "not":
            if len(expr) != 2 or not isinstance(expr[1], list) or not expr[1]:
                raise ValueError("malformed delete effect")
            result.add(expr[1][0])
        elif op in {"when", "forall"}:
            if len(expr) != 3:
                raise ValueError("malformed conditional/quantified effect")
            self.effect_heads(expr[2], result)
        elif op in NUMERIC:
            raise ValueError("numeric PDDL is unsupported")
        elif op not in LOGIC:
            result.add(op)

    def formula(self, expr, facts, env=None):
        env = {} if env is None else env
        if not isinstance(expr, list) or not expr:
            raise ValueError("malformed formula")
        op = expr[0]
        if op == "and":
            return all(self.formula(x, facts, env) for x in expr[1:])
        if op == "or":
            return any(self.formula(x, facts, env) for x in expr[1:])
        if op == "not":
            return len(expr) == 2 and not self.formula(expr[1], facts, env)
        if op == "imply":
            return len(expr) == 3 and (not self.formula(expr[1], facts, env) or self.formula(expr[2], facts, env))
        if op == "=":
            return len(expr) == 3 and env.get(expr[1], expr[1]) == env.get(expr[2], expr[2])
        if op in {"forall", "exists"}:
            if len(expr) != 3:
                raise ValueError("malformed quantifier")
            variables = typed(expr[1])
            values = []
            choices = [self.by_type[t] for _, t in variables]
            for choice in itertools.product(*choices):
                scoped = dict(env)
                scoped.update(dict(zip((v for v, _ in variables), choice)))
                values.append(self.formula(expr[2], facts, scoped))
            return all(values) if op == "forall" else any(values)
        return tuple(env.get(term, term) for term in expr) in facts

    def apply(self, effect, state, env):
        # Effects are evaluated against the state before this action, then their
        # additions/deletions are collected. This is classical simultaneous effect semantics.
        before = self.fixed | state
        after = set(before)

        def walk(expr, local):
            if not isinstance(expr, list) or not expr:
                raise ValueError("malformed effect")
            op = expr[0]
            if op == "and":
                for child in expr[1:]:
                    walk(child, local)
            elif op == "not":
                if len(expr) != 2 or not isinstance(expr[1], list):
                    raise ValueError("malformed delete effect")
                after.discard(tuple(local.get(x, x) for x in expr[1]))
            elif op == "when":
                if len(expr) != 3:
                    raise ValueError("malformed conditional effect")
                if self.formula(expr[1], before, local):
                    walk(expr[2], local)
            elif op == "forall":
                if len(expr) != 3:
                    raise ValueError("malformed quantified effect")
                variables = typed(expr[1])
                for choice in itertools.product(*[self.by_type[t] for _, t in variables]):
                    scoped = dict(local)
                    scoped.update(dict(zip((v for v, _ in variables), choice)))
                    walk(expr[2], scoped)
            elif op in NUMERIC:
                raise ValueError("numeric PDDL is unsupported")
            else:
                after.add(tuple(local.get(x, x) for x in expr))

        walk(effect, env)
        return frozenset(atom for atom in after if atom[0] not in self.static_heads)

    def static_atoms(self, expr):
        """Positive static precondition atoms usable to prune grounding."""
        if not isinstance(expr, list) or not expr:
            return []
        if expr[0] == "and":
            answer = []
            for child in expr[1:]:
                answer.extend(self.static_atoms(child))
            return answer
        return [tuple(expr)] if expr[0] in self.static_heads else []

    def ground_actions(self):
        index = collections.defaultdict(list)
        for atom in self.fixed:
            index[atom[0]].append(atom)
        grounded = []
        for name, params, precondition, effect in self.actions:
            variables = [v for v, _ in params]
            domains = {v: self.by_type[t] for v, t in params}
            constraints = self.static_atoms(precondition)

            def complete(env):
                remaining = [v for v in variables if v not in env]
                if not remaining:
                    grounded.append((name, tuple(env[v] for v in variables), env, precondition, effect))
                    return
                var = min(remaining, key=lambda v: len(domains[v]))
                for obj in domains[var]:
                    next_env = dict(env)
                    next_env[var] = obj
                    complete(next_env)

            def match(env, todo):
                if not todo:
                    complete(env)
                    return
                atom = max(todo, key=lambda x: sum(term in env for term in x[1:]))
                rest = list(todo)
                rest.remove(atom)
                for fact in index[atom[0]]:
                    if len(atom) != len(fact):
                        continue
                    next_env, good = dict(env), True
                    for term, obj in zip(atom[1:], fact[1:]):
                        if isinstance(term, str) and term.startswith("?"):
                            if term not in domains or obj not in domains[term] or (term in next_env and next_env[term] != obj):
                                good = False
                                break
                            next_env[term] = obj
                        elif term != obj:
                            good = False
                            break
                    if good:
                        match(next_env, rest)

            match({}, constraints)
        return grounded


def positive_goal_atoms(expr):
    if not isinstance(expr, list) or not expr:
        return []
    if expr[0] == "and":
        answer = []
        for child in expr[1:]:
            answer.extend(positive_goal_atoms(child))
        return answer
    return [tuple(expr)] if expr[0] not in LOGIC else []


def solve(model, time_limit):
    if model.formula(model.goal, model.fixed | model.initial):
        return []
    actions = model.ground_actions()
    if not actions:
        return None
    goals = positive_goal_atoms(model.goal)
    deadline = time.monotonic() + time_limit

    def heuristic(state):
        return sum(goal not in model.fixed and goal not in state for goal in goals)

    best = {model.initial: 0}
    parent = {model.initial: (None, None)}
    serial = 0
    queue = [(heuristic(model.initial), 0, serial, model.initial)]
    while queue:
        if time.monotonic() > deadline:
            raise TimeoutError("search time limit reached")
        _, cost, _, state = heapq.heappop(queue)
        if best.get(state) != cost:
            continue
        for name, args, env, precondition, effect in actions:
            if not model.formula(precondition, model.fixed | state, env):
                continue
            successor = model.apply(effect, state, env)
            next_cost = cost + 1
            if successor == state or next_cost >= best.get(successor, 10 ** 18):
                continue
            best[successor] = next_cost
            parent[successor] = (state, (name, args))
            if model.formula(model.goal, model.fixed | successor):
                plan = []
                cursor = successor
                while parent[cursor][0] is not None:
                    prior, action = parent[cursor]
                    plan.append(action)
                    cursor = prior
                plan.reverse()
                return plan
            serial += 1
            heapq.heappush(queue, (next_cost + heuristic(successor), next_cost, serial, successor))
    return None


def read_plan(path):
    plan = []
    with open(path, encoding="utf-8") as stream:
        for line_number, raw in enumerate(stream, 1):
            line = raw.split(";", 1)[0].strip().lower()
            if not line:
                continue
            match = re.fullmatch(r"([a-z0-9_-]+)\s*\(\s*([^()]*)\s*\)", line)
            if match:
                args = tuple(x.strip() for x in match.group(2).split(",") if x.strip())
            else:
                match = re.fullmatch(r"\(\s*([a-z0-9_-]+)((?:\s+[a-z0-9_-]+)*)\s*\)", line)
                if not match:
                    raise ValueError("invalid plan line %d" % line_number)
                args = tuple(match.group(2).split())
            plan.append((match.group(1), args))
    return plan


def validate(model, plan):
    schemas = {name: (params, pre, effect) for name, params, pre, effect in model.actions}
    state = model.initial
    for step, (name, args) in enumerate(plan, 1):
        if name not in schemas:
            return {"valid": False, "step": step, "reason": "undeclared action"}
        params, precondition, effect = schemas[name]
        if len(params) != len(args):
            return {"valid": False, "step": step, "reason": "wrong arity"}
        env = dict(zip((var for var, _ in params), args))
        for var, required_type in params:
            obj = env[var]
            if obj not in model.objects or required_type not in set(model.ancestors(model.objects[obj])):
                return {"valid": False, "step": step, "reason": "ill-typed object"}
        if not model.formula(precondition, model.fixed | state, env):
            return {"valid": False, "step": step, "reason": "unsatisfied precondition"}
        state = model.apply(effect, state, env)
    if model.formula(model.goal, model.fixed | state):
        return {"valid": True, "steps": len(plan)}
    return {"valid": False, "reason": "goal not satisfied"}


def manifest_entries(path):
    data = json.load(open(path, encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("tasks", "problems"):
            if isinstance(data.get(key), list):
                return data[key]
    raise ValueError("manifest must be a list or contain tasks/problems")


def main(request):
    manifest = os.path.abspath(request.get("manifest", "problem.json"))
    base = os.path.dirname(manifest)
    entries = manifest_entries(manifest)
    if not entries:
        raise ValueError("manifest has no tasks")
    checking = request.get("mode") == "validate-manifest"

    def entry_paths(entry):
        required = ("domain", "problem", "plan_output")
        if not isinstance(entry, dict) or any(not isinstance(entry.get(k), str) or not entry[k] for k in required):
            raise ValueError("entry requires domain, problem, and plan_output")
        def absolute(value):
            return value if os.path.isabs(value) else os.path.join(base, value)
        return absolute(entry["domain"]), absolute(entry["problem"]), absolute(entry["plan_output"])

    results = []
    for entry in entries:
        label = entry.get("id") if isinstance(entry, dict) else None
        try:
            domain_path, problem_path, output_path = entry_paths(entry)
            model = Model(domain_path, problem_path)
            if checking:
                if not os.path.isfile(output_path):
                    raise ValueError("required plan output is missing: " + output_path)
                results.append({"id": label, "plan_output": output_path, **validate(model, read_plan(output_path))})
                continue

            plan = solve(model, float(request.get("time_limit_sec", 240)))
            if plan is None:
                results.append({"id": label, "status": "unsolved", "plan_output": output_path})
                continue
            replay = validate(model, plan)
            if not replay["valid"]:
                raise ValueError("internal replay failed: " + str(replay))
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            temporary = output_path + ".tmp"
            with open(temporary, "w", encoding="utf-8") as stream:
                for name, args in plan:
                    stream.write(name + "(" + ",".join(args) + ")\n")
            os.replace(temporary, output_path)
            results.append({"id": label, "status": "solved", "plan_output": output_path,
                            "plan_length": len(plan), "validation": replay})
        except TimeoutError as error:
            results.append({"id": label, "status": "timeout", "reason": str(error)})
        except Exception as error:
            if checking:
                results.append({"id": label, "valid": False, "reason": str(error)})
            else:
                results.append({"id": label, "status": "error", "reason": str(error)})

    succeeded = all(result.get("valid") if checking else result.get("status") == "solved" for result in results)
    return {"ok": succeeded, "results": results}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except Exception as error:
        print(json.dumps({"ok": False, "status": "error", "reason": str(error)}, sort_keys=True))
        sys.exit(2)
