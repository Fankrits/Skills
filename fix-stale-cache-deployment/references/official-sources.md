# Authoritative sources and maintenance policy

Last reviewed: 2026-07-16.

Use current official documentation before applying version-sensitive framework or hosting syntax. Prefer installed package documentation or source for the exact project version when the public documentation defaults to a newer major release.

## Protocol and browser platform

- HTTP caching semantics: RFC 9111 — https://www.rfc-editor.org/rfc/rfc9111.html
- `immutable` response directive: RFC 8246 — https://www.rfc-editor.org/rfc/rfc8246.html
- Service worker lifecycle: https://developer.mozilla.org/docs/Web/API/Service_Worker_API/Using_Service_Workers
- `ServiceWorkerRegistration.update()`: https://developer.mozilla.org/docs/Web/API/ServiceWorkerRegistration/update
- `updateViaCache`: https://developer.mozilla.org/docs/Web/API/ServiceWorkerRegistration/updateViaCache
- Cache Storage API: https://developer.mozilla.org/docs/Web/API/CacheStorage
- Performance resource timing: https://developer.mozilla.org/docs/Web/API/PerformanceResourceTiming

## Build tools and frameworks

- Vite production build and load-error handling: https://vite.dev/guide/build.html#load-error-handling
- Next.js caching guide: https://nextjs.org/docs/app/guides/caching
- Next.js revalidation: https://nextjs.org/docs/app/getting-started/revalidating
- Next.js CDN caching: https://nextjs.org/docs/app/guides/cdn-caching
- Next.js self-hosting: https://nextjs.org/docs/app/guides/self-hosting
- Workbox update handling: https://developer.chrome.com/docs/workbox/handling-service-worker-updates
- Workbox module reference: https://developer.chrome.com/docs/workbox/modules

For SvelteKit, Nuxt, Astro, Qwik, TanStack Start, Remix, React Router, and other frameworks, open the official documentation for the installed major version. Do not infer that a Vite-based framework exposes every Vite recovery hook identically.

## Hosting and CDNs

- Vercel cache-control headers: https://vercel.com/docs/headers/cache-control-headers
- Netlify caching overview: https://docs.netlify.com/manage/caching/overview/
- Netlify custom headers: https://docs.netlify.com/manage/routing/headers/
- Cloudflare Pages headers: https://developers.cloudflare.com/pages/configuration/headers/
- Cloudflare Cache Rules: https://developers.cloudflare.com/cache/how-to/cache-rules/
- Cloudflare cache purge: https://developers.cloudflare.com/cache/how-to/purge-cache/
- AWS CloudFront invalidation: https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/Invalidation.html
- AWS S3 object metadata and cache control: https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingMetadata.html
- Firebase Hosting headers: https://firebase.google.com/docs/hosting/full-config#headers
- Azure Static Web Apps configuration: https://learn.microsoft.com/azure/static-web-apps/configuration
- Nginx headers module: https://nginx.org/en/docs/http/ngx_http_headers_module.html

## Fact-check rules

1. Check the installed framework and adapter versions before copying current examples.
2. Confirm whether a managed platform owns the relevant headers or cache. Avoid overriding platform-generated asset policies without evidence.
3. Confirm whether a vendor purge API supports exact URLs, prefixes, tags, surrogate keys, or global purge. Do not assume wildcard semantics.
4. Confirm whether revalidation is platform-coordinated or local to one self-hosted process.
5. Verify generated configuration against a preview or staging deployment and inspect the resulting response headers.
6. Record the documentation page and version used in the final report when a change depends on a vendor-specific behavior.
