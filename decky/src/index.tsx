// ReXNative Manager in the Steam Deck's quick access menu (…): what the PC is doing, the requests
// (the PC downloading, building and sending games) with their progress, a notice when a game is
// ready, the games played last and a button to open the Manager. Without a PC (the Manager's Sem PC
// mode) this Deck does the work, and the texts say so.
import {
  ButtonItem,
  ConfirmModal,
  Field,
  Navigation,
  PanelSection,
  PanelSectionRow,
  ProgressBar,
  showModal,
  staticClasses,
} from "@decky/ui";
import { callable, definePlugin, toaster } from "@decky/api";
import { CSSProperties, ReactNode, RefObject, useEffect, useRef, useState } from "react";

declare const SteamClient: any;

// What a request waits for: the job running before it on the PC, how many are ahead, a restart.
type Waiting = { title?: string; for_s?: number; ahead?: number; restart?: boolean };
type Progress = {
  done?: number; total?: number; rate?: number; eta?: number; step?: string; stage?: string; pstep?: string;
  step_pt?: string; phase?: string; pct?: number; elapsed?: number; step_elapsed?: number;
  phases?: { name: string; now: boolean }[]; waiting?: Waiting | null;
  batch?: { i: number; n: number; current?: string; failed?: number } | null;
};
type Order = {
  id: string; title: string; name?: string; status: string; stage?: string; error?: string; progress?: Progress | null;
  kind?: string; last?: string; report?: { status?: string; summary?: string; text?: string } | null;
  waiting?: Waiting | null; created?: string; started?: string; ended?: string;
};
type Game = { title: string; appid: number; last_played?: number };
// From the PC app 1.19 on; an older one does not send it, and the panel leaves that part out.
type PcWork = { running?: { title?: string; kind?: string; lane?: string; for_s?: number }[]; queued?: number; restart?: boolean };
type Status = {
  installed: boolean; online?: boolean; pc?: string; deck_free?: number; sd_free?: number; error?: string;
  reason?: string; ssh?: boolean | null; pc_work?: PcWork | null; orders?: Order[]; active?: number;
  pending?: { add?: number; remove?: number; titles?: string[] }; gestor_appid?: number; version?: string;
  app_version?: string; plugin_latest?: string; plugin_update?: boolean; gestor_open?: boolean; games?: Game[];
  // Who answered (home.mode: "pc", or "local" for the service on this Deck), and the mode chosen
  // (the mode file: "pc", "local" or "auto").
  mode?: string; setting?: string;
};

const getStatus = callable<[], Status>("status");
const flushNow = callable<[], { flush?: string; error?: string }>("flush");
const updatePlugin = callable<[], { ok?: boolean; version?: string; error?: string }>("update");

const gb = (b?: number) => b == null ? "?" : b >= 1e9 ? (b / 1e9).toFixed(1) + " GB" : Math.max(1, Math.round(b / 1e6)) + " MB";
const eta = (s?: number) => s == null || !isFinite(s) ? "" : s < 90 ? Math.max(1, Math.round(s)) + " s" : s < 5400 ? Math.round(s / 60) + " min" : Math.floor(s / 3600) + " h " + Math.round((s % 3600) / 60) + " min";
// How long ago, from a time of the Deck's own clock (seconds).
const ago = (t?: number) => {
  const d = t ? Date.now() / 1000 - t : -1;
  if (d < 0) return "";
  if (d < 3600) return Math.max(1, Math.round(d / 60)) + " min ago";
  if (d < 86400) return Math.round(d / 3600) + " h ago";
  const n = Math.round(d / 86400);
  return n + (n === 1 ? " day ago" : " days ago");
};
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
// A time the PC wrote ("2026-11-21T19:31:35", its own clock): the hour, and the day when it is not today.
const when = (t?: string) => {
  if (!t || t.length < 16) return "";
  const n = new Date();
  const today = `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(n.getDate()).padStart(2, "0")}`;
  return (t.slice(0, 10) === today ? "" : `${MONTHS[+t.slice(5, 7) - 1] || ""} ${+t.slice(8, 10)}, `) + t.slice(11, 16);
};

// Who does the work: the PC, or this Deck itself (the last answer came from the service on the Deck:
// home.mode "local"). Kept with the games, for the first look before an answer.
let here = false;
const on = () => here ? "on this Deck" : "on the PC";

