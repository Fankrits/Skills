# Monitoring and observability

Measure deployment coherence by release. Do not invent universal cache-hit or error-rate thresholds; establish baselines for the product, traffic shape, CDN, and release cadence.

## Required release context

Attach a non-secret release identifier to as many signals as practical:

- response header such as `X-App-Release`
- HTML meta tag or boot payload
- JavaScript build constant
- service-worker cache name
- error-monitoring release field
- server and edge logs

The identifier must be safe to expose and consistent across entry documents, assets, and server instances.

## High-value signals

### Asset version failures

Track:

- `ChunkLoadError`
- failed dynamic imports
- module-script load failures
- 404 or 410 responses for fingerprinted assets
- recovery attempts, successes, and repeated failures

Dimension by:

- client release
- current server release
- failed asset path without sensitive query values
- route
- browser family
- region or CDN POP
- whether a service worker controlled the page

A spike immediately after release is more informative than an arbitrary absolute threshold.

### Entry-document freshness

Use synthetic checks to record:

- public release marker
- status and redirect chain
- `Cache-Control`
- `Age`
- validators
- CDN cache status
- referenced asset URLs

Compare the public edge with a trusted origin when topology permits.

### Service-worker adoption

Track:

- active worker release
- waiting-worker detection
- prompt shown, accepted, deferred, or failed
- time from release to activation
- reload after `controllerchange`
- repeated activation or reload loops

Do not collect full URLs, form data, or user content with these events.

### Framework and data-cache freshness

Record the revalidation trigger, tags or route identifiers, outcome, serving instance or region, and first observed fresh response. Avoid logging cache keys that contain secrets or personal data.

### Artifact availability

Monitor 404/410 rates for fingerprinted assets by release. Alert when an asset still referenced by a supported release disappears.

## Browser PerformanceResourceTiming

`PerformanceResourceTiming` can support RUM, but fields such as `transferSize === 0` are heuristics rather than proof of a cache hit. Zero transfer can also reflect cross-origin timing restrictions or implementation details, and a validated response may still transfer headers.

Use it as one signal:

```javascript
function collectResourceEvidence() {
  return performance.getEntriesByType('resource')
    .filter((entry) => ['script', 'link', 'css'].includes(entry.initiatorType))
    .map((entry) => ({
      name: new URL(entry.name).pathname,
      initiatorType: entry.initiatorType,
      transferSize: entry.transferSize,
      encodedBodySize: entry.encodedBodySize,
      decodedBodySize: entry.decodedBodySize,
      duration: entry.duration,
      nextHopProtocol: entry.nextHopProtocol,
    }));
}
```

Send sampled aggregates rather than every resource for every user. Respect privacy, consent, retention, and telemetry budgets.

## Error-monitoring pattern

Use the monitoring SDK's release field and tag only recognized asset-version failures:

```javascript
function classifyAssetVersionError(error) {
  return /ChunkLoadError|Loading chunk|Failed to fetch dynamically imported module|Importing a module script failed/i
    .test(String(error?.message ?? error ?? ''));
}

window.addEventListener('error', (event) => {
  if (!classifyAssetVersionError(event.error ?? event.message)) return;

  reportError(event.error ?? new Error(event.message), {
    category: 'asset-version-failure',
    clientRelease: window.__APP_RELEASE__,
    failedPath: event.filename ? new URL(event.filename, location.href).pathname : undefined,
    serviceWorkerControlled: Boolean(navigator.serviceWorker?.controller),
  });
});
```

Implement `reportError` using the project's existing telemetry. Do not add a new monitoring vendor during an incident unless asked.

## Recovery telemetry

Record a state machine rather than a single error:

```text
failure_detected
  -> recovery_reload_started
  -> new_release_loaded
  -> recovery_succeeded
```

or:

```text
failure_detected
  -> recovery_already_attempted
  -> stable_update_message_shown
  -> manual_retry_succeeded | support_required
```

This reveals reload loops and distinguishes successful recovery from users abandoning the page.

## Synthetic audit

Run on a schedule and after deploy:

```bash
python3 <skill-dir>/scripts/audit_cache_headers.py \
  https://example.com \
  --discover-assets \
  --revalidate \
  --json
```

Persist a compact result containing release marker, header summary, findings, and referenced assets. Compare with the previous successful release.

## Alert design

Alert on change from baseline and direct user harm, for example:

- asset 404s begin immediately after a release
- chunk failures increase materially for the previous client release
- public edge release differs from origin beyond the expected propagation window
- a waiting worker remains unactivated beyond the product's update policy
- one region serves a different release
- repeated recovery attempts occur in one session
- a personalized response becomes shared-cacheable

Use explicit product thresholds only after observing normal traffic. Do not copy fixed values such as "healthy above 80%" or "warning above 0.1%" into every application.

## Cache-hit metrics

Separate:

- browser reuse
- CDN hit or validation
- framework/data-cache hit
- origin application hit

A low HTML browser hit rate can be intentional, while a high fingerprinted-asset reuse rate can be desirable. A CDN `HIT` is not automatically good if it serves an obsolete or incorrectly keyed object.

## Privacy and security

- Strip query strings unless explicitly safe.
- Do not send cookies, authorization headers, form state, response bodies, or full user-agent strings by default.
- Hash or bucket identifiers when exact values are unnecessary.
- Sample high-volume resource data.
- Treat cross-account cache evidence as a security incident and preserve forensic logs according to policy.

## Post-release review

For each fixed incident, record:

- stale layer and root cause
- release that introduced it
- detection signal that first fired
- why existing tests missed it
- permanent CI or monitoring gate added
- asset-retention and rollback implications
- whether the Skill references or scripts need updating
