// The UI kit's page (harness/web/kit.html): every part of the kit in its
// states, in the admin's look and the site's, on whichever theme
// <html data-theme> names. Playwright checks it (kernel/tests/e2e/kit.spec.ts):
// axe in both themes, each control's boundary, the focus rings with real Tab
// presses, the table's scroller and the save bar's room. Sample words only.
import "../../../themes/machined-light/tokens.css";
import "../../../themes/vibrant-mindz/tokens.css";
import "../../../kernel/web/src/app/frames.css";
import "./kit.css";

import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider, createBrowserRouter } from "react-router";

import {
  Accordion,
  Attention,
  Button,
  Card,
  Chip,
  Dialog,
  EmptyState,
  Field,
  Icon,
  Input,
  LinkButton,
  LoadError,
  Pill,
  QrCode,
  SaveBar,
  ScrollMemory,
  SaveConflict,
  SectionHistory,
  Select,
  Switch,
  Table,
  Tabs,
  TextArea,
  ToastProvider,
  useToast,
  type Column,
  type HistoryVersion,
} from "@/kernel";

type Person = { id: string; email: string; name: string; roles: string; joined: string; seen: string };

const PEOPLE: Person[] = [
  { id: "1", email: "ann.example@mechframe.test", name: "Ann Example", roles: "Owner, Editor", joined: "12 Nov 2026", seen: "Today" },
  { id: "2", email: "bo.sample@mechframe.test", name: "Bo Sample", roles: "Member", joined: "14 Nov 2026", seen: "Yesterday" },
  { id: "3", email: "cy.placeholder@mechframe.test", name: "Cy Placeholder", roles: "Moderator", joined: "15 Nov 2026", seen: "2 days ago" },
];

const COLUMNS: Column<Person>[] = [
  { key: "name", header: "Name", cell: (person) => person.name },
  { key: "email", header: "Email", cell: (person) => person.email },
  { key: "roles", header: "Roles", cell: (person) => person.roles },
  { key: "joined", header: "Joined", cell: (person) => person.joined },
  { key: "seen", header: "Last seen", cell: (person) => person.seen },
  {
    key: "edit",
    header: "Actions",
    align: "end",
    cell: (person) => <Button size="small">Edit {person.name}</Button>,
  },
];

const PLAIN: Column<Person>[] = COLUMNS.slice(0, 5);

const HISTORY: HistoryVersion[] = [
  { number: 2, changed: ["name"], via: "form", saved_at: "2026-11-18T21:40:00Z", saved_by_id: "u1" },
  { number: 1, changed: ["description"], via: "form", saved_at: "2026-11-17T10:00:00Z", saved_by_id: "u1" },
];

function Toaster() {
  const toast = useToast();
  return (
    <Button
      onClick={() => {
        toast({ tone: "success", text: "Saved" });
      }}
    >
      Show a note
    </Button>
  );
}

