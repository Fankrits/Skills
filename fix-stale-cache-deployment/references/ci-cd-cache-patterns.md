# CI/CD, invalidation, release overlap, and rollback

A deploy pipeline should maintain a coherent set of entry documents, route output, manifests, and fingerprinted assets. Not every platform requires explicit invalidation; determine the deployment model first.

## Classify the deploy model

### Atomic immutable release

Traffic switches from a complete release A to a complete release B. Previous releases may remain addressable. Managed platforms often approximate this model.

Key checks:

- Does rollback restore the entire old release, including assets?
- How long are prior release assets retained?
- Does a custom domain or external CDN add a mutable cache layer?

### Mutable object store or in-place sync

Files are uploaded and deleted in a shared directory or bucket. S3 sync, rsync, and many self-hosted scripts behave this way.

Risks:

- entry HTML can publish before new assets exist
- old assets can be deleted while open tabs still reference them
- rollback can remove forward-release assets
- CDN invalidation can race with uploads

### Rolling server deploy

Multiple instances run different releases during rollout. Risks include incompatible route payloads, build IDs, server-action IDs, and local caches.

Confirm session affinity, build-ID coordination, cache sharing, and asset hosting for the framework version.

## Safe publication order

For mutable deployments, use this order:

1. Build release B in an isolated directory.
2. Validate the build manifest and asset references.
3. Upload all new fingerprinted assets without deleting release-A assets.
4. Deploy or start release-B servers.
5. Run health and compatibility checks.
6. Publish release-B entry documents, manifests, and mutable aliases last.
7. Purge only affected non-fingerprinted edge objects when required.
8. Run public-edge verification.
9. Remove expired release assets only after the overlap and rollback window.

This ordering ensures an entry document never points to an asset that has not been published.

## Asset retention policy

Define retention from actual client behavior:

- maximum expected open-tab duration
- service-worker deferral window
- rollback window
- phased rollout duration
- CDN propagation time
- release frequency

Keep fingerprinted assets for at least the longest supported overlap. Storage is usually cheaper than a deploy-wide blank screen.

Do not retain mutable stable-name files under the assumption that hashes make them safe; only content-addressed URLs have that property.

## Invalidation decision

Invalidate only when a mutable edge object can outlive the acceptable staleness budget and the platform does not atomically replace or revalidate it.

Typical targets:

- `/index.html`
- route HTML or route payloads with known cache keys
- web app manifest
- stable-name service-worker script
- selected API or ISR routes

Usually do not invalidate newly fingerprinted assets. Their URLs are new, and purging them wastes cache capacity.

Before using a vendor API, confirm current support for exact URLs, prefixes, tags, surrogate keys, wildcards, and global purge. Wildcard syntax is not portable.

## CloudFront pattern

For S3 plus CloudFront:

- upload assets and entry points with separate metadata
- avoid deleting prior fingerprinted assets during the deploy
- create invalidations only for mutable paths whose cache policy requires it
- wait for invalidation completion only when the release gate requires it

A typical command is:

```bash
aws cloudfront create-invalidation \
  --distribution-id "$DISTRIBUTION_ID" \
  --paths "/index.html" "/manifest.webmanifest"
```

Use current AWS documentation for quoting, path limits, cost, and waiter behavior.

## Cloudflare pattern

Prefer tag, prefix, hostname, or exact-URL purge when supported by the plan and cache design. Treat `purge_everything` as an emergency or deliberately accepted blast radius, not the default deploy step.

Verify Worker Cache API contents and Cache Rules separately; purging one layer does not prove another is empty.

## Managed atomic platforms

Vercel, Netlify, Cloudflare Pages, Firebase Hosting, and similar platforms often provide atomic or platform-coordinated deploy behavior. Do not bolt on a purge step merely because another host needs one.

Still inspect:

- external CDN or proxy in front of the platform
- custom headers
- framework ISR/data caches
- service-worker lifecycle
- custom domains and alias propagation
- retention of previous deployment assets

## CI gates

### Static project detection

```bash
python3 <skill-dir>/scripts/detect_cache_stack.py --root . --json > cache-stack.json
```

Review unexpected multiple hosts, service workers, or existing chunk-recovery handlers.

### Public response audit

```bash
python3 <skill-dir>/scripts/audit_cache_headers.py \
  "$STAGING_URL" \
  --discover-assets \
  --revalidate \
  --fail-on error
```

Run against the public staging edge, not only an internal container. Store the JSON output as a build artifact when useful.

### Build and manifest integrity

Run the bundled verifier against the generated publish directory before upload:

```bash
python3 <skill-dir>/scripts/verify_build_assets.py \
  <build-dir> \
  --public-prefix / \
  --json
```

It parses generated HTML, follows local CSS `url()` references, inspects supported asset-manifest fields, confirms every referenced local file exists, rejects path escapes, and reports fingerprinted versus stable-name assets. Use `--public-prefix /app/` when the build is mounted below a path prefix. Add a project-specific release-directory check when deployment layout encodes release IDs outside the build root.

### Two-release test

A single deployment cannot prove stale-client recovery. Use release A then release B in a preview or test environment and keep a release-A browser context open during the switch.

## Rollback design

A rollback is another deployment and needs the same coherence guarantees.

1. Keep both release-A and release-B fingerprinted assets during the rollback window.
2. Restore the complete release-A entry points and server code.
3. Invalidate mutable release-B entry points only when required.
4. Verify clients that previously received release B do not request missing assets.
5. Confirm service-worker rollback behavior; an older worker may not automatically replace a newer one if script bytes and lifecycle rules do not cooperate.
6. Record forward and rollback release IDs in telemetry.

## Rolling deploy compatibility

When old and new servers overlap:

- use a stable asset host that serves both releases
- coordinate framework build IDs where documented
- avoid incompatible cookies or serialized route payloads
- make database migrations backward compatible through the rollout
- ensure shared caches cannot mix release-specific response shapes under one key

Cache symptoms can be a sign of release incompatibility rather than a TTL problem.

## Cache warming

Warm only responses intentionally cached at the target layer. A request to HTML with `no-cache` may validate successfully but should not be expected to report a durable `HIT` like a fingerprinted asset.

Use warming when:

- the edge cache is expected to store expensive public responses
- cold-start latency materially affects users
- origin capacity can handle the warm-up

Skip or constrain warming for:

- personalized routes
- non-cacheable HTML
- mutation endpoints
- low-traffic previews
- global fan-out that could overload the origin

Verify warm-up with vendor headers and latency baselines, not a hard-coded expectation that every response must be a cache hit.

## Pipeline anti-patterns

- `sync --delete` before new entry points and old-tab compatibility are verified
- one cache-control value for the entire build directory
- global CDN purge on every release
- reporting deploy success before the public edge serves the new release
- deleting old assets immediately after publishing new HTML
- warming private or non-cacheable routes
- relying on manual invalidation during incidents
- assuming rollback is safe because the source commit changed back