const STAGE = (): Record<string, string> => ({
  download: "Downloading", build: "Building " + on(), deck: here ? "Installing on the Deck" : "Sending to the Deck",
  library: "On the Deck: joins the library when you exit the Manager", done: "In the library",
});
// The steps of a request to install, and of a report, while they run.
const STEPS = ["download", "build", "deck"];
const REPORT = (): Record<string, string> => ({
  deck: "Collecting the log and settings on the Deck", claude: "Claude is investigating " + on(),
  deck_send: here ? "Installing the fixed version" : "Sending the fixed version to the Deck",
});
// Besides the requests to install: reports and what was asked from the Manager (rebuild, send, delete).
const KIND: Record<string, string> = {
  "deck-report": "Report", pipeline: "Rebuild", deck: "Send", "deck-delete": "Delete", "deck-flush": "Library", report: "Report",
  "deck-gestor": "Launcher", "deck-restore": "Restore", "deck-plugin": "Plugin", "deck-batch": "All",
  "linux-build": "Linux build", "linux-deck": "Linux to Deck", "linux-runner": "Linux / Windows",
};
const DOING = (): Record<string, string> => ({
  pipeline: "Rebuilding " + on(), deck: "Sending to the Deck", "deck-delete": "Deleting from the Deck",
  "deck-flush": "Updating the library", "deck-gestor": "Updating the launcher", "deck-restore": "Restoring on the Deck",
  "deck-plugin": "Installing the plugin", "linux-build": "Building for Linux " + on(), "linux-deck": "Sending the Linux build to the Deck",
});
const FIXING = () => "Claude is fixing a step that failed " + on();
const active = (o: Order) => o.status === "running" || o.status === "queued";
const isOrder = (o: Order) => !o.kind || o.kind === "order";

// The game's name (the PC app sends it clean; an old PC only sends the job's title).
const baseName = (o: Order) => o.name || String(o.title || "").replace(/^(Report|Resend to the Deck|Install to the Deck|Delete from the Deck): /, "");
// What it is, for the ones that are not requests to install ("Send", "Rebuild"...).
const kindOf = (o: Order) => isOrder(o) || o.kind === "deck-batch" ? "" : KIND[o.kind || ""] || o.kind || "";
const orderName = (o: Order) => baseName(o) + (kindOf(o) ? " · " + kindOf(o) : "");

// How a request that went well ended. named: with what it was ("Send: ..."), for a notice; beside
// its name on the panel, which already says so, without.
function doneText(o: Order, named = true): string {
  if (isOrder(o)) return STAGE()[o.stage || "done"] || "Ready";
  if (o.kind === "deck-batch") return o.last || "Done";
  const what = o.kind === "deck-report" ? (o.report || {}).status || "done" : o.last || "done";
  return named ? (KIND[o.kind || ""] || "Done") + ": " + what : what.charAt(0).toUpperCase() + what.slice(1);
}

// How a request that is over ended, beside its name.
function endText(o: Order): string {
  if (o.status === "ok") return doneText(o, false);
  if (o.status === "failed") return "Failed: " + (o.error || "see the Manager");
  if (o.status === "cancelled") return "Cancelled";
  if (o.status === "interrupted") return here ? "Interrupted (the Manager on this Deck stopped)" : "Interrupted (the PC app closed)";
  return o.status;
}

// What a request waits for (the wording of Deck mode): the job running before it on the PC (one
// build or Claude at a time), or the restart of the Manager there.
const waitingOf = (o: Order): Waiting | null | undefined =>
  o.status === "queued" ? o.waiting : o.status === "running" ? (o.progress || {}).waiting : null;
const waits = (o: Order) => o.status === "queued" || !!waitingOf(o);
function waitText(w?: Waiting | null): string {
  if (!w) return "Queued";
  const who = here ? "this Deck" : "the PC";
  if (w.restart) return `Continues when the Manager ${on()} has restarted`;
  const n = w.ahead ? `${w.ahead} more request${w.ahead > 1 ? "s" : ""} before this one` : "";
  if (!w.title) return "Waiting: " + (n || who + " is busy");
  return `Waiting for ${who} to finish ${w.title}${w.for_s != null ? " (running for " + eta(w.for_s) + ")" : ""}${n ? ", then " + n : ""}`;
}

