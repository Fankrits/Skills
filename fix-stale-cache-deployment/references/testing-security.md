# Testing and security gates

Cache correctness and cache security are inseparable. A configuration that makes content fresh but mixes users, trusts unkeyed input, or creates reload loops is not a successful fix.

## Minimum test matrix

Test each applicable cell:

| Scenario | Expected result |
|---|---|
| Fresh profile after release B | receives release B without hard refresh |
| Release-A tab kept open through release B | continues with retained assets or recovers once |
| Lazy route first opened after deploy | loads or reaches stable update UI; no blank screen |
| Normal reload | discovers release B according to policy |
| Conditional document request | valid `304` or fresh `200` |
| Service worker waiting | prompt or explicit forced-update policy behaves as designed |
| Two tabs under one worker scope | activation and state preservation remain coherent |
| Rollback from B to A | neither B nor A clients request missing supported assets |
| Authenticated route | never appears in shared cache or another account |
| Multiple regions or instances | release and cache behavior converge within the declared window |

## Automated header audit

Use the bundled auditor instead of a brittle `curl | grep` script:

```bash
python3 <skill-dir>/scripts/audit_cache_headers.py \
  "$STAGING_URL" \
  --discover-assets \
  --revalidate \
  --fail-on error \
  --json > cache-audit.json
```

The auditor checks high-confidence hazards such as immutable HTML, long-lived unfingerprinted assets, public responses that set cookies, and service-worker scripts with stale update policies.

Do not treat a clean audit as proof that ISR, service-worker runtime caching, or CDN cache keys are correct. It covers observable HTTP evidence only.

## Two-release browser test

Build a product-specific Playwright, Cypress, or WebDriver test around a real release transition:

1. Deploy fixture release A.
2. Open a browser context and record the release marker.
3. Navigate through enough routes to establish realistic runtime state, but leave one lazy route unopened.
4. Deploy fixture release B with a changed lazy chunk and visible marker.
5. Open the untouched lazy route from the release-A tab.
6. Assert one of the supported outcomes:
   - old asset remains available and the route works, or
   - guarded recovery reloads once and release B appears.
7. Fail on blank screen, repeated reload, or missing update UI.
8. Open a fresh browser context and assert release B immediately.

Do not simulate success by manually dispatching an error event without exercising the real bundle and deployed artifact lifecycle.

## Manifest integrity test

Parse build output and assert:

- every local script, style, module-preload, font-preload, and manifest reference exists
- referenced filenames match the configured asset base
- fingerprinted assets are not overwritten in place
- entry documents from one release do not reference a different release directory
- prior supported release manifests still resolve during the overlap window

## Service-worker test

- Test with DevTools update forcing disabled.
- Trigger `registration.update()` for deterministic timing.
- Cover a worker already waiting before listeners attach.
- Cover accept, defer, and mandatory-update paths.
- Verify transient state persistence.
- Inspect Cache Storage for user-specific data.
- Verify cleanup deletes only the application's own cache prefix.
- Test multiple tabs and offline startup.

## Security stop conditions

Stop rollout and prioritize containment when any of these occurs:

- one user or tenant can receive another's content
- a response with credentials, PII, financial data, or authorization decisions is shared-cacheable
- a cache key omits tenant, locale, origin, or another dimension that changes the representation
- untrusted request input changes a cached response without participating in the cache key
- a service worker caches authenticated API responses unexpectedly
- purge or invalidation requires exposing long-lived admin credentials in client code or logs

## Personalized responses

Use `private` or `no-store` according to the storage requirement. Do not rely on `Vary: Authorization` as the primary isolation mechanism.

Check:

- `Cache-Control`
- `Set-Cookie`
- CDN cache rules that override origin headers
- anonymous versus authenticated cache keys
- tenant and role variation
- logout behavior
- browser back-forward cache and client router state where sensitive data is involved

A `Set-Cookie` header does not guarantee that every CDN will refuse storage when explicit shared-cache directives or vendor rules say otherwise. Verify the actual platform.

## Cache poisoning review

Shared caches must not store attacker-influenced variants under a key that omits the influencing input.

Review:

- `Host` and forwarded-host handling
- path normalization and encoded separators
- query parameters included or ignored by the CDN
- request headers reflected into HTML, redirects, script URLs, or CSP
- language, device, and experiment headers
- method handling and unexpected caching of non-GET responses
- error-page caching
- origin override headers

Use a staging environment and harmless markers. Do not test destructive poisoning against production without authorization.

## CORS and `Vary`

When a response dynamically selects `Access-Control-Allow-Origin`, include `Vary: Origin` so shared caches separate variants. A fixed public `Access-Control-Allow-Origin: *` can be correct for genuinely public, non-credentialed resources; it is not automatically a leak.

Never combine credentialed CORS, reflected origins, and shared caching without a reviewed key and policy.

## Service-worker security

- Serve workers only over secure contexts, except permitted local development.
- Choose the smallest required scope.
- Validate message types and avoid evaluating message content.
- Cache only expected same-origin `GET` requests by default.
- Keep auth and mutation routes network-only unless an offline design explicitly secures them.
- Do not return opaque or mismatched cached responses to unrelated requests.
- Version and namespace cache entries.
- Review `Service-Worker-Allowed` before broadening scope.

## CSP and integrity

Do not prescribe hash-based CSP as a universal replacement for nonces. Both are valid patterns with different tradeoffs.

Instead verify:

- the HTML body and CSP header belong to the same release and response variant
- nonce-bearing HTML is not reused beyond its intended policy
- Subresource Integrity hashes match retained assets
- old assets retained for open tabs remain compatible with current security headers
- a CDN does not combine a cached body with headers from another variant

## Invalidation credentials

- Store vendor purge credentials in CI secret storage.
- Grant only the scopes needed for the target zone, distribution, or cache tags.
- Never embed purge tokens in frontend code.
- Redact commands and logs that can expose tokens or signed URLs.
- Make invalidation retries idempotent.
- Audit global-purge use.

## Reload-loop test

Instrument recovery attempts and assert:

- first recognized asset-version failure can initiate one recovery
- the same session or release failure cannot initiate another immediate reload
- unrelated exceptions do not trigger cache recovery
- storage failure does not remove the guard entirely
- the fallback UI remains accessible and offers a manual retry or support path

## Completion checklist

- static detector reviewed
- public-edge audit passed
- two-release test passed
- old-tab lazy-load path passed
- rollback passed
- service-worker paths passed when applicable
- personalized route isolation passed
- cache-key review completed
- telemetry records recovery success and repeats
- no undocumented vendor API or config key added
