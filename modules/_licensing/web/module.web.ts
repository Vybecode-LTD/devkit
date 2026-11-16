// licensing's web binding (SPEC.md section 8). Generated scaffold; no business logic here.
import { defineModule } from "@/kernel";

export default defineModule({
  id: "licensing",
  routes: {
    public: [{ path: "/beats", lazy: () => import("./pages/Public") }, { path: "/beats/:slug", lazy: () => import("./pages/Public") }, { path: "/license/:id", lazy: () => import("./pages/Public") }],
    member: [],
    admin: [{ path: "/admin/licensing", lazy: () => import("./pages/LicensingAdmin"), permission: "licensing.work.manage" }],
  },
  slots: {
    "nav.admin": [{ label: "Beats", to: "/admin/licensing" }],
    "nav.public": [{ label: "Beats", to: "/beats" }]
  },
});
