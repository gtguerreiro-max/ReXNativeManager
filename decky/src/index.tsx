// Gestor ReXNative no menu rápido (…) do Steam Deck: os pedidos (o PC a descarregar, compilar e
// enviar jogos) com o progresso, avisos quando um jogo fica pronto, e um botão para abrir o Gestor.
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
import { useEffect, useState } from "react";

declare const SteamClient: any;

type Progress = {
  done?: number; total?: number; rate?: number; eta?: number; step?: string; stage?: string;
  step_pt?: string; phase?: string; pct?: number; step_elapsed?: number; phases?: { name: string; now: boolean }[];
};
type Order = {
  id: string; title: string; name?: string; status: string; stage?: string; error?: string; progress?: Progress;
  kind?: string; last?: string; report?: { status?: string };
};
type Status = {
  installed: boolean; online?: boolean; pc?: string; deck_free?: number; error?: string;
  orders?: Order[]; pending?: { add: number; remove: number; titles?: string[] }; gestor_appid?: number;
  version?: string; plugin_latest?: string; plugin_update?: boolean; gestor_open?: boolean;
  games?: { title: string; appid: number; last_played?: number }[];
};

const getStatus = callable<[], Status>("status");
const flushNow = callable<[], { flush?: string; error?: string }>("flush");
const updatePlugin = callable<[], { ok?: boolean; version?: string; error?: string }>("update");

const gb = (b?: number) => b == null ? "?" : b >= 1e9 ? (b / 1e9).toFixed(1) + " GB" : Math.max(1, Math.round(b / 1e6)) + " MB";
const eta = (s?: number) => s == null || !isFinite(s) ? "" : s < 90 ? Math.max(1, Math.round(s)) + " s" : s < 5400 ? Math.round(s / 60) + " min" : Math.floor(s / 3600) + " h " + Math.round((s % 3600) / 60) + " min";
const STAGE: Record<string, string> = {
  download: "Downloading", build: "Building on the PC", deck: "Sending to the Deck",
  library: "On the Deck: joins the library when you exit the Manager", done: "In the library",
};
const active = (o: Order) => o.status === "running" || o.status === "queued";
// Além dos pedidos de instalar: relatórios e o que se pediu do Gestor (recompilar, enviar, apagar).
const KIND: Record<string, string> = {
  "deck-report": "Report", pipeline: "Rebuild", deck: "Send", "deck-delete": "Delete", "deck-flush": "Library", report: "Report",
  "deck-gestor": "Launcher", "deck-restore": "Restore", "deck-plugin": "Plugin", "deck-batch": "All",
};
const isOrder = (o: Order) => !o.kind || o.kind === "order";

function doneText(o: Order): string {
  if (isOrder(o)) return STAGE[o.stage || "done"] || "Ready";
  if (o.kind === "deck-batch") return o.last || "Done";
  if (o.kind === "deck-report") return "Report: " + ((o.report || {}).status || "done");
  return (KIND[o.kind || ""] || "Done") + ": " + (o.last || "done");
}

// O nome do jogo (a app do PC manda-o limpo; um PC antigo só manda o título da tarefa) e, nas que
// não são pedidos de instalar, o que é ("Send", "Rebuild"...).
function orderName(o: Order): string {
  const n = o.name || o.title.replace(/^(Report|Resend to the Deck|Install to the Deck|Delete from the Deck): /, "");
  return isOrder(o) ? n : `${n} · ${KIND[o.kind || ""] || o.kind}`;
}

