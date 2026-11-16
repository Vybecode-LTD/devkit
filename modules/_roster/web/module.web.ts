// roster's web binding (SPEC.md section 8). Generated scaffold; no business logic here.
import { defineModule } from "@/kernel";

export default defineModule({
  id: "roster",
  routes: {
    public: [{ path: "/collective", lazy: () => import("./pages/Public") }, { path: "/collective/:slug", lazy: () => import("./pages/Public") }],
    member: [],
    admin: [{ path: "/admin/roster", lazy: () => import("./pages/RosterAdmin"), permission: "roster.profile.manage" }],
  },
  slots: {
    "nav.admin": [{ label: "Collective", to: "/admin/roster" }],
    "nav.public": [{ label: "Collective", to: "/collective" }]
  },
});
