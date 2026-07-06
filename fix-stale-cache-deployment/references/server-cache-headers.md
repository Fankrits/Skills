# Server / Host Cache Header Configuration

The universal rule, regardless of host:

- HTML documents → `Cache-Control: no-cache` (browser must revalidate with the server every time)
- Hashed static assets (JS/CSS/fonts with a content hash in the filename) → `Cache-Control: public, max-age=31536000, immutable`

Below is the exact syntax per platform. Only configure the one(s) actually in use — check for the relevant config file or ask the user which host they deploy to if it's not obvious from the repo.

## Table of contents
- [Vercel](#vercel)
- [Netlify](#netlify)
- [Cloudflare Pages / Workers](#cloudflare-pages--workers)
- [Nginx](#nginx)
- [Apache](#apache)
- [AWS S3 + CloudFront](#aws-s3--cloudfront)
- [Express / custom Node server](#express--custom-node-server)

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

## Cloudflare Pages / Workers

For Cloudflare Pages, add a `_headers` file identical in syntax to Netlify's (same format), placed in the build output directory.

If instead fronting an origin with Cloudflare as a CDN (not Pages), the **origin's headers can be overridden by Cloudflare's own cache rules** — check Caching → Configuration → Cache Rules in the dashboard. A common bug is the origin sending correct `no-cache` on HTML while a Cloudflare Page Rule caches everything with a long TTL regardless. Make sure a Cache Rule exists that respects origin headers for the HTML route, e.g.:

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
