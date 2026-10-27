const STORY_BOARD = "https://dontlosedata.site/api/v1/301c06c6-a512-49d3-b85b-1a905840fa84";

async function boardRows() {
  try {
    const res = await fetch(STORY_BOARD, { cache: "no-store" });
    if (res.ok) {
      const rows = await res.json();
      if (Array.isArray(rows)) return rows;
      if (rows == null) return [];
    }
  } catch (err) {}
  const backup = await fetch("data/board-snapshot.json", { cache: "no-store" });
  if (!backup.ok) throw new Error("投稿列表没有读到。");
  const rows = await backup.json();
  if (!Array.isArray(rows)) throw new Error("投稿列表没有读到。");
  return rows;
}

function boardBody(item) {
  const now = new Date().toISOString();
  let status = "submitted";
  if (item.status === "deleted" || item.status === "saved") status = item.status;
  const id = String(item.id || item._id || "").slice(0, 40) || Math.random().toString(16).slice(2, 14);
  let content = String(item.content || "");
  const pack = () => ({
    _id: id,
    id,
    status,
    author: String(item.author || "").slice(0, 40),
    title: String(item.title || "").slice(0, 80) || "未命名",
    tag: String(item.tag || "").slice(0, 80),
    content,
    createdAt: item.createdAt || now,
    updatedAt: now,
    deletedAt: item.deletedAt || ""
  });
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

async function boardSave(item) {
  const record = boardBody(item);
  const headers = { "Content-Type": "application/json" };
  let res = await boardFetch(STORY_BOARD + "/id/" + encodeURIComponent(record.id), {
    method: "PUT",
    headers,
    body: JSON.stringify(record)
  });
  if (res && res.status === 409) {
    res = await boardFetch(STORY_BOARD, {
      method: "POST",
      headers,
      body: JSON.stringify(record)
    });
  }
  if (!res || !res.ok) throw new Error("这次没有保存成功。");
  return record;
}

async function boardPurge(item) {
  const id = item && (item.id || item._id);
  if (!id) throw new Error("没有这条记录。");
  const res = await boardFetch(STORY_BOARD + "/id/" + encodeURIComponent(id), { method: "DELETE" });
  if (!res || !res.ok) throw new Error("没有彻底删除。");
}
