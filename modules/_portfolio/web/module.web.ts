// portfolio's web binding (SPEC.md section 8). Generated scaffold; no business logic here.
import { defineModule } from "@/kernel";

export default defineModule({
  id: "portfolio",
  routes: {
    public: [{ path: "/art", lazy: () => import("./pages/Public") }, { path: "/art/:discipline", lazy: () => import("./pages/Public") }, { path: "/art/piece/:slug", lazy: () => import("./pages/Public") }],
    member: [],
    admin: [{ path: "/admin/portfolio", lazy: () => import("./pages/PortfolioAdmin"), permission: "portfolio.piece.manage" }],
  },
  slots: {
    "nav.admin": [{ label: "Portfolio", to: "/admin/portfolio" }],
    "nav.public": [{ label: "Art", to: "/art" }]
  },
});