// A request the PC is working on: the stage (it changes a few times), the detail of the moment (it
// changes all the time: one line, under the bar), the time and how far the bar goes.
type Live = { head: string; op: string; time: string; pct?: number };
function live(o: Order): Live {
  const p = o.progress || {};
  const pct = p.total ? Math.min(100, (100 * (p.done || 0)) / p.total) : p.pct != null ? Math.max(0, Math.min(100, p.pct)) : undefined;
  const bytes = p.total ? `${gb(p.done)} of ${gb(p.total)}${p.rate ? " · " + (p.rate / 1e6).toFixed(1) + " MB/s" : ""}` : "";
  // "Prepare: Finishing the build", but not "Build: Building: 412 of 1630".
  const said = !!p.step_pt && !!p.phase && p.phase.toLowerCase().startsWith(p.step_pt.toLowerCase());
  let head: string;
  let op = bytes || [said ? "" : p.step_pt, p.phase].filter(Boolean).join(": ");
  if (p.pstep === "claude" || (!isOrder(o) && p.step === "claude")) {
    // While the assistant fixes a step: that, not the command it is running.
    head = FIXING();
    op = "";
  } else if (p.batch) {
    head = `${p.batch.i + 1} of ${p.batch.n}: ${p.batch.current || ""}${p.batch.failed ? ` · ${p.batch.failed} failed` : ""}`;
  } else if (o.kind === "deck-report") {
    head = REPORT()[o.stage || ""] || REPORT().deck;
    op = op || o.last || "";
  } else if (isOrder(o)) {
    const i = STEPS.indexOf(o.stage || "");
    head = i < 0 ? (o.stage ? "Working " + on() : "Starting") : `Step ${i + 1} of ${STEPS.length} · ${STAGE()[STEPS[i]]}`;
  } else {
    head = DOING()[o.kind || ""] || KIND[o.kind || ""] || "Working " + on();
    op = op || o.last || "";
  }
  const time = p.total && p.eta != null && (p.done || 0) < p.total ? eta(p.eta) + " left"
    : !p.total && pct != null ? Math.round(pct) + "%"
    : p.step_elapsed != null ? eta(p.step_elapsed) + " so far"
    : p.elapsed != null ? eta(p.elapsed) + " so far" : "";
  return { head, op, time, pct };
}

// Everything about a request in words, for its sheet.
function fullText(o: Order): string {
  if (!active(o)) return endText(o);
  if (waits(o)) return waitText(waitingOf(o));
  const v = live(o);
  return [v.head, v.op, v.time].filter(Boolean).join(" · ");
}

// -- the state ------------------------------------------------------------------------------------
// The PC is asked every 15 s (also with the menu closed, for the notice when a game is ready), every
// 3 s with the panel on screen, and once a minute while it does not answer.
const HOLD_MS = 45000;  // no answer for less than this: the panel keeps what it had ("trying again")
let last: Status | null = null;  // the last answer, whatever it says
let good: Status | null = null;  // the last one with the PC there
let goodAt = 0;                  // when that one came
let fails = 0;                   // answers in a row without the PC
let asked = 0;                   // when the question on its way was asked (0: none)
const subs = new Set<() => void>();

// The games and the Manager's shortcut stay known between sessions: with the PC off, Play still works.
type Kept = { gestor_appid?: number; games?: Game[]; local?: boolean };
const KEEP = "gestor-rexnative.kept";
let kept: Kept = {};
try {
  const k = JSON.parse(localStorage.getItem(KEEP) || "{}");
  if (k && typeof k === "object") kept = { gestor_appid: k.gestor_appid, games: Array.isArray(k.games) ? k.games : [], local: !!k.local };
} catch (e) {
  // nothing kept
}
here = !!kept.local;
function keep(s: Status) {
  const k: Kept = { gestor_appid: s.gestor_appid, games: s.games || [], local: s.mode === "local" };
  const raw = JSON.stringify(k);
  if (raw === JSON.stringify(kept)) return;
  kept = k;
  try { localStorage.setItem(KEEP, raw); } catch (e) { /* only for this session, then */ }
}

// The notices: a request that ended since the last answer. Not at the first answer (those ended
// before), and with the Manager open on the Deck the page itself tells (they came twice).
const seen: Record<string, string> = {};
let newest: string | null = null;  // the newest request at the first answer (null: no answer yet)
function notify(s: Status) {
  const orders = s.orders || [];
  const done: Order[] = [], bad: Order[] = [];
  for (const o of orders) {
    const before = seen[o.id];
    seen[o.id] = o.status;
    if (newest === null || before === o.status) continue;
    // Never seen running and already over: a short one, between two questions. It counts when it
    // was asked for after the first answer (an old one coming back into the list does not).
    if (!before && !((o.created || "") > newest)) continue;
    if (o.status === "ok") done.push(o);
    else if (o.status === "failed") bad.push(o);
  }
  if (newest === null) newest = orders.reduce((m, o) => ((o.created || "") > m ? o.created || "" : m), "");
  if (s.gestor_open) return;
  // Several ending together are one notice.
  if (done.length === 1) toaster.toast({ title: orderName(done[0]), body: doneText(done[0]) });
  else if (done.length > 1) toaster.toast({ title: "ReXNative Manager", body: `${done.length} requests finished: ${done.map(orderName).join(", ")}` });
  if (bad.length === 1) toaster.toast({ title: orderName(bad[0]), body: "The request failed: " + (bad[0].error || "see the Manager") });
  else if (bad.length > 1) toaster.toast({ title: "ReXNative Manager", body: `${bad.length} requests failed: ${bad.map(orderName).join(", ")}` });
}

