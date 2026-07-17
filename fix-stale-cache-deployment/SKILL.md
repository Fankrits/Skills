---
name: fix-stale-cache-deployment
description: Diagnose and fix deployment-related cache incoherence in web applications. Use when a live site shows an old version until hard refresh, returns ChunkLoadError or failed dynamic-import errors after a release, opens to a blank screen because old HTML references deleted assets, leaves a PWA on an outdated service worker, or serves stale SSR/ISR content through a CDN or reverse proxy. Inspect repository versions and live HTTP evidence before editing. Apply platform-specific guidance only after identifying the framework, host, cache layers, and deployment model. Do not trigger for general cache education or unrelated performance tuning unless release freshness is the actual problem.
---

# Fix stale cache after deployment

Treat this as a cache-coherence incident, not as a reason to add random reloads or purge every cache in sight.

## Non-negotiable rules

1. Gather evidence before changing configuration.
2. Identify the framework version, deployment host, CDN or reverse proxy, service-worker status, and asset-retention model.
3. Separate these layers explicitly: browser HTTP cache, open-tab runtime state, service worker and Cache Storage, CDN or edge cache, reverse proxy, framework or data cache, origin, and deployed artifacts.
4. Preserve framework-managed headers unless current official documentation says to override them.
5. Cache fingerprinted assets by identity, not merely by file extension. Never apply year-long immutable caching to every `.js` or `.css` file unless all matching names are content-addressed.
6. Guard automatic recovery against reload loops. Reload at most once for the same release failure, then show a visible recovery message and report the error.
7. Prefer targeted invalidation. Do not run a global purge unless targeted invalidation is unavailable and the blast radius is acceptable.
8. Treat any shared caching of authenticated, personalized, financial, or otherwise sensitive responses as a security incident. Stop performance tuning and fix isolation first.
9. Check current official documentation for version-sensitive syntax. Do not invent config keys, framework APIs, or purge endpoints.
10. Verify generated entry documents and manifests reference files that actually exist before blaming caching.
11. Do not claim success until a two-release test passes with an old tab or old client state.

## Choose an operating mode

### Repository-access mode

Use this mode when project files are available.

1. Run the detector from the project root:

   ```bash
   python3 <skill-dir>/scripts/detect_cache_stack.py --root . --json
   ```

2. If a generated build or publish directory is available, verify its local reference graph before deployment:

   ```bash
   python3 <skill-dir>/scripts/verify_build_assets.py <build-dir> --json
   ```

3. Inspect every file named by the detector. Confirm versions from lockfiles or package manifests rather than assuming the latest release.
4. Inspect deployment and infrastructure configuration before editing application code.

### Conversation-only mode

Use this mode when project files are unavailable.

Collect the minimum evidence that can change the diagnosis:

- affected URL and exact symptom
- framework and version
- deployment host and any separate CDN or proxy
- whether a service worker or PWA is present
- response headers for the HTML document and one failed or fingerprinted asset
- whether the problem affects open tabs, fresh incognito sessions, one region, or authenticated users only

Do not provide host-specific configuration when the host or topology is unknown. Give a bounded diagnostic plan instead.

## Workflow

### Step 1: Reproduce and classify the symptom

Record:

- first bad release and current release identifier
- fresh navigation versus already-open tab behavior
- hard refresh versus normal refresh behavior
- failing URL, HTTP status, and console error
- whether HTML is old, data is old, or only a lazy-loaded asset fails
- whether the issue is global, regional, account-specific, or device-specific

Use a stable release marker when possible, such as a response header, HTML meta tag, build ID, or telemetry tag.

### Step 2: Collect build and live HTTP evidence

When a generated build is available, run the local verifier first:

```bash
python3 <skill-dir>/scripts/verify_build_assets.py <build-dir> --json
```

Treat missing build files as an artifact or deploy-order problem, not a cache-header problem. Use `--public-prefix /app/` for applications mounted below the origin root and `--manifest` for nonstandard JSON asset manifests.

When a safe URL is available, run:

```bash
python3 <skill-dir>/scripts/audit_cache_headers.py \
  https://example.com \
  --discover-assets \
  --revalidate \
  --json
```

The auditor redacts query strings, limits response bodies, and blocks non-loopback private network targets unless explicitly allowed. Never pass untrusted URLs containing credentials or secrets.

Also inspect browser DevTools when available:

- Preserve log across navigation.
- Disable DevTools cache only for comparison, not as proof of the production behavior.
- Inspect the document request, the failed chunk, service-worker control, and Cache Storage separately.
- Record `Cache-Control`, `Age`, validators, `Vary`, CDN-specific cache headers, redirect chain, and status codes.

