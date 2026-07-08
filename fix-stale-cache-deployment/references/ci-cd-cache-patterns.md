# CI/CD Cache Invalidation Patterns

Correct cache headers on the deployed files aren't enough — your CI/CD pipeline needs to actively invalidate CDN and edge caches after deploying new content. This is the most commonly forgotten step, and the most common reason "the headers are right but users still see old content."

## Table of contents
- [Automated invalidation in CI pipelines](#automated-invalidation-in-ci-pipelines)
- [Preview deployment cache strategies](#preview-deployment-cache-strategies)
- [Rollback cache recovery](#rollback-cache-recovery)
- [Atomic deploys vs. gradual propagation](#atomic-deploys-vs-gradual-propagation)
- [Cache warming after deploy](#cache-warming-after-deploy)

---

## Automated invalidation in CI pipelines

Never rely on manual cache invalidation — automate it in your deploy pipeline.

### AWS CloudFront invalidation

```yaml
# .github/workflows/deploy.yml
- name: Deploy to S3
  run: aws s3 sync ./dist s3://your-bucket --delete

- name: Invalidate CloudFront
  run: |
    INVALIDATION_ID=$(aws cloudfront create-invalidation \
      --distribution-id ${{ secrets.CF_DIST_ID }} \
      --paths "/index.html" "/blog/*" \
      --query 'Invalidation.Id' --output text)
    echo "Invalidation $INVALIDATION_ID created"
    aws cloudfront wait invalidation-completed \
      --distribution-id ${{ secrets.CF_DIST_ID }} \
      --id $INVALIDATION_ID
```

**Key points:**
- Invalidate `/index.html` and any non-hashed entry points (not hashed assets — those get new URLs)
- `aws cloudfront wait` blocks until invalidation completes — prevents the pipeline from reporting success before CDN is updated
- CloudFront charges per invalidation path; batch paths with wildcards (`/blog/*`) to reduce cost

### Vercel

Vercel auto-invalidates on deploy, but for on-demand ISR revalidation:

```yaml
- name: Revalidate ISR pages
  run: |
    curl -X POST "https://your-app.vercel.app/api/revalidate" \
      -H "Content-Type: application/json" \
      -d '{"secret": "${{ secrets.REVALIDATE_SECRET }}", "paths": ["/", "/blog"]}'
```

### Netlify

Netlify doesn't have explicit cache invalidation — it deploys atomically. But if you're using Netlify's CDN with custom headers, ensure the `_headers` file is part of the build output.

### Cloudflare

```yaml
# Purge Cloudflare cache after deploy
- name: Purge Cloudflare cache
  run: |
    curl -X POST "https://api.cloudflare.com/client/v4/zones/${{ secrets.CF_ZONE_ID }}/purge_cache" \
      -H "Authorization: Bearer ${{ secrets.CF_API_TOKEN }}" \
      -H "Content-Type: application/json" \
      --data '{"purge_everything":true}'
```

**Note:** `purge_everything` is nuclear — for production, purge specific URLs:

```json
{"files": ["https://yourapp.com/", "https://yourapp.com/blog/*"]}
```

---

## Preview deployment cache strategies

Preview deployments (Vercel, Netlify, Cloudflare Pages) need completely separate cache from production:

### Why preview deploys get fresh cache automatically

Vercel and Netlify assign unique URLs to each preview deploy (e.g., `your-app-git-branch-abc123.vercel.app`). Since the URL is different from production, there's zero cache conflict — the browser has never seen this URL before, so there's nothing stale.

### Manual preview environments (self-hosted)

If you're running preview deploys on your own infrastructure (e.g., staging server), you MUST separate cache:

```nginx
# Staging Nginx — different cache zone
proxy_cache_path /var/cache/nginx/staging levels=1:2 keys_zone=staging:10m max_size=1g;

server {
    location / {
        proxy_cache staging;
        proxy_cache_valid 200 5m;  # short TTL for staging
        proxy_cache_bypass $http_x_preview_deploy;
        add_header X-Cache-Status $upstream_cache_status;
    }
}
```

**Rule of thumb:** Preview deploys should have short or no cache. Production deploys should have aggressive caching. Never share a cache zone between preview and production.

---

## Rollback cache recovery

When you roll back a deploy, users may have cached references to the *forward-deployed* version's chunk URLs. This is a real problem:

### The rollback trap

1. Deploy v2 → users get HTML pointing at `main.abc123.js`
2. Roll back to v1 → server now serves v1's HTML pointing at `main.def456.js`
3. Users who cached v2's HTML still request `main.abc123.js` — which no longer exists

### Fixes

**Option 1: Keep old chunks on the server (recommended)**

Don't delete old build artifacts immediately. Keep the previous N versions of hashed assets on the server:

```bash
# In deploy script — don't delete old hashed assets
aws s3 sync ./dist s3://your-bucket \
  --delete \
  --exclude "assets/main.*.js" \  # keep all hashed JS
  --exclude "assets/styles.*.css"  # keep all hashed CSS
```

Old hashed files are safe to keep because they'll never change (the hash is in the filename). Storage cost is minimal compared to the rollback safety.

**Option 2: Atomic deploys (swap entire directory)**

Some hosts (Vercel, Netlify) swap traffic atomically — the old version stays serving until the new version is fully deployed. If you roll back, you swap back to the old directory that still has all its chunks.

**Option 3: CloudFront invalidation on rollback**

```bash
# After rollback deploy, invalidate CDN so it re-fetches from origin
aws cloudfront create-invalidation \
  --distribution-id $DIST_ID \
  --paths "/index.html"
```

---

## Atomic deploys vs. gradual propagation

Different hosts deploy differently — understanding this matters for cache:

| Host | Deploy model | Cache implication |
|------|-------------|-------------------|
| **Vercel** | Atomic swap | Old chunks stay accessible until next deploy replaces them. Safe for rollback. |
| **Netlify** | Atomic swap | Same as Vercel — old deploy's files remain until next deploy. |
| **S3 + CloudFront** | Gradual (S3 sync + CloudFront invalidation) | Old chunks deleted on `--delete` before CDN invalidation completes. Race condition risk. |
| **Cloudflare Pages** | Atomic swap | Similar to Vercel. |
| **Self-hosted (rsync)** | Gradual | Files deleted before server cache clears. Most dangerous for rollback. |

**For gradual deploys (S3, self-hosted):** Always invalidate CDN AFTER confirming the new deploy is live, and keep old hashed assets.

---

## Cache warming after deploy

First visitors after a deploy hit cold cache — they download everything fresh. For high-traffic sites, this causes a latency spike:

### Automated cache warming

```yaml
# GitHub Actions — warm cache after deploy
- name: Warm CDN cache
  run: |
    # Hit critical pages to populate CDN edge cache
    for path in "/" "/blog" "/pricing"; do
      curl -s -o /dev/null -w "%{http_code}" \
        "https://yourapp.com${path}" &
    done
    wait
    echo "Cache warming complete"
```

### Vercel-specific

Vercel automatically warms the edge cache on deploy for high-traffic sites. For low-traffic preview deploys, you can use the Deploy Webhook API to trigger warming.

### When to warm

- **Always:** After production deploys to high-traffic sites
- **Consider:** After deploys that change critical above-the-fold content
- **Skip:** Low-traffic sites, preview deploys, background/worker deploys