async function poll() {
  // One question at a time: a PC that is off takes seconds to not answer, and the panel asks every 3.
  if (asked && Date.now() - asked < 30000) return;
  asked = Date.now();
  try {
    let s: Status | null = null;
    try {
      s = await getStatus();
    } catch (e) {
      // Decky still starting (or its side of the plugin gone): the next one may answer
    }
    if (s && s.installed && s.online) {
      here = s.mode === "local";
      try { notify(s); } catch (e) { /* a notice that fails does not stop the panel */ }
      good = s;
      goodAt = Date.now();
      fails = 0;
      keep(s);
    } else fails++;
    if (s) last = s;
    else if (last || fails >= 3) last = { installed: last ? last.installed : true, online: false, reason: "plugin", version: last ? last.version : undefined };
    subs.forEach(f => f());
  } finally {
    asked = 0;
  }
}

// What the panel shows: the last answer with the PC there. A question without an answer is not "no
// PC" yet: for a while (held) the panel keeps what it had. d is null with no PC to show.
function shown(): { d: Status | null; held: boolean } {
  const s = last;
  if (!s || !s.installed) return { d: null, held: false };
  const held = !s.online && !!good && Date.now() - goodAt < HOLD_MS;
  return { d: s.online ? s : held ? good : null, held };
}

// Draws again when an answer comes (and when asked to: what it gives back).
function useStore(): () => void {
  const [, bump] = useState(0);
  const [redraw] = useState(() => () => bump(n => n + 1));  // the same one while the piece lives
  useEffect(() => {
    subs.add(redraw);
    return () => { subs.delete(redraw); };
  }, []);
  return redraw;
}
// Whether the quick access menu is on screen: its window says so (found from a mark the panel draws,
// with nothing of Decky's or Steam's insides). Decky takes the panel down when the menu closes; one
// that left it up would have it asking the PC every 3 s behind the game.
function useOnScreen(): [boolean, RefObject<HTMLSpanElement | null>] {
  const mark = useRef<HTMLSpanElement | null>(null);
  const [on, setOn] = useState(true);
  useEffect(() => {
    const doc = mark.current ? mark.current.ownerDocument : null;
    if (!doc) return undefined;
    const see = () => setOn(!doc.hidden);
    see();
    doc.addEventListener("visibilitychange", see);
    return () => doc.removeEventListener("visibilitychange", see);
  }, []);
  return [on, mark];
}

function openGestor(appid?: number) {
  if (!appid) return;
  const gameId = ((BigInt(appid) << 32n) | 0x02000000n).toString();
  SteamClient.Apps.RunGame(gameId, "", -1, 100);
  Navigation.CloseSideMenus();
}

// -- the pieces -----------------------------------------------------------------------------------
const C = { ok: "#59bf40", bad: "#ff6b6b", warn: "#ffc82c", blue: "#1a9fff", dim: "#b8bcbf" };
// At most n lines, then "…": a long title or a long reason never pushes the rest of the panel around.
const clamp = (n: number): CSSProperties => ({
  display: "-webkit-box", WebkitBoxOrient: "vertical", WebkitLineClamp: n, overflow: "hidden",
  overflowWrap: "anywhere", whiteSpace: "normal",
});
const small: CSSProperties = { fontSize: "12px", lineHeight: "16px", color: C.dim };
const line: CSSProperties = { display: "flex", alignItems: "flex-start", gap: "8px", minWidth: 0, width: "100%" };

const Dot = ({ color }: { color: string }) => (
  <span style={{ flex: "none", width: "8px", height: "8px", borderRadius: "50%", background: color, marginTop: "6px" }} />
);

