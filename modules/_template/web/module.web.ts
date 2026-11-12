// my-module's web binding (SPEC.md section 8). No business logic here: anything a
// desktop or mobile app would also need lives in the backend and is reached through the API.
import { defineModule } from "@/kernel";

export default defineModule({
  id: "my-module",
  routes: {
    public: [],
    member: [],
    admin: [{ path: "/admin/my-module", lazy: () => import("./pages/MyModuleAdmin"), permission: "my-module.item.manage" }],
  },
  slots: {
    "nav.admin": [{ label: "My module", to: "/admin/my-module" }],
  },
});
