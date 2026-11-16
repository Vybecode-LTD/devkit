// comments's web binding (SPEC.md section 8). Generated scaffold; no business logic here.
import { defineModule } from "@/kernel";

export default defineModule({
  id: "comments",
  routes: {
    public: [],
    member: [],
    admin: [{ path: "/admin/comments", lazy: () => import("./pages/CommentsAdmin"), permission: "comments.comment.approve" }],
  },
  slots: {
    "nav.admin": [{ label: "Comments", to: "/admin/comments" }]
  },
});
