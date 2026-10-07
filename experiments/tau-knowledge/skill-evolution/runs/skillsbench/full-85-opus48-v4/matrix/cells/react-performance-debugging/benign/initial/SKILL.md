---
name: nextjs-react-performance-fix
description: >
  Diagnose and fix performance problems in a Next.js (App Router) + React
  codebase without breaking its behavior. Use when a task asks to make a slow
  Next.js app faster by addressing API-route fetch waterfalls, excessive
  client re-rendering, and JavaScript bundle bloat, while preserving test
  hooks (data-testid attributes) and instrumentation (performance.mark calls).
  The deliverable is the edited source tree that still builds and behaves
  correctly, not a written report.
---

# Next.js / React Performance Fix

## When to use

Use this Skill for tasks of the form "this Next.js app is slow, find the root
cause and fix it" focused on three categories:

1. **API route optimization** - server route handlers / server components that
   `await` independent calls sequentially (waterfall) or `await` non-critical
   side effects (analytics/telemetry/logging) on the request path.
2. **Bundle size reduction** - heavy libraries pulled into the initial route
   bundle through barrel imports or static imports of interaction-gated UI.
3. **Excessive re-rendering** - list children that re-render on every parent
   state change because they are not memoized and/or receive unstable
   function/object props.

The fix must keep the app working: homepage shows product data, add-to-cart
works, and gated tabs still render their `data-testid` content. Never remove
`data-testid` attributes or `performance.mark()` calls, and never fake data,
hard-code identifiers, or delete required response fields just to make timing
look better (see `references/patterns.md`).

## Workflow

Run everything from the app root (the directory containing `package.json` and
`next.config.js`; typically `/app`). Read the actual files first - do not
assume file names or library names; the diagnostic script discovers them.

### 1. Inspect the codebase

```
cd /app
ls -R src
cat package.json
```

Read each source file the task mentions and each file under `src/`. Identify:
server route handlers under `src/app/**/route.ts`, server components (async
`page.tsx`), client components (files with `"use client"`), the API client
module, and any page that imports a large library.

### 2. Automated diagnosis

Run the scanner to surface candidate anti-patterns. It reads real files, so its
output reflects the current instance, not a template.

```
echo '{"app_root": "/app"}' | python3 environment/skills/current/scripts/diagnose.py
```

(Adjust the script path to wherever this Skill is installed, e.g.
`$SKILL_DIR/scripts/diagnose.py`.) Output is JSON: a `findings` array where each
entry has `file`, `category`, `detail`, and `suggestion`. Treat findings as
leads to verify by reading the code, not as proof - confirm each one before
editing.

### 3. Apply targeted fixes

Use `references/patterns.md` for the exact code shapes. In short:

- **Fetch waterfalls** in route handlers / async server components: start all
  genuinely independent async calls together and `await Promise.all([...])`.
  Keep real dependency chains sequential (chain the dependent call off the
  promise it needs); do not put a dependent call in the same concurrent group
  as its prerequisite.
- **Non-critical awaited side effects** (analytics/telemetry/logging that the
  response does not depend on): fire-and-forget - call without `await`, and add
  a `.catch()` so a rejected background promise cannot crash the process. Keep
  awaiting anything the response correctness depends on (e.g. identity checks,
  persisted writes the response reflects).
- **Excessive re-render**: wrap list-item components in `React.memo`; stabilize
  handler props with `useCallback` (use functional state updaters so deps can
  stay empty); stabilize derived data (filter/sort, lookup maps) with
  `useMemo`. All three together - memo without stable props, or stable props
  without memo, does nothing.
- **Bundle bloat**: for a heavy library used only behind interaction (e.g. a
  tab), move its consumer into a separate module file and load it via Next.js
  `dynamic(() => import(...))` with a loading placeholder. For a library where
  only a few functions are used, prefer a direct/subpath import over the barrel
  **only if** the package actually publishes that subpath (verify against the
  installed `package.json` `exports` / module layout). If no stable subpath
  exists, keep the legal entry point and split via dynamic import instead.

### 4. Preserve constraints (hard requirements)

- Do not change or remove any `data-testid` attribute, and do not remove any
  component that renders one. The gated/advanced tab content must still render.
- Do not remove `performance.mark()` calls (notably in the product card).
- Keep required response fields and real service calls; do not disable caching
  semantics that correctness depends on, and do not add caching that would
  serve stale data where freshness is required.

### 5. Verify

```
echo '{"app_root": "/app"}' | python3 environment/skills/current/scripts/verify.py
```

`verify.py` reports JSON with `ok` (bool) and `checks`. It fails if a
`data-testid` that existed before is now missing or if `performance.mark` was
removed from the product card, and it reports whether the optimization patterns
(Promise.all / memoization / dynamic import) are now present. Then run the real
build and, where possible, measure routes end to end - a structural check that
`Promise.all` exists does not prove the critical path is short:

```
npm run build
# optional runtime measurement if a dev/prod server + the api-simulator run:
# time curl -s localhost:3000/api/<route> > /dev/null   (measure more than once;
#   discard the first cold-start sample and compare steady-state)
```

A successful `npm run build` (type-check + compile pass) plus `verify.py`
`ok: true` is the minimum bar. If the build fails, read the error and fix the
edit (common causes: broken import subpath, dependent fetch moved into a
concurrent group so it receives `undefined`, missing `"use client"` for hooks).

## Failure handling

- If the scanner finds nothing in a category, do not invent a change there.
- If a proposed direct import path does not resolve during build, revert to the
  public entry point and use dynamic import instead.
- If removing an `await` would drop data the response returns, keep the await.
- Never satisfy a timing requirement by faking a field or hard-coding an id.