// How a request stands, before its name: done, failed, stopped, waiting.
function Mark({ kind }: { kind: "ok" | "bad" | "off" | "wait" }) {
  const color = kind === "ok" ? C.ok : kind === "bad" ? C.bad : C.dim;
  const d = kind === "ok" ? "M5 12.5l4.5 4.5L19 7.5" : kind === "bad" ? "M7 7l10 10M17 7L7 17" : kind === "wait" ? "M12 7.5V12l3 2" : "M7 12h10";
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" style={{ flex: "none", marginTop: "3px" }}>
      {kind === "wait" && <circle cx="12" cy="12" r="9" stroke={color} strokeWidth="2.4" />}
      <path d={d} stroke={color} strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function Name({ o, mark }: { o: Order; mark?: ReactNode }) {
  const kind = kindOf(o);
  return (
    <div style={line}>
      {mark}
      <span style={{ ...clamp(2), flex: 1, minWidth: 0 }}>
        {baseName(o)}{kind && <span style={{ opacity: 0.6 }}> · {kind}</span>}
      </span>
    </div>
  );
}

// Steam's own bar (Decky finds it by its code, so a Steam update can leave it without one: then a
// plain one). Without a known size it moves from side to side; newer Steam wants 0 for that.
const SteamBar = ProgressBar as typeof ProgressBar | undefined;
function Bar({ pct }: { pct?: number }) {
  if (SteamBar) return <SteamBar nProgress={pct ?? 0} indeterminate={pct == null} />;
  return (
    <div style={{ height: "8px", borderRadius: "10px", background: "#3d4450", overflow: "hidden" }}>
      <div style={{ width: `${pct ?? 0}%`, height: "100%", borderRadius: "10px", background: C.blue }} />
    </div>
  );
}

// The sheet of a request (A on it): everything in full, which the panel cuts to a line or two. It
// follows the request while it is open.
function Details({ id, snap }: { id: string; snap: Order }) {
  useStore();
  const o = ((good && good.orders) || []).find(x => x.id === id) || snap;
  const r = o.report || {};
  const summary = String(r.summary || "").replace(/\s*(REXNATIVE|COMMITS|SUSPECTS|SUSPEITOS):[\s\S]*$/, "").replace(/\s+/g, " ").trim();
  const text = fullText(o);
  const times = [o.created ? "Asked " + when(o.created) : "", o.ended ? "ended " + when(o.ended) : ""].filter(Boolean).join(" · ");
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "10px", overflowWrap: "anywhere" }}>
      <div style={{ color: o.status === "failed" ? C.bad : undefined }}>{text}</div>
      {o.last && !text.includes(o.last) && <div>Last step: {o.last}</div>}
      {r.text && <div>You wrote: {r.text}</div>}
      {summary && <div>{summary.length > 600 ? summary.slice(0, 600) + "…" : summary}</div>}
      {times && <div style={small}>{times}</div>}
    </div>
  );
}

let opened = 0;
function openDetails(o: Order) {
  if (Date.now() - opened < 400) return;  // A and the touch of the same press: one sheet
  opened = Date.now();
  const appid = (good || kept).gestor_appid;
  showModal(
    <ConfirmModal strTitle={orderName(o)} strDescription={<Details id={o.id} snap={o} />}
      strOKButtonText="Open the Manager" strCancelButtonText="Close" bOKDisabled={!appid}
      onOK={() => openGestor(appid)} />);
}

// A request the PC is working on: the stage, the bar, the detail of the moment and the time.
function Running({ o }: { o: Order }) {
  const v = live(o);
  const open = () => openDetails(o);
  return (
    <Field label={<Name o={o} />} childrenLayout="below" childrenContainerWidth="max" bottomSeparator="none"
      focusable={true} highlightOnFocus={true} onActivate={open} onClick={open} onOKActionDescription="Details">
      <div style={{ width: "100%" }}>
        <div style={{ ...small, ...clamp(2), marginBottom: "6px" }}>{v.head}</div>
        <Bar pct={v.pct} />
        <div style={{ ...small, display: "flex", gap: "8px", marginTop: "6px", minHeight: "16px" }}>
          <span style={{ ...clamp(1), flex: 1, minWidth: 0 }}>{v.op}</span>
          <span style={{ flex: "none" }}>{v.time}</span>
        </div>
      </div>
    </Field>
  );
}

// One that waits (for a turn on the PC, for its restart), and one that is over.
function Waits({ o }: { o: Order }) {
  const open = () => openDetails(o);
  return (
    <Field label={<Name o={o} mark={<Mark kind="wait" />} />} description={<span style={clamp(3)}>{waitText(waitingOf(o))}</span>}
      bottomSeparator="none" focusable={true} highlightOnFocus={true} onActivate={open} onClick={open} onOKActionDescription="Details" />
  );
}
function Ended({ o }: { o: Order }) {
  const open = () => openDetails(o);
  const failed = o.status === "failed";
  const text = endText(o) + (when(o.ended) ? " · " + when(o.ended) : "");
  return (
    <Field label={<Name o={o} mark={<Mark kind={o.status === "ok" ? "ok" : failed ? "bad" : "off"} />} />}
      description={<span style={{ ...clamp(failed ? 3 : 2), color: failed ? C.bad : undefined }}>{text}</span>}
      focusable={true} highlightOnFocus={true} onActivate={open} onClick={open} onOKActionDescription="Details" />
  );
}

