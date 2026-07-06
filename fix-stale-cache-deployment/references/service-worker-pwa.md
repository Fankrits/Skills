# Service Worker Update Pattern (PWA)

Only relevant if the project actually registers a service worker. This is the layer that handles the case where the browser has cached the app shell so aggressively (for offline support) that even correct HTTP headers can't reach it — the service worker sits in front of the network entirely.

## Why not just force-reload immediately

`self.skipWaiting()` + reload-on-`controllerchange` works, but firing it the instant a new worker installs can yank a user out of a half-filled form or a game mid-session. Production PWAs (Twitter/X, Pinterest, Spotify) instead let the new worker sit in a `waiting` state and surface a small, dismissible **"Update available"** banner, only reloading when the user opts in. Use the immediate-reload version only for things like internal admin dashboards where nobody's mid-task and interruption is harmless.

## Raw Service Worker (no Workbox)

**`public/sw.js`** — note there's no unconditional `skipWaiting()` call at install time; it waits for a message instead:

```javascript
const CACHE_NAME = 'app-cache-v1'; // bump this string on every deploy that changes cached assets

self.addEventListener('install', (event) => {
  // Pre-cache whatever this version needs, but do NOT skipWaiting() here —
  // that would activate immediately and defeat the point of the banner below.
});

self.addEventListener('message', (event) => {
  if (event.data?.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

self.addEventListener('activate', (event) => {
  // Clean up old cache versions
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
});
```

**Client-side registration + banner trigger** (e.g. `app/layout.tsx`, `main.js`, wherever the app registers the worker):

```javascript
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').then((registration) => {
    registration.addEventListener('updatefound', () => {
      const newWorker = registration.installing;
      newWorker?.addEventListener('statechange', () => {
        if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
          // A new version is ready and waiting — surface the UI banner here.
          showUpdateBanner(() => {
            newWorker.postMessage({ type: 'SKIP_WAITING' });
          });
        }
      });
    });
  });

  // Reload only after the new worker has actually taken control
  let refreshing = false;
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (refreshing) return;
    refreshing = true;
    window.location.reload();
  });
}
```

**Minimal banner UI** (React example — adapt markup/styling to the project's existing design system rather than pasting this verbatim):

```jsx
function UpdateBanner({ onUpdate }) {
  return (
    <div role="alert" style={{ position: 'fixed', bottom: 16, left: 16, right: 16 }}>
      <span>A new version is available.</span>
      <button onClick={onUpdate}>Update now</button>
    </div>
  );
}
```

Wire `showUpdateBanner` to mount this component with `onUpdate` calling the `postMessage` above.

## With Workbox (recommended over hand-rolled service workers)

Most production sites don't hand-write service worker logic — they use Google's Workbox, which handles precaching and update detection with far less code to get wrong.

**Build step** — `GenerateSW` (via `vite-plugin-pwa`, `next-pwa`, or `workbox-webpack-plugin` depending on bundler) auto-generates the service worker and precache manifest at build time. Configure it to **not** auto-skip-waiting:

```javascript
// example: vite-plugin-pwa config
VitePWA({
  registerType: 'prompt', // NOT 'autoUpdate' — 'prompt' is what enables the banner pattern
  workbox: {
    cleanupOutdatedCaches: true,
  },
})
```

**Client side**, using `workbox-window` for the clean event-based API instead of raw `serviceWorker.register`:

```javascript
import { Workbox } from 'workbox-window';

const wb = new Workbox('/sw.js');

wb.addEventListener('waiting', () => {
  showUpdateBanner(() => {
    wb.messageSkipWaiting();
  });
});

wb.addEventListener('controlling', () => {
  window.location.reload();
});

wb.register();
```

This does the same skipWaiting → controllerchange → reload sequence as the raw version, just with `workbox-window`'s events (`waiting`, `controlling`) doing the bookkeeping instead of manually tracking `registration.installing`/`statechange`.

## Testing this specific layer

Service worker updates are notoriously easy to "test" against a false positive because DevTools has its own override that masks the real behavior:

1. In Chrome DevTools → Application → Service Workers, **uncheck "Update on reload"** — that setting bypasses the exact lifecycle you're trying to verify.
2. Deploy version 1, load the site, close DevTools.
3. Deploy version 2 (bump the cache name / build hash).
4. Reopen the tab without hard-refreshing — the banner should appear within one poll cycle (browsers check for service worker updates roughly every 24h automatically, or immediately on navigation — trigger it manually via `registration.update()` during testing rather than waiting).
