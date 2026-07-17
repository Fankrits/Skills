# SSR, ISR, route, and data-cache diagnosis

A current HTML shell can still render stale data. Separate HTTP caching from framework-managed route output, fetched-data caches, server-function caches, client router state, database replicas, and external APIs.

## Build the cache topology

Document every serving layer in order:

```text
browser navigation or client router
  -> service worker, if any
  -> CDN or reverse proxy
  -> framework route/output cache
  -> framework data/function cache
  -> application API or backend cache
  -> database, replica, or external source
```

For each layer record:

- cache key
- freshness lifetime
- invalidation trigger
- stale-serving behavior
- scope: browser, process, region, global, or external service
- evidence header or log
- owner and rollback path

Do not use the word "cache" without naming the layer.

## Distinguish stale output from stale data

### Stale route output

The server or edge returns an old rendered document or route payload. Evidence can include an old release marker, old generated timestamp, or unchanged route bytes despite fresh source data.

### Stale fetched data

The route output is newly rendered but embeds a cached API, database, or function result. Compare server logs and direct source queries.

### Stale client router state

A single-page navigation can retain route payloads or client state even when a full navigation is fresh. Reproduce with both in-app navigation and a new top-level navigation.

### Stale external edge object

The framework revalidated correctly, but a separate CDN still serves a stored response. Compare trusted origin and public edge responses.

## Next.js version-aware workflow

Next.js caching behavior differs by major version and by whether Cache Components are enabled. Inspect `package.json`, configuration, router, and deployment platform before applying advice.

### Identify the model

- Determine App Router versus Pages Router.
- Check the installed Next.js version.
- Check whether the current Cache Components model is enabled.
- Identify static generation, dynamic rendering, route handlers, server actions, and custom cache handlers.
- Identify Vercel-managed deployment versus self-hosting and any external CDN.

### Revalidate with documented primitives

Use the API supported by that version, such as path, tag, or cache-life primitives. A minimal example for versions supporting these APIs is:

```javascript
import { revalidatePath, revalidateTag } from 'next/cache';

revalidatePath('/catalog');
revalidateTag('catalog');
```

Do not assume the call invalidates:

- a separate third-party CDN
- a custom reverse proxy
- a browser's client router state
- an application-level Redis cache
- an unsupported self-hosted cache handler

Verify the next public response and the underlying data, not merely the function return.

### Self-hosted multi-instance deployments

Check the official self-hosting documentation for the installed version. Determine whether route and data caches are local, shared, or coordinated by a custom cache handler. Test two different instances or regions if possible.

Do not paste a hand-written Redis cache handler from a generic example. Cache-handler interfaces and stored value shapes are framework-version-specific and can corrupt revalidation semantics.

### External CDN in front of Next.js

Preserve framework-required cache keys and variation. In particular:

- do not strip query parameters used to distinguish route payloads
- do not collapse HTML and RSC/data responses
- preserve required `Vary` behavior
- do not convert personalized or dynamic responses into shared objects
- confirm whether the CDN honors or replaces Next.js cache directives

Use the current Next.js CDN-caching guide and the CDN's official cache-key documentation.

## Other SSR frameworks

### Nuxt and Nitro

Inspect route rules, cached handlers, storage drivers, Nitro preset, and hosting adapter. Verify whether invalidation is local or platform-coordinated. Do not treat all Vite output as static hosting.

### SvelteKit

Inspect the adapter, server `handle` hooks, route headers, prerender settings, and any platform cache. Distinguish browser navigation data from full document responses.

### Remix and React Router

Inspect headers returned by loaders and routes, adapter behavior, and client revalidation decisions. `shouldRevalidate` controls route-data behavior; it is not a CDN purge mechanism.

### Astro

Classify each route as prerendered, server-rendered, or hybrid. Use the current adapter's documented response and cache APIs. Do not add an undocumented cache export copied from another framework.

### Qwik City, TanStack Start, and SolidStart

These frameworks and adapters change quickly. Inspect the installed version and generated server output. Verify route cache APIs from official documentation and test the deployed adapter rather than relying on ecosystem resemblance.

## CDN and origin separation

A successful framework revalidation can coexist with a stale edge object.

Compare:

- public URL
- trusted origin URL or vendor-supported origin bypass
- a cache-busting diagnostic request only when the cache key behavior is understood
- vendor cache status and `Age`
- release marker and validators

Do not use a random query string as the production fix. It can merely create a new cache key and hide the stale object.

## Revalidation design

Choose a strategy based on the staleness budget:

### Event-driven invalidation

Use when content changes are known. Trigger framework revalidation and any required external cache purge from the same trusted event. Make retries idempotent.

### Time-based revalidation

Use when bounded staleness is acceptable. Set a TTL based on product requirements, not copied numbers.

### Dynamic or no-store rendering

Use when every request must reflect current or user-specific state. Confirm the performance and origin-load cost.

### Stale-while-revalidate

Use when a stale response is acceptable while a background refresh occurs. Document that the first request after expiry can still receive stale content.

### Stale-if-error

Use when availability is more important than absolute freshness during origin failure. Never apply it to authorization decisions, financial state, or other correctness-critical responses without explicit review.

## Cache-key review

For every shared cache, check whether the response varies by:

- host and scheme
- path and normalized query
- locale or content negotiation
- authentication or session
- tenant
- device or experiment assignment
- request headers
- route-data or framework markers

A missing key dimension can leak or mix content. An unnecessary key dimension can fragment the cache and make invalidation appear inconsistent.

## Verification after mutation

1. Change source data with a unique marker.
2. Trigger the documented revalidation event.
3. Record framework logs or cache-tag activity.
4. Request the trusted origin and public edge separately.
5. Test a fresh navigation and an existing client-router session.
6. Repeat across instances or regions when self-hosted.
7. Confirm personalized variants remain isolated.
8. Verify rollback or replay of the invalidation event is safe.

## Reject these claims without evidence

- "The CDN always knows when the framework revalidates."
- "Revalidation only affects one instance" on every platform.
- "A successful API response means every cache is fresh."
- "Setting `no-cache` on the browser response disables the framework's internal cache."
- "A vendor has a purge endpoint" without current official documentation.
- "One cache-busting query proves the original cache key is correct."
