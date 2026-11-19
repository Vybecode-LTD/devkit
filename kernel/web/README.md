# kernel/web

`index.ts` is the public surface; `testing.ts` is for tests only (`@/kernel/testing`).

Built:

- **The typed client** (`src/api/`): `api`, `useApiQuery`, `useApiMutation` and `apiQueryOptions` for the kernel's paths, `createApiClient<paths>()` for a module's, and `ApiProblem`, thrown by any answer but a success. Its types, `src/api/schema.ts`, are generated from `kernel/openapi.json` (`npm run api:types`; decision 0042).
- **`defineModule`** (`src/modules.ts`): a module's routes and its typed slots (`src/slots/types.ts`), checked.
- **The app shell** (`src/app/`): `mountApp` (a data router, `createRoot`), the site and admin frames, the kernel's own pages (`pages.ts`, held to `kernel.json`), the home, 404, no-access and unreachable pages, the router's error page, and the CSS that hides the server's words until React replaces them (`server-copy.css`).
- **The session** (`src/session/`): `useSession`, `useSignOut`. **The guards** (`src/guards/`): `RequireAuth`, `RequirePermission`, `RequireAdmin`, and `safeNext` for a sign-in's way back.
- **The slots** (`src/slots/`): `useSlot`, `SlotOutlet`, and the admin sidebar's order. **The site** (`src/site/`): `useSite`, `useModuleEnabled`. **`<Seo>`** (`src/seo/`).

- **The UI kit** (`src/ui/`, its `README.md`): every part a screen is built from, with `RouteFocus`, `ScrollMemory` and `ErrorBoundary`, the toasts and the icon set.

- **The look** comes from the site's theme (`themes/`, `<html data-theme>`): `frames.css` puts the page, text, type, links and focus on its `--mf-*` tokens and holds no colour of its own.

Planned (the rest of K4, `dev plans/contracts/k4-web-kernel.md`): `SignedInDevices` with the account screens, `useSettings`, and the auth, account and admin screens.
