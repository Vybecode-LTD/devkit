// discography's web binding (SPEC.md section 8). Generated scaffold; no business logic here.
import { defineModule } from "@/kernel";

export default defineModule({
  id: "discography",
  routes: {
    public: [{ path: "/music", lazy: () => import("./pages/Public") }, { path: "/music/:album", lazy: () => import("./pages/Public") }, { path: "/music/:album/:track", lazy: () => import("./pages/Public") }],
    member: [],
    admin: [{ path: "/admin/discography", lazy: () => import("./pages/DiscographyAdmin"), permission: "discography.release.manage" }],
  },
  slots: {
    "nav.admin": [{ label: "Music", to: "/admin/discography" }],
    "nav.public": [{ label: "Music", to: "/music" }]
  },
});
