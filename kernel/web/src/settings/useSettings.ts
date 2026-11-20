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
import { useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { api, useApiQuery } from "../api/client";
import { ApiProblem } from "../api/problem";
import type { components } from "../api/schema";
import { resolveConflict, settingsConflict, type Choices, type SettingsConflict } from "../ui/SaveConflict";
import type { HistoryVersion } from "../ui/SectionHistory";
import { SettingsGroupContext } from "./group";

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
  // What the person's changes began from: the version and values read when
  // they made their first, kept until they're saved or discarded. A read in
  // the background (a focus) may move the section on meanwhile; the save
  // still goes at this version, so the kernel can tell the edit never saw
  // what changed since and merges it, or says it's a conflict (Codex on #87).
  const [base, setBase] = useState<{ version: number; values: SettingsValues } | null>(null);
  // What a save on its way sent. A field in it that the person has set to
  // anything else since, back to where its edit began included, is a change:
  // the newest word, kept from a move away and saved after (CodeRabbit on #87).
  const [flying, setFlying] = useState<Readonly<Record<string, unknown>>>({});

  const saved = query.data?.values ?? EMPTY;
  const from = useMemo(() => base ?? (query.data ? { version: query.data.version, values: query.data.values } : null), [base, query.data]);
  const fromValues = from?.values ?? EMPTY;
  // With no edit left (saved, discarded, or changed back), the form begins
  // again from what's saved (CodeRabbit on #87): settled while drawing.
  if (base !== null && Object.keys(draft).length === 0) setBase(null);
  // The latest read, for a save that ends after the render that sent it.
  const latest = useRef(query.data);
  useLayoutEffect(() => {
    latest.current = query.data;
  });
  const changes = useMemo(
    () =>
      Object.fromEntries(
        Object.entries(draft).filter(([field, value]) => !same(value, fromValues[field]) || (field in flying && !same(value, flying[field]))),
      ),
    [draft, fromValues, flying],
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
    async (version: number, sent: Readonly<Record<string, unknown>>, kept: Readonly<Record<string, unknown>> = {}): Promise<SaveOutcome> => {
      setSaving(true);
      setErrors({});
      setFlying(sent);
      try {
        const { data } = await api.PUT("/api/kernel/admin/settings/{id}", { ...init, body: { version, changes: { ...sent } } });
        setConflict(null);
        // What was saved leaves the draft, and so does each field the person
        // gave to the other save, as it was when they did; anything typed
        // while this was on its way stays (CodeRabbit on #87).
        setDraft((now) =>
          Object.fromEntries(
            Object.entries(now).filter(
              ([field, value]) => !(field in kept && same(value, kept[field])) && !(field in sent && same(value, sent[field])),
            ),
          ),
        );
        // An edit made while this was on its way keeps the values it started
        // from, with this save's on top. It moves on to the version this save
        // made only if no one else saved in between: then that version is the
        // edit's start with this save applied. Otherwise it may hold another
        // admin's change to the same field, so the edit keeps its first
        // version and the kernel still finds the conflict (CodeRabbit on #87).
        setBase((now) => {
          if (!data) return null;
          const started = now?.values ?? latest.current?.values ?? EMPTY;
          const onlyThis = data.changed.length > 0 ? data.version === version + 1 : data.version === version;
          return { version: onlyThis ? data.version : (now?.version ?? version), values: { ...started, ...sent } };
        });
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
        setFlying({});
        setSaving(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [reread, id],
  );

  const save = useCallback(async (): Promise<SaveOutcome> => {
    if (from === null || !dirty) return { status: "unchanged" };
    return send(from.version, changes);
  }, [from, dirty, send, changes]);

  const resolve = useCallback(
    async (choices: Choices): Promise<SaveOutcome> => {
      if (conflict === null) return { status: "unchanged" };
      const again = resolveConflict(changes, conflict, choices);
      const theirs = conflict.conflicts.filter(({ field }) => choices[field] === "theirs").map(({ field }) => field);
      return send(again.version, again.changes, Object.fromEntries(theirs.map((field) => [field, draft[field]])));
    },
    [conflict, changes, send, draft],
  );

  // On a page with one Save (the Site tab), this form joins it while drawn.
  const group = useContext(SettingsGroupContext);
  const key = useRef<symbol>(Symbol(id));
  const saveNow = useRef(save);
  useLayoutEffect(() => {
    saveNow.current = save;
  });
  useEffect(() => {
    group?.join(key.current, { dirty, save: () => saveNow.current() });
  }, [group, dirty]);
  useEffect(() => {
    if (!group) return;
    const mine = key.current;
    return () => {
      group.leave(mine);
    };
  }, [group]);

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
      const read = query.data;
      if (from !== null && field in from.values && same(value, from.values[field]) && !(field in flying)) {
        // Changed back to where it began: no longer an edit (CodeRabbit on #87).
        // Not while a save of it is on its way: then it's the latest word.
        setDraft((now) => Object.fromEntries(Object.entries(now).filter(([key]) => key !== field)));
      } else {
        if (read) setBase((now) => now ?? { version: read.version, values: read.values });
        setDraft((now) => ({ ...now, [field]: value }));
      }
      setErrors((now) => (field in now ? Object.fromEntries(Object.entries(now).filter(([key]) => key !== field)) : now));
    },
    discard: () => {
      setDraft({});
      setBase(null);
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
