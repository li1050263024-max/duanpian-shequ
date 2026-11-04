let boardSource = "";
let boardCache = [];
let crudIds = {};
const BOARD_DRAFTS_KEY = "storygen.submissionDrafts";
const CRUD_BOARD = "https://crudcrud.com/api/63224c73389c46d184547c139a387a9e/submissions";

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
  const data = await res.json();
  const rows = Array.isArray(data) ? data : data && data.items;
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

function storyKey(item) {
  return String((item && (item.id || item._id)) || "");
}

function asStory(row) {
  if (!row) return null;
  const id = String(row.id || "");
  if (!/^[0-9a-zA-Z]{8,40}$/.test(id)) return null;
  const cover = String(row.cover || "");
  const safeCover = cover.startsWith("data:image/")
    ? cover
    : (cover.startsWith("assets/covers/") && cover.indexOf("..") < 0 ? cover.slice(0, 180) : "");
  return {
    id,
    _id: id,
    crudId: row.crudId || "",
    status: row.status || "submitted",
    author: String(row.author || ""),
    title: String(row.title || ""),
    tag: String(row.tag || ""),
    cover: safeCover,
    content: String(row.content || ""),
    createdAt: row.createdAt || "",
    updatedAt: row.updatedAt || "",
    deletedAt: row.deletedAt || ""
  };
}

function mergeStory(prev, next) {
  if (!prev) return next;
  if (!next) return prev;
  const prevTime = Date.parse(prev.updatedAt || prev.createdAt || 0) || 0;
  const nextTime = Date.parse(next.updatedAt || next.createdAt || 0) || 0;
  const newer = nextTime >= prevTime ? next : prev;
  const older = newer === next ? prev : next;
  const merged = Object.assign({}, older, newer);
  if (String(older.content || "").length > String(newer.content || "").length) merged.content = older.content;
  const covers = [String(newer.cover || ""), String(older.cover || "")];
  merged.cover = covers.find(value => value.startsWith("data:image/")) || covers.find(Boolean) || "";
  merged.id = storyKey(prev) || storyKey(next);
  merged._id = merged.id;
  merged.crudId = next.crudId || prev.crudId || "";
  return merged;
}

function mergeBoard(base, extra) {
  const byId = {};
  const order = [];
  base.concat(extra).forEach(item => {
    const story = asStory(item);
    if (!story) return;
    if (!byId[story.id]) order.push(story.id);
    byId[story.id] = mergeStory(byId[story.id], story);
  });
  return order.map(id => byId[id]);
}

async function crudRows() {
  try {
    const res = await fetch(CRUD_BOARD, { cache: "no-store" });
    if (!res.ok) return [];
    const data = await res.json();
    if (!Array.isArray(data)) return [];
    crudIds = {};
    return data.map(row => {
      const story = asStory(row);
      if (story && row._id) {
        story.crudId = row._id;
        crudIds[story.id] = row._id;
      }
      return story;
    }).filter(Boolean);
  } catch (err) {
    return [];
  }
}

async function finishRows(rows) {
  const cloud = await crudRows();
  const merged = withDrafts(mergeBoard(rows, cloud), await savedDrafts());
  boardCache = merged;
  return merged;
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
        return finishRows(rows);
      }
    } catch (err) {
    } finally {
      clearTimeout(timer);
    }
  }
  const rows = await readSnapshot("data/board-snapshot.json");
  if (!rows) throw new Error("投稿列表没有读到。");
  boardSource = onBoardLocalhost() ? "local" : "repo";
  return finishRows(rows);
}

function boardBody(item) {
  const now = new Date().toISOString();
  let status = "submitted";
  if (item.status === "deleted" || item.status === "saved") status = item.status;
  const id = String(item.id || item._id || "").slice(0, 40);
  const cover = String(item.cover || "");
  const safeCover = cover.startsWith("assets/covers/") && !cover.includes("..") ? cover.slice(0, 180) : "";
  return {
    _id: id,
    id,
    status,
    author: String(item.author || "").slice(0, 40),
    title: String(item.title || "").slice(0, 80) || "未命名",
    tag: String(item.tag || "").slice(0, 80),
    cover: safeCover,
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

function relayPayload(item) {
  const record = boardBody(item);
  const cover = String(item.cover || "");
  if (cover.startsWith("data:image/")) record.cover = cover;
  delete record._id;
  delete record.crudId;
  return record;
}

async function crudUpsert(item) {
  const payload = relayPayload(item);
  const id = payload.id;
  if (!id) throw new Error("没有这条记录。");
  let crudId = item.crudId || crudIds[id] || "";
  if (!crudId) {
    await crudRows();
    crudId = crudIds[id] || "";
  }
  const headers = { "Content-Type": "application/json" };
  if (crudId) {
    const res = await boardFetch(CRUD_BOARD + "/" + crudId, {
      method: "PUT",
      headers,
      body: JSON.stringify(payload)
    });
    if (!res || !res.ok) {
      const message = res ? await res.text() : "";
      throw new Error(message || "云端没有保存。");
    }
    crudIds[id] = crudId;
    return Object.assign({}, item, payload, { id, _id: id, crudId });
  }
  const res = await boardFetch(CRUD_BOARD, {
    method: "POST",
    headers,
    body: JSON.stringify(payload)
  });
  if (!res || !res.ok) {
    const message = res ? await res.text() : "";
    throw new Error(message || "云端没有保存。");
  }
  const saved = await res.json();
  const story = asStory(saved);
  if (story && saved._id) {
    story.crudId = saved._id;
    crudIds[id] = saved._id;
  }
  return story || Object.assign({}, payload, { id, _id: id });
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
  if (!onBoardLocalhost()) {
    if (record.status !== "submitted") throw new Error("这里只能提交，不能删除。");
    const saved = await crudUpsert(item);
    removeBrowserDraft(record.id);
    return saved;
  }
  const path = record.status === "saved" ? "/api/submissions" : "/api/board";
  const res = await boardFetch(localApi(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(record)
  });
  if (!res || !res.ok) {
    throw new Error(record.status === "saved"
      ? "这次没有保存到本机。先运行 python tools/serve.py。"
      : "投稿没有保存。");
  }
  const data = await res.json();
  const saved = data.item || record;
  if (record.status === "submitted") {
    removeBrowserDraft(record.id);
    await crudUpsert(Object.assign({}, item, saved, { cover: item.cover || saved.cover || "" }));
  }
  return saved;
}

async function boardCover(id, image) {
  if (!String(image || "").startsWith("data:image/")) throw new Error("封面需要是图片");
  const current = boardCache.find(item => storyKey(item) === String(id)) || { id, status: "submitted" };
  const next = Object.assign({}, current, { cover: image });
  if (!onBoardLocalhost()) return crudUpsert(next);
  const res = await boardFetch(localApi("/api/cover"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, image })
  });
  if (!res || !res.ok) {
    const message = res ? await res.text() : "";
    throw new Error(message || "封面没有传上。");
  }
  const data = await res.json();
  const saved = data.item || next;
  await crudUpsert(Object.assign({}, next, saved, { cover: image }));
  return saved;
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
