/**
 * A landing's token (K4 contract §2): a link from a mail opens the page with
 * `?token=`. It's read once and taken out of the address bar before the page
 * is painted, so it stays out of the history, a bookmark and a shared
 * screenshot. The page acts on it only when the person presses its button,
 * never on load, since mail scanners open links.
 */
import { useLayoutEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router";

export function useAddressToken(): string {
  const location = useLocation();
  const navigate = useNavigate();
  const [token] = useState(() => new URLSearchParams(location.search).get("token") ?? "");
  const carries = new URLSearchParams(location.search).has("token");
  useLayoutEffect(() => {
    if (!carries) return;
    const rest = new URLSearchParams(location.search);
    rest.delete("token");
    const search = rest.toString();
    void navigate({ pathname: location.pathname, search: search ? `?${search}` : "", hash: location.hash }, { replace: true });
  }, [carries, location.pathname, location.search, location.hash, navigate]);
  return token;
}
