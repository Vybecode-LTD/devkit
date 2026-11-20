/**
 * `/admin/settings`, the Site tab (K4 contract §2 addition 6, change 19; VM
 * Website `AdminSettings.dc.html`): the site's identity (the settings section
 * `kernel.site`) and who may make an account (`kernel.auth`), then each
 * module's section (`admin.settings.section`). Save sends each section's
 * changes at the version it was read at; a field someone else changed
 * meanwhile comes back as a conflict to settle. The board's Save, in the
 * page's header, is the page's one Save; leaving with changes asks first.
 *
 * Left off, not faked: the board's tagline, address, contact email and time
 * zone (no section holds them), and "Members must use a second factor"
 * (nothing enforces it). The name is the host's SITE_NAME, shown as it is.
 */
import { Suspense, useCallback, useId, useMemo, useState, type ComponentPropsWithRef, type ReactNode } from "react";

import { ApiProblem } from "../api/problem";
import { lazyPart } from "../app/lazy";
import { said } from "../auth/words";
import { useSite } from "../site/site";
import { SettingsGroupContext, type GroupMember, type SettingsGroup } from "../settings/group";
import { useSettings, type SaveOutcome, type SettingsForm } from "../settings/useSettings";
import { useSlot } from "../slots/slots";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { ErrorBoundary } from "../ui/ErrorBoundary";
import { Field, Input, Select, Switch, TextArea } from "../ui/Field";
import { LoadError } from "../ui/LoadError";
import { SaveConflict } from "../ui/SaveConflict";
import { SectionHistory } from "../ui/SectionHistory";
import { useToast } from "../ui/Toast";
import { UnsavedDialog } from "../ui/UnsavedDialog";
import { useUnsavedGuard } from "../ui/unsaved";
import { SettingsPage } from "./SettingsPage";

export const SITE_LABELS: Readonly<Record<string, string>> = {
  description: "Description",
  kind: "What the site is",
  logo: "Logo",
  card_image: "Share image",
  same_as: "Profiles elsewhere",
  llms_summary: "Summary for AI tools",
  ai_crawlers: "AI crawlers",
};

export const ACCOUNT_LABELS: Readonly<Record<string, string>> = { sign_up_mode: "Sign-up" };

const KINDS = [
  ["Organization", "An organization"],
  ["LocalBusiness", "A local business"],
  ["MusicGroup", "A band or music group"],
  ["Person", "A person"],
] as const;

const text = (value: unknown): string => (typeof value === "string" ? value : "");
const lines = (value: unknown): string => (Array.isArray(value) ? value.map(String).join("\n") : "");
const listed = (typed: string): string[] =>
  typed
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

/**
 * A list a line each, kept as typed while it's edited, so Enter starts the
 * next line; the form holds the lines trimmed, the blank ones left out
 * (Codex on #87). A list from elsewhere (a discard, a save read back)
 * replaces what's shown.
 */
function LinesArea({ value, onList, ...rest }: { value: unknown; onList: (list: string[]) => void } & Omit<ComponentPropsWithRef<"textarea">, "value" | "onChange">) {
  const [text, setText] = useState(() => lines(value));
  const wanted = JSON.stringify(listed(lines(value)));
  if (JSON.stringify(listed(text)) !== wanted) setText(lines(value));
  return (
    <TextArea
      {...rest}
      value={text}
      onChange={(event) => {
        setText(event.target.value);
        onList(listed(event.target.value));
      }}
    />
  );
}

/** What the sign-up switch says under itself, by the mode saved. */
export function signUpHint(mode: unknown): string {
  if (mode === "open") return "New accounts are members. Staff roles are given in People.";
  if (mode === "invite") return "Invite only, so no one can join until invites arrive. Switch it on to let anyone sign up.";
  return "The site takes no new accounts. Switch it on to let anyone sign up as a member.";
}

