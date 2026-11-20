// fixture-notes's web binding: no pages, for the CLI's tests.
import { defineModule } from "@/kernel";

export default defineModule({
  id: "fixture-notes",
  routes: { public: [], member: [], admin: [] },
});
