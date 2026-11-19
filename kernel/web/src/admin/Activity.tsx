/**
 * `/admin/activity`, the activity log (K4 contract §2 and §4 item 6; SPEC
 * 14.10; VM Website `AdminActivity.dc.html`): who did what, and when, from
 * every module's entries (`GET /api/kernel/admin/audit`, `auth.audit.read`),
 * newest first, fifty at a time, filtered by kind. Picking what happened
 * shows everything the entry holds beneath the table. Entries can't be
 * edited or deleted, and leave on their own once past the keep.
 *
 * The board's search and Export CSV have no route behind them yet, so they're
 * left off, not drawn (as K4.5 left off what had no home).
 */
import { useInfiniteQuery } from "@tanstack/react-query";
import { Fragment, useState } from "react";

import { ApiProblem, api } from "../api/client";
import type { components } from "../api/schema";
import { Accordion } from "../ui/Accordion";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { LoadError } from "../ui/LoadError";
import { Chip, Pill } from "../ui/Pill";
import { Table, type Column } from "../ui/Table";
import { KINDS, kindOf, whatHappened, type Kind } from "./actions";
import { AdminPage } from "./AdminPage";

type Entry = components["schemas"]["AuditEntry"];
type Person = components["schemas"]["AuditPerson"];
type People = Readonly<Record<string, Person>>;

/** What staff read for the kernel itself: the board's "MechFrame, System". */
export const SYSTEM = { name: "MechFrame", role: "System" } as const;

function When({ at }: { at: string }) {
  const moment = new Date(at);
  const shown = Number.isNaN(moment.getTime())
    ? at
    : moment.toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" });
  return <time dateTime={at}>{shown}</time>;
}

function roleNames(person: Person): string {
  const held = person.roles.filter((role) => role.id !== "member");
  return (held.length > 0 ? held : person.roles).map((role) => role.name).join(", ");
}

/** Who did it: their name or email and their roles; the kernel itself; someone not signed in; or an account since removed. */
export function who(entry: Entry, people: People): { name: string; role: string } {
  if (entry.actor_id === null) {
    return entry.ip !== null || entry.user_agent !== "" ? { name: "Someone", role: "Not signed in" } : SYSTEM;
  }
  const person = people[entry.actor_id];
  if (!person) return { name: "A removed account", role: "" };
  return { name: person.name ?? person.email, role: roleNames(person) };
}

function subjectName(entry: Entry, people: People): string {
  if (entry.subject_id === null) return "someone";
  const person = people[entry.subject_id];
  return person ? (person.name ?? person.email) : "a removed account";
}

export function said(entry: Entry, people: People): string {
  const what = whatHappened(entry.action, subjectName(entry, people));
  return entry.result === "success" ? what : `${what} (didn't go through)`;
}

