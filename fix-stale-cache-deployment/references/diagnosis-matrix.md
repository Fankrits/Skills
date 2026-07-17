# Cache-coherence diagnosis matrix

Use this file after collecting repository and live-response evidence. Do not diagnose from a single header or a user report alone.

## Evidence collection order

1. Record the current release identifier from the origin and the client.
2. Capture the entry document response and one referenced asset.
3. Reproduce in a fresh browser profile and an already-open tab.
4. Check service-worker control and Cache Storage.
5. Compare edge and origin responses when a CDN or reverse proxy exists.
6. Trace framework or data-cache invalidation only after the HTTP and service-worker layers are understood.

## Symptom matrix

| Symptom | Confirm with | Likely mechanism | Avoid |
|---|---|---|---|
| Normal refresh stays old; hard refresh updates | document headers, `Age`, service-worker controller | reusable HTML, edge cache, or worker interception | telling users to clear cache as the final fix |
| Fresh navigation is correct; an old tab later throws a chunk error | failed chunk URL, release IDs, artifact inventory | old runtime requests a deleted release asset | infinite automatic reloads |
| Fresh incognito works; normal profile is stale | Application panel, worker registrations, Cache Storage | waiting or active service worker, browser cache | changing CDN rules before checking the worker |
| HTML release marker is old at the edge but current at origin | origin-bypass request, CDN cache headers | stale edge object or wrong cache key | purging all assets when only entry documents are stale |
| HTML is current but API or page data is old | route/API headers, framework logs, data-cache tags | ISR/SSR/data cache or API cache | shortening all static-asset TTLs |
| Only one geography is stale | multi-region probes, POP headers, `Age` | propagation, tiered cache, or regional origin inconsistency | assuming a browser-only issue |
| Only authenticated users are stale | response variation, cookies, auth headers | client router cache, private response reuse, or incorrect shared caching | making personalized responses public-cacheable |
| One user receives another user's content | cache key and response headers | shared-cache isolation failure | continuing normal rollout; treat as security incident |
| A deploy fixes itself after the old tab closes | old asset availability and open-tab duration | release overlap shorter than client lifetime | deleting previous hashed assets immediately |
| App reloads repeatedly after deploy | session storage, error boundary, worker lifecycle | unguarded recovery or persistent bad entry point | another unconditional `location.reload()` |
| Rollback causes missing chunks | artifact inventory for both releases | forward-release assets removed during rollback | invalidating only HTML while deleting assets |
| PWA update appears only after many hours | worker script policy, update checks, waiting state | delayed worker update discovery or no prompt | marking the worker script immutable |
| Revalidation endpoint succeeds but users stay stale | external CDN, multiple instances, route cache | invalidation did not reach every serving layer | inventing a vendor purge endpoint |

## Layer isolation tests

### Browser HTTP cache

- Compare normal navigation with a fresh profile.
- Inspect whether the document is served from memory or disk cache.
- Repeat with a conditional request using `ETag` or `Last-Modified`.
- Do not use DevTools "Disable cache" as the only proof; it changes the behavior under test.

### Open-tab runtime state

- Keep release A open while deploying release B.
- Trigger a lazy route or dynamic import that was not loaded before the deploy.
- Check whether release-A assets still exist.
- Verify recovery executes once and preserves or clearly discards transient user state.

### Service worker

- Check `navigator.serviceWorker.controller` and the registration's `installing`, `waiting`, and `active` workers.
- Inspect Cache Storage names and contents.
- Confirm whether navigation and asset requests are intercepted.
- Test with "Update on reload" disabled in DevTools.

### CDN or reverse proxy

- Compare the public edge with a trusted origin path or vendor-supported bypass.
- Record `Age`, `Via`, `X-Cache`, `CF-Cache-Status`, `X-Vercel-Cache`, and equivalent headers.
- Check the cache key: host, path, query, method, cookies, request headers, device/language variants, and RSC/data markers where applicable.
- Verify that origin and edge do not emit conflicting cache directives.

### Framework and data caches

- Identify the framework version and enabled caching model.
- Distinguish route output, fetched data, server-function results, client router state, and external API caches.
- Trigger the supported revalidation primitive and observe the serving layer, not merely the endpoint's return code.
- Confirm multi-instance behavior for self-hosted deployments.

### Artifact store

- List entry documents and all referenced assets for release A and release B.
- Confirm deploy order: assets first, entry documents last.
- Confirm prior fingerprinted assets remain available for the intended overlap and rollback window.
- Verify a cleanup job cannot delete assets still referenced by supported releases.

## Confidence labels

Use one label in the diagnosis:

- **Confirmed:** direct evidence identifies the stale layer and mechanism.
- **Probable:** evidence strongly favors one layer, but origin or platform evidence is missing.
- **Possible:** multiple layers remain plausible; provide the next discriminating test.

Never label a diagnosis confirmed solely because a hard refresh changed the result.
