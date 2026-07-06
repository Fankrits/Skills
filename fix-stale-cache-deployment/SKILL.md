---
name: fix-stale-cache-deployment
description: Use this skill whenever a user reports that their deployed website shows old/outdated content after a new deploy, users have to hard-refresh (Ctrl+Shift+R) to see updates, or they see errors like "ChunkLoadError", "Loading chunk X failed", "Failed to fetch dynamically imported module", "Unexpected token" html-parsing errors after deployment, or a blank white screen right after pushing a new version live. Also trigger for requests about service worker update handling, PWA "new version available" prompts, browser caching strategy for JS/CSS bundles, cache-control headers, or any mention of stale cache / cache busting / cache invalidation for a website. Works across any frontend framework (Next.js, Vite, Create React App, SvelteKit, Nuxt/Vue, vanilla) and any host (Vercel, Netlify, Cloudflare, Nginx, Apache, S3+CloudFront). Trigger this proactively even if the user just describes the symptom ("my users say the site looks broken until they clear their cache") without naming any of the technical terms above.
---

# Fixing Stale Browser Cache After Deployment

## What's actually going on

When you ship a new deploy, some users keep seeing the old version, or their app crashes with an error trying to load a JS/CSS file that no longer exists. This one bug wears three different names depending on who's describing it and at which layer:

- **Chunk Load Error** — the framework/bundler term (React, Webpack, Vite, Next.js). A dynamic `import()` tries to fetch a JS/CSS chunk by its old hashed filename, but that file was deleted from the server on the last deploy.
- **Stale Cache / Cache Incoherency** — the general term. The browser served a cached HTML page that still points at old asset filenames, while the server only has the new ones.
- **Service Worker "waiting" phase** — the PWA-specific version. A new service worker installed successfully but won't activate because an old tab is still open, so the app is stuck running old cached code.

All three come from the same root cause: **the HTML shell and the hashed assets it references went out of sync.** The fix is always a combination of the same three layers — you don't pick one, you stack them. Which layers matter most depends on the stack, which is why the first step is figuring out what you're working with.

## Step 1: Diagnose the project

Before touching anything, check what's actually in the project. Run these checks (skip any that don't apply):

```bash
# What framework/bundler?
cat package.json 2>/dev/null | grep -E '"(next|vite|react-scripts|svelte|nuxt|vue|@sveltejs)"'

# Is this a PWA / does it register a service worker?
grep -rl "serviceWorker.register\|navigator.serviceWorker" --include="*.{js,jsx,ts,tsx}" . 2>/dev/null | head -5
find . -iname "sw.js" -o -iname "service-worker.js" -o -iname "workbox-*.js" 2>/dev/null | grep -v node_modules | head -5

# Where is it hosted / deployed? Look for host-specific config
ls vercel.json netlify.toml _headers 2>/dev/null
find . -iname "nginx.conf" -o -iname ".htaccess" 2>/dev/null | grep -v node_modules
```

Use the results to decide which reference files apply:

| Finding | What it means | Read |
|---|---|---|
| Next.js, Vite, CRA/webpack, SvelteKit, Nuxt detected | Framework-specific header config + ChunkLoadError handling | `references/framework-specific.md` |
| Service worker file or `serviceWorker.register` found, or user says "PWA"/"installable app" | Need the update-banner + skipWaiting pattern | `references/service-worker-pwa.md` |
| Host config found, or user names a host (Vercel/Netlify/Nginx/Apache/Cloudflare/S3) | Server-level cache headers | `references/server-cache-headers.md` |
| None of the above found (plain static site, unknown host) | Default to the general HTML/asset header rule below, ask the user where it's hosted before writing host-specific config | `references/server-cache-headers.md` (general section) |

Don't guess the host — if it's not obvious from config files, ask the user rather than writing config for the wrong platform.

## Step 2: Apply the fixes, layered

Apply these in order. Layer A is close to universal; B and C depend on Step 1's findings.

### Layer A — Cache headers (do this regardless of framework)

