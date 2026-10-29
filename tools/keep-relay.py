# -*- coding: utf-8 -*-
"""把本机生成接口公开给其他电脑。通道断开后自动换一条，并写下新地址。"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLOUDFLARED = Path(os.environ.get("TEMP", ".")) / "cloudflared.exe"
LOG = Path(os.environ.get("TEMP", ".")) / "story-relay.log"
METRICS = "http://127.0.0.1:20241/metrics"
READY = "http://127.0.0.1:20241/ready"
URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
RELAY_JS = ROOT / "data" / "relay.js"
RELAY_JSON = ROOT / "data" / "relay.json"
AUTHOR = "li1050263024-max"
EMAIL = "310904057+li1050263024-max@users.noreply.github.com"


def note(text):
    line = time.strftime("%H:%M:%S ") + text
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def http_json(url):
    with urllib.request.urlopen(url, timeout=3) as res:
        return json.loads(res.read().decode())


def tunnel_ready():
    try:
        data = http_json(READY)
    except Exception:
        return False
    return data.get("status") == 200 and int(data.get("readyConnections") or 0) > 0


def tunnel_url():
    try:
        with urllib.request.urlopen(METRICS, timeout=3) as res:
            text = res.read().decode("utf-8", "replace")
    except Exception:
        text = ""
    found = URL_RE.findall(text)
    if found:
        return found[-1]
    if LOG.exists():
        found = URL_RE.findall(LOG.read_text(encoding="utf-8", errors="replace"))
        if found:
            return found[-1]
    return ""


def write_address(url):
    RELAY_JSON.write_text(json.dumps({"url": url}, ensure_ascii=False) + "\n", encoding="utf-8")
    RELAY_JS.write_text('const PUBLIC_RELAY = "%s";\n' % url, encoding="utf-8")


def publish(url):
    write_address(url)
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = AUTHOR
    env["GIT_AUTHOR_EMAIL"] = EMAIL
    env["GIT_COMMITTER_NAME"] = AUTHOR
    env["GIT_COMMITTER_EMAIL"] = EMAIL
    subprocess.run(["git", "add", "--", "data/relay.json", "data/relay.js"], cwd=ROOT, check=False)
    quiet = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT)
    if quiet.returncode == 0:
        return
    subprocess.run(["git", "commit", "-m", "更新其他电脑用的连接地址。"], cwd=ROOT, env=env, check=False)
    pushed = subprocess.run(["git", "push", "origin", "HEAD"], cwd=ROOT, env=env)
    note("已推送新地址" if pushed.returncode == 0 else "新地址写好了，推送没有成功")


def stop_tunnel():
    subprocess.run(["taskkill", "/F", "/IM", "cloudflared.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def start_tunnel():
    if not CLOUDFLARED.exists():
        raise SystemExit("没有找到 cloudflared.exe")
    stop_tunnel()
    time.sleep(1)
    handle = LOG.open("a", encoding="utf-8")
    handle.write("\n----- start %s -----\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
    handle.flush()
    subprocess.Popen(
        [str(CLOUDFLARED), "tunnel", "--url", "http://127.0.0.1:8766", "--protocol", "http2", "--no-autoupdate"],
        stdout=handle,
        stderr=subprocess.STDOUT,
        cwd=str(ROOT),
        creationflags=0x00000200,
    )
    deadline = time.time() + 40
    while time.time() < deadline:
        url = tunnel_url()
        if url and tunnel_ready():
            note("已连上 " + url)
            return url
        time.sleep(1)
    url = tunnel_url()
    if url:
        note("地址已有，通道还在接通 " + url)
        return url
    raise SystemExit("通道没有接通")


def main():
    watch = "--watch" in sys.argv
    url = start_tunnel()
    publish(url)
    if not watch:
        return
    misses = 0
    while True:
        time.sleep(15)
        current = tunnel_url()
        if tunnel_ready() and current:
            misses = 0
            if current != url:
                url = current
                note("地址变了 " + url)
                publish(url)
            continue
        misses += 1
        if misses < 2:
            note("通道没有应答，再等一次")
            continue
        note("通道断开，正在重连")
        url = start_tunnel()
        publish(url)
        misses = 0


if __name__ == "__main__":
    main()
