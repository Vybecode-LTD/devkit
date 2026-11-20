// fixture-pins's web binding: no pages, for the CLI's tests.
import { defineModule } from "@/kernel";

export default defineModule({
  id: "fixture-pins",
  routes: { public: [], member: [], admin: [] },
});
