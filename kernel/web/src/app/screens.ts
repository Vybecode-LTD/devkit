/**
 * The kernel pages' screens, by path, each loaded only when its page opens
 * (`lazyPart`, so a failed load asks again on Try again). A kernel page
 * without one here still shows its heading (`Pending`) until its screen is
 * built: the admin's Settings, K4.8.
 */
import type { Lazy } from "../slots/types";

const landing =
  (name: "VerifyEmail" | "SignInByLink" | "ResetPassword" | "ConfirmEmailChange" | "UndoEmailChange" | "UndoSecondFactor" | "Unsubscribe"): Lazy =>
  () =>
    import("../auth/Landings").then((screens) => ({ default: screens[name] }));

export const SCREENS: Readonly<Record<string, Lazy>> = {
  "/sign-in": () => import("../auth/SignIn"),
  "/sign-up": () => import("../auth/SignUp"),
  "/forgot-password": () => import("../auth/ForgotPassword"),
  "/auth/verify": landing("VerifyEmail"),
  "/auth/link": landing("SignInByLink"),
  "/auth/reset": landing("ResetPassword"),
  "/auth/email": landing("ConfirmEmailChange"),
  "/auth/email/undo": landing("UndoEmailChange"),
  "/auth/second-factor/undo": landing("UndoSecondFactor"),
  "/notifications/unsubscribe": landing("Unsubscribe"),
  "/account": () => import("../account/Account"),
  "/account/notifications": () => import("../account/Notifications"),
  "/account/activity": () => import("../account/Activity"),
  "/admin": () => import("../admin/Dashboard"),
  "/admin/people": () => import("../admin/People"),
  "/admin/roles": () => import("../admin/Roles"),
  "/admin/activity": () => import("../admin/Activity"),
};
