# Server / Host Cache Header Configuration

The universal rule, regardless of host:

- HTML documents → `Cache-Control: no-cache` (browser must revalidate with the server every time)
- Hashed static assets (JS/CSS/fonts with a content hash in the filename) → `Cache-Control: public, max-age=31536000, immutable`

Below is the exact syntax per platform. Only configure the one(s) actually in use — check for the relevant config file or ask the user which host they deploy to if it's not obvious from the repo.

## Table of contents
- [Vercel](#vercel)
- [Netlify](#netlify)
- [Cloudflare Pages](#cloudflare-pages)
- [Cloudflare Workers (advanced)](#cloudflare-workers-advanced)
- [Nginx](#nginx)
- [Apache](#apache)
- [AWS S3 + CloudFront](#aws-s3--cloudfront)
- [Express / custom Node server](#express--custom-node-server)
- [Deno Deploy](#deno-deploy)
- [Firebase Hosting](#firebase-hosting)
- [Azure Static Web Apps](#azure-static-web-apps)
- [Fly.io](#flyio)
- [stale-while-revalidate / stale-if-error patterns](#stale-while-revalidate--stale-if-error-patterns)

---

## Vercel

`vercel.json` at the project root:

```json
{
  "headers": [
    {
      "source": "/(.*)\\.(js|css|woff2|woff|png|jpg|svg)",
      "headers": [{ "key": "Cache-Control", "value": "public, max-age=31536000, immutable" }]
    },
    {
      "source": "/((?!.*\\.(js|css|woff2|woff|png|jpg|svg)).*)",
      "headers": [{ "key": "Cache-Control", "value": "no-cache, must-revalidate" }]
    }
  ]
}
```

Note: if this is a Next.js project on Vercel, `/_next/static/*` is already immutable-cached by the platform by default — this config is mainly for other static assets and to be explicit about the HTML layer.

## Netlify

`public/_headers` (or wherever the publish directory is):

```
/*
  Cache-Control: no-cache, must-revalidate

/assets/*
  Cache-Control: public, max-age=31536000, immutable

/*.js
  Cache-Control: public, max-age=31536000, immutable

/*.css
  Cache-Control: public, max-age=31536000, immutable
```

Netlify applies rules top-to-bottom with later, more specific rules winning — keep the broad HTML rule first.

## Cloudflare Pages

For Cloudflare Pages, add a `_headers` file identical in syntax to Netlify's (same format), placed in the build output directory.

## Cloudflare Workers (advanced)

When using Cloudflare Workers to serve your app (not just Pages), you have full programmatic control over caching:

```javascript
// worker.js
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    
    // Cache hashed assets at the edge for 1 year
    if (/\.(js|css|woff2?|png|jpg|svg)$/.test(url.pathname)) {
      const cacheKey = new Request(url.toString(), request);
      const cached = await caches.default.match(cacheKey);
      if (cached) return cached;
      
      const response = await fetch(request);
      const cloned = response.clone();
      cloned.headers.set('Cache-Control', 'public, max-age=31536000, immutable');
      await caches.default.put(cacheKey, cloned);
      return response;
    }
    
    // HTML — always revalidate
    const response = await fetch(request);
    const cloned = response.clone();
    cloned.headers.set('Cache-Control', 'no-cache, must-revalidate');
    return cloned;
  },
};
```

**Workers-specific gotchas:**
- Workers run at the edge — `caches.default` is the edge cache, not the browser cache
- `Cache-Control` headers set in the Worker override origin headers
- Use `cf.cacheTtl` in the fetch options for fine-grained control: `fetch(request, { cf: { cacheTtl: 3600 } })`
- `cacheTtl` only applies to successful responses (200-299); errors bypass cache by default

If fronting an origin with Cloudflare as a CDN (not Pages), the **origin's headers can be overridden by Cloudflare's own cache rules** — check Caching → Configuration → Cache Rules in the dashboard. A common bug is the origin sending correct `no-cache` on HTML while a Cloudflare Page Rule caches everything with a long TTL regardless. Make sure a Cache Rule exists that respects origin headers for the HTML route, e.g.:

```
# Cache Rule: bypass cache for HTML
When: URI Path does not match \.(js|css|woff2?|png|jpg|svg)$
Then: Cache Level = Bypass
```

## Nginx

In the `server` block serving the built app:

```nginx
location ~* \.(js|css|woff2?|png|jpg|jpeg|svg|ico)$ {
    add_header Cache-Control "public, max-age=31536000, immutable";
}

location / {
    add_header Cache-Control "no-cache, must-revalidate";
    try_files $uri $uri/ /index.html; # SPA fallback, if applicable
}
```

Reload nginx after editing (`nginx -s reload`) — config changes don't apply until then, which is an easy step to forget mid-debug.

## Apache

`.htaccess` in the web root, or the equivalent in the vhost config:

```apache
<IfModule mod_headers.c>
  <FilesMatch "\.(js|css|woff2?|png|jpg|jpeg|svg|ico)$">
    Header set Cache-Control "public, max-age=31536000, immutable"
  </FilesMatch>
  <FilesMatch "\.html$">
    Header set Cache-Control "no-cache, must-revalidate"
  </FilesMatch>
</IfModule>
```

Requires `mod_headers` enabled (`a2enmod headers` on Debian/Ubuntu, then restart Apache).

## AWS S3 + CloudFront

S3 doesn't infer content type intent from filenames the way a web server does — cache-control has to be set as **object metadata at upload time**, not as a blanket bucket policy:

```bash
# Hashed assets — long cache, immutable
aws s3 sync ./dist/assets s3://your-bucket/assets \
  --cache-control "public, max-age=31536000, immutable"

# HTML — no-cache
aws s3 cp ./dist/index.html s3://your-bucket/index.html \
  --cache-control "no-cache, must-revalidate"
```

Then in CloudFront, create a **cache invalidation** for `/index.html` (and any other non-hashed entry points) after every deploy — otherwise CloudFront's edge cache can keep serving the old HTML even with correct S3 metadata, since CloudFront caches independently of origin headers unless configured to respect them:

```bash
aws cloudfront create-invalidation --distribution-id YOUR_DIST_ID --paths "/index.html"
```

Automate this invalidation step in the deploy pipeline (CI script) rather than relying on someone remembering to run it manually — that's the most common reason this setup "should work but doesn't" in practice.

## Express / custom Node server

If serving the built app directly from an Express (or similar) server rather than a static host:

```javascript
const express = require('express');
const path = require('path');
const app = express();

app.use(express.static(path.join(__dirname, 'dist'), {
  setHeaders: (res, filePath) => {
    if (/\.(js|css|woff2?|png|jpg|svg)$/.test(filePath)) {
      res.setHeader('Cache-Control', 'public, max-age=31536000, immutable');
    } else {
      res.setHeader('Cache-Control', 'no-cache, must-revalidate');
    }
  },
}));
```

## Deno Deploy

Deno Deploy uses a vendor-specific header for CDN caching: `Deno-CDN-Cache-Control`. It automatically invalidates cached routes when you deploy a new version.

```typescript
// main.ts
Deno.serve((req) => {
  const url = new URL(req.url);
  
  if (/\.(js|css|woff2?|png|jpg|svg)$/.test(url.pathname)) {
    return new Response(/* ... */, {
      headers: {
        'Cache-Control': 'public, max-age=31536000, immutable',
      },
    });
  }
  
  return new Response(/* ... */, {
    headers: {
      'Cache-Control': 'no-cache, must-revalidate',
    },
  });
});
```

**Deno Deploy gotcha:** Routes with dynamic segments (`/blog/:slug`) are NOT automatically cached — you must explicitly set `Cache-Control` headers. Static routes get basic caching by default.

## Firebase Hosting

Configure in `firebase.json`:

```json
{
  "hosting": {
    "public": "dist",
    "headers": [
      {
        "source": "**/*.@(js|css|woff2|woff|png|jpg|svg)",
        "headers": [
          { "key": "Cache-Control", "value": "public, max-age=31536000, immutable" }
        ]
      },
      {
        "source": "**",
        "headers": [
          { "key": "Cache-Control", "value": "no-cache, must-revalidate" }
        ]
      }
    ]
  }
}
```

Firebase deploys atomically — old versions are replaced instantly. No CDN invalidation step needed.

## Azure Static Web Apps

Configure in `staticwebapp.config.json` at the build output root:

```json
{
  "responseOverrides": {},
  "globalHeaders": {
    "Cache-Control": "no-cache, must-revalidate"
  },
  "routeRules": [
    {
      "route": "/assets/*",
      "responseHeaders": {
        "Cache-Control": "public, max-age=31536000, immutable"
      }
    },
    {
      "route": "/*.js",
      "responseHeaders": {
        "Cache-Control": "public, max-age=31536000, immutable"
      }
    },
    {
      "route": "/*.css",
      "responseHeaders": {
        "Cache-Control": "public, max-age=31536000, immutable"
      }
    }
  ]
}
```

Azure SWA deploys atomically to the edge. Cache invalidation is automatic.

## Fly.io

Fly.io serves static apps via its built-in Edge Apps or custom Docker containers. For static apps, set headers in `fly.toml` isn't directly supported — use the app's internal server or CDN configuration.

For apps served by Caddy (Fly's default static server):

```Caddyfile
# Caddyfile
@static {
  path *.js *.css *.woff2 *.png *.jpg *.svg
}

header @static Cache-Control "public, max-age=31536000, immutable"
header Cache-Control "no-cache, must-revalidate"
```

For apps behind Fly's built-in CDN (Edge Apps), cache headers propagate automatically. For custom Docker deployments, configure the web server (Nginx/Apache/Caddy) inside the container.

## stale-while-revalidate / stale-if-error patterns

These `Cache-Control` extensions are useful for any host. Add them to the general patterns above when appropriate:

### stale-while-revalidate

```http
Cache-Control: public, max-age=60, stale-while-revalidate=3600
```

Serve the cached copy immediately, fetch fresh content in the background. Users never wait for regeneration. Good for ISR pages, API routes, any page where "slightly old is better than slow."

### stale-if-error

```http
Cache-Control: public, max-age=60, stale-if-error=86400
```

If the origin fails, serve the last cached copy instead of an error page. Critical during deploys when the origin may be temporarily unreachable.

### Combined pattern

```http
Cache-Control: public, max-age=60, stale-while-revalidate=3600, stale-if-error=86400
```

Serve cached for 60s, background-refresh up to 1h, serve stale for up to 24h if origin fails.
