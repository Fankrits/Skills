# Monitoring & Observability

After deploying cache fixes, you need to confirm they're working in production — not just in DevTools. This covers how to measure cache effectiveness, track chunk load errors, and monitor real user impact.

## Table of contents
- [Real User Monitoring (RUM) for cache hits](#real-user-monitoring-rum-for-cache-hits)
- [Core Web Vitals and caching](#core-web-vitals-and-caching)
- [Chunk load error tracking](#chunk-load-error-tracking)
- [Cache warming monitoring](#cache-warming-monitoring)

---

## Real User Monitoring (RUM) for cache hits

### Browser-based cache detection

Use the `PerformanceObserver` API to detect whether resources were served from cache:

```javascript
// Detect cache hits vs. network fetches
const observer = new PerformanceObserver((list) => {
  for (const entry of list.getEntries()) {
    if (entry.initiatorType === 'script' || entry.initiatorType === 'link') {
      const fromCache = entry.transferSize === 0 && entry.decodedBodySize > 0;
      // transferSize === 0 means served from cache (304 or memory cache)
      // decodedBodySize > 0 means there was content (not a 204)
      console.log(`${entry.name}: ${fromCache ? 'CACHED' : 'NETWORK'}`);
    }
  }
});
observer.observe({ type: 'resource', buffered: true });
```

### Send cache metrics to your analytics

```javascript
// Send to your analytics endpoint
function reportCacheMetrics() {
  const entries = performance.getEntriesByType('resource');
  const metrics = {
    totalResources: entries.length,
    cachedResources: entries.filter(e => e.transferSize === 0).length,
    totalTransferKB: entries.reduce((sum, e) => sum + e.transferSize, 0) / 1024,
    cacheHitRate: 0,
  };
  metrics.cacheHitRate = metrics.cachedResources / metrics.totalResources;

  // Send to your analytics (Sentry, Datadog, custom endpoint)
  fetch('/api/analytics/cache', {
    method: 'POST',
    body: JSON.stringify(metrics),
    keepalive: true,
  });
}

// Report when page unloads (most reliable for single-page apps)
window.addEventListener('pagehide', reportCacheMetrics);
```

### What to watch

| Metric | Healthy | Warning | Action |
|--------|---------|---------|--------|
| Cache hit rate (static assets) | > 80% | 50-80% | Check if hashed filenames are consistent across deploys |
| Cache hit rate (HTML) | N/A (should NOT be cached) | > 0% | Your no-cache header isn't working |
| Transfer size reduction | > 50% vs. cold | < 30% | CDN may not be respecting cache headers |

---

## Core Web Vitals and caching

Cache headers directly impact Core Web Vitals:

### LCP (Largest Contentful Paint)

Cached fonts and CSS render faster. If your LCP element relies on a web font:
- **With cache:** Font loads from cache → LCP renders immediately
- **Without cache:** Font re-downloads → LCP delayed by network round-trip + font parse

**Check:** Ensure font files have `Cache-Control: public, max-age=31536000, immutable` and use `font-display: swap` to avoid FOIT.

### FID / INP (Interaction to Next Paint)

Cached JavaScript avoids re-parse and re-compile. A cached main bundle means the browser can respond to interactions faster on repeat visits.

**Check:** Measure FID/INP on repeat visits vs. first visits. Repeat visits should be significantly faster if caching is working.

### CLS (Cumulative Layout Shift)

CLS is mostly unaffected by caching, but stale cache can cause CLS if the cached HTML references different layout structure than the current version.

---

## Chunk load error tracking

### Sentry integration

```javascript
// Sentry initialization with chunk error detection
Sentry.init({
  dsn: 'your-dsn',
  beforeSend(event) {
    if (event.exception) {
      const error = event.exception.values?.[0];
      if (/Loading chunk|ChunkLoadError|Failed to fetch dynamically imported module/i.test(error?.value)) {
        // Tag as chunk load error for filtering
        event.tags = { ...event.tags, chunkLoadError: true };
        // Add deploy context
        event.extra = {
          ...event.extra,
          deployVersion: window.__DEPLOY_VERSION__, // set during build
          assetBaseUrl: window.__ASSET_BASE_URL__,
        };
      }
    }
    return event;
  },
});
```

### Monitoring chunk error rates

```javascript
// Simple chunk error rate monitoring (no Sentry needed)
window.addEventListener('error', (event) => {
  if (/Loading chunk|ChunkLoadError|Failed to fetch dynamically imported module/i.test(event.message)) {
    fetch('/api/analytics/chunk-error', {
      method: 'POST',
      body: JSON.stringify({
        message: event.message,
        filename: event.filename,
        deployVersion: window.__DEPLOY_VERSION__,
        userAgent: navigator.userAgent,
        url: window.location.href,
      }),
      keepalive: true,
    });
  }
});
```

### What to watch

| Metric | Healthy | Warning | Action |
|--------|---------|---------|--------|
| Chunk error rate | < 0.1% | 0.1-1% | Check cache headers; ensure old chunks aren't deleted immediately |
| Chunk errors per deploy | 0-5 | 5-50 | Increase chunk error boundary reload threshold; check rollback process |
| Chunk errors spike | None | Sudden spike after deploy | Deploy may have deleted old chunks too aggressively |

---

## Cache warming monitoring

After deploying cache warming in CI/CD, verify it's effective:

### Verify cache warming worked

```bash
# After deploy + cache warming, verify edge cache is warm
curl -s -o /dev/null -w "HTTP %{http_code}, Time: %{time_total}s\n" \
  -H "Cache-Control: no-cache" \
  https://yourapp.com/

# Check X-Cache header (varies by CDN)
curl -s -I https://yourapp.com/ | grep -i "x-cache\|cf-cache-status\|x-vercel-cache"
# Should show: HIT (cache is warm) not MISS (cache cold)
```

### Automated warming verification

```yaml
# In CI — verify cache warming succeeded
- name: Verify cache warming
  run: |
    sleep 5  # wait for CDN propagation
    STATUS=$(curl -s -I https://yourapp.com/ | grep -i "cf-cache-status\|x-cache" | head -1)
    if echo "$STATUS" | grep -qi "hit"; then
      echo "Cache warming successful: $STATUS"
    else
      echo "Warning: Cache may not be warm: $STATUS"
      exit 1
    fi
```
