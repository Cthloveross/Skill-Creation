---
name: nextjs-performance-repair
description: Diagnose and repair a small Next.js e-commerce application with slow API routes, costly client rerenders, and an optional heavy compare view. Use when the source tree and any backing API simulator are available locally and the application must preserve existing UI/test hooks.
---

# Next.js performance repair

Use this Skill to make measured, correctness-preserving performance fixes in an existing Next.js App Router project. Read the current code before editing: names, APIs, data shapes, dependencies, and route contracts are instance-specific and must not be guessed.

## Non-negotiable preservation rules

1. Do not delete, rename, or alter any existing `data-testid` attribute, and do not remove a component that contains one.
2. Do not remove `performance.mark()` calls from `ProductCard`; instrumentation is not the performance problem.
3. Keep all data required by the homepage, cart behavior, checkout, and the advanced compare tab. Do not fake data or hard-code IDs to reduce latency.
4. Do not add response caching unless the existing route contract explicitly permits stale results. Checkout and other correctness-sensitive routes should continue to request fresh data.
5. Keep imports legal for the installed package versions. Do not assume a library has a private/function-level import path without verifying its exports.

## Inputs and expected workspace

This Skill operates on the copied project at `/app` and, when present, its API simulator at `/services/api-simulator`. Important files commonly include:

- `/app/src/app/api/**/route.ts` for server routes;
- `/app/src/services/api-client.ts` for upstream request behavior;
- `/app/src/components/ProductList.tsx` and `ProductCard.tsx` for cart-driven renders;
- `/app/src/app/compare/page.tsx` for the optional advanced view.

The exact source layout is authoritative. Inspect `package.json`, relevant source files, and upstream simulator endpoints before choosing changes.

## Workflow

### 1. Establish the actual contract and bottleneck

Read every affected route/component and trace:

- which requests each API route makes;
- which results are included in its response or are required for a correctness-affecting write;
- dependencies between calls (a request needing an ID/token from another is dependent);
- which state update occurs when an item is added to cart;
- which props flow from the list to each product card;
- which module(s) implement the compare advanced tab and which large dependencies they import.

Inspect the API simulator and API client rather than inventing endpoint paths, request bodies, headers, or returned fields. Note simulated latency if present. If a request fails, preserve or improve the route's existing error handling rather than silently returning incomplete success data.

Optionally record representative end-to-end timings (more than one request, separating first/cold from later requests) before and after changes. Source-pattern checks alone are not proof that a waterfall is gone.

### 2. Repair API route critical paths

For every group of truly independent upstream reads, create all promises before awaiting any of them, then await them together with `Promise.all` (or use `Promise.allSettled` only when partial failure is part of the route contract). Preserve the response schema and failure semantics.

For a dependency graph, start each root and any unrelated request immediately. Chain a dependent operation from the promise that yields its required input, then await the resulting promises together. For example, a prerequisite result must be obtained before calling a request that needs its identifier; do not place that dependent call beside its prerequisite with an undefined argument.

A frequent near-miss is awaiting a prerequisite *and an unrelated slow request* in one `Promise.all`, and only then starting the dependent call. That leaves avoidable time on the critical path. Instead, retain the promises and construct the dependent promise immediately:

```ts
const prerequisitePromise = getPrerequisite();
const independentPromise = getIndependentData();
const dependentPromise = prerequisitePromise.then(({ id }) => getDependentData(id));
const [prerequisite, independent, dependent] = await Promise.all([
  prerequisitePromise, independentPromise, dependentPromise,
]);
```

This preserves the dependency while allowing the dependent request to start as soon as its input exists. Do not replace this with an unsafe call using an ID that has not resolved.

Await writes, validation, authorization, inventory, payment, and any operation whose result affects the response or correctness. A telemetry/analytics call can be unawaited only when its result is explicitly noncritical; attach a rejection handler so it cannot become an unhandled rejection. Do not fire-and-forget a checkout write merely to improve timing.

Avoid accidental serial work after the fetches: parse/process independent results only after the concurrent work has settled, and preserve dynamic/no-store behavior where it is required for freshness. If the framework can cache server `fetch` calls by default and the route is freshness-sensitive, explicitly use its supported no-store option in the client wrapper; do not let a benchmark pass by serving stale upstream data.

### 3. Stop cart state changes from rendering every product card

In the client component that owns cart state:

- derive expensive product filtering, sorting, review lookup maps, or other calculations with `useMemo`, keyed to all data that changes their result;
- use a functional state update in the add-to-cart handler and wrap that handler with `useCallback` when this makes its dependency list stable;
- avoid recreating object/array props in the render loop when a stable memoized value can be passed instead.

Wrap the individual product-card component in `React.memo` (or export a memoized card) while retaining its complete rendered markup, all test IDs, and every `performance.mark()` call. The card must receive stable primitive/object data and stable callback references for memoization to skip unchanged cards. Do not use an unsafe custom comparator that ignores product fields or callback behavior.

A card whose own selected/cart quantity legitimately changes should still render. The goal is to avoid renders of unrelated cards when another cart item changes.

### 4. Split the optional compare advanced view legally

Keep the default compare page useful without loading code needed only for the advanced tab. Move the heavy advanced tab implementation into a separate module if it is currently in the page module. From the page, use `next/dynamic` to import that module and provide a small loading fallback. Render the dynamically loaded component only when the advanced tab is selected.

The separate module must retain the exact advanced UI and the element carrying `data-testid="advanced-content"`. Pass the current data/props through normally; do not replace the tab with a placeholder. Keep client-component directives where hooks or browser APIs require them.

Before converting a barrel import to a direct library subpath, inspect the installed package's `package.json` `exports` and types or resolve it with the project tooling. If there is no public function-level path, retain the legal public import inside the dynamically imported advanced module. Dynamic module separation still removes it from the initial page bundle.

### 5. Validate the deliverable

Run the project checks defined by its package scripts, then at minimum run the production build from `/app`:

```sh
cd /app && npm run build
```

Use the package's intended development/start command and the API simulator's documented command when end-to-end behavior must be exercised. Verify all of the following against the running application when the environment permits:

- homepage receives and displays real product data;
- adding a product updates cart behavior and remains interactive;
- selecting the advanced compare tab eventually renders `[data-testid="advanced-content"]`;
- affected API routes return their complete expected payload and still fail appropriately when an upstream call fails;
- repeated route timing reflects concurrent independent work rather than a sum of independent simulated delays; for a dependency graph, compare it with the longest chain, not merely whether the source has `Promise.all`.

Finally run the packaged static guard as a regression reminder. It is intentionally advisory: a successful guard does not replace the build or runtime checks.

```sh
python3 /app/environment/skills/current/scripts/performance_guard.py <<'JSON'
{"app_root":"/app"}
JSON
```

## Failure handling

If a referenced route, test ID, mark, dependency, or package cannot be found, stop making speculative transformations and report the mismatch. If build errors reveal server/client boundary or dynamic-import export issues, correct the module boundary while preserving behavior. If a latency target remains unmet after legitimate concurrency, report the remaining dependency-chain/upstream latency rather than dropping required work.
