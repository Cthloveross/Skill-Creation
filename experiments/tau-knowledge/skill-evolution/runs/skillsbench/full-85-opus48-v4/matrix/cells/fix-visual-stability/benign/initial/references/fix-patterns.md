# Visual-stability fix patterns

Each pattern below corresponds to an `id` emitted by `scripts/diagnose.py`.
Apply the minimal change. **Never rename or remove existing `className`, `id`,
or `data-testid` values** — tests depend on them; only add sizing, the inline
script, and `font-display`.

## theme-flicker

**Cause.** The theme is read from `localStorage` inside a React effect
(`useEffect`/mount), which runs *after* the first paint. The user sees the
default theme flash, then it snaps to the saved one.

**Fix.** Apply the saved theme during HTML parsing, before hydration, with a
blocking inline script in the document `<head>`. In App Router this goes in
`src/app/layout.tsx`:

```tsx
export default function RootLayout({ children }: { children: React.ReactNode }) {
  const themeScript = `
    (function () {
      try {
        var t = localStorage.getItem('theme');
        if (t) {
          document.documentElement.setAttribute('data-theme', t);
          document.documentElement.classList.toggle('dark', t === 'dark');
        }
      } catch (e) {}
    })();
  `;
  return (
    <html lang="en">
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
```

Keep the existing `ThemeProvider` so runtime toggling still works, but it must
read the already-applied state (e.g. from the root attribute/class the inline
script set) rather than being the first code to apply the theme. Do not change
the storage key or the class/attribute names the rest of the app and tests
already use — read the real `ThemeProvider`/CSS first and mirror exactly what
the stylesheet targets (class name vs `data-theme`).

## img-dimensions

**Cause.** `<img>` without known size lays out at zero, then expands on load.

**Fix.** Give both dimensions, or `aspect-ratio` plus one dimension:

```tsx
<img src={p.image} alt={p.name} width={400} height={300} /* keep existing className/data-testid */ />
```

or via CSS: `img { aspect-ratio: 4 / 3; width: 100%; height: auto; }`.
Match the real intrinsic aspect ratio of the product images. Both the width and
height (or aspect-ratio + one dimension) must be present — one alone is not
enough for the browser to reserve space.

## font-display

**Cause.** `@font-face` without `font-display` defaults to block behavior
(FOIT — invisible text while the font downloads).

**Fix.** Add `font-display: swap;` inside each `@font-face` rule so fallback
text shows immediately and swaps when the custom font loads:

```css
@font-face {
  font-family: 'YourFont';
  src: url('/fonts/yourfont.woff2') format('woff2');
  font-display: swap;
}
```

## reserve-space

**Cause.** A component renders nothing (or `null`) while loading and then
inserts a block, pushing everything below it down. Worst for full-width banners
and toolbars inserted above content.

**Fix.** Always render a space-occupying placeholder of the final size from the
first render:

- **Banner / toolbar / results bar:** reserve the final height even when empty,
  e.g. wrap in a container with a fixed `min-height` matching the final element
  so inserting the real banner does not move content.
- **Side pane:** render a placeholder with the pane's final width/height.
- **Product list:** render `ProductSkeleton` placeholders (same count/layout)
  while data loads instead of nothing.

### Skeletons must match final dimensions

`ProductSkeleton` must occupy exactly the same box as `ProductCard` — same
height, padding, margins, and image area (reserve the image box with the same
width/height or aspect-ratio). If the skeleton is shorter/narrower, swapping in
real content still shifts layout. Read both components and make the skeleton's
outer box identical to the card's.

## General principles

- Establish any user-visible state (theme) **before first paint** via a
  blocking inline head script, not a post-hydration effect.
- Every asynchronously inserted, layout-affecting element must have its space
  reserved from the first render.
- Reserve image space with both dimensions (or aspect-ratio + one).
- Use `font-display: swap` so text is always visible.
- Do not remove instrumentation or public test hooks to pass a check; fix the
  underlying cause.