const SAVE_PROBLEMS: Readonly<Record<string, string>> = {
  "kernel.settings_version_unknown": "These settings changed in a way this page can't follow. Reload the page and make your change again.",
};

/** A save's outcome as the one line the page says, or null once it's saved. */
function sayOutcome(outcome: SaveOutcome): string | null {
  if (outcome.status === "saved" || outcome.status === "unchanged") return null;
  if (outcome.status === "conflict") return "Someone else saved these settings since you opened them. Choose which values to keep.";
  const { problem } = outcome;
  if (problem instanceof ApiProblem) {
    if (problem.code === "kernel.invalid_request") return "Some of these settings aren't valid. Check the fields marked.";
    return said(problem, SAVE_PROBLEMS);
  }
  return "That didn't work. Try again.";
}

function Conflict({ form, labels }: { form: SettingsForm; labels: Readonly<Record<string, string>> }) {
  const toast = useToast();
  if (!form.conflict) return null;
  return (
    <SaveConflict
      conflict={form.conflict}
      labels={labels}
      saving={form.saving}
      onResolve={(choices) => {
        void form.resolve(choices).then((outcome) => {
          const problem = sayOutcome(outcome);
          toast(problem ? { tone: "danger", text: problem } : { tone: "success", text: "Settings saved." });
        });
      }}
      onCancel={form.dropConflict}
    />
  );
}

/** A section's saves, with each saver named (their name, or their address). */
function History({ form, labels }: { form: SettingsForm; labels: Readonly<Record<string, string>> }) {
  const [names, setNames] = useState<Readonly<Record<string, string>>>({});
  const { history } = form;
  const load = useCallback(
    () =>
      history().then((got) => {
        setNames(got.names);
        return got.versions;
      }),
    [history],
  );
  return <SectionHistory version={form.version} labels={labels} load={load} names={names} />;
}

function ModuleSections() {
  const sections = useSlot("admin.settings.section");
  return (
    <>
      {sections.map((section) => {
        const Part = lazyPart(section.lazy);
        return (
          <Card key={section.key} className="mf-settings-card" title={section.title} description={`From the ${section.module} module`}>
            <ErrorBoundary where={`${section.module}'s settings section`}>
              <Suspense fallback={<p className="mf-settings-quiet">Loading…</p>}>
                <Part />
              </Suspense>
            </ErrorBoundary>
          </Card>
        );
      })}
    </>
  );
}

function Loaded({ forms, children }: { forms: readonly SettingsForm[]; children: ReactNode }) {
  const failed = forms.find((form) => form.read === "failed");
  if (failed) {
    return (
      <LoadError what="the site's settings" error={failed.problem} onRetry={failed.retry} />
    );
  }
  if (forms.some((form) => form.read === "loading")) return <p className="mf-settings-quiet">Loading the settings…</p>;
  return <>{children}</>;
}

