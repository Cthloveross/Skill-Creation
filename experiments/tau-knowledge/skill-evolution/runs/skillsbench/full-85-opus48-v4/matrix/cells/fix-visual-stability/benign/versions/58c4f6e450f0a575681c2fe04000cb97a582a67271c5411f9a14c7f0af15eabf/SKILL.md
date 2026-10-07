---
name: fix-visual-stability-nextjs
description: >-
  Diagnose and fix visual instability (Cumulative Layout Shift and theme/font
  flicker) in a server-rendered React / Next.js App Router app. Use this when a
  Next.js app shows unexpected content jumps on load, a flash of the wrong theme
  before it corrects, invisible text while fonts load, or images/banners/side
  panels that push content down as they appear. The Skill scans the project
  source for the known root-cause anti-patterns and gives concrete, test-safe
  edits that establish correct visual state before first paint and reserve space
  for asynchronously inserted content.
---

# Fixing visual stability in a Next.js app

## When to use

The task gives a Next.js (App Router) e-commerce app (default at `/app`) whose
users see layout shifts and "a bad experience." You must find the root causes
using React/Next.js best practices and fix them, **without breaking existing
functionality and without changing any existing class names, `id`s, or
`data-testid` attributes** (automated tests rely on them).

## Root-cause taxonomy (what to look for)

Visual instability in this kind of app comes from a small, well-understood set
of causes. Fix the cause, not the symptom. See `references/fix-patterns.md` for
the exact code patterns.

1. **Theme flicker (FOUC) from a post-hydration effect.** A `ThemeProvider`
   that reads `localStorage` inside a `useEffect`/mount hook applies the theme
   *after* the first paint, so the user sees the default (light) theme flash
   before it corrects. Fix: apply the saved theme during HTML parsing via a
   **blocking inline script in `<head>`** (in `layout.tsx`, using
   `<script dangerouslySetInnerHTML={{ __html: ... }} />`) that reads
   `localStorage` and sets a class / `data-theme` attribute on the root element
   *before* React hydrates. Keep the existing provider working for runtime theme
   switches, but it must no longer be the first thing that applies the theme.

2. **Images without reserved space.** `<img>` tags without both `width` and
   `height` (or an equivalent CSS `aspect-ratio` + one dimension) lay out at
   zero size, then jump to natural size when they load. Fix: give every raw
   `<img>` explicit `width` and `height` attributes (or `aspect-ratio` plus a
   dimension). Do not remove or rename any existing attributes used by tests.

3. **Fonts causing FOIT.** An `@font-face` rule without `font-display: swap`
   defaults to block behavior (invisible text while loading). Fix: add
   `font-display: swap;` to each `@font-face` rule.

4. **Async content that renders nothing then appears.** Components (late
   banners, side panes, results bars, product lists/skeletons) that return
   `null` / render nothing while loading and then insert a block push
   everything below them down. Fix: always render a **same-sized placeholder**
   that occupies the final content's space (fixed min-height container,
   skeleton matching real dimensions, or reserved banner height) from the first
   render. A full-width banner inserted above content causes the largest shift,
   so reserving its height matters most.

5. **Skeletons that don't match final dimensions.** A `ProductSkeleton` must
   occupy exactly the same box (height, padding, margins, image area) as the
   real `ProductCard`, otherwise swapping real data in still shifts layout.

## Workflow

1. **Inspect first.** Read the real files under the app's `src/` (do not trust
   this document's examples as the instance's contents). Start with
   `src/app/layout.tsx`, `src/app/page.tsx`, `src/app/globals.css`,
   `src/components/ThemeProvider.tsx`, `ProductCard.tsx`, `ProductSkeleton.tsx`,
   `LateBanner.tsx`, `SidePane.tsx`, `ResultsBar.tsx`, `Banner.tsx`.

2. **Run the diagnostic scanner** to enumerate concrete occurrences of the
   anti-patterns above:

   ```bash
   echo '{"app_root": "/app"}' | python3 /app/environment/skills/current/scripts/diagnose.py
   ```

   (Use the actual skill directory from the environment; the default is
   `/app/environment/skills/current`.) The script prints a JSON report listing
   each detected issue with the file, a short reason, and the matching
   fix-pattern id. Treat it as a checklist, not as a complete oracle — confirm
   each finding by reading the file, and look for additional cases it may miss.

3. **Apply the fixes** from `references/fix-patterns.md`, editing the real
   files. Preserve every existing `className`, `id`, and `data-testid`
   verbatim — only add sizing/space-reservation, the inline theme script, and
   `font-display`. Prefer minimal, local edits over rewrites.

4. **Verify** (see below). Re-run the scanner; it should report no remaining
   issues (or only intentional, justified ones). Then build the app.

## Verification

After editing, confirm nothing is broken and the fixes are real:

```bash
cd /app
npm install            # if node_modules absent; network is allowed
npm run build          # must succeed with no type/compile errors
echo '{"app_root": "/app"}' | python3 <skill_dir>/scripts/diagnose.py
```

Checklist to confirm manually:
- `layout.tsx` `<head>` contains an inline `<script dangerouslySetInnerHTML>`
  that references `localStorage` and sets a class or `data-theme` on the root
  element (theme applied before hydration).
- Every raw `<img>` has both `width` and `height` (or `aspect-ratio` + a
  dimension).
- Every `@font-face` rule has `font-display: swap`.
- No layout-affecting component returns nothing/`null` while loading; each
  reserves its final space (placeholder, fixed min-height, or matching
  skeleton).
- All original `className` / `id` / `data-testid` strings are unchanged
  (`git diff` should show only additions of sizing/script/font-display, not
  renames). You can grep the diff: `cd /app && git diff | grep -E 'data-testid|className|id='` and confirm no test hooks were removed or renamed.

## Failure modes / limits

- If a file the scanner expects is absent, it reports it as `missing` rather
  than failing; inspect the real tree and adapt.
- The scanner uses text heuristics (regex), so it may both over- and
  under-report. Always confirm against the source.
- Do not fix flicker with a post-paint effect, do not remove performance or
  test instrumentation, and do not change public attributes to make a check
  pass. Reserve space; apply critical visual state before first paint.
