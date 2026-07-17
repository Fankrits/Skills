# HTTP and host cache policy

Use this reference after classifying each response by identity and rendering model. Do not apply one policy to an entire extension family.

## Cache-Control semantics that matter

- `no-cache`: allow storage, but require successful validation before reuse.
- `no-store`: instruct private and shared caches not to store the response. Use for sensitive data or when storage itself is unacceptable.
- `max-age=N`: freshness lifetime for browsers and other caches unless a shared-cache directive overrides it.
- `s-maxage=N`: freshness lifetime for shared caches; it does not set browser freshness.
- `private`: prohibit shared-cache storage; a browser may still cache according to other directives.
- `public`: explicitly permit shared caching when otherwise restricted. It does not by itself define freshness.
- `immutable`: assert that the representation will not change while fresh. Use only when the URL changes with the bytes.
- `must-revalidate`: prohibit serving stale after freshness expires when failed validation would cause incorrect behavior. Do not add it by reflex.
- `stale-while-revalidate` and `stale-if-error`: availability and latency tools, not automatic freshness fixes.

When origin, framework, proxy, and CDN emit different directives, determine which header the client and shared cache actually obey. Vendor-specific headers such as `CDN-Cache-Control` or `Surrogate-Control` can intentionally differ from browser policy.

## Classify before configuring

| Response class | Safe default direction | Key condition |
|---|---|---|
| Static entry HTML for a versioned frontend | validation-oriented, commonly `no-cache` | the document must discover new asset URLs promptly |
| Fingerprinted JS, CSS, fonts, images, or WASM | long-lived, commonly one year plus `immutable` | filename or path must change when bytes change |
| Unfingerprinted JS/CSS or copied public file | short-lived or validation-oriented | extension alone is not proof of immutability |
| Service-worker script | update-oriented, commonly `no-cache` or `max-age=0` | update discovery must not be delayed by a long fresh lifetime |
| Web app manifest | short-lived or validation-oriented | its URL is often stable while metadata changes |
| Public SSR/ISR route | application-specific browser and shared TTLs | revalidation and invalidation must reach every serving layer |
| Personalized or authenticated response | `private` and usually `no-store` or strict validation | never allow shared reuse without a reviewed isolation design |
| Public API response | business-specific | cache key, staleness budget, and invalidation must be explicit |
| Error response | short or no storage unless intentionally resilient | avoid pinning deploy failures or authorization errors |

## Fingerprint test

Treat an asset as fingerprinted only when the build guarantees that a content change produces a new URL. Common evidence:

- a content hash in the generated filename
- a release-specific immutable directory
- a manifest mapping logical names to content-addressed files

Do not infer fingerprinting from:

- `.js` or `.css` extension
- a query parameter added manually
- a build timestamp that might be reused
- a CDN URL with no documented versioning guarantee

Use `scripts/audit_cache_headers.py` to flag unfingerprinted assets that are marked immutable.

## Static frontend pattern

For a traditional static app shell with content-hashed build assets:

```http
# Entry document
Cache-Control: no-cache
ETag: "..."

# Fingerprinted asset
Cache-Control: public, max-age=31536000, immutable
```

This pattern is not a mandate for SSR/ISR pages. A server-rendered route may intentionally use `s-maxage` and revalidation while keeping browser freshness short. Confirm the framework and host behavior first.

## Host configuration strategy

### Managed framework platforms

- Inspect the deployed headers before overriding defaults.
- Preserve framework-generated asset policies and routing headers.
- Apply custom rules to explicit, known paths rather than broad negative regular expressions.
- Confirm whether the platform strips or rewrites `s-maxage`, `CDN-Cache-Control`, `Vary`, or surrogate-key headers before they reach browsers.
- Use the platform's supported revalidation and purge mechanisms only.

For Next.js on Vercel, do not add a blanket rule for `/_next/static/*` merely to duplicate the platform's managed immutable policy. Focus on the actual stale layer.

### Netlify and Cloudflare Pages `_headers`

Order and matching behavior are platform-specific. Keep generated `_headers` in the publish directory and verify the deployed result. Prefer explicit asset directories whose contents are known to be fingerprinted:

