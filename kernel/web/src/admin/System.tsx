/**
 * `/admin/settings/system` (K4 contract §2 addition 8, change 19; VM Website
 * `AdminSettings.dc.html`): the background jobs (`GET
 * /api/kernel/admin/system`), the jobs that failed for good with Retry and
 * Discard (`kernel.jobs.manage`), and the services as the host set them up.
 *
 * Left off, not faked: whether email and storage are working (there's no
 * health check, contract §6: the page says how each is set up) and whether
 * MechFrame is up to date (nothing checks).
 */
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type RefObject } from "react";

import { ApiProblem, api, useApiQuery } from "../api/client";
import type { components } from "../api/schema";
import { said } from "../auth/words";
import { useSession } from "../session/session";
import { Attention } from "../ui/Attention";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { Dialog } from "../ui/Dialog";
import { LoadError } from "../ui/LoadError";
import { Pill, type Tone } from "../ui/Pill";
import { StatCard } from "../ui/StatCard";
import { Table, type Column } from "../ui/Table";
import { useToast } from "../ui/Toast";
import { when } from "../ui/words";
import { SettingsPage } from "./SettingsPage";

export type SystemRead = components["schemas"]["System"];
export type DeadJob = components["schemas"]["DeadJob"];

const FAILED_PLACE = "failed-jobs";
const PAGE = 50;

const jobs = (count: number): string => (count === 1 ? "1 job" : `${String(count)} jobs`);

/** The email row: how mail goes out, and its state as a pill. */
export function emailRow(email: SystemRead["services"]["email"]): { line: string; tone: Tone; state: string } {
  if (email === "smtp") return { line: "Sending by SMTP", tone: "success", state: "Set up" };
  if (email === "resend") return { line: "Sending through Resend", tone: "success", state: "Set up" };
  return { line: "Not sending: mail is only written to the log. Set the SMTP variables on the host.", tone: "warning", state: "Not set up" };
}

/** The storage row: which buckets the host set, and its state as a pill. */
export function storageRow(storage: SystemRead["services"]["storage"]): { line: string; tone: Tone; state: string } {
  if (!storage.configured) return { line: "Uploads are off until the storage variables are set on the host.", tone: "neutral", state: "Not set up" };
  return {
    line: storage.public ? "Two buckets: public files and private downloads" : "One private bucket, for downloads",
    tone: "success",
    state: "Set up",
  };
}

function Jobs({ system }: { system: SystemRead }) {
  const { queued, running, dead, worker } = system.jobs;
  return (
    <div className="mf-settings-stats">
      <StatCard
        label="Background jobs"
        state={worker === "ok" ? { tone: "success", label: "Healthy" } : { tone: "warning", label: "Behind" }}
        value={worker === "ok" ? "Running" : "Behind"}
        line={
          worker === "ok"
            ? `${running === 0 ? "Nothing" : jobs(running)} running now`
            : "A job is more than 2 minutes late. Check the worker is running."
        }
      />
      <StatCard label="Waiting" state={{ tone: "neutral", label: "Normal" }} value={queued} line="Due now or scheduled" />
      <StatCard
        label="Failed for good"
        state={dead > 0 ? { tone: "danger", label: "Needs you" } : { tone: "success", label: "None" }}
        value={dead}
        line={dead > 0 ? "Shown below" : "Nothing has run out of tries"}
      />
    </div>
  );
}

function Services({ system }: { system: SystemRead }) {
  const email = emailRow(system.services.email);
  const storage = storageRow(system.services.storage);
  const rows = [
    { name: "Email", ...email },
    { name: "File storage", ...storage },
  ];
  return (
    <Card title="Services">
      <ul className="mf-settings-rows">
        {rows.map((row) => (
          <li key={row.name} className="mf-settings-row">
            <span className="mf-settings-row-words">
              <span className="mf-settings-row-name">{row.name}</span>
              <span className="mf-settings-row-line">{row.line}</span>
            </span>
            <Pill tone={row.tone}>{row.state}</Pill>
          </li>
        ))}
        <li className="mf-settings-row">
          <span className="mf-settings-row-words">
            <span className="mf-settings-row-name">MechFrame</span>
            <span className="mf-settings-row-line">
              Kernel {system.version}; {system.modules.installed === 1 ? "1 module" : `${String(system.modules.installed)} modules`},{" "}
              {String(system.modules.on)} on
            </span>
          </span>
        </li>
      </ul>
    </Card>
  );
}

const REFUSED: Readonly<Record<string, string>> = {
  "kernel.job_not_dead": "That job is waiting to run again already.",
  "kernel.job_not_found": "That job is gone: someone discarded it.",
};

