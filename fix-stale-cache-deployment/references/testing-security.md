# Testing & Security

## Table of contents
- [Testing patterns](#testing-patterns)
  - [Automated cache header validation](#automated-cache-header-validation)
  - [Stale cache simulation in CI](#stale-cache-simulation-in-ci)
  - [Service worker testing](#service-worker-testing)
- [Security considerations](#security-considerations)
  - [Cache poisoning prevention](#cache-poisoning-prevention)
  - [Sensitive data in cached responses](#sensitive-data-in-cached-responses)
  - [CORS + cache interaction](#cors--cache-interaction)
  - [Service worker security](#service-worker-security)
  - [CSP + caching](#csp--caching)

---

## Testing patterns

### Automated cache header validation

Add cache header checks to your CI pipeline. This catches regressions where someone removes or misconfigures cache headers:

```bash
#!/bin/bash
# scripts/test-cache-headers.sh — run against your staging/production URL

BASE_URL="${1:-http://localhost:3000}"
PASS=0
FAIL=0

check_header() {
  local url="$1"
  local expected_name="$2"
  local expected_pattern="$3"
  
  HEADER=$(curl -s -I "$url" | grep -i "$expected_name" | head -1)
  if echo "$HEADER" | grep -qiE "$expected_pattern"; then
    echo "  ✓ $url → $HEADER"
    PASS=$((PASS + 1))
  else
    echo "  ✗ $url → expected $expected_name matching '$expected_pattern', got: '$HEADER'"
    FAIL=$((FAIL + 1))
  fi
}

echo "Testing cache headers..."

# HTML should NOT be cached
check_header "$BASE_URL/" "cache-control" "no-cache|no-store|must-revalidate"

# Hashed assets should be cached forever
# Find a JS file from the HTML
JS_FILE=$(curl -s "$BASE_URL/" | grep -oE '/[^"]+\.js' | head -1)
if [ -n "$JS_FILE" ]; then
  check_header "${BASE_URL}${JS_FILE}" "cache-control" "max-age=31536000|immutable"
fi

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ $FAIL -eq 0 ] || exit 1
```

**GitHub Actions integration:**

```yaml
# .github/workflows/test-cache.yml
- name: Deploy to staging
  run: # your deploy command

- name: Test cache headers
  run: bash scripts/test-cache-headers.sh "${{ secrets.STAGING_URL }}"
```

### Stale cache simulation in CI

Test that users with stale cache can recover:

```javascript
// tests/cache-recovery.test.js (Playwright)
import { test, expect } from '@playwright/test';

test('user with stale cache recovers on reload', async ({ page, context }) => {
  // 1. Visit the site (simulates "current version")
  await page.goto('/');
  
  // 2. Add a cache entry for an old JS chunk that no longer exists
  await context.route('**/assets/old-chunk.js', async (route) => {
    await route.fulfill({
      status: 404,
      body: 'Not Found',
    });
  });
  
  // 3. Simulate a dynamic import failing
  await page.evaluate(() => {
    window.dispatchEvent(new ErrorEvent('error', {
      message: 'Loading chunk failed',
      filename: '/assets/old-chunk.js',
    }));
  });
  
  // 4. Verify the app shows the update/reload UI (not a blank screen)
  await expect(page.locator('text=Updating')).toBeVisible({ timeout: 5000 });
});
```

### Service worker testing

Service workers have a notoriously hard-to-test lifecycle. Use these patterns:

```javascript
// tests/sw-update.test.js (Playwright)
import { test, expect } from '@playwright/test';

test('service worker update shows banner', async ({ page, context }) => {
  // IMPORTANT: Uncheck "Update on reload" in DevTools — it masks real behavior
  // In Playwright, this is not an issue since we control the browser context
  
  // 1. Register a service worker
  await page.goto('/');
  const swRegistered = await page.evaluate(async () => {
    const reg = await navigator.serviceWorker.ready;
    return !!reg.active;
  });
  expect(swRegistered).toBe(true);
  
  // 2. Simulate a new service worker version
  await context.route('/sw-v2.js', async (route) => {
    // Serve a new service worker that calls skipWaiting
    await route.fulfill({
      contentType: 'application/javascript',
      body: `
        self.addEventListener('install', e => self.skipWaiting());
        self.addEventListener('activate', e => self.waitUntil(self.clients.claim()));
      `,
    });
  });
  
  // 3. Trigger update check
  await page.evaluate(() => {
    navigator.serviceWorker.getRegistration().then(reg => reg.update());
  });
  
  // 4. Verify update banner appears (or page reloads)
  // Implementation depends on your banner component
});
```

---

## Security considerations

### Cache poisoning prevention

Cache poisoning occurs when an attacker causes a CDN or browser to cache a malicious response. Prevent it by:

**1. Never cache POST/PUT/DELETE responses:**

```nginx
# Nginx — explicitly prevent caching of write operations
location / {
    # Only cache GET and HEAD requests
    if ($request_method !~ ^(GET|HEAD)$) {
        proxy_cache_bypass 1;
        add_header Cache-Control "no-store";
    }
}
```

**2. Include Authorization in Vary:**

```http
Cache-Control: private
Vary: Authorization
```

This ensures each user gets their own cache entry, preventing one user's authenticated response from being served to another.

**3. Don't cache error responses permanently:**

```http
# Bad — caches a 500 error for 1 year
Cache-Control: public, max-age=31536000

# Good — short TTL for errors
Cache-Control: public, max-age=60
```

### Sensitive data in cached responses

**Never cache responses containing:**
- Authentication tokens or session data
- Personal information (PII)
- Financial data
- API keys or secrets

**Detection rule:**

```bash
# Find responses with Set-Cookie (never cached by compliant caches)
curl -s -I https://yourapp.com/ | grep -i "set-cookie"

# If Set-Cookie is present but Cache-Control is "public, max-age=...", fix it:
# Either set Cache-Control: private, or strip Set-Cookie before caching
```

**Framework-specific:**
- **Next.js:** API routes with `cookies()` or `headers()` are automatically dynamic (not cached)
- **Remix:** Use `cookie()` helper — responses with `Set-Cookie` are not cached by browsers
- **General:** If a response has `Set-Cookie`, browsers won't cache it (spec compliance), but CDNs might — check your CDN's behavior

### CORS + cache interaction

When `Access-Control-Allow-Origin: *` is set, a cached response can be served to requests from any origin. If the response contains user-specific data, this is a data leak:

**Fix:** Use specific origins instead of `*`, and combine with `Vary: Origin`:

```http
Access-Control-Allow-Origin: https://yourapp.com
Vary: Origin
Cache-Control: public, max-age=300
```

This means each origin gets its own cached copy, preventing cross-origin data leakage.

### Service worker security

**Scope restriction:**

```javascript
// Register service worker at the root only
navigator.serviceWorker.register('/sw.js'); // scope: /

// NOT from a subdirectory — this would give the SW access to /api/*
navigator.serviceWorker.register('/app/sw.js'); // scope: /app/ (too broad)
```

**Don't cache sensitive API responses:**

```javascript
// In service worker fetch handler
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  
  // Skip caching for API routes and auth endpoints
  if (url.pathname.startsWith('/api/') || url.pathname.includes('/auth/')) {
    return; // let browser handle directly
  }
  
  // Cache static assets only
  if (event.request.destination === 'style' || event.request.destination === 'script') {
    event.respondWith(caches.match(event.request));
  }
});
```

### CSP + caching

Content Security Policy nonces rotate with each deploy. If a user has a cached HTML page with nonce `abc123` and the new deploy uses nonce `def456`, inline scripts in the cached HTML won't match the new CSP.

**Fix:** Use hash-based CSP instead of nonce-based for deployable apps:

```http
Content-Security-Policy: script-src 'self' 'sha256-abc123...'
```

Or set `Cache-Control: no-cache` on HTML (which you should already be doing) so nonces are always fresh.

**If you must use nonces:** Ensure HTML has `Cache-Control: no-cache, must-revalidate` so the browser always revalidates and gets fresh nonces.
