# Framework-Specific Implementation

Jump to the section matching what Step 1 detected. Each covers: where header config lives (if the framework controls it, rather than the host) and how to catch chunk load failures idiomatically for that framework.

## Table of contents
- [Next.js (App Router)](#nextjs-app-router)
- [Next.js (Pages Router)](#nextjs-pages-router)
- [Vite (React/Vue/vanilla)](#vite)
- [Create React App / plain Webpack](#create-react-app--plain-webpack)
- [SvelteKit](#sveltekit)
- [Nuxt / Vue](#nuxt--vue)

---

## Next.js (App Router)

Next.js already hashes build output and sets long-lived caching on `/_next/static/*` automatically — you usually don't need to touch that. What you *do* need to configure is the HTML/RSC layer and chunk-error recovery.

**Headers** (if not already handled by your host config from `server-cache-headers.md`), in `next.config.js`:

```javascript
module.exports = {
  async headers() {
    return [
      {
        source: '/_next/static/:path*',
        headers: [{ key: 'Cache-Control', value: 'public, max-age=31536000, immutable' }],
      },
      {
        source: '/((?!_next/static).*)', // everything else (pages, RSC payloads)
        headers: [{ key: 'Cache-Control', value: 'no-cache, must-revalidate' }],
      },
    ];
  },
};
```

**Chunk error recovery** — add a root-level `error.tsx` (App Router's built-in error boundary) that specifically detects and recovers from chunk failures:

```tsx
// app/error.tsx
'use client';
import { useEffect } from 'react';

export default function GlobalError({ error }: { error: Error }) {
  useEffect(() => {
    if (/Loading chunk|ChunkLoadError|Failed to fetch dynamically imported module/i.test(error.message)) {
      window.location.reload();
    }
  }, [error]);

  return <p>Something went wrong. Reloading…</p>;
}
```

## Next.js (Pages Router)

Same headers config as above works in `next.config.js`. For chunk errors, use `_app.tsx` with a top-level error boundary class component (React error boundaries must be class components pre-React 19) or hook into Next's router events:

```tsx
// pages/_app.tsx
import Router from 'next/router';

Router.events.on('routeChangeError', (err) => {
  if (/Loading chunk|Failed to fetch dynamically imported module/i.test(err?.message ?? '')) {
    window.location.reload();
  }
});
```

## Vite

Vite emits a native browser event specifically for this — no manual try/catch needed around every import:

```javascript
// main.js / main.ts, near the top, before mounting the app
window.addEventListener('vite:preloadError', (event) => {
  event.preventDefault(); // stop it from surfacing as an unhandled error
  window.location.reload();
});
```

For headers: Vite itself doesn't serve production traffic (that's your host's job — see `server-cache-headers.md`), but confirm `build.rollupOptions.output` isn't overriding the default content-hash filenames (`[name].[hash].js`), since that hash is what makes the "cache forever" rule on Layer A safe.

## Create React App / plain Webpack

CRA's default build already content-hashes `static/js/*.js` and `static/css/*.css` — same "cache forever" logic applies. For chunk errors, wrap lazy-loaded routes in a React error boundary:

```jsx
class ChunkErrorBoundary extends React.Component {
  state = { hasError: false };

  static getDerivedStateFromError(error) {
    if (/Loading chunk|ChunkLoadError/i.test(error.message)) {
      window.location.reload();
      return { hasError: true };
    }
    throw error; // not a chunk error, let it propagate normally
  }

  render() {
    return this.state.hasError ? <p>Updating…</p> : this.props.children;
  }
}

// Wrap around <Suspense> / lazy-loaded route trees
<ChunkErrorBoundary>
  <Suspense fallback={<Loading />}>
    <Routes>{/* ... */}</Routes>
  </Suspense>
</ChunkErrorBoundary>
```

If it's a raw Webpack config (no CRA), confirm `output.filename` uses `[contenthash]` and check `webpack-dev-server`/prod server config for header handling, or defer entirely to host-level headers in `server-cache-headers.md`.

## SvelteKit

SvelteKit emits its own reload-on-stale-chunk event similar to Vite (it's Vite-based under the hood):

```javascript
// hooks.client.js
export const handleError = ({ error }) => {
  if (/Failed to fetch dynamically imported module|Importing a module script failed/i.test(error?.message ?? '')) {
    window.location.reload();
  }
};
```

Headers: set in `svelte.config.js` adapter options if self-hosting with `adapter-node`, or via host config (Vercel/Netlify adapters mostly handle asset caching automatically — verify with the Network tab rather than assuming).

## Nuxt / Vue

Nuxt 3's Vite-based build benefits from the same `vite:preloadError` handling. In a Nuxt plugin:

```javascript
// plugins/chunk-error-reload.client.js
export default defineNuxtPlugin(() => {
  window.addEventListener('vite:preloadError', () => {
    window.location.reload();
  });
});
```

For plain Vue Router lazy routes without Nuxt, wrap `router.onError`:

```javascript
router.onError((error) => {
  if (/Loading chunk|Failed to fetch dynamically imported module/i.test(error.message)) {
    window.location.reload();
  }
});
```
