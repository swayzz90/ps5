"use strict";
const $ = (id) => document.getElementById(id);
const dateFormat = new Intl.DateTimeFormat("de-DE", {timeZone:"Europe/Berlin", day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"});
let requesting = false;

function localDate(value) {
  if (!value) return "Noch nie";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "Unbekannt" : dateFormat.format(d) + " Uhr";
}
function statusCopy(s) {
  if (s === "available") return {tag:"VERFÜGBAR", title:"Wieder verfügbar!", sub:"PlayStation zeigt einen Kaufbutton. Prüfe den Shop sofort.", symbol:"✓", label:"Verfügbar"};
  if (s === "unavailable") return {tag:"NICHT VERFÜGBAR", title:"Noch ausverkauft", sub:"PlayStation bietet diese PS5 aktuell nicht zum Kauf an.", symbol:"×", label:"Nicht verfügbar"};
  return {tag:"UNKLAR", title:"Status unbekannt", sub:"Der Kaufstatus konnte nicht eindeutig ermittelt werden.", symbol:"?", label:"Unbekannt"};
}
function render(data) {
  const status = ["available","unavailable","unknown"].includes(data.status) ? data.status : "unknown";
  const copy = statusCopy(status);
  const card = document.querySelector(".status-card");
  card.classList.remove("available","unavailable","unknown"); card.classList.add(status);
  $("statusTag").textContent = copy.tag;
  $("statusText").textContent = copy.title;
  $("statusSubtext").textContent = status === "unknown" && data.note ? data.note : copy.sub;
  $("statusSymbol").textContent = copy.symbol;
  $("checkedAt").textContent = localDate(data.checked_at);
  const warning = $("staleNotice");
  const age = data.checked_at ? Date.now() - new Date(data.checked_at).getTime() : Number.POSITIVE_INFINITY;
  if (!data.checked_at) {
    warning.textContent = "Die erste automatische Überprüfung wurde noch nicht durchgeführt.";
    warning.hidden = false;
  } else if (age > 90*60*1000) {
    warning.textContent = "Achtung: Die letzte Prüfung liegt länger als 90 Minuten zurück. Möglicherweise ist die GitHub-Aktion unterbrochen.";
    warning.hidden = false;
  } else warning.hidden = true;
  const history = Array.isArray(data.history) ? data.history.slice(-6).reverse() : [];
  $("historyCount").textContent = `${history.length} Prüfungen`;
  const list = $("historyList");
  list.replaceChildren();
  if (!history.length) {
    const p = document.createElement("p");p.className="empty";p.textContent="Noch keine Prüfungen vorhanden.";list.append(p);
  }
  history.forEach(item => {
    const s = ["available","unavailable","unknown"].includes(item.status) ? item.status : "unknown";
    const row = document.createElement("div");row.className="history-row";
    const label = document.createElement("span");label.className="history-label";
    const dot = document.createElement("span");dot.className=`history-dot ${s}`;
    const name = document.createElement("span");name.textContent=statusCopy(s).label;
    label.append(dot,name);
    const timestamp = document.createElement("time");timestamp.textContent=localDate(item.at);
    if (item.at) timestamp.dateTime=item.at;
    row.append(label,timestamp);list.append(row);
  });
}
async function refresh() {
  if (requesting) return;
  requesting = true;
  $("refreshButton").disabled = true;
  $("refreshSymbol").textContent = "…";
  try {
    // A refresh fetches the last result, not a new shop query. Only GitHub Actions queries PlayStation.
    const response = await fetch(`./data/status.json?v=${Date.now()}`, {cache:"no-store"});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    render(await response.json());
  } catch (error) {
    render({status:"unknown",note:"Der gespeicherte Status konnte nicht geladen werden.",checked_at:null,history:[]});
  } finally {
    requesting = false;
    $("refreshButton").disabled = false;
    $("refreshSymbol").textContent = "↻";
  }
}
$("refreshButton").addEventListener("click", refresh);

document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
setInterval(() => { if (!document.hidden) refresh(); }, 60_000);
refresh();

$("generateTopic").addEventListener("click", () => {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  $("topicValue").textContent = "ps5-" + Array.from(bytes, x => x.toString(16).padStart(2,"0")).join("");
  $("topicBox").hidden = false;
  $("copyTopic").textContent = "Kopieren";
});
$("copyTopic").addEventListener("click", async () => {
  const topic = $("topicValue").textContent;
  try {
    await navigator.clipboard.writeText(topic);
    $("copyTopic").textContent = "Kopiert";
  } catch (_) {
    $("copyTopic").textContent = "Markieren";
    const selection = window.getSelection();
    const range = document.createRange();range.selectNodeContents($("topicValue"));selection.removeAllRanges();selection.addRange(range);
  }
});
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("./sw.js").catch(() => {}));
}


// iOS Safari: Installationshinweis nur im Browser, nicht in der Home-Bildschirm-App.
(function setUpIPhoneHomeScreenTip() {
  const tip = $("iphoneInstall");
  const dismiss = $("dismissInstall");
  if (!tip || !dismiss) return;
  const userAgent = navigator.userAgent || "";
  const isIOS = /iPhone|iPad|iPod/i.test(userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const isInstalled = window.matchMedia("(display-mode: standalone)").matches ||
    navigator.standalone === true;
  let hiddenForSession = false;
  try { hiddenForSession = sessionStorage.getItem("ps5InstallDismissed") === "1"; }
  catch (_) { /* session storage may be disabled */ }
  if (isIOS && !isInstalled && !hiddenForSession) tip.hidden = false;
  dismiss.addEventListener("click", () => {
    tip.hidden = true;
    try { sessionStorage.setItem("ps5InstallDismissed", "1"); }
    catch (_) { /* no persistence available */ }
  });
})();
