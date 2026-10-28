let boardSource = "";

function localApi(path) {
  const host = location.hostname;
  if (host === "127.0.0.1" || host === "localhost") return path;
  return "http://127.0.0.1:8765" + path;
}

async function readSnapshot(url, signal) {
  const res = await fetch(url, { cache: "no-store", signal });
  if (!res.ok) return null;
  const rows = await res.json();
  return Array.isArray(rows) ? rows : null;
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
        return rows;
      }
    } catch (err) {
    } finally {
      clearTimeout(timer);
    }
  }
  const rows = await readSnapshot("data/board-snapshot.json");
  if (!rows) throw new Error("投稿列表没有读到。");
  boardSource = "repo";
  return rows;
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
  const path = record.status === "saved" ? "/api/submissions" : "/api/board";
  const res = await boardFetch(localApi(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(record)
  });
  if (!res || !res.ok) {
    throw new Error(record.status === "saved"
      ? "这次没有保存到本机。先运行 python tools/serve.py。"
      : "这次没有写进仓库里的稿库。先在本机运行 python tools/serve.py。");
  }
  const data = await res.json();
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