```text
/index.html
  Cache-Control: no-cache

/assets/*
  Cache-Control: public, max-age=31536000, immutable

/sw.js
  Cache-Control: no-cache
```

Do not mark `/assets/*` immutable when the project copies stable-name files into that directory.

### Nginx

Use separate locations for the entry document and a known fingerprinted asset directory. A safer pattern is path-based rather than extension-only:

```nginx
location /assets/ {
    add_header Cache-Control "public, max-age=31536000, immutable" always;
    try_files $uri =404;
}

location = /index.html {
    add_header Cache-Control "no-cache" always;
}

location / {
    try_files $uri $uri/ /index.html;
}
```

Check inherited `add_header` behavior, upstream headers, and any proxy cache separately. Test the final response after reloading Nginx.

### Apache

Use explicit directories or hash-aware rules. Confirm `mod_headers` is active and that a CDN does not override the origin:

```apache
<IfModule mod_headers.c>
  <Files "index.html">
    Header set Cache-Control "no-cache"
  </Files>

  <FilesMatch "[._-][0-9a-fA-F]{8,}[._-].*\.(js|css|woff2?)$">
    Header set Cache-Control "public, max-age=31536000, immutable"
  </FilesMatch>
</IfModule>
```

Adjust the hash pattern to the build output rather than trusting this example blindly.

### S3 and CloudFront

Set cache metadata at upload time and deploy in a safe order:

1. Upload new fingerprinted assets with long immutable metadata.
2. Keep previous release assets.
3. Upload entry documents and manifests with validation-oriented or intentionally short metadata.
4. Invalidate only stale non-fingerprinted paths when the CloudFront policy requires it.
5. Wait for invalidation only when rollout semantics require a hard completion gate.

Do not use one `aws s3 sync` command with a single cache policy for the entire build.

### Cloudflare CDN or Workers

Separate browser policy from edge policy deliberately. Inspect Cache Rules, Worker code, and origin headers together. A Worker can change response headers without changing what is stored in `caches.default`, and a Cache Rule can override origin intent.

Never assume a file pattern is safe merely because it looks static. Confirm the cache key and content identity.

### Express or custom servers

Set policies by resolved artifact class. Avoid an extension-only `express.static` rule when stable-name assets and fingerprinted assets share extensions. Serve the SPA fallback document with its own policy after static-file resolution.

### Firebase Hosting and Azure Static Web Apps

Use route-specific header configuration and inspect precedence. Keep a catch-all document policy from overriding the fingerprinted-asset rule, or vice versa. Verify the deployed result because platform route matching can differ from local expectations.

## `Vary` and cache keys

`Vary` tells caches which request headers select representations. Use it only for headers that truly change the response.

- Add `Vary: Origin` when the response reflects or selects by `Origin`.
- Preserve framework-required variation such as encoding or route-data markers.
- Avoid `Vary: Cookie` on broadly cacheable pages unless the design accepts severe cache fragmentation.
- Do not use `Vary: Authorization` as a substitute for `private` or `no-store` on personalized responses.
- Treat `Vary: *` as effectively non-reusable and investigate why it exists.

Also inspect query-string, cookie, host, language, device, and custom-header participation in the CDN cache key. A correct response header cannot repair a wrong cache key.

## Conflicts and precedence

Flag these as defects:

- `public` and `private` together
- `no-store` combined with a positive long TTL or `immutable`
- fingerprinted and unfingerprinted files matched by the same immutable rule
- origin says `no-cache` while a CDN rule forces a long edge TTL without an invalidation path
- multiple `Cache-Control` headers whose combined directives conflict
- shared-cacheable responses that set cookies or contain personalized data

## Validation checklist

1. Audit a fresh document request and at least one fingerprinted asset.
2. Confirm normal navigation discovers a new release without hard refresh.
3. Confirm a conditional request returns a valid `304` or a fresh `200`.
4. Confirm old fingerprinted assets remain available during the supported overlap window.
5. Confirm the service-worker script and manifest are not accidentally immutable.
6. Confirm personalized responses are not stored in shared caches.
7. Re-run the audit against the public edge, not only localhost or origin.
