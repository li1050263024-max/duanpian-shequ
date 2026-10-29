let boardSource = "";
const BOARD_DRAFTS_KEY = "storygen.submissionDrafts";

function localApi(path) {
  const host = location.hostname;
  if (host === "127.0.0.1" || host === "localhost") return path;
  return "http://127.0.0.1:8765" + path;
}

function onBoardLocalhost() {
  return location.hostname === "127.0.0.1" || location.hostname === "localhost";
}

function browserDrafts() {
  try {
    const rows = JSON.parse(localStorage.getItem(BOARD_DRAFTS_KEY) || "[]");
    return Array.isArray(rows) ? rows.filter(row => row && row.status === "saved") : [];
  } catch (err) {
    return [];
  }
}

function writeBrowserDrafts(rows) {
  localStorage.setItem(BOARD_DRAFTS_KEY, JSON.stringify(rows));
}

function removeBrowserDraft(id) {
  if (!id) return;
  writeBrowserDrafts(browserDrafts().filter(row => String(row.id || row._id) !== String(id)));
}

function makeBoardId() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") return window.crypto.randomUUID().replace(/-/g, "").slice(0, 12);
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

async function publicRelay(force) {
  if (!force && typeof PUBLIC_RELAY === "string" && PUBLIC_RELAY) return PUBLIC_RELAY.replace(/\/$/, "");
  try {
    const res = await fetch("data/relay.json?t=" + Date.now(), { cache: "no-store" });
    if (res.ok) {
      const data = await res.json();
      if (data && data.url) return String(data.url).replace(/\/$/, "");
    }
  } catch (err) {}
  return typeof PUBLIC_RELAY === "string" ? PUBLIC_RELAY.replace(/\/$/, "") : "";
}

async function readSnapshot(url, signal) {
  const res = await fetch(url, { cache: "no-store", signal });
  if (!res.ok) return null;
  const rows = await res.json();
  return Array.isArray(rows) ? rows : null;
}

async function savedDrafts() {
  const localRows = browserDrafts();
  if (!onBoardLocalhost()) return localRows;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 1200);
  try {
    const res = await fetch(localApi("/api/submissions?status=saved"), { cache: "no-store", signal: ctrl.signal });
    if (!res.ok) return localRows;
    const data = await res.json();
    const rows = Array.isArray(data) ? data : (data.items || []);
    return withDrafts(rows.filter(row => row && row.status === "saved" && (row.id || row._id)), localRows);
  } catch (err) {
    return localRows;
  } finally {
    clearTimeout(timer);
  }
}

function withDrafts(rows, drafts) {
  const ids = new Set(rows.map(row => String(row.id || row._id || "")));
  const extra = drafts.filter(row => !ids.has(String(row.id || row._id || "")));
  return extra.concat(rows);
}

async function boardRows() {
  boardSource = "";
  const local = localApi("data/board-snapshot.json");
  if (local !== "data/board-snapshot.json") {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 1200);
    try {
      const rows = await readSnapshot(local, ctrl.signal);
      if (rows) {
        boardSource = "local";
        return withDrafts(rows, await savedDrafts());
      }
    } catch (err) {
    } finally {
      clearTimeout(timer);
    }
  }
  const rows = await readSnapshot("data/board-snapshot.json");
  if (!rows) throw new Error("投稿列表没有读到。");
  boardSource = "repo";
  return withDrafts(rows, await savedDrafts());
}

function boardBody(item) {
  const now = new Date().toISOString();
  let status = "submitted";
  if (item.status === "deleted" || item.status === "saved") status = item.status;
  const id = String(item.id || item._id || "").slice(0, 40);
  return {
    _id: id,
    id,
    status,
    author: String(item.author || "").slice(0, 40),
    title: String(item.title || "").slice(0, 80) || "未命名",
    tag: String(item.tag || "").slice(0, 80),
    content: String(item.content || ""),
    createdAt: item.createdAt || now,
    updatedAt: now,
    deletedAt: status === "deleted" ? (item.deletedAt || now) : ""
  };
}

async function boardFetch(url, options) {
  let last;
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const res = await fetch(url, options);
      if (res.ok || (res.status !== 429 && res.status < 500)) return res;
      last = res;
    } catch (err) {
      last = null;
    }
    if (attempt === 0) await new Promise(resolve => setTimeout(resolve, 600));
  }
  return last;
}

async function boardSave(item) {
  const record = boardBody(item);
  if (record.status === "saved" && !onBoardLocalhost()) {
    record.id = record.id || makeBoardId();
    record._id = record.id;
    const rows = browserDrafts().filter(row => String(row.id || row._id) !== record.id);
    rows.unshift(record);
    writeBrowserDrafts(rows);
    return record;
  }
  const path = record.status === "saved" ? "/api/submissions" : "/api/board";
  let url = localApi(path);
  if (!onBoardLocalhost() && record.status === "submitted") {
    const relay = await publicRelay(false);
    if (!relay) throw new Error("投稿通道暂时没有连接，请稍后再试。");
    url = relay + "/api/submit";
  }
  let res = await boardFetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(record)
  });
  if ((!res || !res.ok) && !onBoardLocalhost() && record.status === "submitted") {
    const relay = await publicRelay(true);
    if (relay && url !== relay + "/api/submit") {
      res = await boardFetch(relay + "/api/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(record)
      });
    }
  }
  if (!res || !res.ok) {
    throw new Error(record.status === "saved"
      ? "这次没有保存到本机。先运行 python tools/serve.py。"
      : "投稿通道暂时没有连接，请稍后再试。");
  }
  const data = await res.json();
  if (record.status === "submitted") removeBrowserDraft(record.id);
  return data.item || record;
}

async function boardPurge(item) {
  const id = item && (item.id || item._id);
  if (!id) throw new Error("没有这条记录。");
  const res = await boardFetch(localApi("/api/board"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "purge", id })
  });
  if (!res || !res.ok) throw new Error("没有彻底删除。");
}