function AdminLook() {
  const [open, setOpen] = useState(true);
  const [on, setOn] = useState(true);
  const [pressed, setPressed] = useState(true);
  const [dialog, setDialog] = useState(false);
  return (
    <section className="mf-admin-look kit-section" aria-labelledby="admin-look">
      <h2 id="admin-look">The admin's look</h2>

      <h3>Buttons</h3>
      <div className="kit-row">
        <Button variant="primary" data-kit-boundary="filled">
          Save and go live
        </Button>
        <Button>Discard</Button>
        <Button size="small" icon="external">
          View site
        </Button>
        <Button disabled>Not now</Button>
        <LinkButton to="/kit.html#tabs">Go to the tabs</LinkButton>
        <Button
          onClick={() => {
            setDialog(true);
          }}
        >
          Open a dialog
        </Button>
        <Toaster />
      </div>
      {dialog ? (
        <Dialog
          title="Delete this role?"
          onClose={() => {
            setDialog(false);
          }}
        >
          <p className="mf-dialog-lead">No one holds it, so nothing else changes.</p>
          <div className="mf-dialog-actions">
            <Button
              variant="primary"
              onClick={() => {
                setDialog(false);
              }}
            >
              Delete
            </Button>
            <Button
              onClick={() => {
                setDialog(false);
              }}
            >
              Keep it
            </Button>
          </div>
        </Dialog>
      ) : null}

      <h3 id="fields">Fields</h3>
      <div className="kit-grid">
        <Field label="Site name" hint="Shown in the title bar.">
          <Input defaultValue="MechFrame test site" data-kit-boundary="field" />
        </Field>
        <Field label="Contact email" error="That's not an email address.">
          <Input defaultValue="not an address" data-kit-boundary="field" />
        </Field>
        <Field label="Time zone">
          <Select defaultValue="ny" data-kit-boundary="field">
            <option value="ny">America/New_York</option>
            <option value="la">America/Los_Angeles</option>
          </Select>
        </Field>
        <Field label="Description">
          <TextArea placeholder="A line or two about the site" data-kit-boundary="field" />
        </Field>
      </div>
      <div className="kit-stack">
        <Switch label="Open sign-up" hint="Anyone can make an account." checked={on} onChange={setOn} />
        <Switch label="Direct messages" checked={false} onChange={() => undefined} />
      </div>

      <h3>Pills and chips</h3>
      <div className="kit-row">
        <Pill tone="success">Live</Pill>
        <Pill tone="warning">Processing</Pill>
        <Pill tone="danger">Can't play</Pill>
        <Pill>Draft</Pill>
        <Chip pressed={pressed} onPressedChange={setPressed} data-kit-boundary="pressed">
          Drafts
        </Chip>
        <Chip pressed={false} onPressedChange={() => undefined}>
          Scheduled
        </Chip>
      </div>

      <h3>Needs you</h3>
      <div className="kit-stack">
        <Attention
          tone="warning"
          what="The site has no description"
          why="Search engines show the home page's first words instead."
          action={{ label: "Write one", to: "/kit.html#fields" }}
        />
        <Attention tone="danger" what="Three jobs failed" why="Their mail wasn't sent." action={{ label: "See them", to: "/kit.html" }} />
      </div>

      <h3>Cards, sections and tabs</h3>
      <div className="kit-stack">
        <Card title="Recent activity" actions={<LinkButton to="/kit.html" size="small">All activity</LinkButton>}>
          <p>Ann Example changed the site's name.</p>
        </Card>
        <Accordion id="kit-mail" title="Mail" meta="SMTP, set">
          <p>Mail goes out through the site's SMTP server.</p>
        </Accordion>
        <Accordion id="kit-storage" title="Storage" state={{ tone: "danger", label: "Not set up" }}>
          <p>Files can't be uploaded until storage is set up.</p>
        </Accordion>
        <div id="tabs">
          <Tabs
            label="Settings"
            tabs={[
              { id: "site", label: "Site", panel: <p>The site's name and description.</p> },
              { id: "features", label: "Features", panel: <p>Which modules are on.</p> },
              { id: "system", label: "System", panel: <p>Jobs and services.</p> },
            ]}
          />
        </div>
        <SectionHistory version={2} labels={{ name: "Site name", description: "Description" }} load={() => Promise.resolve(HISTORY)} names={{ u1: "Ann Example" }} />
      </div>

      <h3>Tables</h3>
      <div className="kit-stack">
        <Card title="People" flush>
          <div data-kit="people">
            <Table caption="People" captionHidden columns={COLUMNS} rows={PEOPLE} rowKey={(person) => person.id} />
          </div>
        </Card>
        <Card title="Sign-ins" flush>
          <div data-kit="plain">
            <Table caption="Sign-ins" captionHidden columns={PLAIN} rows={PEOPLE} rowKey={(person) => person.id} />
          </div>
        </Card>
        <Card title="Roles of your own">
          <EmptyState title="No roles of your own yet" action={<Button size="small" icon="plus">New role</Button>}>
            Roles you make show here, beside the built-in ones.
          </EmptyState>
        </Card>
        <LoadError what="The jobs" error="The server didn't answer." onRetry={() => undefined} />
      </div>

      <h3>Saving</h3>
      <div className="kit-stack">
        <SaveConflict
          conflict={{
            detail: "Someone else saved these settings since you opened them, and changed name too.",
            version: 3,
            at: "2026-11-18T21:40:00Z",
            conflicts: [{ field: "name", yours: "My name", theirs: "Their name" }],
          }}
          labels={{ name: "Site name" }}
          saving={false}
          onResolve={() => undefined}
          onCancel={() => undefined}
        />
        {Array.from({ length: 6 }, (_, at) => (
          <Field key={at} label={`Setting ${String(at + 1)}`}>
            <Input defaultValue={`Value ${String(at + 1)}`} />
          </Field>
        ))}
      </div>
      <SaveBar
        changes={open ? 2 : 0}
        saveLabel="Save and go live"
        onSave={() => {
          setOpen(false);
        }}
        onDiscard={() => {
          setOpen(false);
        }}
      />
    </section>
  );
}

function SiteLook() {
  return (
    <section className="kit-section mf-site-look" aria-labelledby="site-look">
      <h2 id="site-look">The site's look</h2>
      <div className="kit-row">
        <Button variant="primary">Sign in</Button>
        <Button>Use a passkey</Button>
      </div>
      <Field label="Email">
        <Input type="email" defaultValue="ann.example@mechframe.test" data-kit-boundary="field" />
      </Field>
      <h3>Sign-in's sizes</h3>
      <div className="kit-stack kit-narrow">
        <Button variant="strong" size="large" data-kit-boundary="filled">
          <Icon name="key" />
          Sign in with a passkey
        </Button>
        <Field label="Password" size="large" hint="At least 12 characters." aside={<a href="#site-look">Forgot password?</a>}>
          <Input type="password" defaultValue="quiet orbit lantern" data-kit-boundary="field" />
        </Field>
        <Button variant="primary" size="large" data-kit-boundary="filled">
          Create account
        </Button>
        <Button size="large">
          <Icon name="mail" />
          Email me a code instead
        </Button>
      </div>
      <h3>A QR code</h3>
      <QrCode value="otpauth://totp/UI%20kit:ann.example%40mechframe.test?secret=JBSWY3DPEHPK3PXP&issuer=UI%20kit" label="A sample QR code" size={160} />
      <h3>The account's cards</h3>
      <Card title="Signed-in devices" description="Anywhere your account is open right now." actions={<Button>Sign out everywhere else</Button>}>
        <p>
          This device <Pill>Now</Pill> <Pill tone="success">On</Pill>
        </p>
      </Card>
    </section>
  );
}

function KitPage() {
  return (
    <main id="main" className="kit">
      <h1>UI kit</h1>
      <p>Every part of the kernel's kit, in its states. Sample words only.</p>
      <SiteLook />
      <AdminLook />
    </main>
  );
}

const router = createBrowserRouter([
  {
    path: "*",
    element: (
      <>
        <ScrollMemory />
        <KitPage />
      </>
    ),
  },
]);
const root = document.getElementById("root");
if (!root) throw new Error("The kit page has no #root.");
createRoot(root).render(
  <StrictMode>
    <ToastProvider>
      <RouterProvider router={router} />
    </ToastProvider>
  </StrictMode>,
);