export default function Site() {
  const formId = useId();
  const toast = useToast();
  const site = useSite();
  const identity = useSettings("kernel.site");
  const accounts = useSettings("kernel.auth");
  const forms = [identity, accounts];
  // The modules' sections drawn below, each a useSettings form that joins
  // this page's one Save and its question (CodeRabbit on #87).
  const [members, setMembers] = useState<ReadonlyMap<symbol, GroupMember>>(new Map());
  const group = useMemo<SettingsGroup>(
    () => ({
      join: (key, member) => {
        setMembers((now) => new Map(now).set(key, member));
      },
      leave: (key) => {
        setMembers((now) => {
          if (!now.has(key)) return now;
          const next = new Map(now);
          next.delete(key);
          return next;
        });
      },
    }),
    [],
  );
  const dirty = identity.dirty || accounts.dirty || [...members.values()].some((member) => member.dirty);
  const saving = identity.saving || accounts.saving;

  const saveAll = useCallback(async (): Promise<string | null> => {
    for (const form of [identity, accounts, ...members.values()]) {
      if (!form.dirty) continue;
      const problem = sayOutcome(await form.save());
      if (problem) return problem;
    }
    return null;
  }, [identity, accounts, members]);

  const guard = useUnsavedGuard(dirty, saveAll);

  const submit = () => {
    void saveAll().then((problem) => {
      toast(problem ? { tone: "danger", text: problem } : { tone: "success", text: "Settings saved." });
    });
  };

  const values = identity.values;
  const mode = accounts.values.sign_up_mode;

  return (
    <SettingsPage
      page="Settings"
      actions={
        <Button type="submit" form={formId} variant="primary" disabled={!dirty || saving}>
          {saving ? "Saving…" : "Save"}
        </Button>
      }
    >
      <Loaded forms={forms}>
        <form
          id={formId}
          className="mf-settings-form"
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
        >
          <Card className="mf-settings-card" title="The site">
            <Conflict form={identity} labels={SITE_LABELS} />
            <div className="mf-settings-grid">
              <Field label="Site name" hint="Set on the host, as SITE_NAME.">
                <Input value={site?.name ?? ""} readOnly />
              </Field>
              <Field label={SITE_LABELS.kind} error={identity.errors.kind}>
                <Select
                  value={text(values.kind)}
                  onChange={(event) => {
                    identity.set("kind", event.target.value);
                  }}
                >
                  {KINDS.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label={SITE_LABELS.logo} hint="An https address, or a path on this site such as /logo.png." error={identity.errors.logo}>
                <Input
                  value={text(values.logo)}
                  maxLength={2000}
                  onChange={(event) => {
                    identity.set("logo", event.target.value);
                  }}
                />
              </Field>
              <Field label={SITE_LABELS.card_image} hint="Shown beside a link to the site wherever it's shared." error={identity.errors.card_image}>
                <Input
                  value={text(values.card_image)}
                  maxLength={2000}
                  onChange={(event) => {
                    identity.set("card_image", event.target.value);
                  }}
                />
              </Field>
            </div>
            <Field
              label={SITE_LABELS.description}
              hint="Search engines and AI answers describe the site with it. At most 300 characters."
              error={identity.errors.description}
            >
              <TextArea
                rows={3}
                maxLength={300}
                value={text(values.description)}
                onChange={(event) => {
                  identity.set("description", event.target.value);
                }}
              />
            </Field>
            <Field label={SITE_LABELS.same_as} hint="The site's pages on other services, one address on each line." error={identity.errors.same_as}>
              <LinesArea
                rows={3}
                value={values.same_as}
                onList={(list) => {
                  identity.set("same_as", list);
                }}
              />
            </Field>
            <Field label={SITE_LABELS.llms_summary} hint="What llms.txt says after the description, for AI tools." error={identity.errors.llms_summary}>
              <TextArea
                rows={3}
                maxLength={2000}
                value={text(values.llms_summary)}
                onChange={(event) => {
                  identity.set("llms_summary", event.target.value);
                }}
              />
            </Field>
            <Switch
              label="Let AI crawlers read the site"
              hint="Off, robots.txt asks them to stay away."
              checked={values.ai_crawlers !== "refuse"}
              onChange={(on) => {
                identity.set("ai_crawlers", on ? "allow" : "refuse");
              }}
            />
            <History form={identity} labels={SITE_LABELS} />
          </Card>
          <Card className="mf-settings-card" title="Accounts">
            <Conflict form={accounts} labels={ACCOUNT_LABELS} />
            <Switch
              label="Anyone can sign up"
              hint={signUpHint(mode)}
              checked={mode === "open"}
              onChange={(on) => {
                accounts.set("sign_up_mode", on ? "open" : "closed");
              }}
            />
            <History form={accounts} labels={ACCOUNT_LABELS} />
          </Card>
        </form>
        <SettingsGroupContext value={group}>
          <ModuleSections />
        </SettingsGroupContext>
      </Loaded>
      <UnsavedDialog guard={guard} what="The site's settings" several />
    </SettingsPage>
  );
}