function orderText(o: Order): string {
  const p = o.progress || {};
  if (o.status === "queued") return "Queued";
  if (o.status === "ok") return doneText(o);
  if (o.status === "failed") return o.error || "Failed";
  if (o.status === "cancelled") return "Cancelled";
  if (o.status === "interrupted") return "Interrupted";
  if (p.total) return `${isOrder(o) ? STAGE[o.stage || ""] || "" : KIND[o.kind || ""] || ""}: ${gb(p.done)} of ${gb(p.total)}${p.rate ? " · " + (p.rate / 1e6).toFixed(1) + " MB/s" : ""}`;
  if (p.phase) {
    const done = (p.phases || []).filter(x => !x.now).map(x => "✓ " + x.name).join(" ");
    return `${p.step_pt ? p.step_pt + ": " : ""}${p.phase}${p.pct != null ? " (" + Math.round(p.pct) + "%)" : ""}${done ? " · " + done : ""}${p.step_elapsed ? " · " + eta(p.step_elapsed) + " so far" : ""}`;
  }
  return p.step || (isOrder(o) ? STAGE[o.stage || ""] : o.last) || "Starting";
}

// O estado vem de 15 em 15 s (mesmo com o menu fechado, para avisar quando um jogo fica pronto).
let last: Status | null = null;
const seen: Record<string, string> = {};
const subs = new Set<(s: Status) => void>();

async function poll() {
  try {
    const s = await getStatus();
    const good: Order[] = [], bad: Order[] = [];
    for (const o of s.orders || []) {
      const before = seen[o.id];
      seen[o.id] = o.status;
      if (!before || before === o.status) continue;
      if (o.status === "ok") good.push(o);
      else if (o.status === "failed") bad.push(o);
    }
    // Com o Gestor aberto no Deck, a própria página avisa (eram avisos a dobrar); e vários que acabam
    // ao mesmo tempo são um aviso só.
    if (!s.gestor_open) {
      if (good.length === 1) toaster.toast({ title: orderName(good[0]), body: doneText(good[0]) });
      else if (good.length > 1) toaster.toast({ title: "ReXNative Manager", body: `${good.length} requests finished: ${good.map(orderName).join(", ")}` });
      if (bad.length === 1) toaster.toast({ title: orderName(bad[0]), body: "The request failed: " + (bad[0].error || "see the Manager") });
      else if (bad.length > 1) toaster.toast({ title: "ReXNative Manager", body: `${bad.length} requests failed: ${bad.map(orderName).join(", ")}` });
    }
    last = s;
    subs.forEach(f => f(s));
  } catch (e) {
    // o Decky ainda a arrancar: tenta da próxima vez
  }
}

function openGestor(appid?: number) {
  if (!appid) return;
  const gameId = ((BigInt(appid) << 32n) | 0x02000000n).toString();
  SteamClient.Apps.RunGame(gameId, "", -1, 100);
  Navigation.CloseSideMenus();
}