// What the PC is doing (the build lane and the report lane), one line each: why a request waits.
// Without the PC, what this Deck is doing.
function Pc({ s, held }: { s: Status; held: boolean }) {
  const w = s.pc_work;
  const run = (w && w.running) || [];
  const working = (s.orders || []).some(o => o.status === "running" && !waits(o));
  const deck = s.mode === "local";
  return (
    <Field label={<div style={line}><Dot color={held ? C.warn : run.length ? C.blue : C.ok} /><span style={{ ...clamp(1), flex: 1, minWidth: 0 }}>{deck ? "This Deck" : `PC ${s.pc || ""}`}</span></div>}
      description={<>
        {held && <div style={{ color: C.warn }}>No answer for {eta((Date.now() - goodAt) / 1000)}: trying again…</div>}
        {run.map((r, i) => <div key={i} style={clamp(1)}>{i ? "and " : "Working on "}{r.title || "a job"}{r.for_s != null ? ` (${eta(r.for_s)})` : ""}</div>)}
        {!run.length && <div>{deck ? (working ? "Working" : "Nothing running") : w && !working ? "The PC is free" : "Connected"}</div>}
        {w && !!w.queued && <div>{w.queued} job{w.queued > 1 ? "s" : ""} waiting</div>}
        {w && w.restart && <div style={clamp(2)}>It restarts after the running jobs, the queue continues afterwards</div>}
        {!deck && s.ssh === false && <div style={{ ...clamp(2), color: C.warn }}>The PC cannot reach the Deck (SSH): sending waits</div>}
      </>} />
  );
}

// Why there is no PC, in words, and what to do about it.
const WHY: Record<string, [string, string]> = {
  unreachable: ["No connection to the PC", "Turn on the PC and open the Manager there."],
  unpaired: ["This Deck is not paired with the PC", "In the PC app: Settings → Deck mode → Reinstall the Manager on the Deck."],
  refused: ["The PC does not accept this Deck", "In the PC app: Settings → Deck mode → Accept connections from the home network."],
  login: ["The PC app waits for a sign-in", "Sign in with GitHub in the Manager on the PC."],
  error: ["The PC answered with an error", ""],
  plugin: ["The plugin is not answering", "Reload it in Decky's settings, or restart Steam."],
};
// Without the PC (the mode chosen is "local"), or with neither ("auto"), the service on this Deck is
// the one not answering.
const WHY_DECK: [string, string] = ["No connection to the Manager on this Deck", "It may still be starting. If it keeps failing, restart the Deck or install the Sem PC mode again."];
const WHY_BOTH: [string, string] = ["No connection to the PC or to this Deck", "Turn on the PC and open the Manager there, or check the Sem PC mode on this Deck."];
const WHY_DECK_ERR: [string, string] = ["The Manager on this Deck answered with an error", ""];
function NoPc({ s }: { s: Status }) {
  const r = s.reason || "unreachable";
  const why = r === "plugin" ? WHY.plugin
    : s.setting === "local" ? (r === "unreachable" ? WHY_DECK : WHY_DECK_ERR)
    : s.setting === "auto" && r === "unreachable" ? WHY_BOTH
    : WHY[r] || WHY.unreachable;
  const said = s.reason === "error" || s.reason === "refused" ? s.error : "";
  return (
    <Field label={<div style={line}><Dot color={C.bad} /><span style={{ ...clamp(2), flex: 1, minWidth: 0 }}>{why[0]}</span></div>}
      description={<>
        {why[1] && <div>{why[1]}</div>}
        {said && <div style={clamp(3)}>It said: {said}</div>}
        <div>{goodAt ? `Last answer ${eta((Date.now() - goodAt) / 1000)} ago. ` : ""}Trying again…</div>
      </>} />
  );
}

function Manager({ appid }: { appid?: number }) {
  return (
    <ButtonItem layout="below" disabled={!appid} onClick={() => openGestor(appid)}>
      Open the Manager
    </ButtonItem>
  );
}

