---
name: fix-nextjs-visual-stability
description: Assess and repair visual instability in an existing React/Next.js application: layout shifts from late content or media, persisted-theme flicker, font-loading visibility, and avoidable client rendering or initial-bundle costs. Use when source files must be safely edited without changing existing selectors, ids, data-testid values, or behavior contracts.
---

# Fix Next.js Visual Stability

Work in the supplied application root (normally `/app`). This is a source-editing Skill: inspect the actual app before choosing changes, then implement only fixes supported by the code and validate the resulting application. Do not replace functional features with static mockups, remove required data, or rename/remove existing `className` values, `id` values, or `data-testid` values.

## 1. Establish the application contract

1. Read `package.json`, framework configuration, the root layout, global styles, and all components rendered by the affected page.
2. Identify whether the App Router or Pages Router is in use, which files are client components, where data is loaded, and available `build`, `lint`, typecheck, and test scripts.
3. Trace the first render and subsequent updates. Look specifically for:
   - components returning `null`/empty output until a timeout, effect, or fetch resolves;
   - banners, toolbars, results bars, side panes, modals, or notices inserted above or beside already-painted content;
   - images without intrinsic dimensions or a pre-load aspect ratio;
   - custom `@font-face` declarations without a non-blocking display strategy;
   - a persisted visual preference read in `useEffect` after the initial document has painted;
   - needless rerenders caused by unstable handlers or repeatedly computed list data;
   - truly optional heavy client UI imported into the initial route.
4. Preserve the component's public DOM hooks. You may add styles, attributes, wrappers, semantic attributes, or new modules when needed, but do not change existing class names, ids, data-testids, interactive behavior, displayed data, or API contracts.

## 2. Repair the actual instability sources

Apply the smallest compatible changes for the causes found. Do not add unrelated optimizations merely because they are generally useful.

### Reserve geometry before asynchronous content appears

A component that later inserts a block into normal document flow must occupy equivalent space on the initial render.

- Render a loading/skeleton/reserved container instead of `null` when content will appear after a fetch, timer, or client effect.
- Ensure the placeholder matches the final component's width, height/min-height, padding, margins, borders, and grid/flex placement closely enough that replacement does not move neighboring content.
- For top-of-page banners or notification strips, reserve the banner's final block height from the first render. Do not solve this by positioning an essential banner over content unless that was already the intended behavior and accessibility remains correct.
- Keep loading status accessible where appropriate (for example, `aria-busy` on an existing or added container) without changing test hooks.
- Prefer CSS classes or CSS rules that retain current selectors. If a component already has a skeleton component, compare its geometry against the final card and correct the mismatch rather than creating unrelated markup.

### Give media deterministic layout dimensions

For each image that affects layout, provide the browser enough information before the file downloads:

- Use valid `width` and `height` attributes based on the image's known intrinsic dimensions, or an explicit CSS `aspect-ratio` plus a constrained dimension.
- In Next.js, use `next/image` only when its source configuration and image usage support it. Supply its `width` and `height`, or use `fill` with a deliberately sized/positioned parent.
- Preserve responsive behavior with CSS such as `width: 100%; height: auto` when appropriate; intrinsic attributes still communicate the ratio.
- Do not invent dimensions. Derive them from supplied image metadata, existing data, a documented fixed design ratio, or the asset itself. If dimensions cannot be established, use a stable aspect-ratio container matching the intended design.

### Apply persisted theme before first paint

When the app uses localStorage (or equivalent client persistence) to select light/dark visual state, applying it in a mounted effect alone causes a flash.

- Keep interactive theme controls and their state behavior intact.
- Add a small, synchronous, inline critical-path script in the document head/root layout, or the framework's supported pre-interactive equivalent, so it reads the persisted value and applies the same root class or data attribute that the CSS/theme provider uses before first paint.
- Make the script defensive: storage access can throw, a stored value can be invalid, and server rendering has no browser globals. Fall back to the app's existing default or, only if the application already supports it, the system preference.
- Avoid a post-paint removal/addition sequence. The client provider should initialize consistently with the already-applied DOM state to avoid hydration flicker or mismatch warnings.
- For App Router layouts, use the current framework's supported script placement/API and preserve valid HTML structure.

### Keep text visible during web-font loading

If custom fonts are declared through `@font-face`, add `font-display: swap` (or a deliberate existing non-blocking policy) inside each relevant rule. Do not claim this is needed for system-only fonts or framework-managed fonts that already specify an appropriate display behavior.

### Apply React and bundle optimizations only where evidence supports them

- For expensive derived list data that is recomputed on unrelated state updates, use `useMemo` with complete, correct dependencies.
- For list children that rerender unnecessarily, use `React.memo` only after ensuring object and callback props are stable. Use `useCallback` where a handler is passed to a memoized child; use functional state updates when that safely permits a minimal dependency list. Do not introduce stale closures.
- If a large component is not needed on the initial user path, place it in a separate module and dynamically import that module with Next.js's supported dynamic-import API and a layout-stable loading fallback. Do not dynamically split essential above-the-fold content or use undocumented/private dependency import paths.
- Never use memoization, code splitting, or caching to conceal a functional or layout bug.

## 3. CSS and hydration safety checks

Before validation, review the resulting render path for these failure modes:

- Skeleton and final content do not share geometry, especially margins and grid row height.
- A reservation is added only after hydration rather than being present in server/initial markup.
- Image sizing distorts the asset, overflows its card, or changes responsive behavior.
- Theme CSS selectors do not match the class/data attribute set by the early script.
- The early script can throw on unavailable storage or invalid stored values.
- A client component imports server-only code, a server component uses browser APIs directly, or the edit introduces hydration mismatch warnings.
- Existing `className`, `id`, and `data-testid` tokens were renamed, removed, or altered.

## 4. Validate the deliverable

1. Run the project’s available static checks and tests, using the scripts defined by the app rather than assuming tool names.
2. Run the production build (normally `npm run build`) from the app root. Treat nonzero exits, type errors, lint errors configured as build errors, and warnings indicating broken rendering as issues to inspect.
3. If the project supplies a runnable server and browser-capable checks, load the affected route and exercise existing UI flows, including any persisted theme and delayed/loading states. Confirm content does not visibly move when delayed sections, banners, product data, or media resolve.
4. Re-inspect the diff to verify all existing test selectors and functional contracts are retained and that no local build artifacts or generated dependencies were added to source control unnecessarily.

If an expected prerequisite (image dimensions, a running API, an available test command, or a supported dynamic-import target) is missing, do not fabricate it. Retain functionality, implement only the safe portion that can be justified by the source, and report the limitation with the exact prerequisite needed.

## Completion report

State which concrete root causes were found, which source files were changed, how each change prevents a specific first-paint or later layout shift, and the exact validation commands/results. Clearly distinguish checks that were not available from checks that passed.
