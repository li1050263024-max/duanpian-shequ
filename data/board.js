let boardSource = "";
const REMOTE_BOARD = "https://dontlosedata.site/api/v1/301c06c6-a512-49d3-b85b-1a905840fa84";

function localApi(path) {
  const host = location.hostname;
  if (host === "127.0.0.1" || host === "localhost") return path;
  return "http://127.0.0.1:8765" + path;
}

async function readRows(url) {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) return null;
  const data = await res.json();
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.items)) return data.items;
  return null;
}

async function boardRows() {
  boardSource = "";
  try {
    const rows = await readRows(localApi("/api/submissions"));
    if (rows) {
      boardSource = "live";
      return rows;
    }
  } catch (err) {}
  try {
    const rows = await readRows(REMOTE_BOARD);
    if (rows) {
      boardSource = "remote";
      return rows;
    }
  } catch (err) {}
  const backup = await fetch("data/board-snapshot.json", { cache: "no-store" });
  if (!backup.ok) throw new Error("投稿列表没有读到。");
  const rows = await backup.json();
  if (!Array.isArray(rows)) throw new Error("投稿列表没有读到。");
  boardSource = "backup";
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

function fitRemote(record) {
  const copy = Object.assign({}, record);
  let content = String(copy.content || "");
  const pack = () => {
    copy.content = content;
    return copy;
  };
  let body = pack();
  while (content.length > 200 && new TextEncoder().encode(JSON.stringify(body)).length > 28000) {
    content = content.slice(0, Math.floor(content.length * 0.85));
    body = pack();
  }
  return body;
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

async function saveRemote(record) {
  const headers = { "Content-Type": "application/json" };
  const body = JSON.stringify(fitRemote(record));
  let res = null;
  if (record.id) {
    res = await boardFetch(REMOTE_BOARD + "/id/" + encodeURIComponent(record.id), {
      method: "PUT",
      headers,
      body
    });
  }
  if (!res || res.status === 404 || res.status === 409) {
    res = await boardFetch(REMOTE_BOARD, { method: "POST", headers, body });
  }
  if (!res || !res.ok) return null;
  try {
    const data = await res.json();
    return data && typeof data === "object" ? Object.assign({}, record, data) : record;
  } catch (err) {
    return record;
  }
}

async function boardSave(item) {
  const record = boardBody(item);
  try {
    const res = await boardFetch(localApi("/api/submissions"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(record)
    });
    if (res && res.ok) {
      const data = await res.json();
      return data.item || record;
    }
  } catch (err) {}
  const saved = await saveRemote(record);
  if (!saved) throw new Error("这次没有保存成功。");
  return saved;
}

async function boardPurge(item) {
  const id = item && (item.id || item._id);
  if (!id) throw new Error("没有这条记录。");
  const local = await boardFetch(localApi("/api/submissions"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "purge", id })
  });
  if (local && local.ok) return;
  const remote = await boardFetch(REMOTE_BOARD + "/id/" + encodeURIComponent(id), { method: "DELETE" });
  if (!remote || !remote.ok) throw new Error("没有彻底删除。");
}