function Update({ s }: { s: Status }) {
  return (
    <ButtonItem layout="below" description={`This plugin is v${s.version}; ${s.mode === "local" ? "the Manager on this Deck" : "the PC"} has v${s.plugin_latest}.`}
      onClick={() => showModal(
        <ConfirmModal strTitle={`Update the plugin to v${s.plugin_latest}?`}
          strDescription={`Decky installs the new version from ${s.mode === "local" ? "the Manager on this Deck" : "the PC"} and reloads this panel (a few seconds).`}
          strOKButtonText="Update" strCancelButtonText="Not now"
          onOK={async () => {
            toaster.toast({ title: "ReXNative Manager", body: `Updating the plugin to v${s.plugin_latest}…` });
            const r = await updatePlugin();
            if (r && r.error) toaster.toast({ title: "ReXNative Manager", body: "Update failed: " + r.error });
          }} />)}>
      Update the plugin
    </ButtonItem>
  );
}

// The games sent to the Deck that wait to join the library (Steam has to restart for that).
function Library({ s }: { s: Status }) {
  const p = s.pending || {};
  const add = p.add || 0, remove = p.remove || 0;
  if (!add && !remove) return null;
  const first = (p.titles || [])[0];
  const what = [
    add ? (first ? first + (add > 1 ? ` and ${add - 1} more` : "") : `${add} game${add > 1 ? "s" : ""}`) + " to add" : "",
    remove ? `${remove} shortcut${remove > 1 ? "s" : ""} to remove` : "",
  ].filter(Boolean).join(", ");
  return (
    <PanelSection title="Library">
      <PanelSectionRow>
        {s.gestor_open ? (
          // With the Manager open, leaving it does this (and Steam would close it to restart).
          <Field description={<span style={clamp(3)}>When you exit the Manager: {what}.</span>} />
        ) : (
          <ButtonItem layout="below" description={<span style={clamp(3)}>{what}. Steam closes and reopens for a few seconds.</span>}
            onClick={() => showModal(
              <ConfirmModal strTitle="Update the library now?"
                strDescription="Steam closes and reopens for a few seconds to add the new games to the library. If a game is running, wait until you exit it."
                strOKButtonText="Update" strCancelButtonText="Not now"
                onOK={async () => {
                  const r = await flushNow();
                  if (r && r.error) toaster.toast({ title: "ReXNative Manager", body: "The library was not updated: " + r.error });
                }} />)}>
            Add to the library now
          </ButtonItem>
        )}
      </PanelSectionRow>
    </PanelSection>
  );
}

// The games played last, each one a Play button (it works with the PC off too).
const FEW = 4;
function Games({ games }: { games: Game[] }) {
  const [all, setAll] = useState(false);
  if (!games.length) return null;
  return (
    <PanelSection title="Play">
      {(all ? games : games.slice(0, FEW)).map(g => (
        <PanelSectionRow key={g.appid}>
          <ButtonItem layout="below" bottomSeparator="none" onClick={() => openGestor(g.appid)}>
            <div style={{ display: "flex", alignItems: "center", gap: "8px", width: "100%", minWidth: 0 }}>
              <span style={{ ...clamp(1), flex: 1, minWidth: 0, textAlign: "left" }}>{g.title}</span>
              <span style={{ flex: "none", fontSize: "11px", opacity: 0.6 }}>{g.last_played ? ago(g.last_played) : "new"}</span>
            </div>
          </ButtonItem>
        </PanelSectionRow>
      ))}
      {games.length > FEW && (
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => setAll(!all)}>
            {all ? "Fewer games" : `${games.length - FEW} more game${games.length - FEW > 1 ? "s" : ""}`}
          </ButtonItem>
        </PanelSectionRow>
      )}
    </PanelSection>
  );
}

function About({ s, online }: { s: Status; online: boolean }) {
  const versions = [s.version ? "Plugin v" + s.version : "", online && s.app_version ? (s.mode === "local" ? "Manager v" : "PC app v") + s.app_version : ""].filter(Boolean).join(" · ");
  if (!online || s.deck_free == null) return versions ? <PanelSection><PanelSectionRow><Field description={versions} focusable={true} /></PanelSectionRow></PanelSection> : null;
  return (
    <PanelSection>
      <PanelSectionRow>
        <Field label="Free on the Deck" focusable={true}
          description={[s.sd_free != null ? `microSD card: ${gb(s.sd_free)} free` : "", versions].filter(Boolean).join(" · ")}>
          {gb(s.deck_free)}
        </Field>
      </PanelSectionRow>
    </PanelSection>
  );
}

function Content() {
  const redraw = useStore();
  const [visible, mark] = useOnScreen();
  useEffect(() => {
    if (!visible) return undefined;
    poll();
    const t = setInterval(poll, 3000);
    return () => clearInterval(t);
  }, [visible]);
  // Without the PC the panel counts the time ("no answer for 12 s") by itself.
  const away = visible && !!last && last.installed && !last.online;
  useEffect(() => {
    if (!away) return undefined;
    const t = setInterval(redraw, 1000);
    return () => clearInterval(t);
  }, [away]);
  return (
    <>
      <span ref={mark} style={{ display: "none" }} />
      <Panel />
    </>
  );
}

