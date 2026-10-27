const STORY_BOARD = "https://crudcrud.com/api/63224c73389c46d184547c139a387a9e/submissions";

async function boardRows() {
  const res = await fetch(STORY_BOARD, { cache: "no-store" });
  if (!res.ok) throw new Error("投稿列表没有读到。");
  const rows = await res.json();
  return Array.isArray(rows) ? rows : [];
}

function boardBody(item) {
  const now = new Date().toISOString();
  let status = "submitted";
  if (item.status === "deleted" || item.status === "saved") status = item.status;
  return {
    id: String(item.id || "").slice(0, 40) || Math.random().toString(16).slice(2, 14),
    status,
    author: String(item.author || "").slice(0, 40),
    title: String(item.title || "").slice(0, 80) || "未命名",
    tag: String(item.tag || "").slice(0, 80),
    content: String(item.content || "").slice(0, 100000),
    createdAt: item.createdAt || now,
    updatedAt: now,
    deletedAt: item.deletedAt || ""
  };
}

async function boardFetch(url, options) {
  let last;
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const res = await fetch(url, options);
      if (res.ok || (res.status !== 429 && res.status < 500)) return res;
      last = res;
    } catch (err) {
      last = null;
    }
    if (attempt < 2) await new Promise(resolve => setTimeout(resolve, 500 * (attempt + 1)));
  }
  return last;
}

async function boardSave(item) {
  const body = boardBody(item);
  const headers = { "Content-Type": "application/json" };
  const payload = JSON.stringify(body);
  if (item._id) {
    const res = await boardFetch(STORY_BOARD + "/" + item._id, {
      method: "PUT",
      headers,
      body: payload
    });
    if (res && res.ok) return Object.assign({ _id: item._id }, body);
  }
  const res = await boardFetch(STORY_BOARD, {
    method: "POST",
    headers,
    body: payload
  });
  if (!res || !res.ok) throw new Error("这次没有保存成功。");
  const text = await res.text();
  try {
    const saved = JSON.parse(text);
    if (saved && saved._id) return saved;
  } catch (err) {}
  return Object.assign({ _id: "" }, body);
}

async function boardPurge(item) {
  if (!item || !item._id) throw new Error("没有这条记录。");
  const res = await fetch(STORY_BOARD + "/" + item._id, { method: "DELETE" });
  if (!res.ok) throw new Error("没有彻底删除。");
}
