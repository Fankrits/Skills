# Framework and bundler implementation guide

Use this file only after detecting the installed package version and deployment adapter. Framework APIs and defaults change; verify current official documentation listed in `official-sources.md` before editing.

## Universal implementation principles

1. Preserve generated content hashes and public base paths.
2. Keep previous fingerprinted assets available during release overlap.
3. Fix the entry-document policy before adding a reload handler.
4. Catch only known asset-version failures. Do not swallow unrelated exceptions.
5. Reload at most once, then render a stable update message with a manual retry.
6. Record the client release, current server release, failed asset URL, and recovery result.
7. Avoid changing framework-managed headers unless live evidence proves they are wrong.

## One-shot recovery guard

Use a guard around any framework-specific reload. Adapt storage and UI to the project:

```javascript
const RECOVERY_KEY = 'asset-version-recovery';
const RECOVERY_WINDOW_MS = 60_000;

function recoverFromStaleAssets(error) {
  const message = String(error?.message ?? error ?? '');
  const isAssetVersionFailure =
    /ChunkLoadError|Loading chunk|Failed to fetch dynamically imported module|Importing a module script failed/i.test(message);

  if (!isAssetVersionFailure) return false;

  try {
    const previous = Number(sessionStorage.getItem(RECOVERY_KEY) || 0);
    const now = Date.now();
    if (now - previous < RECOVERY_WINDOW_MS) {
      // Do not reload again. Render a stable "new version available" state
      // and report the repeated failure to telemetry.
      return true;
    }
    sessionStorage.setItem(RECOVERY_KEY, String(now));
  } catch {
    // Storage may be unavailable. Use an in-memory guard in the actual app.
  }

  window.location.reload();
  return true;
}
```

A time window is only a fallback. Prefer a release-specific key such as `asset-recovery:<build-id>` when a build ID is available.

## Vite

Vite emits `vite:preloadError` when a dynamic import cannot be loaded. Register the handler before mounting the app:

```javascript
window.addEventListener('vite:preloadError', (event) => {
  event.preventDefault();
  recoverFromStaleAssets(event.payload);
});
```

Then verify:

- generated asset names still contain content hashes
- `base` points to the deployed path
- old release assets are not removed before open clients can finish
- entry HTML validates promptly

Do not wrap every dynamic import manually when the Vite event covers the failure mode.

## Next.js

Inspect the installed major version, router, deployment target, and whether the project uses the current Cache Components model or the previous caching model.

### Asset and document policy

- Preserve Next.js-managed caching for `/_next/static/*` on supported platforms.
- Do not add a broad `next.config` header rule that accidentally changes RSC, route-data, API, image-optimization, or personalized responses.
- When placing an external CDN in front of Next.js, preserve required query parameters and `Vary` behavior. Never collapse HTML and RSC/data responses into one cache key.
- On self-hosted multi-instance deployments, verify cache coordination and deployment IDs using the official self-hosting documentation for that version.

### Chunk recovery

Use the highest error boundary that can reliably catch the installed version's client navigation or lazy-loading failure. Pair it with the one-shot guard. Do not assume `app/error.tsx`, `global-error.tsx`, Pages Router events, or a custom boundary catch failures that occur before the relevant runtime initializes; test the actual old-tab scenario.

### Revalidation

Use only the documented APIs for the installed version, such as path, tag, or cache-life primitives. Verify the observable public response after invalidation. An endpoint returning success is not proof that an external CDN or every self-hosted instance is fresh.

## React with Webpack or Create React App

- Confirm production output uses `[contenthash]` or the framework's equivalent.
- Confirm `publicPath` or asset prefix matches the deployed base URL.
- Wrap route-level lazy loading in an error boundary that calls the one-shot recovery helper only for chunk failures.
- Keep the fallback UI stable when recovery has already been attempted.
- Avoid throwing from `getDerivedStateFromError` as a generic propagation mechanism; use a reviewed boundary structure that distinguishes recoverable chunk errors from application errors.

Create React App is maintenance-mode legacy software in many estates. Do not modernize the entire build system during a cache incident unless the user explicitly asks.

## SvelteKit

- Detect the adapter and host first; header behavior usually belongs to the adapter, host, or server response.
- Confirm the current SvelteKit client error hook and navigation behavior for the installed version.
- Because SvelteKit uses Vite, test whether `vite:preloadError` reaches the production client before relying on it. Do not assume every adapter preserves identical behavior.
- Keep service-worker handling separate from chunk recovery when the project uses `src/service-worker.*`.

## Nuxt and Vue Router

- Detect Nuxt version, Nitro preset, and deployment adapter.
- Inspect route rules and Nitro cache settings before adding server headers.
- For Vite-powered builds, test `vite:preloadError`; for router-level lazy failures, use the documented router error hook for the installed version.
- Do not apply a static-SPA HTML policy to server-rendered routes without checking Nitro and CDN behavior.

## Remix and React Router

- Separate document requests, loader/data responses, and browser navigation state.
- Define cache policy in documented response headers or route APIs, then verify what the hosting adapter emits.
- Use route error boundaries for recoverable lazy-module failures only after confirming the error reaches them.
- Do not confuse `shouldRevalidate` route-data decisions with HTTP cache invalidation or missing build assets.

## Astro

- Determine whether the route is prerendered, server-rendered, or hybrid and which adapter serves it.
- Set headers through the documented response or adapter mechanism for the installed version.
- Treat generated Vite assets as immutable only when names are fingerprinted.
- Test the Vite preload-error event in the final adapter output before adding it globally.
- Do not use an undocumented `export const cache` shape merely because another framework supports one.

## Qwik City

- Confirm the installed Qwik and Qwik City versions and adapter.
- Use documented cache APIs from route loaders or server handlers.
- Test resumability and lazy symbol loading across a two-release deploy; missing old symbols can resemble generic chunk failures.
- Avoid inventing React-style error-boundary APIs for Qwik.

## TanStack Start and SolidStart

- Confirm the current package name, router version, server runtime, and adapter; these ecosystems evolve quickly.
- Inspect generated asset naming and server-response APIs rather than copying examples from a different release.
- Test `vite:preloadError` in the production build if Vite is present.
- Use the framework's documented error component or router hook, wrapped with the one-shot guard.

## Framework-neutral checks

Run these before and after the patch:

```bash
python3 <skill-dir>/scripts/detect_cache_stack.py --root .
python3 <skill-dir>/scripts/audit_cache_headers.py https://example.com --discover-assets --revalidate
```

Inspect the production build manifest when available. Confirm every entry document references assets that exist and every retained release manifest remains internally consistent.

## Reject these tempting fixes

- shortening the TTL of correctly fingerprinted assets to hide stale HTML
- appending a random query string to every asset instead of fixing build identity
- unconditional `window.location.reload()` in a global error handler
- adding a service worker to a non-PWA solely to solve ordinary HTTP caching
- overriding every framework response with `Cache-Control: no-cache`
- deleting `.next`, build, or CDN caches in production without locating the stale layer
- treating a successful local development refresh as deployment verification
