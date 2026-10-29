# -*- coding: utf-8 -*-
"""同时提供面板页面，并把生成请求转发到 OpenAI 兼容接口。只监听本机。"""
import json
import os
import re
import sys
import threading
import uuid
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"
PORT = 8765
STORE = ROOT / "data" / "submissions.json"
ARCHIVE = ROOT / "data" / "我的全部稿件.json"
SNAPSHOT = ROOT / "data" / "board-snapshot.json"
PUBLIC = ROOT / "data" / "public-submissions.json"
STORE_LOCK = threading.Lock()


def extract_text(obj):
    if not isinstance(obj, dict):
        return ""
    kind = str(obj.get("type") or "")
    if "reasoning" in kind:
        return ""
    if isinstance(obj.get("delta"), str) and ("output_text" in kind or not kind):
        return obj["delta"]
    choice = (obj.get("choices") or [{}])[0] if obj.get("choices") else {}
    delta = choice.get("delta") or {}
    message = choice.get("message") or {}
    if isinstance(delta, dict) and delta.get("content"):
        return delta["content"]
    if isinstance(message, dict) and message.get("content"):
        return message["content"]
    parts = []
    for item in obj.get("output") or []:
        if not isinstance(item, dict):
            continue
        for block in item.get("content") or []:
            if isinstance(block, dict) and block.get("text") and "reasoning" not in str(block.get("type") or ""):
                parts.append(block["text"])
    return "".join(parts)


def ark_input(system, prompt, system_role):
    user_text = prompt
    messages = []
    if system and system_role:
        messages.append({"role": "system", "content": [{"type": "input_text", "text": system}]})
    elif system:
        user_text = system + "\n\n" + prompt
    messages.append({"role": "user", "content": [{"type": "input_text", "text": user_text}]})
    return messages


def supports_thinking_off(model):
    return model.startswith(("deepseek-", "doubao-", "glm-5-2"))


def open_upstream(url, payload, api_key):
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    req = Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    return urlopen(req, timeout=180)


def normalize_key(api_key):
    text = str(api_key or "").strip().strip("\"'")
    if text.lower().startswith("bearer "):
        text = text[7:].strip()
    found = re.search(r"ark-[0-9a-fA-F]+(?:-[0-9a-fA-F]+)+", text)
    if found:
        return found.group(0)
    return re.sub(r"\s+", "", text)


def allowed_target(base_url):
    parsed = urlparse(base_url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    local = host in ("127.0.0.1", "localhost", "::1")
    if parsed.scheme == "http" and not local:
        return False
    if host in ("169.254.169.254", "metadata.google.internal"):
        return False
    return True


def load_list(path):
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, dict):
        data = data.get("items") or []
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def load_submissions():
    return load_list(STORE)


def write_personal(items):
    STORE.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(items, ensure_ascii=False, indent=2) + "\n"
    STORE.write_text(text, encoding="utf-8")
    ARCHIVE.write_text(text, encoding="utf-8")


def load_board():
    return load_list(SNAPSHOT)


