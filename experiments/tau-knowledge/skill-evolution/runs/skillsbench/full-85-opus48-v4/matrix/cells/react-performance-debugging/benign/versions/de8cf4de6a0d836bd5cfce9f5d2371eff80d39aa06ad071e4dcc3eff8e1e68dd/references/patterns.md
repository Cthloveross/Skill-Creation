# Fix patterns for Next.js / React performance

These are the canonical code shapes. Adapt names to the actual files; never
copy instance-specific identifiers from here (there are none on purpose).

## 1. API route / server-component fetch waterfall

### Sequential (slow) - total time ~ a + b + c
```ts
const a = await getA();
const b = await getB();
const c = await getC();
```

### Parallel (independent calls) - total time ~ max(a, b, c)
```ts
const [a, b, c] = await Promise.all([getA(), getB(), getC()]);
```

### Mixed: one call depends on another
Start the prerequisite and every independent call concurrently, then chain the
dependent call off the prerequisite's promise. Do NOT place the dependent call
in the same `Promise.all` group as its prerequisite - it would receive
`undefined` and throw.
```ts
const userPromise = getUser();            // prerequisite, started now
const configPromise = getConfig();        // independent, started now
const profilePromise = userPromise.then(u => getProfile(u.id)); // chained
const [user, config, profile] = await Promise.all([
  userPromise, configPromise, profilePromise,
]);
```
Critical path becomes `max(user + profile, config)`.

### Do not cheat the timing
Data required for correctness must stay on the critical path. Do not hard-code
an id, fabricate a response field, remove a required field, or add caching that
serves stale data where freshness is required (e.g. a checkout that must verify
identity in real time).

## 2. Fire-and-forget non-critical side effects

Analytics / telemetry / logging the response does not depend on should not be
awaited:
```ts
// before
await logAnalytics(event);
return Response.json(data);

// after
logAnalytics(event).catch(() => {}); // background; failure is acceptable
return Response.json(data);
```
Keep awaiting writes/reads the response reflects for correctness.

## 3. Prevent excessive re-rendering (apply all three together)

```tsx
// child list item - memoized
import { memo } from "react";
function ProductCardBase(props: Props) { /* ... keep performance.mark(...) ... */ }
export default memo(ProductCardBase);
```
```tsx
// parent - stabilize props
const handleAdd = useCallback((id: string) => {
  setCart(prev => [...prev, id]);   // functional updater => empty deps OK
}, []);

const visible = useMemo(
  () => products.filter(matches).sort(byName),
  [products /* and real inputs */]
);

const reviewCountById = useMemo(() => {
  const m = new Map<string, number>();
  for (const r of reviews) m.set(r.productId, (m.get(r.productId) ?? 0) + 1);
  return m;
}, [reviews]);
```
Memo without stable props, or stable props without memo on the child, has no
effect. Keep every `data-testid` and `performance.mark()` intact while editing.

## 4. Bundle size

### Dynamic import for interaction-gated heavy UI
The heavy consumer MUST live in its own module file (split boundary is the
module). Keep the gated content's `data-testid`.
```tsx
import dynamic from "next/dynamic";
const AdvancedPanel = dynamic(() => import("./AdvancedPanel"), {
  loading: () => <div>Loading...</div>,
});
// render <AdvancedPanel/> only when its tab is active
```

### Direct vs barrel import
Only rewrite to a subpath the package actually publishes - check the installed
`package.json` `exports` map / module layout, then run the real build. A
plausible filesystem path is not necessarily a public import path. If no stable
function-level subpath exists, keep the legal entry point and split with
`dynamic()` instead; a broken private subpath is not an optimization.

## 5. Validation is structural AND behavioral

Finding `Promise.all`, `memo`, or `dynamic(` in source does not prove the route
is fast or still correct. Always run `npm run build`, confirm it passes, and
where a server + simulator are available, measure the route more than once
(discard cold start, compare steady state). Confirm homepage shows products,
add-to-cart works, and the gated/advanced tab still renders its content.