This is the foundation everything else depends on. The rule industry sites follow:

- **HTML documents** (`index.html`, or any server-rendered page): `Cache-Control: no-cache` (or `no-store, must-revalidate`) — the browser must always ask the server "is this still current?" before using a cached copy. This is what lets the *next* deploy be discovered at all.
- **Hashed static assets** (`main.4341de68.js`, `styles.a1b2c3.css`): `Cache-Control: public, max-age=31536000, immutable` — safe to cache forever, because if the content changes, the filename changes too (that's what the hash is for). Never fix this layer by shortening the max-age on hashed assets — that just makes users re-download unchanged files. The fix belongs on the HTML layer, not here.

Exact syntax per host is in `references/server-cache-headers.md`.

### Layer B — Handle ChunkLoadError gracefully (any bundler with code-splitting)

Even with correct headers, a user with a tab open across a deploy can still hit a dead chunk URL mid-session. Catch it and recover instead of showing a crash:

```javascript
// Wrap dynamic imports / route-level lazy loading
import(/* webpackChunkName: "..." */ './SomeComponent')
  .catch((err) => {
    if (/Loading chunk|Failed to fetch dynamically imported module/i.test(err.message)) {
      // The chunk is gone because a new version was deployed underneath us.
      // A hard navigation re-fetches the current index.html and its correct chunk map.
      window.location.reload();
    } else {
      throw err; // real error, don't swallow it
    }
  });
```

Framework-specific placement (React error boundaries, Next.js `error.tsx`, Vite's `vite:preloadError` event, etc.) is in `references/framework-specific.md`.

### Layer C — Service worker update pattern (only if a service worker is involved)

If Step 1 found a service worker, the fix needs one more piece: deciding *when* to reload. Force-reloading the instant a new service worker activates will yank the page out from under someone mid-form-fill, so the standard approach used by production PWAs is the **update banner**, not an immediate reload:

1. New service worker installs in the background and sits in the `waiting` state.
2. The client detects `registration.waiting` and shows a small "Update available" banner.
3. User clicks the banner → app sends `{type: 'SKIP_WAITING'}` to the waiting worker → it calls `self.skipWaiting()`.
4. `controllerchange` fires → *then* `window.location.reload()`.

Full code for both raw service workers and Workbox (`workbox-window`) is in `references/service-worker-pwa.md`, including why silent auto-reload is discouraged and when it's actually fine to skip the banner (e.g., an internal admin tool where interrupting nobody matters).

## Step 3: Verify the fix actually works

Don't consider this done until you've confirmed it end-to-end:

1. Deploy the change, then simulate a *second* deploy (bump a version string, change some visible text, redeploy).
2. With the site already open in a tab from before the second deploy, confirm:
   - Static JS/CSS requests in the Network tab show `cache-control: public, max-age=31536000, immutable` and a `200` (or `304` only for the HTML) — not a full re-download of unchanged hashed files.
   - The HTML document request shows `cache-control: no-cache` (or equivalent) and actually re-validates against the server.
   - If Layer C applies: the update banner appears without you refreshing manually, and clicking it updates the page without an error.
   - If you force a ChunkLoadError (e.g., by deleting an old chunk file from the deployed `_next/static` or `assets` folder before the fix), confirm the app recovers via reload instead of showing a blank screen.
3. If the user has real analytics/error tracking (Sentry, etc.), suggest they watch ChunkLoadError rates for a day or two after shipping this — that's the real confirmation signal.

## Notes

- If the project uses a CDN in front of the origin (Cloudflare, CloudFront, Fastly), the CDN's own cache rules can override or duplicate the origin's headers — check both layers, they need to agree. This is covered in `references/server-cache-headers.md`.
- Don't reach for a service-worker-based fix (Layer C) if the project doesn't already have one and isn't a PWA — that's adding a large chunk of complexity to solve a problem Layers A+B already solve for regular websites. Only bring in Layer C when Step 1 actually found a service worker or the user explicitly wants offline/installable support.
