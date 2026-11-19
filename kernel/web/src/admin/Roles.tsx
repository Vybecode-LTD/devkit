/**
 * `/admin/roles` (K4 contract §2 additions 4 and 5, §4 item 7; SPEC 14.8; VM
 * Website `AdminRoles.dc.html`): what each role can do, as a card per role
 * with how many hold it, and the permissions in groups against the roles
 * (`GET /api/auth/admin/roles`, `auth.user.manage`). With `auth.role.manage`,
 * New role and each of the site's own roles' Edit open the role's editor
 * (`POST`, `PUT` and `DELETE /api/auth/admin/roles…`, step-up). The built-in
 * roles stay as the site's modules declare them.
 *
 * Left off, not faked: Invite someone (K2 step 10), the reminder (no route
 * sends one), and per-resource grants such as "own" (decision 0042's non-goals).
 */
import { useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";

import { ApiProblem, api, useApiQuery } from "../api/client";
import { refusedQuietly } from "../auth/StepUp";
import { said } from "../auth/words";
import { useSession } from "../session/session";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { Dialog } from "../ui/Dialog";
import { Field, Input, Switch, TextArea } from "../ui/Field";
import { Icon } from "../ui/Icon";
import { LoadError } from "../ui/LoadError";
import { StatCard } from "../ui/StatCard";
import { Table, type Column } from "../ui/Table";
import { useToast } from "../ui/Toast";
import { AdminPage } from "./AdminPage";
import { OWNER, permissionGroups, useHeld, type PermissionGroup, type PermissionView, type RoleView } from "./roleAccess";

/** The server's pattern for a role's id: a letter, then letters, digits and dashes, 2 to 64 in all. */
export const ROLE_ID = /^[a-z][a-z0-9-]{1,63}$/;

/** An id from a name: "Beat makers" is "beat-makers". */
export function idFrom(name: string): string {
  const slug = name
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^[^a-z]+/, "")
    .replace(/-+$/, "")
    .slice(0, 64)
    .replace(/-+$/, "");
  return slug;
}

const REFUSED: Readonly<Record<string, string>> = {
  "auth.role_not_yours": "A role can carry only permissions you hold.",
  "auth.permission_unknown": "One of those permissions is no longer declared. Close this and open the role again.",
  "auth.role_builtin": "A built-in role stays as the site's modules declare it.",
  "auth.role_in_use": "Someone holds this role. Take it from them on People first.",
  "auth.role_not_found": "This role was just deleted.",
};

function Granted({ on }: { on: boolean }) {
  return on ? (
    <span className="mf-role-check mf-role-check--on">
      <Icon name="check" size={14} />
      <span className="mf-visually-hidden">Yes</span>
    </span>
  ) : (
    <span className="mf-role-check">
      <span className="mf-visually-hidden">No</span>
    </span>
  );
}

function Matrix({ group, roles }: { group: PermissionGroup; roles: readonly RoleView[] }) {
  const columns: Column<PermissionView>[] = [
    {
      key: "permission",
      header: "Permission",
      cell: (permission) => (
        <span className="mf-role-permission">
          <span>{permission.description || permission.key}</span>
          <code className="mf-role-key">{permission.key}</code>
        </span>
      ),
    },
    ...roles.map((role) => ({
      key: role.id,
      header: role.name,
      cell: (permission: PermissionView) => <Granted on={role.permissions.includes(permission.key)} />,
    })),
  ];
  return (
    <Table caption={group.label} columns={columns} rows={group.items} rowKey={(permission) => permission.key} />
  );
}

type Editing = { role: RoleView | null };

