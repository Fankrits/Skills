# ISR / SSR Cache Layers

When your app renders pages on the server (SSR) or uses Incremental Static Regeneration (ISR), there's a cache layer *between* your code and the CDN that can serve stale content independently of browser caching. This layer is often the actual root cause when "the deploy went live but users still see old content" even after confirming browser cache headers are correct.

## Table of contents
- [ISR on-demand revalidation](#isr-on-demand-revalidation)
- [CDN propagation gotchas](#cdn-propagation-gotchas)
- [Stale-while-revalidate / stale-if-error](#stale-while-revalidate--stale-if-error)
- [ETag / Last-Modified revalidation](#etag--last-modified-revalidation)
- [Framework-specific ISR/SSR patterns](#framework-specific-isrssr-patterns)

---

## ISR on-demand revalidation

ISR pages serve stale content while regenerating in the background. On-demand revalidation (via `revalidateTag` / `revalidatePath` in Next.js) lets you invalidate specific pages when data changes — but there are two critical gotchas:

### Gotcha 1: Multi-instance invalidation

On-demand revalidation only invalidates the **server-side cache instance that receives the call**. In a multi-instance deployment (e.g., multiple serverless functions, multiple containers), other instances keep serving stale content until their time-based revalidation expires.

**Fix:** Use a shared cache handler that stores ISR cache in external storage (Redis, Vercel KV, Upstash) instead of per-instance memory:

```javascript
// next.config.js
module.exports = {
  cacheHandler: require.resolve('./cache-handler.js'),
  cacheMaxMemorySize: 0, // disable in-memory cache, use external
};
```

```javascript
// cache-handler.js
const Redis = require('ioredis');
const redis = new Redis(process.env.REDIS_URL);

module.exports = class CacheHandler {
  async get(key) {
    const data = await redis.get(key);
    return data ? JSON.parse(data) : null;
  }
  async set(key, data, ctx) {
    const ttl = ctx.revalidate || 3600;
    await redis.set(key, JSON.stringify(data), 'EX', ttl);
  }
  async revalidateTag(tag) {
    // Find and invalidate all keys with this tag
    const keys = await redis.keys(`tag:${tag}:*`);
    if (keys.length) await redis.del(...keys);
  }
};
```

### Gotcha 2: CDN doesn't know about on-demand revalidation

`revalidatePath('/blog/post-1')` invalidates Next.js's server cache, but **the CDN's edge cache is NOT invalidated**. The CDN will keep serving its cached copy until `s-maxage` expires.

**Fix options (pick one):**

1. **Short `s-maxage`** — Set `s-maxage` low enough that staleness is tolerable (e.g., 60s), rely on time-based revalidation for CDN freshness.
2. **Purge CDN after revalidation** — After calling `revalidatePath`, also purge the CDN:
   ```javascript
   // After revalidation
   await fetch(`https://api.vercel.com/v1/artifacts/${path}/purge`, {
     method: 'DELETE',
     headers: { Authorization: `Bearer ${process.env.VERCEL_TOKEN}` },
   });
   ```
3. **Use `no-store` for truly dynamic pages** — If content must always be fresh, skip ISR entirely and use `export const dynamic = 'force-dynamic'` to disable caching.

---

## CDN propagation gotchas

### Vary header and CDN correctness

CDNs cache based on the full request including `Vary` headers. If a CDN ignores `Vary` on custom headers, it can serve the wrong response.

Next.js uses the `_rsc` search parameter as a cache key because some CDNs ignore `Vary: RSC`. This means:
- RSC payload requests and HTML requests get different cache keys
- But if a CDN strips query parameters from cache keys, RSC and HTML responses can collide

**Fix:** Ensure your CDN respects `Vary` headers, or set `Cache-Control: private` on RSC responses so CDNs skip them entirely.

### CDN cache vs. origin cache separation

Most CDN + origin setups have two independent caches:
1. **Origin cache** (e.g., Next.js ISR cache, Vercel Edge Cache)
2. **CDN edge cache** (e.g., CloudFront, Cloudflare edge)

On-demand revalidation hits origin cache only. CDN edge cache has its own TTL. This double-caching is the most common reason "revalidation works in staging but not production."

---

## Stale-while-revalidate / stale-if-error

These `Cache-Control` extensions are powerful for ISR and CDN edge caching:

### stale-while-revalidate

```http
Cache-Control: public, max-age=60, stale-while-revalidate=86400
```

Tells the CDN/browser: "Serve the cached copy immediately, but fetch a fresh copy in the background." Users never wait for regeneration — they get the stale version now and the fresh version on their next request.

**When to use:** ISR pages, API routes with acceptable staleness, any page where "slightly old is better than slow."

### stale-if-error

```http
Cache-Control: public, max-age=60, stale-if-error=86400
```

If the origin is down or returns an error, serve the last cached copy instead of an error page. Critical for resilience during deploys when the origin may be temporarily unreachable.

**When to use:** Public-facing pages, API health endpoints, any page where an error page is worse than slightly stale content.

### Combining both

```http
Cache-Control: public, max-age=60, stale-while-revalidate=3600, stale-if-error=86400
```

This pattern means: serve cached for 60s, background-refresh up to 1h, serve stale for up to 24h if origin fails.

---

## ETag / Last-Modified revalidation

When a response has an `ETag` or `Last-Modified` header, the browser can validate with the server using conditional requests:

- `ETag` → `If-None-Match: "abc123"` → server returns `304 Not Modified` if unchanged
- `Last-Modified` → `If-Modified-Since: Thu, 01 Jan 2024 00:00:00 GMT` → same

This interacts with `Cache-Control: no-cache` on HTML documents:
1. Browser requests HTML → gets response with `ETag` + `Cache-Control: no-cache`
2. On next visit, browser sends `If-None-Match` with the ETag
3. Server returns `304` (no body, no re-download) or `200` with new content
4. This is how `no-cache` differs from `no-store` — `no-cache` allows revalidation, `no-store` never caches

**Important:** `Cache-Control: no-cache` on HTML is correct for deployments — it means "always check with the server." The 304 response is fast (no body transfer) and still lets the server signal "new version deployed, here's the updated HTML."

---

## Framework-specific ISR/SSR patterns

### Next.js (App Router)

```javascript
// Force dynamic rendering — never cache this route
export const dynamic = 'force-dynamic';

// ISR with time-based revalidation
export const revalidate = 60; // seconds

// ISR with on-demand revalidation
import { revalidateTag, revalidatePath } from 'next/cache';

// In a Server Action or Route Handler:
revalidateTag('blog-posts');
revalidatePath('/blog');
```

### Remix / React Router v7

Remix handles caching through HTTP headers directly:

```javascript
// app/routes/blog.$slug.tsx
export function loader({ request }) {
  // Remix's built-in caching via Cache-Control headers
  const headers = new Headers();
  headers.set('Cache-Control', 'public, max-age=60, stale-while-revalidate=3600');
  return json(data, { headers });
}

// Route-level header config
export function headers({ loaderHeaders }) {
  return {
    'Cache-Control': loaderHeaders.get('Cache-Control'),
  };
}
```

React Router v7 adds `shouldRevalidate` for fine-grained control:

```javascript
export function shouldRevalidate({ currentParams, nextParams, currentUrl, nextUrl }) {
  // Only revalidate if the slug changed
  return currentParams.slug !== nextParams.slug;
}
```

### Astro

Astro supports per-route caching when using SSR adapters:

```astro
---
// src/pages/blog/[slug].astro
export const prerender = false; // SSR mode

// Cache for 60 seconds, serve stale for 1 hour
export const cache = {
  maxAge: 60,
  staleWhileRevalidate: 3600,
};
---
```

Astro also integrates with first-party cache providers (Cloudflare, Netlify, Vercel) when using their adapters.

### Qwik City

Qwik City provides a `cacheControl` API from route loaders:

```typescript
// src/routes/blog/[slug]/index.tsx
import { routeLoader$ } from '@builder.io/qwik-city';

export const useLoader = routeLoader$(async ({ cache, headers }) => {
  cache({
    maxAge: 60,
    staleWhileRevalidate: 3600,
    // Qwik supports nested layout overrides
  });
  return fetchData();
});
```