function Content() {
  const [s, setS] = useState<Status | null>(last);
  useEffect(() => {
    subs.add(setS);
    poll();
    const t = setInterval(poll, 3000);  // com o menu aberto, mais depressa
    return () => { subs.delete(setS); clearInterval(t); };
  }, []);

  if (!s) return <PanelSection><PanelSectionRow><Field label="Asking the PC…" /></PanelSectionRow></PanelSection>;
  if (!s.installed) {
    return (
      <PanelSection title="ReXNative Manager">
        <PanelSectionRow>
          <Field description="Install the Manager on the Deck from the PC app: Settings → Deck mode → Install the Manager on the Deck." />
        </PanelSectionRow>
      </PanelSection>
    );
  }
  const orders = s.orders || [];
  const now = orders.filter(active);
  const recent = orders.filter(o => !active(o)).slice(0, 3);
  const p = s.pending || { add: 0, remove: 0 };
  return (
    <>
      <PanelSection>
        <PanelSectionRow>
          <Field label="PC" description={s.online ? `${s.pc} · connected` : "Not connected: turn on the PC and open the Manager"}>
            {s.online && s.deck_free != null ? `${gb(s.deck_free)} free` : ""}
          </Field>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={!s.gestor_appid} onClick={() => openGestor(s.gestor_appid)}>
            Open the Manager
          </ButtonItem>
        </PanelSectionRow>
        {s.plugin_update && (
          <PanelSectionRow>
            <ButtonItem layout="below" description={`This plugin is v${s.version}; the PC has v${s.plugin_latest}.`}
              onClick={() => showModal(
                <ConfirmModal strTitle={`Update the plugin to v${s.plugin_latest}?`}
                  strDescription="Decky installs the new version from the PC and reloads this panel (a few seconds)."
                  strOKButtonText="Update" strCancelButtonText="Not now"
                  onOK={async () => {
                    toaster.toast({ title: "ReXNative Manager", body: `Updating the plugin to v${s.plugin_latest}…` });
                    const r = await updatePlugin();
                    if (r && r.error) toaster.toast({ title: "ReXNative Manager", body: "Update failed: " + r.error });
                  }} />)}>
              Update the plugin
            </ButtonItem>
          </PanelSectionRow>
        )}
      </PanelSection>
      {now.length > 0 && (
        <PanelSection title="In progress">
          {now.map(o => {
            const pr = o.progress || {};
            const pct = pr.total ? Math.min(100, (100 * (pr.done || 0)) / pr.total) : pr.pct != null ? Math.min(100, pr.pct) : undefined;
            const left = pr.total && pr.eta != null && (pr.done || 0) < pr.total ? ` · ${eta(pr.eta)} left` : "";
            return (
              <PanelSectionRow key={o.id}>
                <Field label={orderName(o)} description={orderText(o) + left} focusable={true} highlightOnFocus={true}
                  childrenLayout="below" bottomSeparator="none">
                  <ProgressBar nProgress={pct} indeterminate={pct == null} />
                </Field>
              </PanelSectionRow>
            );
          })}
        </PanelSection>
      )}
      {(s.games || []).length > 0 && (
        <PanelSection title="Play">
          {(s.games || []).map(g => (
            <PanelSectionRow key={g.appid}>
              <ButtonItem layout="below" onClick={() => openGestor(g.appid)}>{g.title}</ButtonItem>
            </PanelSectionRow>
          ))}
        </PanelSection>
      )}
      {(p.add > 0 || p.remove > 0) && (
        <PanelSection title="Library">
          <PanelSectionRow>
            <ButtonItem layout="below"
              description={`${p.add ? p.add + " game(s) to add" : ""}${p.add && p.remove ? ", " : ""}${p.remove ? p.remove + " shortcut(s) to remove" : ""}. Steam closes and reopens for a few seconds.`}
              onClick={() => showModal(
                <ConfirmModal strTitle="Update the library now?"
                  strDescription="Steam closes and reopens for a few seconds to add the new games to the library. If a game is running, wait until you exit it."
                  strOKButtonText="Update" strCancelButtonText="Not now"
                  onOK={async () => { const r = await flushNow(); if (r.error) toaster.toast({ title: "ReXNative Manager", body: r.error }); }} />)}>
              Add to the library now
            </ButtonItem>
          </PanelSectionRow>
        </PanelSection>
      )}
      {recent.length > 0 && (
        <PanelSection title="Recent requests">
          {recent.map(o => (
            <PanelSectionRow key={o.id}>
              <Field label={orderName(o)} description={orderText(o)} focusable={true} highlightOnFocus={true} />
            </PanelSectionRow>
          ))}
        </PanelSection>
      )}
    </>
  );
}

function Icon() {
  return (
    <svg width="1em" height="1em" viewBox="0 0 24 24" fill="none">
      <rect x="2" y="2" width="20" height="20" rx="5" stroke="currentColor" strokeWidth="2" />
      <path d="M8 7l8 10M16 7L8 17" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" />
    </svg>
  );
}

export default definePlugin(() => {
  poll();
  const timer = setInterval(poll, 15000);
  return {
    name: "Gestor ReXNative",
    titleView: <div className={staticClasses.Title}>ReXNative Manager</div>,
    content: <Content />,
    icon: <Icon />,
    onDismount() { clearInterval(timer); },
  };
});