def write_board(items):
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(items, ensure_ascii=False, indent=2) + "\n"
    published = [item for item in items if item.get("status") == "submitted"]
    SNAPSHOT.write_text(text, encoding="utf-8")
    PUBLIC.write_text(json.dumps(published, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clip(value, limit):
    return str(value or "").strip()[:limit]


def upsert_submission(body, load=load_submissions, write=write_personal):
    status = str(body.get("status") or "saved")
    if status not in ("submitted", "saved", "deleted"):
        status = "saved"
    content = clip(body.get("content"), 100000)
    author = clip(body.get("author"), 40)
    title = clip(body.get("title"), 80) or "未命名"
    tag = clip(body.get("tag"), 80)
    if not content:
        return None, "正文是空的"
    if status == "submitted" and not author:
        return None, "先填写提交人"
    if status == "submitted" and not tag:
        return None, "先填写同人标签，写明是哪个 IP 或人"
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    incoming_id = clip(body.get("id") or body.get("_id"), 40)
    with STORE_LOCK:
        items = load()
        found = None
        for item in items:
            if incoming_id and incoming_id in (str(item.get("id") or ""), str(item.get("_id") or "")):
                found = item
                break
        if found is None:
            new_id = incoming_id or uuid.uuid4().hex[:12]
            found = {"id": new_id, "_id": new_id, "createdAt": body.get("createdAt") or now}
            items.insert(0, found)
        found.update({
            "_id": found.get("_id") or found.get("id"),
            "status": status,
            "author": author,
            "title": title,
            "tag": tag,
            "content": content,
            "updatedAt": now,
            "deletedAt": (body.get("deletedAt") or now) if status == "deleted" else "",
        })
        write(items)
        return dict(found), ""


def change_submission(body, load=load_submissions, write=write_personal):
    action = str(body.get("action") or "")
    incoming_id = clip(body.get("id"), 40)
    if action not in ("delete", "restore", "purge") or not incoming_id:
        return None, "没有这条记录"
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    with STORE_LOCK:
        items = load()
        found = None
        for item in items:
            if incoming_id in (str(item.get("id") or ""), str(item.get("_id") or "")):
                found = item
                break
        if found is None:
            return None, "没有这条记录"
        if action == "purge":
            kept = [
                item for item in items
                if incoming_id not in (str(item.get("id") or ""), str(item.get("_id") or ""))
            ]
            write(kept)
            return {"id": incoming_id, "status": "purged"}, ""
        if action == "delete":
            found["status"] = "deleted"
            found["deletedAt"] = now
        else:
            found["status"] = "submitted"
            found.pop("deletedAt", None)
        found["updatedAt"] = now
        write(items)
        return dict(found), ""


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/submissions":
            want = (parse_qs(parsed.query).get("status") or ["all"])[0]
            with STORE_LOCK:
                items = load_submissions()
            if want in ("submitted", "saved", "deleted"):
                items = [item for item in items if item.get("status") == want]
            self._json(200, {"items": items})
            return
        super().do_GET()

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/submissions":
            self._save_submission(load_submissions, write_personal)
            return
        if path == "/api/board":
            self._save_submission(load_board, write_board)
            return
        if path != "/api/chat":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 500_000:
            self._text(400, "请求体无效")
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            self._text(400, "请求不是 JSON")
            return
        base = str(body.get("baseUrl") or "").strip().rstrip("/")
        model = str(body.get("model") or "").strip()
        prompt = str(body.get("prompt") or "").strip()
        system = str(body.get("system") or "").strip()
        api_key = normalize_key(body.get("apiKey"))
        try:
            api_key.encode("latin-1")
        except UnicodeEncodeError:
            self._text(400, "方舟 API 只填写 ark- 开头的密钥。不要把整段 curl、中文或提示词贴进这个框。")
            return
        if not base or not model or not prompt:
            self._text(400, "接口地址、模型名和提示词都不能空")
            return
        if not allowed_target(base):
            self._text(400, "接口地址需要是 https，或本机的 http://127.0.0.1")
            return
        host = urlparse(base).hostname or ""
        ark = "volces.com" in host
        thinking_off = supports_thinking_off(model) if ark else False
        system_role = True
        upstream = None
        last_code = 502
        last_detail = ""
        for _ in range(3):
            if ark:
                url = base if base.endswith("/responses") else base + "/responses"
                payload = {
                    "model": model,
                    "stream": True,
                    "input": ark_input(system, prompt, system_role),
                }
                if thinking_off:
                    payload["thinking"] = {"type": "disabled"}
            else:
                url = base if base.endswith("/chat/completions") else base + "/chat/completions"
                user_text = prompt if system_role or not system else system + "\n\n" + prompt
                chat = []
                if system and system_role:
                    chat.append({"role": "system", "content": system})
                chat.append({"role": "user", "content": user_text})
                payload = {"model": model, "messages": chat, "stream": True}
            try:
                upstream = open_upstream(url, payload, api_key)
                break
            except HTTPError as err:
                detail = err.read().decode("utf-8", "replace")[:800]
                last_code = err.code
                last_detail = detail
                low = detail.lower()
                if err.code == 400 and thinking_off and "thinking" in low:
                    thinking_off = False
                    continue
                if err.code == 400 and system_role and system and "role" in low:
                    system_role = False
                    continue
                code = err.code if 400 <= err.code < 500 else 502
                self._text(code, "模型接口返回 %s。%s" % (err.code, detail[:500]))
                return
            except URLError as err:
                self._text(502, "连不上模型接口：%s" % err.reason)
                return
            except Exception as err:
                self._text(502, "转发失败：%s" % err)
                return
        if upstream is None:
            code = last_code if 400 <= last_code < 500 else 502
            self._text(code, "模型接口返回 %s。%s" % (last_code, last_detail[:500]))
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        try:
            self._pipe(upstream)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            upstream.close()

    def _pipe(self, upstream):
        wrote = False
        pending = b""
        for chunk in iter(lambda: upstream.read(1024), b""):
            pending += chunk
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                wrote = self._emit_line(line.decode("utf-8", "replace")) or wrote
        if pending:
            text = pending.decode("utf-8", "replace").strip()
            if text and not text.startswith("data:"):
                self._emit_json(text)
                wrote = True
            else:
                wrote = self._emit_line(text) or wrote
        if not wrote:
            self.wfile.write("模型没有返回正文。".encode("utf-8"))

    def _emit_line(self, line):
        line = line.strip()
        if not line.startswith("data:"):
            return False
        data = line[5:].strip()
        if not data or data == "[DONE]":
            return False
        return self._emit_json(data)

    def _emit_json(self, data):
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            return False
        text = extract_text(obj)
        if not text:
            return False
        self.wfile.write(text.encode("utf-8"))
        self.wfile.flush()
        return True

    def _save_submission(self, load, write):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 500_000:
            self._text(400, "请求体无效")
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            self._text(400, "请求不是 JSON")
            return
        if body.get("action"):
            item, err = change_submission(body, load, write)
        else:
            item, err = upsert_submission(body, load, write)
        if err:
            self._text(400, err)
            return
        self._json(200, {"item": item})

    def _json(self, code, payload):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _text(self, code, message):
        raw = message.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class PublicHandler(Handler):
    """公网通道只接受生成请求和新投稿，不暴露稿库读取、修改或删除。"""

    def do_GET(self):
        self.send_error(404)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/submit":
            self._save_submission(load_board, write_board)
            return
        if path == "/api/chat":
            super().do_POST()
            return
        self.send_error(404)


if __name__ == "__main__":
    os.chdir(ROOT)
    chat_only = "--chat-only" in sys.argv
    port = 8766 if chat_only else PORT
    server = ThreadingHTTPServer((HOST, port), PublicHandler if chat_only else Handler)
    if chat_only:
        print("生成转发：http://%s:%s/api/chat" % (HOST, port), flush=True)
    else:
        print("短篇测试生成面板：http://%s:%s/studio.html" % (HOST, port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
