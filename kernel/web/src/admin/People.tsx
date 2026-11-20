/**
 * `/admin/people` (K4 contract §2 addition 4 and §4 item 7; SPEC 14.1; VM
 * Website `AdminPeople.dc.html`): everyone with an account, the newest first,
 * fifty at a time, found by address (`GET /api/auth/admin/users`,
 * `auth.user.manage`). Open someone to change their roles
 * (`PUT /api/auth/admin/users/{id}/roles`, `auth.role.assign`, step-up).
 *
 * Left off, not faked: Invite someone and the Invites tab (K2 step 10),
 * Export, the Staff and Members chips (the list has no filter by role), the
 * reminders (no route sends one), suspending and restoring from here, and
 * names (nothing sets one yet: the address stands in).
 */
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useState } from "react";

import { ApiProblem, api } from "../api/client";
import type { components } from "../api/schema";
import { refusedQuietly } from "../auth/StepUp";
import { said } from "../auth/words";
import { refreshSession, useSession } from "../session/session";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { Dialog } from "../ui/Dialog";
import { Field, Input, Switch } from "../ui/Field";
import { LoadError } from "../ui/LoadError";
import { Pill, type Tone } from "../ui/Pill";
import { Table, type Column } from "../ui/Table";
import { useToast } from "../ui/Toast";
import { AdminPage } from "./AdminPage";
import { MEMBER, roleName, useHeld, useRoles, whyNotGrant, type RoleView } from "./roleAccess";

export type Person = components["schemas"]["Person"];

/** How long typing rests before the list is asked again. */
export const SEARCH_REST_MS = 300;

function useRested(value: string, ms: number): string {
  const [rested, setRested] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => {
      setRested(value);
    }, ms);
    return () => {
      clearTimeout(timer);
    };
  }, [value, ms]);
  return rested;
}

function Day({ at }: { at: string | null }) {
  if (at === null) return <>Never</>;
  const moment = new Date(at);
  const shown = Number.isNaN(moment.getTime()) ? at : moment.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  return <time dateTime={at}>{shown}</time>;
}

/** A person's standing: suspended, being deleted, their email unconfirmed, or active. */
export function standing(person: Person): { tone: Tone; label: string } {
  if (person.status === "suspended") return { tone: "danger", label: "Suspended" };
  if (person.status === "deleting") return { tone: "neutral", label: "Being deleted" };
  if (!person.verified) return { tone: "warning", label: "Email not confirmed" };
  return { tone: "success", label: "Active" };
}

/** The roles a person's row shows: a member's role left out beside any other, as the board draws it. */
export function shownRoles(roles: readonly string[]): readonly string[] {
  const staff = roles.filter((role) => role !== MEMBER);
  return staff.length > 0 ? staff : roles;
}

/** Staff without a second factor can't open the admin: that's worth a warning, a member's isn't. */
export function secondFactor(person: Person): { tone: Tone; label: string } | null {
  if (person.second_factor) return { tone: "success", label: "On" };
  if (person.roles.some((role) => role !== MEMBER)) return { tone: "warning", label: "Not set up" };
  return null;
}

const REFUSED: Readonly<Record<string, string>> = {
  "auth.last_owner": "The site's last owner stays an owner. Make someone else an owner first.",
  "auth.role_not_yours": "You can only grant or remove a role whose permissions you all hold.",
  "auth.role_unknown": "One of those roles was just deleted. Close this and open the person again.",
  "auth.account_not_active": "This account is being deleted, or yours is no longer active.",
};

function PersonRoles({ person, roles, onClose }: { person: Person; roles: readonly RoleView[]; onClose: () => void }) {
  const session = useSession();
  const queryClient = useQueryClient();
  const toast = useToast();
  const { held, owner } = useHeld();
  const [chosen, setChosen] = useState<ReadonlySet<string>>(new Set(person.roles));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const same = chosen.size === person.roles.length && person.roles.every((role) => chosen.has(role));
  // Not while a save is on its way: its ending closes this dialog, and would
  // close another person's opened meanwhile (CodeRabbit on #85).
  const close = () => {
    if (!busy) onClose();
  };

  const save = async () => {
    setBusy(true);
    setError("");
    try {
      await api.PUT("/api/auth/admin/users/{id}/roles", { params: { path: { id: person.id } }, body: { roles: [...chosen] } });
      // A list still loading its first page (a search just begun) would be handed that read,
      // begun before this save, rather than read again: stop it first (K4's gate).
      await queryClient.cancelQueries({ queryKey: ["get", "/api/auth/admin/users"] });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["get", "/api/auth/admin/users"] }),
        queryClient.invalidateQueries({ queryKey: ["get", "/api/auth/admin/roles"] }),
        // Your own roles: the session is read again, a read begun before stopped.
        session.status === "signed-in" && session.user.id === person.id ? refreshSession(queryClient) : Promise.resolve(),
      ]);
      toast({ tone: "success", text: `Saved ${person.name ?? person.email}'s roles.` });
      onClose();
    } catch (caught) {
      if (refusedQuietly(caught)) return;
      setError(caught instanceof ApiProblem ? said(caught, REFUSED) : "That didn't work. Try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog title={person.name ?? person.email} onClose={close}>
      <p className="mf-people-dialog-lead">
        Their roles decide what they can do. Staff roles need a second factor before the admin opens for them.
      </p>
      <fieldset className="mf-people-roles">
        <legend>Roles</legend>
        {roles.map((role) => {
          const why = whyNotGrant(role, held, owner);
          return (
            <Switch
              key={role.id}
              label={role.name}
              hint={why ?? (role.description || undefined)}
              checked={chosen.has(role.id)}
              disabled={why !== null || busy}
              onChange={(on) => {
                const next = new Set(chosen);
                if (on) next.add(role.id);
                else next.delete(role.id);
                setChosen(next);
              }}
            />
          );
        })}
      </fieldset>
      {error ? (
        <p className="mf-dialog-error" role="alert">
          {error}
        </p>
      ) : null}
      <div className="mf-dialog-actions">
        <Button variant="primary" disabled={busy || same} onClick={() => void save()}>
          Save roles
        </Button>
        <Button disabled={busy} onClick={close}>
          Cancel
        </Button>
      </div>
    </Dialog>
  );
}