const MOST = 4;  // requests in progress on the panel; the Manager has them all
function Panel() {
  const s = last;
  if (!s) return <PanelSection><PanelSectionRow><Field label={here ? "Asking the Manager on this Deck…" : "Asking the PC…"} /></PanelSectionRow></PanelSection>;
  if (!s.installed) {
    return (
      <PanelSection>
        <PanelSectionRow>
          <Field label="Not set up on this Deck"
            description="Install the Manager on the Deck from the PC app: Settings → Deck mode → Install the Manager on the Deck. Or install the Sem PC mode on this Deck to use it without a PC." />
        </PanelSectionRow>
      </PanelSection>
    );
  }
  const { d, held } = shown();
  if (!d) {
    const k = good || kept;
    return (
      <>
        <PanelSection>
          <PanelSectionRow><NoPc s={s} /></PanelSectionRow>
          <PanelSectionRow><Manager appid={k.gestor_appid} /></PanelSectionRow>
        </PanelSection>
        <Games games={k.games || []} />
        <About s={s} online={false} />
      </>
    );
  }
  const orders = d.orders || [];
  const now = orders.filter(active).sort((a, b) => (waits(a) ? 1 : 0) - (waits(b) ? 1 : 0));
  const count = Math.max(now.length, d.active || 0);
  const recent = orders.filter(o => !active(o)).slice(0, 3);
  return (
    <>
      <PanelSection>
        <PanelSectionRow><Pc s={d} held={held} /></PanelSectionRow>
        <PanelSectionRow><Manager appid={d.gestor_appid} /></PanelSectionRow>
        {d.plugin_update && <PanelSectionRow><Update s={d} /></PanelSectionRow>}
      </PanelSection>
      <PanelSection title={count ? `In progress (${count})` : "Requests"}>
        {now.slice(0, MOST).map(o => (
          <PanelSectionRow key={o.id}>{waits(o) ? <Waits o={o} /> : <Running o={o} />}</PanelSectionRow>
        ))}
        {count > MOST && <PanelSectionRow><Field description={`And ${count - MOST} more: see them in the Manager.`} /></PanelSectionRow>}
        {!count && (
          <PanelSectionRow>
            <Field description={`Nothing in progress. Choose a game in the Manager's Catalogue and press Install: ${d.mode === "local" ? "this Deck" : "the PC"} does the work.`} />
          </PanelSectionRow>
        )}
      </PanelSection>
      <Library s={d} />
      <Games games={d.games || []} />
      {recent.length > 0 && (
        <PanelSection title="Recent requests">
          {recent.map(o => <PanelSectionRow key={o.id}><Ended o={o} /></PanelSectionRow>)}
        </PanelSection>
      )}
      <About s={d} online={true} />
    </>
  );
}

// How many requests are in progress, as far as the panel knows.
function inProgress(): number {
  const { d } = shown();
  return d ? Math.max(d.active || 0, (d.orders || []).filter(active).length) : 0;
}

function Title() {
  useStore();
  const n = inProgress();
  return (
    <div className={staticClasses.Title}>
      ReXNative Manager
      {n > 0 && (
        <span style={{
          display: "inline-block", marginLeft: "8px", minWidth: "18px", height: "18px", padding: "0 5px", boxSizing: "border-box",
          borderRadius: "9px", background: C.blue, color: "#fff", fontSize: "12px", lineHeight: "18px", fontWeight: 700,
          textAlign: "center", verticalAlign: "middle",
        }}>{n}</span>
      )}
    </div>
  );
}

// With a request in progress the icon has a dot (in Decky's list of plugins too).
function Icon() {
  useStore();
  return (
    <svg width="1em" height="1em" viewBox="0 0 24 24" fill="none">
      <rect x="2" y="2" width="20" height="20" rx="5" stroke="currentColor" strokeWidth="2" />
      <path d="M8 7l8 10M16 7L8 17" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" />
      {inProgress() > 0 && <circle cx="19.5" cy="4.5" r="4.5" fill={C.blue} />}
    </svg>
  );
}

export default definePlugin(() => {
  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const loop = async () => {
    await poll();
    if (!stopped) timer = setTimeout(loop, fails >= 3 ? 60000 : 15000);
  };
  loop();
  return {
    name: "Gestor ReXNative",
    titleView: <Title />,
    content: <Content />,
    icon: <Icon />,
    onDismount() {
      stopped = true;
      if (timer) clearTimeout(timer);
    },
  };
});
