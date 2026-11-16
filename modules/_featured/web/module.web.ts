// featured's web binding (SPEC.md section 8). Generated scaffold; no business logic here.
import { defineModule } from "@/kernel";

export default defineModule({
  id: "featured",
  routes: {
    public: [],
    member: [],
    admin: [{ path: "/admin/featured", lazy: () => import("./pages/FeaturedAdmin"), permission: "featured.placement.manage" }],
  },
  slots: {
    "nav.admin": [{ label: "Homepage", to: "/admin/featured" }]
  },
});
