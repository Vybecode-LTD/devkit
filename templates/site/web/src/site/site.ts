/**
 * This site's own pages and the slots it fills (decision 0048). They're always
 * on, with no switch on Features, and win a tie with a module's route.
 *
 * Each public page here has its server copy in `backend/app/site/pages.py`,
 * with the same words, so a crawler that runs no script reads what a person
 * sees: add both together. Member pages sit behind sign-in.
 */
import { defineSite } from "@/kernel";

export const site = defineSite({
  routes: {
    public: [{ path: "/", lazy: () => import("./Home") }],
    member: [],
  },
});