export default function People() {
  const session = useSession();
  const searchId = useId();
  const [typed, setTyped] = useState("");
  const q = useRested(typed.trim(), SEARCH_REST_MS);
  const roles = useRoles();
  const [open, setOpen] = useState<Person | null>(null);
  const canAssign = session.status === "signed-in" && session.can("auth.role.assign");
  const pages = useInfiniteQuery({
    queryKey: ["get", "/api/auth/admin/users", "pages", q],
    initialPageParam: "",
    queryFn: async ({ pageParam }) => {
      const query = { ...(q ? { q } : {}), ...(pageParam ? { cursor: pageParam } : {}) };
      const { data } = await api.GET("/api/auth/admin/users", { params: { query } });
      if (!data) throw ApiProblem.unreachable();
      return data;
    },
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const people = pages.data?.pages.flatMap((page) => page.items) ?? [];
  const known = roles.data?.roles;

  const columns: Column<Person>[] = [
    {
      key: "person",
      header: "Person",
      cell: (person) => (
        <span className="mf-people-who">
          <span className="mf-people-name">{person.name ?? person.email}</span>
          {person.name ? <span className="mf-people-email">{person.email}</span> : null}
        </span>
      ),
    },
    {
      key: "roles",
      header: "Roles",
      cell: (person) => (
        <span className="mf-people-pills">
          {shownRoles(person.roles).map((role) => (
            <Pill key={role} tone={role === MEMBER ? "neutral" : "info"}>
              {roleName(role, known)}
            </Pill>
          ))}
        </span>
      ),
    },
    {
      key: "factor",
      header: "Second factor",
      cell: (person) => {
        const factor = secondFactor(person);
        return factor ? <Pill tone={factor.tone}>{factor.label}</Pill> : <span className="mf-people-off">Off</span>;
      },
    },
    { key: "seen", header: "Last seen", cell: (person) => <Day at={person.last_seen_at} /> },
    {
      key: "status",
      header: "Status",
      cell: (person) => {
        const shown = standing(person);
        return <Pill tone={shown.tone}>{shown.label}</Pill>;
      },
    },
    ...(canAssign && known
      ? [
          {
            key: "open",
            header: <span className="mf-visually-hidden">Actions</span>,
            align: "end" as const,
            cell: (person: Person) => (
              <Button
                size="small"
                aria-label={`Open ${person.name ?? person.email}`}
                onClick={() => {
                  setOpen(person);
                }}
              >
                Open
              </Button>
            ),
          },
        ]
      : []),
  ];

  return (
    <AdminPage page="People" title="People" lead="Everyone with an account. Open someone to change their roles.">
      <div className="mf-people-search">
        <Field label="Search by email" id={searchId}>
          <Input
            id={searchId}
            type="search"
            value={typed}
            placeholder="name@example.com"
            onChange={(event) => {
              setTyped(event.target.value);
            }}
          />
        </Field>
      </div>
      {roles.error ? (
        // The list still shows; Open waits for the roles (CodeRabbit on #85).
        <LoadError what="The roles" error={roles.error} onRetry={() => void roles.refetch()} inline />
      ) : null}
      {pages.error ? (
        <LoadError what="The people list" error={pages.error} onRetry={() => void pages.refetch()} />
      ) : pages.isPending ? null : (
        <Card flush>
          <Table
            caption={q ? `People whose email holds "${q}", newest first` : "People, newest first"}
            captionHidden
            columns={columns}
            rows={people}
            rowKey={(person) => person.id}
            empty={<p className="mf-needs-clear">{q ? "No one's email holds that." : "No one has an account yet."}</p>}
          />
          {pages.hasNextPage ? (
            <div className="mf-activity-more">
              <Button disabled={pages.isFetchingNextPage} onClick={() => void pages.fetchNextPage()}>
                Show more
              </Button>
            </div>
          ) : null}
        </Card>
      )}
      {open && known ? (
        <PersonRoles
          person={open}
          roles={known}
          onClose={() => {
            setOpen(null);
          }}
        />
      ) : null}
    </AdminPage>
  );
}