function words(key: string): string {
  const spaced = key.replace(/[_.]+/g, " ").trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

function shown(value: unknown): string {
  if (value === null) return "None";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  // A list of plain values reads as words: "description, logo".
  if (Array.isArray(value) && value.every((each) => ["string", "number", "boolean"].includes(typeof each))) return value.join(", ");
  return JSON.stringify(value);
}

/** The details column: an entry's first two details, "Method: totp". */
export function summary(entry: Entry): string {
  return Object.entries(entry.details)
    .slice(0, 2)
    .map(([key, value]) => `${words(key)}: ${shown(value)}`)
    .join(", ");
}

function EntryPanel({ entry, people }: { entry: Entry; people: People }) {
  const by = who(entry, people);
  return (
    <div className="mf-activity-entry" id="activity-entry">
      <Accordion
        id={`activity-entry-${String(entry.id)}`}
        title={said(entry, people)}
        meta={
          <>
            <When at={entry.at} />, by {by.name}
          </>
        }
        defaultOpen
      >
        <dl className="mf-activity-fields">
          <dt>When</dt>
          <dd>
            <When at={entry.at} />
          </dd>
          <dt>By</dt>
          <dd>{by.role ? `${by.name}, ${by.role}` : by.name}</dd>
          <dt>Result</dt>
          <dd>{entry.result === "success" ? "Went through" : "Didn't go through"}</dd>
          {Object.entries(entry.details).map(([key, value]) => (
            <Fragment key={key}>
              <dt>{words(key)}</dt>
              <dd>{shown(value)}</dd>
            </Fragment>
          ))}
          {entry.target ? (
            <>
              <dt>About</dt>
              <dd>
                {entry.target.type} {entry.target.id}
              </dd>
            </>
          ) : null}
          {entry.ip ? (
            <>
              <dt>From</dt>
              <dd>{entry.ip}</dd>
            </>
          ) : null}
          {entry.user_agent ? (
            <>
              <dt>Browser</dt>
              <dd>{entry.user_agent}</dd>
            </>
          ) : null}
          <dt>Entry</dt>
          <dd>{entry.id}</dd>
        </dl>
      </Accordion>
    </div>
  );
}

export default function Activity() {
  const [kind, setKind] = useState<Kind | null>(null);
  const [picked, setPicked] = useState<number | null>(null);
  const pages = useInfiniteQuery({
    queryKey: ["get", "/api/kernel/admin/audit", "pages", kind?.label ?? "all"],
    initialPageParam: "",
    queryFn: async ({ pageParam }) => {
      const query = {
        ...(kind ? { action: [...kind.actions] } : {}),
        ...(pageParam ? { cursor: pageParam } : {}),
      };
      const { data } = await api.GET("/api/kernel/admin/audit", { params: { query } });
      if (!data) throw ApiProblem.unreachable();
      return data;
    },
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const entries = pages.data?.pages.flatMap((page) => page.items) ?? [];
  const people: People = Object.fromEntries((pages.data?.pages ?? []).flatMap((page) => Object.entries(page.people)));
  const kept = pages.data?.pages[0]?.kept_days;
  const chosen = entries.find((entry) => entry.id === picked) ?? entries[0];

  const columns: Column<Entry>[] = [
    { key: "when", header: "When", cell: (entry) => <span className="mf-activity-when"><When at={entry.at} /></span> },
    {
      key: "who",
      header: "Who",
      cell: (entry) => {
        const by = who(entry, people);
        return (
          <span className="mf-activity-who">
            <span className="mf-activity-name">{by.name}</span>
            {by.role ? <span className="mf-activity-role">{by.role}</span> : null}
          </span>
        );
      },
    },
    {
      key: "what",
      header: "What happened",
      cell: (entry) => (
        <button
          type="button"
          className="mf-activity-what"
          aria-pressed={entry.id === chosen?.id}
          aria-controls="activity-entry"
          onClick={() => {
            setPicked(entry.id);
          }}
        >
          {said(entry, people)}
        </button>
      ),
    },
    { key: "details", header: "Details", cell: (entry) => <span className="mf-activity-details">{summary(entry)}</span> },
    { key: "kind", header: "Kind", cell: (entry) => <Pill>{kindOf(entry.action)}</Pill> },
  ];

  const choose = (next: Kind | null) => {
    setKind(next);
    setPicked(null);
  };

  return (
    <AdminPage page="Activity" crumb="Activity log" title="Activity log" lead="Who did what, and when. Entries can't be edited or deleted.">
      <div role="group" aria-label="Kind" className="mf-activity-kinds">
        <Chip
          pressed={kind === null}
          onPressedChange={() => {
            choose(null);
          }}
        >
          All
        </Chip>
        {KINDS.map((each) => (
          <Chip
            key={each.label}
            pressed={kind === each}
            onPressedChange={(pressed) => {
              choose(pressed ? each : null);
            }}
          >
            {each.label}
          </Chip>
        ))}
      </div>
      {pages.error ? (
        <LoadError what="The activity log" error={pages.error} onRetry={() => void pages.refetch()} />
      ) : pages.isPending ? null : (
        <>
          <Card flush>
            <Table
              caption={kind ? `${kind.label} entries, newest first` : "Entries, newest first"}
              captionHidden
              columns={columns}
              rows={entries}
              rowKey={(entry) => entry.id}
              empty={<p className="mf-needs-clear">Nothing here yet.</p>}
            />
            {pages.hasNextPage ? (
              <div className="mf-activity-more">
                <Button disabled={pages.isFetchingNextPage} onClick={() => void pages.fetchNextPage()}>
                  Show older
                </Button>
              </div>
            ) : null}
          </Card>
          {chosen ? <EntryPanel key={chosen.id} entry={chosen} people={people} /> : null}
          {kept === undefined ? null : (
            <p className="mf-activity-kept">Kept for {kept} days. Older entries leave the log on their own.</p>
          )}
        </>
      )}
    </AdminPage>
  );
}