function RoleEditor({
  role,
  groups,
  onClose,
}: {
  role: RoleView | null;
  groups: readonly PermissionGroup[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { held, owner } = useHeld();
  const nameId = useId();
  const idId = useId();
  const describeId = useId();
  const [name, setName] = useState(role?.name ?? "");
  const [id, setId] = useState(role?.id ?? "");
  const [idTouched, setIdTouched] = useState(false);
  const [description, setDescription] = useState(role?.description ?? "");
  const [chosen, setChosen] = useState<ReadonlySet<string>>(new Set(role?.permissions ?? []));
  const [errors, setErrors] = useState<Readonly<Record<string, string>>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const shownId = role ? role.id : idTouched ? id : idFrom(name);

  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ["get", "/api/auth/admin/roles"] }),
      queryClient.invalidateQueries({ queryKey: ["get", "/api/auth/session"] }),
    ]);

  const failed = (caught: unknown) => {
    if (refusedQuietly(caught)) return;
    if (caught instanceof ApiProblem && caught.code === "auth.role_exists") {
      setErrors({ id: "A role already has that id. Pick another." });
      return;
    }
    if (caught instanceof ApiProblem && caught.code === "kernel.invalid_request") {
      setErrors(Object.fromEntries(Object.entries(caught.errors).map(([field, said]) => [field, said.join(" ")])));
      return;
    }
    setError(caught instanceof ApiProblem ? said(caught, REFUSED) : "That didn't work. Try again.");
  };

  const save = async () => {
    const found: Record<string, string> = {};
    if (!name.trim()) found.name = "Give the role a name.";
    if (!role && !ROLE_ID.test(shownId)) found.id = "Start with a letter; use lowercase letters, digits and dashes, 2 to 64 in all.";
    setErrors(found);
    setError("");
    if (Object.keys(found).length > 0) return;
    setBusy(true);
    try {
      const body = { name: name.trim(), description: description.trim(), permissions: [...chosen].sort() };
      if (role) {
        await api.PUT("/api/auth/admin/roles/{id}", { params: { path: { id: role.id } }, body });
      } else {
        await api.POST("/api/auth/admin/roles", { body: { ...body, id: shownId } });
      }
      await refresh();
      toast({ tone: "success", text: role ? `Saved ${body.name}.` : `Made ${body.name}.` });
      onClose();
    } catch (caught) {
      failed(caught);
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!role) return;
    setBusy(true);
    setError("");
    try {
      await api.DELETE("/api/auth/admin/roles/{id}", { params: { path: { id: role.id } } });
      await refresh();
      toast({ tone: "success", text: `Deleted ${role.name}.` });
      onClose();
    } catch (caught) {
      failed(caught);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog title={role ? `Edit ${role.name}` : "New role"} onClose={onClose} wide>
      <form
        className="mf-role-form"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
      >
        <Field label="Name" id={nameId} error={errors.name}>
          <Input
            id={nameId}
            value={name}
            maxLength={120}
            onChange={(event) => {
              setName(event.target.value);
            }}
          />
        </Field>
        {role ? null : (
          <Field label="Id" id={idId} hint="Lowercase letters, digits and dashes. It can't change later." error={errors.id}>
            <Input
              id={idId}
              value={shownId}
              maxLength={64}
              onChange={(event) => {
                setIdTouched(true);
                setId(event.target.value);
              }}
            />
          </Field>
        )}
        <Field label="What it's for" id={describeId} error={errors.description}>
          <TextArea
            id={describeId}
            value={description}
            maxLength={500}
            rows={2}
            onChange={(event) => {
              setDescription(event.target.value);
            }}
          />
        </Field>
        {groups.map((group) => (
          <fieldset key={group.label} className="mf-role-permissions">
            <legend>{group.label}</legend>
            {group.items.map((permission) => {
              const yours = owner || held.has(permission.key);
              return (
                <Switch
                  key={permission.key}
                  label={permission.description || permission.key}
                  hint={yours ? permission.key : `${permission.key}: you don't hold this one.`}
                  checked={chosen.has(permission.key)}
                  disabled={!yours || busy}
                  onChange={(on) => {
                    const next = new Set(chosen);
                    if (on) next.add(permission.key);
                    else next.delete(permission.key);
                    setChosen(next);
                  }}
                />
              );
            })}
          </fieldset>
        ))}
        {error ? (
          <p className="mf-dialog-error" role="alert">
            {error}
          </p>
        ) : null}
        <div className="mf-dialog-actions">
          <Button type="submit" variant="primary" disabled={busy}>
            {role ? "Save role" : "Make role"}
          </Button>
          <Button onClick={onClose}>Cancel</Button>
        </div>
        {role ? (
          <div className="mf-role-delete">
            {role.people > 0 ? (
              <p className="mf-role-delete-note">
                {role.people === 1 ? "One person holds" : `${String(role.people)} people hold`} this role. Take it from them on
                People before deleting it.
              </p>
            ) : deleting ? (
              <>
                <p className="mf-role-delete-note">Delete {role.name}? This can't be undone.</p>
                <div className="mf-dialog-actions">
                  <Button disabled={busy} onClick={() => void remove()}>
                    Delete {role.name}
                  </Button>
                  <Button
                    onClick={() => {
                      setDeleting(false);
                    }}
                  >
                    Keep it
                  </Button>
                </div>
              </>
            ) : (
              <Button
                onClick={() => {
                  setDeleting(true);
                }}
              >
                Delete role
              </Button>
            )}
          </div>
        ) : null}
      </form>
    </Dialog>
  );
}

export default function Roles() {
  const session = useSession();
  const read = useApiQuery("get", "/api/auth/admin/roles");
  const [editing, setEditing] = useState<Editing | null>(null);
  const canEdit = session.status === "signed-in" && session.can("auth.role.manage");
  const roles = read.data?.roles ?? [];
  const groups = permissionGroups(read.data?.permissions ?? []);

  return (
    <AdminPage
      page="Roles"
      title="Roles and permissions"
      lead="What each role can do. Owners can do everything; changes are written to the activity log."
      actions={
        canEdit && read.data ? (
          <Button
            variant="primary"
            icon="plus"
            onClick={() => {
              setEditing({ role: null });
            }}
          >
            New role
          </Button>
        ) : undefined
      }
    >
      {read.error ? (
        <LoadError what="The roles" error={read.error} onRetry={() => void read.refetch()} />
      ) : read.isPending ? null : (
        <>
          <ul className="mf-role-cards" aria-label="Roles">
            {roles.map((role) => (
              <li key={role.id} className="mf-role-card">
                <StatCard
                  label={role.name}
                  value={role.people}
                  line={role.id === OWNER ? "Everything, always" : role.description || (role.builtin ? "Built in" : "")}
                  level={2}
                />
                {canEdit && !role.builtin ? (
                  <Button
                    size="small"
                    aria-label={`Edit ${role.name}`}
                    onClick={() => {
                      setEditing({ role });
                    }}
                  >
                    Edit
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
          <Card flush>
            <div className="mf-role-matrix">
              {groups.map((group) => (
                <Matrix key={group.label} group={group} roles={roles} />
              ))}
            </div>
          </Card>
        </>
      )}
      {editing ? (
        <RoleEditor
          role={editing.role}
          groups={groups}
          onClose={() => {
            setEditing(null);
          }}
        />
      ) : null}
    </AdminPage>
  );
}