function Failed({ count, heading }: { count: number; heading: RefObject<HTMLHeadingElement | null> }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const session = useSession();
  const mayAct = session.status === "signed-in" && session.can("kernel.jobs.manage");
  const [discarding, setDiscarding] = useState<DeadJob | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const list = useInfiniteQuery({
    queryKey: ["get", "/api/kernel/admin/jobs/dead"],
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) => {
      const { data } = await api.GET("/api/kernel/admin/jobs/dead", { params: { query: { limit: PAGE, ...(pageParam ? { cursor: pageParam } : {}) } } });
      return data ?? { items: [], next_cursor: null };
    },
    getNextPageParam: (last) => last.next_cursor,
  });

  const settle = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ["get", "/api/kernel/admin/jobs/dead"] }),
      queryClient.invalidateQueries({ queryKey: ["get", "/api/kernel/admin/system"] }),
      queryClient.invalidateQueries({ queryKey: ["get", "/api/kernel/admin/attention"] }),
    ]);

  const act = async (job: DeadJob, how: "retry" | "discard") => {
    setBusy(job.id);
    let done = false;
    try {
      if (how === "retry") await api.POST("/api/kernel/admin/jobs/{id}/retry", { params: { path: { id: job.id } } });
      else await api.DELETE("/api/kernel/admin/jobs/{id}", { params: { path: { id: job.id } } });
      toast({ tone: "success", text: how === "retry" ? `${job.name} will run again shortly.` : `${job.name} is discarded.` });
      done = true;
    } catch (caught) {
      toast({ tone: "danger", text: caught instanceof ApiProblem ? said(caught, REFUSED) : "That didn't work. Try again." });
    } finally {
      setBusy(null);
      setDiscarding(null);
      await settle();
      // The row and its buttons went with the job: the focus goes to the
      // list's heading, not nowhere (CodeRabbit on #87). A refusal keeps it.
      if (done) heading.current?.focus();
    }
  };

  const rows = list.data?.pages.flatMap((page) => page.items) ?? [];
  const columns: Column<DeadJob>[] = [
    {
      key: "job",
      header: "Job",
      cell: (job) => (
        <span className="mf-settings-job" data-job={job.id}>
          <span className="mf-settings-mono">{job.name}</span>
          <span className="mf-settings-row-line">
            {job.module === "kernel" ? "The kernel" : `The ${job.module} module`}, failed {when(job.failed_at)}
          </span>
        </span>
      ),
    },
    {
      key: "error",
      header: "Last error",
      cell: (job) => <span className="mf-settings-mono mf-settings-table-mono">{job.last_error ?? "None given"}</span>,
    },
    { key: "tries", header: "Tries", cell: (job) => String(job.tries) },
    {
      key: "actions",
      header: <span className="mf-visually-hidden">Actions</span>,
      align: "end",
      cell: (job) =>
        mayAct ? (
          <span className="mf-settings-job-actions">
            {job.retryable ? (
              <Button
                size="small"
                disabled={busy !== null}
                onClick={() => {
                  void act(job, "retry");
                }}
              >
                Retry
              </Button>
            ) : null}
            <Button
              size="small"
              disabled={busy !== null}
              onClick={() => {
                setDiscarding(job);
              }}
            >
              Discard
            </Button>
          </span>
        ) : null,
    },
  ];

  if (list.error) {
    return <LoadError what="the failed jobs" error={list.error} onRetry={() => void list.refetch()} />;
  }
  return (
    <>
      <Card flush>
        <Table
          caption="Jobs that failed for good"
          captionHidden
          columns={columns}
          rows={rows}
          rowKey={(job) => job.id}
          empty={list.isPending ? "Loading…" : "No job has failed for good."}
        />
      </Card>
      {rows.some((job) => !job.retryable) ? (
        <p className="mf-settings-quiet">
          A job without Retry can't run again: its contents were private and were wiped when it failed, or nothing on the site runs
          it any more.
        </p>
      ) : null}
      {!mayAct && count > 0 ? <p className="mf-settings-quiet">Retrying and discarding failed jobs needs the jobs permission.</p> : null}
      {list.hasNextPage ? (
        <Button
          disabled={list.isFetchingNextPage}
          onClick={() => {
            void list.fetchNextPage();
          }}
        >
          {list.isFetchingNextPage ? "Loading…" : "Show more"}
        </Button>
      ) : null}
      {discarding ? (
        <Dialog
          title={`Discard ${discarding.name}?`}
          onClose={() => {
            if (busy === null) setDiscarding(null);
          }}
        >
          <p className="mf-dialog-lead">It won't run again, and whatever it was doing won't happen. This can't be undone.</p>
          <div className="mf-dialog-actions">
            <Button
              disabled={busy !== null}
              onClick={() => {
                setDiscarding(null);
              }}
            >
              Keep it
            </Button>
            <Button
              variant="primary"
              disabled={busy !== null}
              onClick={() => {
                void act(discarding, "discard");
              }}
            >
              {busy === discarding.id ? "Discarding…" : "Discard"}
            </Button>
          </div>
        </Dialog>
      ) : null}
    </>
  );
}

export default function System() {
  const read = useApiQuery("get", "/api/kernel/admin/system");
  const heading = useRef<HTMLHeadingElement>(null);
  let body;
  if (read.error) {
    body = <LoadError what="the system's state" error={read.error} onRetry={() => void read.refetch()} />;
  } else if (!read.data) {
    body = <p className="mf-settings-quiet">Loading…</p>;
  } else {
    const system = read.data;
    const dead = system.jobs.dead;
    body = (
      <>
        {dead > 0 ? (
          <Attention
            tone="danger"
            what={`${jobs(dead)} failed for good`}
            why="Each ran out of tries. Until you retry or discard them, whatever they were doing hasn't happened."
            action={{ label: "Review below", to: `#${FAILED_PLACE}` }}
          />
        ) : null}
        <Jobs system={system} />
        <section aria-labelledby={FAILED_PLACE} className="mf-settings-failed">
          {/* The board's "Failed for good", named apart from the card of that name. */}
          <h2 id={FAILED_PLACE} ref={heading} className="mf-settings-heading" tabIndex={-1}>
            Jobs that failed for good
          </h2>
          <Failed count={dead} heading={heading} />
        </section>
        <Services system={system} />
      </>
    );
  }
  return <SettingsPage page="System">{body}</SettingsPage>;
}
