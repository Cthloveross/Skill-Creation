---
name: nextjs-ecommerce-performance-remediation
description: Diagnose and remediate slow Next.js e-commerce pages and route handlers while preserving UI contracts. Use for tasks involving API waterfalls, slow cart updates caused by excessive React renders, and optional compare-page content inflating the initial bundle.
---

# Next.js e-commerce performance remediation

Use this Skill in the supplied application workspace. Inspect the actual source before editing: performance fixes must preserve the response shape, routes, visible behavior, all existing `data-testid` values/components, and every `performance.mark()` in `ProductCard`.

## 1. Establish the implementation and contracts

1. Read `package.json`, all files under `src/app/api`, `src/app/page.tsx`, `src/app/compare/page.tsx`, `src/components/ProductCard.tsx`, `src/components/ProductList.tsx`, and `src/services/api-client.ts`.
2. Identify:
   - which API simulator endpoints and response fields are consumed;
   - which route calls are independent and which require a prior result;
   - cart state ownership and every prop passed into each product card;
   - the compare page's default and advanced-tab rendering paths;
   - existing test IDs and product-card performance marks.
3. Do not change API response contracts merely to shorten timing. Do not add caching unless the existing task explicitly permits staleness. Preserve error handling and meaningful HTTP failures.

## 2. Fix API critical paths

For each route handler, initiate independent upstream work before awaiting any of it, then await it together:

```ts
const productsPromise = getProducts();
const promotionsPromise = getPromotions();
const [products, promotions] = await Promise.all([productsPromise, promotionsPromise]);
```

For a real dependency, start unrelated work concurrently and chain only the dependent request:

```ts
const userPromise = getUser();
const configPromise = getConfig();
const profilePromise = userPromise.then((user) => getProfile(user.id));
const [user, config, profile] = await Promise.all([userPromise, configPromise, profilePromise]);
```

Apply this to both product and checkout routes where supported by their actual service calls. Never invoke a dependent request with an unavailable ID just to place it in `Promise.all`. Keep writes or data needed in the response awaited. Only nonessential telemetry/logging may be detached, and detached promises must have explicit rejection handling so they do not create unhandled rejections.

Maintain Next.js route conventions and any configured no-store/freshness behavior. Use the actual API client and environment URL conventions already present rather than hardcoding a local service address.

## 3. Stop cart state from rerendering unchanged cards

In the product list/client component:

1. Wrap `ProductCard` in `React.memo` (or retain its existing memo wrapper).
2. Make the add-to-cart callback stable with `useCallback`. When only updating cart state, use a functional updater so the callback can have an empty dependency list:

```ts
const handleAddToCart = useCallback((product: Product) => {
  setCart((current) => [...current, product]);
}, []);
```

Adapt the updater to the existing cart data model; do not introduce duplicate/incorrect cart behavior.
3. Use `useMemo` for genuinely derived expensive values, such as filtering/sorting products or building an ID-keyed review/count lookup. Depend on the source data and relevant filters only.
4. Pass stable primitive values or memoized objects to the memoized card. Do not create inline callback wrappers, object literals, or rebuilt lookup structures per card on every cart update.
5. Keep every existing `performance.mark()` call in `ProductCard`, including its original marker semantics. Memoization should prevent needless card invocation; it must not remove observability.

Do not memoize a component if required props still deliberately change on a cart update. Instead separate cart-only display from immutable product-card props when that is necessary to preserve functionality.

## 4. Code-split optional compare content legally

Find the expensive advanced comparison/chart/statistics content. Move that content, including its heavy-library import, to a separate component module under `src/components` (or another appropriate source directory). The separate file must export a React component and retain the advanced content's DOM and `data-testid="advanced-content"` exactly.

In `src/app/compare/page.tsx`, dynamically load that separate module using Next.js `dynamic`:

```tsx
import dynamic from "next/dynamic";

const AdvancedComparison = dynamic(() => import("../../components/AdvancedComparison"), {
  loading: () => <p>Loading advanced comparison…</p>,
});
```

Use the correct relative path and export form for the actual project. Render the dynamic component only on the advanced tab. Do not define the heavy component in `page.tsx`; a module boundary is essential for a real split. Keep the default tab functional and do not dynamically import a component that must be present for the initial page contract.

If attempting to replace a barrel import, first inspect the installed package `exports` map and types (or resolve it with the project resolver). Use a direct package subpath only when it is publicly exported. Otherwise retain the legal import inside the dynamically loaded advanced module; do not import package-private filesystem paths.

## 5. Validate the deliverable

After edits, run the supplied structural helper, then run the project checks appropriate to the repository (at minimum TypeScript/build checks; use the package scripts actually declared):

```sh
python3 /app/environment/skills/current/scripts/validate_next_performance.py <<'JSON'
{"root":"/app"}
JSON
npm run build
```

If services are needed for a runtime smoke test, start them using their documented package scripts, then verify the homepage returns product content, a cart add updates the cart, and selecting the advanced compare tab renders `[data-testid="advanced-content"]`. Also request both API routes and verify successful responses preserve their expected fields. Treat build/type failures, invalid dynamic import paths, failed API calls, and missing UI contracts as failures to fix.

The validator is a guardrail, not a performance benchmark. Confirm the implementation has reduced true critical paths: independent calls are dispatched before the first await, cards have stable memoized props, and the heavy advanced module is not statically imported by the initial compare-page module.

## Helper interface

`scripts/validate_next_performance.py` reads one JSON object from stdin:

```json
{"root":"/app"}
```

It prints JSON with `ok`, `errors`, and `checks`. It performs source-level checks only; it does not modify the project or replace build/runtime validation.