### Step 3: Locate the stale layer

Use this evidence map:

| Evidence | Most likely layer | Next action |
|---|---|---|
| Old HTML references a missing fingerprinted chunk | document cache, open tab, or deleted prior assets | inspect document policy, release overlap, and one-shot chunk recovery |
| HTML release is current but rendered data is old | framework data cache, ISR/SSR cache, API cache, or CDN | inspect revalidation and cache keys; read `references/isr-ssr-cache.md` |
| Fresh incognito works but normal profile does not | browser cache or service worker | inspect Application panel and read `references/service-worker-pwa.md` |
| Only tabs opened before deploy fail | runtime chunk map plus removed old assets | keep prior assets and add guarded recovery |
| Edge shows `HIT` or increasing `Age` while origin is current | CDN or reverse proxy | compare origin and edge; inspect cache rules and purge only affected keys |
| One region or POP is stale | propagation, tiered cache, or inconsistent keying | compare regions and vendor cache headers |
| One account sees another account's content | shared-cache data leak | disable shared caching immediately and follow the security checklist |
| Reload repeats indefinitely | unguarded recovery handler or persistent stale layer | disable auto-reload and surface a stable error state |

Read `references/diagnosis-matrix.md` for deeper branch logic.

### Step 4: State the diagnosis before patching

Produce a brief evidence-backed statement containing:

- stale layer
- mechanism
- affected requests
- why the evidence rules out adjacent layers
- smallest safe change
- rollback and verification plan

Label uncertainty. Do not hide missing evidence behind confident wording.

### Step 5: Apply the smallest layered fix

Apply only the layers supported by evidence:

1. **Entry document or app shell:** require validation or use an intentionally short policy appropriate to the rendering model.
2. **Fingerprint-addressed assets:** retain them across release overlap and cache them for a long time.
3. **Unfingerprinted assets and manifests:** use short-lived or validating policies; do not mark them immutable.
4. **Chunk-load recovery:** add a framework-appropriate, one-shot recovery path.
5. **Service worker:** prompt for activation or use an explicitly justified forced-update flow.
6. **SSR/ISR/data cache:** use framework-supported revalidation and coordinate multi-instance or external CDN caches.
7. **CDN or proxy:** correct cache keys and rules; purge only affected entry points or routes when required.
8. **Deployment pipeline:** upload new immutable assets before publishing entry documents; preserve prior assets long enough for open tabs and rollback.

Route implementation details through these references:

| Situation | Read |
|---|---|
| Framework or bundler-specific recovery | `references/framework-specific.md` |
| HTTP and host cache policies | `references/server-cache-headers.md` |
| Service worker or PWA lifecycle | `references/service-worker-pwa.md` |
| SSR, ISR, route, or data caching | `references/isr-ssr-cache.md` |
| Deploy order, invalidation, rollback | `references/ci-cd-cache-patterns.md` |
| Telemetry and production signals | `references/monitoring-observability.md` |
| Tests and security gates | `references/testing-security.md` |
| Current authoritative documentation | `references/official-sources.md` |

### Step 6: Verify with two releases

Do not mark the issue resolved until all applicable checks pass:

1. Deploy version A and open it in at least one tab.
2. Deploy version B with a visible release marker and at least one changed lazy chunk.
3. Keep the version-A tab open through the version-B deploy.
4. Verify a fresh navigation receives version B without hard refresh.
5. Verify the old tab either continues safely with retained assets or recovers once without a reload loop.
6. Verify fingerprinted assets are long-lived and still available when referenced by the supported release-overlap window.
7. Verify entry documents, service-worker scripts, manifests, SSR/ISR routes, and personalized responses each follow their intended policy.
8. Run `scripts/verify_build_assets.py` against each generated release and confirm every checked entry-document, CSS, and manifest reference resolves.
9. Verify rollback does not strand clients on missing forward-release assets.
10. Watch production error and asset-404 signals by release identifier after rollout.

Use the CI and test patterns in `references/testing-security.md` and `references/ci-cd-cache-patterns.md`.

## Required final report

Use this structure unless the user's requested format is stricter:

```markdown
# Deployment cache diagnosis

## Evidence
- [request, header, file, version, or reproduction result]

## Root cause
[stale layer + mechanism + confidence]

## Changes made
- [file/config and exact behavioral change]

## Verification
- [two-release checks and results]

## Remaining risks
- [unknowns, rollout concerns, or monitoring window]
```

Never report a hard refresh, clearing browser data, or asking users to reinstall the PWA as the final fix. Those are diagnostic controls, not production remediation.
