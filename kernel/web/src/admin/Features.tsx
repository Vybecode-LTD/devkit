/**
 * `/admin/settings/features` (K4 contract §2 addition 7, change 19; SPEC 12;
 * VM Website `AdminSettings.dc.html`): each module the deploy's MODULES
 * allows, grouped by its kind, with its switch (`kernel.module.manage`).
 * Switching one off turns off every module that needs it, which keeps its own
 * switch, so the page asks first, naming them. A module that's switched on
 * while one it needs is off stays off, and says why.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiProblem, api, useApiQuery } from "../api/client";
import type { components } from "../api/schema";
import { said } from "../auth/words";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { Dialog } from "../ui/Dialog";
import { EmptyState } from "../ui/EmptyState";
import { Switch } from "../ui/Field";
import { LoadError } from "../ui/LoadError";
import { useToast } from "../ui/Toast";
import { and } from "../ui/words";
import { SettingsPage } from "./SettingsPage";

export type ModuleItem = components["schemas"]["ModuleItem"];

/** The manifests' categories (schema/module.schema.json), in the order the page shows them. */
export const CATEGORIES: readonly (readonly [string, string])[] = [
  ["content", "Content"],
  ["media", "Media"],
  ["community", "Community"],
  ["comms", "Messages and email"],
  ["commerce", "Shop and payments"],
  ["admin", "Running the site"],
  ["security", "Security"],
  ["ai", "AI"],
];

/** The modules in groups by category, in CATEGORIES' order; one of no known category goes last. */
export function grouped(items: readonly ModuleItem[]): { id: string; title: string; items: ModuleItem[] }[] {
  const known = new Map(CATEGORIES);
  const groups = new Map<string, ModuleItem[]>();
  for (const item of items) {
    const id = known.has(item.category) ? item.category : "other";
    groups.set(id, [...(groups.get(id) ?? []), item]);
  }
  const order = [...CATEGORIES.map(([id]) => id), "other"];
  return order
    .filter((id) => groups.has(id))
    .map((id) => ({ id, title: known.get(id) ?? "Other", items: groups.get(id) ?? [] }));
}

/** What a module's switch says under it: its summary, and why it's off if its switch is on. */
export function moduleHint(item: ModuleItem, byId: ReadonlyMap<string, ModuleItem>): string {
  if (!item.switched || item.on) return item.summary;
  const waiting = item.requires.filter((id) => !(byId.get(id)?.on ?? false)).map((id) => byId.get(id)?.name ?? id);
  const needs = waiting.length > 0 ? waiting : item.requires.map((id) => byId.get(id)?.name ?? id);
  return `${item.summary} Off while ${and(needs)} ${needs.length === 1 ? "is" : "are"} off.`;
}

const LIST = ["get", "/api/kernel/admin/modules"] as const;

export default function Features() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const read = useApiQuery("get", "/api/kernel/admin/modules");
  const [asking, setAsking] = useState<ModuleItem | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const items = read.data?.items ?? [];
  const byId = new Map(items.map((item) => [item.id, item]));

  const flip = async (item: ModuleItem, on: boolean) => {
    setBusy(item.id);
    try {
      const { data } = await api.PUT("/api/kernel/admin/modules/{id}", { params: { path: { id: item.id } }, body: { on } });
      if (data) queryClient.setQueryData(LIST, data);
      // The frame's menus and slots follow the modules on.
      await queryClient.invalidateQueries({ queryKey: ["get", "/api/kernel/modules"] });
      toast({ tone: "success", text: on ? `${item.name} is switched on.` : `${item.name} is switched off.` });
    } catch (caught) {
      toast({ tone: "danger", text: caught instanceof ApiProblem ? said(caught) : "That didn't work. Try again." });
      await queryClient.invalidateQueries({ queryKey: LIST });
    } finally {
      setBusy(null);
      setAsking(null);
    }
  };

  // Every module on that goes off with it, down the chain: what needs it,
  // what needs those, and so on (CodeRabbit on #87).
  const dependents = (item: ModuleItem): ModuleItem[] => {
    const found: ModuleItem[] = [];
    const seen = new Set([item.id]);
    const waiting = [...item.required_by];
    for (let id = waiting.shift(); id !== undefined; id = waiting.shift()) {
      if (seen.has(id)) continue;
      seen.add(id);
      const next = byId.get(id);
      if (!next) continue;
      if (next.on) found.push(next);
      waiting.push(...next.required_by);
    }
    return found;
  };

  const choose = (item: ModuleItem, on: boolean) => {
    if (!on && dependents(item).length > 0) {
      setAsking(item);
      return;
    }
    void flip(item, on);
  };

  let body;
  if (read.error) {
    body = <LoadError what="the site's modules" error={read.error} onRetry={() => void read.refetch()} />;
  } else if (!read.data) {
    body = <p className="mf-settings-quiet">Loading the modules…</p>;
  } else if (items.length === 0) {
    body = (
      <EmptyState title="No modules to switch">
        This site has no modules installed, or the host's MODULES leaves them all out.
      </EmptyState>
    );
  } else {
    body = grouped(items).map((group) => (
      <Card key={group.id} className="mf-settings-card" title={group.title}>
        {group.items.map((item) => (
          <Switch
            key={item.id}
            label={item.name}
            hint={moduleHint(item, byId)}
            checked={item.switched}
            disabled={busy !== null}
            onChange={(on) => {
              choose(item, on);
            }}
          />
        ))}
      </Card>
    ));
  }

  const off = asking ? dependents(asking) : [];
  return (
    <SettingsPage page="Features">
      <p className="mf-settings-lead">
        Switching a module off hides its pages and admin. Its data stays, and its background work waits until it's back on.
      </p>
      {body}
      {asking ? (
        <Dialog
          title={`Switch off ${asking.name}?`}
          onClose={() => {
            if (busy === null) setAsking(null);
          }}
        >
          <p className="mf-dialog-lead">
            {and(off.map((item) => item.name))} {off.length === 1 ? "needs" : "need"} {asking.name}, so{" "}
            {off.length === 1 ? "it goes" : "they go"} off too. Their data stays, and each keeps its own switch for when{" "}
            {asking.name} is back on.
          </p>
          <div className="mf-dialog-actions">
            <Button
              onClick={() => {
                setAsking(null);
              }}
              disabled={busy !== null}
            >
              Keep it on
            </Button>
            <Button
              variant="primary"
              disabled={busy !== null}
              onClick={() => {
                void flip(asking, false);
              }}
            >
              {busy === asking.id ? "Switching off…" : `Switch off ${String(off.length + 1)}`}
            </Button>
          </div>
        </Dialog>
      ) : null}
    </SettingsPage>
  );
}
