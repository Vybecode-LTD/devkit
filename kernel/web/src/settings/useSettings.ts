/**
 * A settings section as an admin form edits it (K4 contract §2, `useSettings`;
 * change 19): `GET /api/kernel/admin/settings/{id}` read, the person's draft
 * on top, and a save that sends only what they changed, at the version the
 * form was read at, so the kernel merges it with any save since
 * (`kernel.settings`). A field both changed comes back as a conflict for
 * `SaveConflict`, and `resolve` sends again with the person's choices.
 *
 * A secret reads as `{kept, changes}` and is typed to change: `set(field,
 * "text")` replaces it, `set(field, "")` removes it.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";

import { api, useApiQuery } from "../api/client";
import { ApiProblem } from "../api/problem";
import type { components } from "../api/schema";
import { resolveConflict, settingsConflict, type Choices, type SettingsConflict } from "../ui/SaveConflict";
import type { HistoryVersion } from "../ui/SectionHistory";

export type SettingsValues = Readonly<Record<string, unknown>>;
export type SettingsHistoryPage = components["schemas"]["SettingsHistory"];

/** How a save went: saved, a conflict to resolve, or refused (field errors, or a problem said). */
export type SaveOutcome =
  | { status: "saved"; changed: readonly string[]; merged: readonly string[] }
  | { status: "unchanged" }
  | { status: "conflict"; conflict: SettingsConflict }
  | { status: "refused"; problem: unknown };

export type SettingsForm = {
  /** The section's id: `kernel.site`, or a module's. */
  id: string;
  read: "loading" | "failed" | "read";
  /** Why the read failed, and a way to try again. */
  problem: ApiProblem | null;
  retry: () => void;
  /** The version the form was read at; null until it's read. */
  version: number | null;
  /** The values as saved. */
  saved: SettingsValues;
  /** The values the form shows: what's saved with the person's changes on top. */
  values: SettingsValues;
  /** Only what the person changed, by field. */
  changes: SettingsValues;
  dirty: boolean;
  set: (field: string, value: unknown) => void;
  discard: () => void;
  save: () => Promise<SaveOutcome>;
  saving: boolean;
  /** The last save's errors beside their fields, by field. */
  errors: Readonly<Record<string, string>>;
  /** The last save's conflict, until it's resolved or put away. */
  conflict: SettingsConflict | null;
  resolve: (choices: Choices) => Promise<SaveOutcome>;
  dropConflict: () => void;
  /** The section's saves, newest first, and their savers' names by id (`SectionHistory`). */
  history: () => Promise<{ versions: readonly HistoryVersion[]; names: Readonly<Record<string, string>> }>;
};

const same = (one: unknown, other: unknown): boolean => JSON.stringify(one) === JSON.stringify(other);

const EMPTY: SettingsValues = {};

/** The section's history, read in pages: the first hundred saves. */
const HISTORY_LIMIT = 100;

/** A field's errors as one line, by the field's name ("same_as.0" is `same_as`). */
function fieldErrors(problem: ApiProblem): Record<string, string> {
  const found: Record<string, string[]> = {};
  for (const [key, messages] of Object.entries(problem.errors)) {
    const field = key.replace(/^body\.changes\./, "").split(".")[0] ?? key;
    (found[field] ??= []).push(...messages);
  }
  return Object.fromEntries(Object.entries(found).map(([field, messages]) => [field, messages.join(" ")]));
}

export function useSettings(id: string): SettingsForm {
  const queryClient = useQueryClient();
  const init = { params: { path: { id } } };
  const query = useApiQuery("get", "/api/kernel/admin/settings/{id}", init);
  const [draft, setDraft] = useState<Readonly<Record<string, unknown>>>({});
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Readonly<Record<string, string>>>({});
  const [conflict, setConflict] = useState<SettingsConflict | null>(null);

  const saved = query.data?.values ?? EMPTY;
  const changes = useMemo(
    () => Object.fromEntries(Object.entries(draft).filter(([field, value]) => !same(value, saved[field]))),
    [draft, saved],
  );
  const values = useMemo(() => ({ ...saved, ...draft }), [saved, draft]);
  const dirty = Object.keys(changes).length > 0;

  const reread = useCallback(
    () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ["get", "/api/kernel/admin/settings/{id}", init] }),
        queryClient.invalidateQueries({ queryKey: ["get", "/api/kernel/admin/settings/{id}/history"] }),
        // A section the site's frame reads (its name, card and description) shows the save.
        queryClient.invalidateQueries({ queryKey: ["get", "/api/kernel/site"] }),
        queryClient.invalidateQueries({ queryKey: ["get", "/api/kernel/admin/attention"] }),
      ]),
    // `init` is made from `id` alone.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [queryClient, id],
  );

  const send = useCallback(
    async (version: number, sent: Readonly<Record<string, unknown>>, kept: readonly string[] = []): Promise<SaveOutcome> => {
      setSaving(true);
      setErrors({});
      try {
        const { data } = await api.PUT("/api/kernel/admin/settings/{id}", { ...init, body: { version, changes: { ...sent } } });
        setConflict(null);
        // What was saved leaves the draft, and so does each field the person
        // gave to the other save; anything typed while this was on its way stays.
        setDraft((now) =>
          Object.fromEntries(Object.entries(now).filter(([field, value]) => !kept.includes(field) && !(field in sent && same(value, sent[field])))),
        );
        await reread();
        if (!data || data.changed.length === 0) return { status: "unchanged" };
        return { status: "saved", changed: data.changed, merged: data.merged };
      } catch (caught) {
        const found = settingsConflict(caught);
        if (found) {
          setConflict(found);
          return { status: "conflict", conflict: found };
        }
        if (caught instanceof ApiProblem && caught.code === "kernel.invalid_request") setErrors(fieldErrors(caught));
        return { status: "refused", problem: caught };
      } finally {
        setSaving(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [reread, id],
  );

  const save = useCallback(async (): Promise<SaveOutcome> => {
    if (query.data === undefined || !dirty) return { status: "unchanged" };
    return send(query.data.version, changes);
  }, [query.data, dirty, send, changes]);

  const resolve = useCallback(
    async (choices: Choices): Promise<SaveOutcome> => {
      if (conflict === null) return { status: "unchanged" };
      const again = resolveConflict(changes, conflict, choices);
      const theirs = conflict.conflicts.filter(({ field }) => choices[field] === "theirs").map(({ field }) => field);
      return send(again.version, again.changes, theirs);
    },
    [conflict, changes, send],
  );

  const history = useCallback(async () => {
    const { data } = await api.GET("/api/kernel/admin/settings/{id}/history", { params: { path: { id }, query: { limit: HISTORY_LIMIT } } });
    const people = data?.people ?? {};
    return {
      versions: data?.items ?? [],
      names: Object.fromEntries(Object.entries(people).map(([person, found]) => [person, found.name ?? found.email])),
    };
  }, [id]);

  return {
    id,
    read: query.data !== undefined ? "read" : query.error ? "failed" : "loading",
    problem: query.error ?? null,
    retry: () => {
      void query.refetch();
    },
    version: query.data?.version ?? null,
    saved,
    values,
    changes,
    dirty,
    set: (field, value) => {
      setDraft((now) => ({ ...now, [field]: value }));
      setErrors((now) => (field in now ? Object.fromEntries(Object.entries(now).filter(([key]) => key !== field)) : now));
    },
    discard: () => {
      setDraft({});
      setErrors({});
      setConflict(null);
    },
    save,
    saving,
    errors,
    conflict,
    resolve,
    dropConflict: () => {
      setConflict(null);
    },
    history,
  };
}
