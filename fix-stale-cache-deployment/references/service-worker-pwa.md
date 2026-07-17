# Service-worker and PWA update handling

Use this reference only when a service worker is registered or generated. A service worker can intercept navigation and asset requests before normal HTTP caching, so verify its state rather than guessing.

## Diagnose the lifecycle first

In the affected browser, inspect:

```javascript
const registration = await navigator.serviceWorker.getRegistration();
console.table({
  controller: navigator.serviceWorker.controller?.scriptURL,
  installing: registration?.installing?.scriptURL,
  waiting: registration?.waiting?.scriptURL,
  active: registration?.active?.scriptURL,
  updateViaCache: registration?.updateViaCache,
  scope: registration?.scope,
});
```

Also inspect Cache Storage and confirm which requests the worker handles. A worker file existing in the repository does not prove it controls the page.

## Choose an update policy deliberately

### Prompted update

Prefer a visible update prompt for applications with forms, editors, media, games, or other transient state. Let the new worker wait until the user accepts, preserve draft state, activate it, then reload once.

### Forced update

Use immediate activation only when interruption is explicitly acceptable or a mandatory security update outweighs state loss. Document the reason and ensure the app persists critical state first.

### Background continuation

For long-running applications, consider allowing the current tab to continue on its existing release while new navigations use the new worker. This requires retained assets and compatibility across releases.

## Raw service-worker pattern

### Worker

Use an application-specific cache prefix. Never delete caches owned by other applications on the same origin.

```javascript
const CACHE_PREFIX = 'my-app-';
const CACHE_NAME = `${CACHE_PREFIX}release-<build-id>`;

self.addEventListener('message', (event) => {
  if (event.data?.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(
      keys
        .filter((key) => key.startsWith(CACHE_PREFIX) && key !== CACHE_NAME)
        .map((key) => caches.delete(key))
    );
    await self.clients.claim();
  })());
});
```

Do not call `skipWaiting()` unconditionally during install when using a prompted update flow.

### Client registration and existing-waiting handling

Handle both a newly installed worker and one that was already waiting before the current page registered listeners:

```javascript
let refreshing = false;

function offerUpdate(registration) {
  if (!registration.waiting) return;

  showUpdateBanner(async () => {
    await persistTransientState();
    registration.waiting?.postMessage({ type: 'SKIP_WAITING' });
  });
}

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (refreshing) return;
    refreshing = true;
    window.location.reload();
  });

  navigator.serviceWorker.register('/sw.js', {
    // Use only when bypassing HTTP cache for imported worker scripts is intentional.
    updateViaCache: 'none',
  }).then((registration) => {
    if (registration.waiting && navigator.serviceWorker.controller) {
      offerUpdate(registration);
    }

    registration.addEventListener('updatefound', () => {
      const worker = registration.installing;
      worker?.addEventListener('statechange', () => {
        if (worker.state === 'installed' && navigator.serviceWorker.controller) {
          offerUpdate(registration);
        }
      });
    });
  });
}
```

Adapt `showUpdateBanner` and `persistTransientState` to the product. The update UI should be keyboard accessible, announced politely to assistive technology, and clear about whether unsaved work will be preserved.

## Workbox pattern

Use the API for the installed Workbox version. The official `workbox-window` flow listens for a waiting worker, prompts the user, calls `messageSkipWaiting()`, and reloads on `controlling`:

```javascript
import { Workbox } from 'workbox-window';

const wb = new Workbox('/sw.js');

wb.addEventListener('waiting', async (event) => {
  const accepted = await promptForUpdate({
    wasWaitingBeforeRegister: event.wasWaitingBeforeRegister,
  });
  if (!accepted) return;

  await persistTransientState();
  wb.messageSkipWaiting();
});

wb.addEventListener('controlling', () => {
  window.location.reload();
});

wb.register();
```

When using a plugin such as `vite-plugin-pwa`, Serwist, or a framework wrapper, verify its current registration mode and generated worker behavior. Do not mix an auto-update mode with a custom prompt and assume both lifecycle owners will cooperate.

## Update discovery

Browsers perform service-worker update checks, but timing is not a product-level freshness guarantee. Trigger a bounded check on meaningful lifecycle events when needed:

```javascript
const registration = await navigator.serviceWorker.getRegistration();
await registration?.update();
```

Reasonable triggers include app startup after a long absence or returning to a visible tab. Avoid aggressive polling that wastes bandwidth or creates update races.

Serve the worker script with an update-oriented HTTP policy. Do not mark `/sw.js` or imported worker scripts immutable unless their URLs are fingerprinted and the registration URL changes with each release.

## Multiple tabs

Activation affects every controlled client on the scope. Coordinate the prompt across tabs when duplicate banners or simultaneous state persistence would be harmful.

Possible tools:

- `BroadcastChannel`
- `clients.matchAll()` plus `postMessage`
- a shared local-storage lease with expiration

Test at least two open tabs. Confirm only one activation decision is needed and every tab reaches a valid state.

## Scope rules

Service-worker scope is derived from the script URL unless restricted during registration or by `Service-Worker-Allowed`.

- `/sw.js` commonly controls `/` and therefore has broad reach.
- `/app/sw.js` commonly controls `/app/` and is narrower, not broader.
- Choose the smallest scope that covers the offline or update behavior you need.
- Never expand scope to API, admin, or unrelated applications without reviewing interception and cache rules.

## Cache strategy safety

- Cache only `GET` requests.
- Do not cache authenticated API responses by default.
- Avoid cache-first for stable-name HTML or API data unless staleness is explicitly bounded.
- Match runtime routes precisely; a broad `caches.match(request)` can return a response from the wrong cache or release.
- Keep navigation fallback behavior distinct from asset caching.
- Preserve content type and status when returning cached responses.
- Version cache names and delete only owned caches.

## Testing procedure

1. Disable DevTools "Update on reload".
2. Deploy release A and load the PWA in two tabs.
3. Enter unsaved state in one tab.
4. Deploy release B with a changed worker and changed precache manifest.
5. Trigger `registration.update()` for deterministic testing.
6. Confirm the waiting state and update prompt.
7. Accept the update and verify state persistence, activation, one reload per tab, and release-B assets.
8. Decline or defer the prompt and verify release-A assets remain available.
9. Test offline startup for both the active and updated release.
10. Confirm no user-specific API response appears in Cache Storage.

## Common failure modes

- registering listeners after a worker is already waiting and never checking `registration.waiting`
- posting `SKIP_WAITING` to the wrong worker instance
- reloading before `controllerchange` or `controlling`
- deleting all origin caches rather than the application's own prefix
- auto-updating while a form is unsaved
- serving the worker script with a year-long fresh lifetime
- testing with a DevTools setting that forces updates and masks production behavior
- using a broad worker scope that intercepts unrelated routes
