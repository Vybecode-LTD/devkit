/**
 * The top bar's notices (VM Website `AdminDashboard.dc.html`: the bell, with
 * a dot while some are unread): the signed-in person's own notices
 * (`GET /api/kernel/notifications`, decision 0038), opened from the bell as a
 * panel under it. A notice with a page opens it and counts as read; Mark all
 * read reads them all. Escape, a click or the focus elsewhere closes it, and
 * Escape puts the focus back on the bell.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router";

import { api, useApiQuery } from "../api/client";
import type { components } from "../api/schema";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";
import { LoadError } from "../ui/LoadError";

type Notice = components["schemas"]["Notice"];

const NOTICES = ["get", "/api/kernel/notifications"] as const;
/** How many the panel shows: the newest. */
export const SHOWN = 10;

function When({ at }: { at: string }) {
  const moment = new Date(at);
  const shown = Number.isNaN(moment.getTime())
    ? at
    : moment.toLocaleString(undefined, { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
  return <time dateTime={at}>{shown}</time>;
}

/** A notice's page, when it's on this site: a path, never another site's address. */
function pageOf(notice: Notice): string | null {
  const link = notice.link;
  return link && link.startsWith("/") && !link.startsWith("//") ? link : null;
}

export function Notices() {
  const id = useId();
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();
  const notices = useApiQuery("get", "/api/kernel/notifications", { params: { query: { limit: SHOWN } } });
  const unread = notices.data?.unread ?? 0;

  useEffect(() => {
    if (!open) return;
    const away = (event: Event) => {
      if (event.target instanceof Node && box.current?.contains(event.target)) return;
      setOpen(false);
    };
    document.addEventListener("pointerdown", away);
    document.addEventListener("focusin", away);
    return () => {
      document.removeEventListener("pointerdown", away);
      document.removeEventListener("focusin", away);
    };
  }, [open]);

  const reread = () => queryClient.invalidateQueries({ queryKey: NOTICES });
  const markRead = (body: { ids: string[] } | { all: true }) => {
    api
      .POST("/api/kernel/notifications/read", { body })
      .then(reread)
      .catch((error: unknown) => {
        console.error("Marking notices read failed.", error);
      });
  };
  const items = notices.data?.items ?? [];

  return (
    <div
      ref={box}
      className="mf-admin-notices"
      onKeyDown={(event) => {
        if (event.key === "Escape" && open) {
          event.stopPropagation();
          setOpen(false);
          button.current?.focus();
        }
      }}
    >
      <button
        ref={button}
        type="button"
        className="mf-admin-icon-button"
        aria-label={unread > 0 ? `Notices, ${String(unread)} unread` : "Notices"}
        aria-expanded={open}
        aria-controls={`${id}-panel`}
        onClick={() => {
          setOpen((was) => !was);
        }}
      >
        <Icon name="bell" />
        {unread > 0 ? <span className="mf-admin-dot" aria-hidden="true" /> : null}
      </button>
      {open ? (
        <section id={`${id}-panel`} className="mf-admin-notices-panel" aria-labelledby={`${id}-title`}>
          <div className="mf-admin-notices-head">
            <h2 id={`${id}-title`} className="mf-admin-notices-title">
              Notices
            </h2>
            {unread > 0 ? (
              <Button
                size="small"
                onClick={() => {
                  markRead({ all: true });
                }}
              >
                Mark all read
              </Button>
            ) : null}
          </div>
          {notices.error ? (
            <LoadError what="Your notices" error={notices.error} onRetry={() => void notices.refetch()} inline />
          ) : notices.isPending ? null : items.length === 0 ? (
            <p className="mf-admin-notices-empty">Nothing yet. What the site tells you shows here.</p>
          ) : (
            <ul className="mf-admin-notices-list">
              {items.map((notice) => {
                const page = pageOf(notice);
                const words = (
                  <>
                    <span className="mf-admin-notice-title">
                      {notice.read_at ? null : <span className="mf-visually-hidden">Unread: </span>}
                      {notice.title}
                    </span>
                    <span className="mf-admin-notice-when">
                      <When at={notice.created_at} />
                    </span>
                  </>
                );
                return (
                  <li key={notice.id} className={notice.read_at ? "mf-admin-notice" : "mf-admin-notice mf-admin-notice--unread"}>
                    {page ? (
                      <Link
                        to={page}
                        onClick={() => {
                          setOpen(false);
                          if (!notice.read_at) markRead({ ids: [notice.id] });
                        }}
                      >
                        {words}
                      </Link>
                    ) : (
                      <span>{words}</span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
          <Link
            className="mf-admin-notices-choose"
            to="/account/notifications"
            onClick={() => {
              setOpen(false);
            }}
          >
            Choose what you're told
          </Link>
        </section>
      ) : null}
    </div>
  );
}
