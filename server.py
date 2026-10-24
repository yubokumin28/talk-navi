"""相談会ナビ: デスクトップのアイコンから起動する小さなアプリ(このPCの中だけで動く)。

  pythonw server.py --open   … 起動して、ホーム画面をタブの無い専用の窓で開く(もう動いていれば窓を開くだけ)

ホーム: 回の一覧 → 「進行ナビ」「編集」「新しい回」
編集  : 話題・要点・見せる画面(URL)・メモを手で埋めて保存すると、Obsidian のノートに書き込まれる
ノート: ノートのフォルダ(config.json の notes_dir。無ければこのフォルダの notes)の *.md のうち type: talk_navi のもの
"""
import datetime as dt
import html
import json
import re
import shutil
import socket
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import build
import screens
import talk_note

HERE = Path(__file__).resolve().parent
# 置き場は config.json で変えられる(config.example.json を写して直す)。無ければこのフォルダの notes を使う
_cfg_file = HERE / "config.json"
CFG = json.loads(_cfg_file.read_text(encoding="utf-8")) if _cfg_file.is_file() else {}
NOTES = Path(CFG.get("notes_dir") or HERE / "notes")
BACKUP = HERE / "backups"
TRASH = Path(CFG.get("trash_dir") or NOTES / ".trash")  # Obsidian の保管庫なら、その .trash を指すとごみ箱から戻せる
SERIES = CFG.get("series") or "相談会"  # 「＋新しい回」で付く題名「第N回 〇〇」
PORT = 5417  # 5398 は別の作業のプレビューと重なったので避けた(2026-10-22)
BASE = f"http://127.0.0.1:{PORT}"


def note_path(name: str):
    """名前のチェック(フォルダの外を触らせない)。"""
    if not name or not re.fullmatch(r"[\w\-]+\.md", name):
        return None
    p = NOTES / name
    return p if p.is_file() else None


def list_notes():
    items = []
    for p in sorted(NOTES.glob("*.md"), reverse=True):
        note = talk_note.parse(p.read_text(encoding="utf-8"))
        if note["fm"].get("type") == "talk_navi":
            items.append((p.name, note))
    return items


def next_saturday(after: dt.date) -> dt.date:
    d = after + dt.timedelta(days=1)
    while d.weekday() != 5:
        d += dt.timedelta(days=1)
    return d


def new_note() -> str:
    items = list_notes()
    last_no, last_date = 0, dt.date.today() - dt.timedelta(days=1)
    for _, n in items:
        m = re.search(r"第(\d+)回", n["fm"].get("title", ""))  # 題名の「第N回」から次の番号を決める
        if m:
            last_no = max(last_no, int(m.group(1)))
        try:
            last_date = max(last_date, dt.date.fromisoformat(n["fm"].get("date", "")))
        except ValueError:
            pass
    no, day = last_no + 1, next_saturday(max(last_date, dt.date.today() - dt.timedelta(days=1)))
    note = {
        "fm": {"type": "talk_navi", "date": day.isoformat(), "title": f"第{no}回 {SERIES}",
               "start": "8:00", "end": "9:30", "theme": "resort"},
        "head": ["%% 相談会ナビの編集画面で作った回。手で直してもよい。"],
        "secs": [
            {"title": "オープニング", "min": 10, "points": ["今日のゴール: 明日試せることを1つ持ち帰る", "話題は2つ + 相談タイム", "相談はいつでもOK(声でもチャットでも)"], "links": [], "memo": ""},
            {"title": "話題1", "min": 20, "points": [], "links": [], "memo": ""},
            {"title": "話題2", "min": 20, "points": [], "links": [], "memo": ""},
            {"title": "相談タイム", "min": 25, "points": ["相談を1つずつ聞く", "「AとBならどっち?」で絞る", "次の一歩を1つ決める"], "links": [], "memo": ""},
            {"title": "まとめ・次回予告", "min": 10, "points": ["今日の要点を1行ずつ", "持ち帰る次の一歩", "次回は来週土曜 8:00〜(予定)"], "links": [], "memo": ""},
        ],
    }
    name = f"{day.strftime('%y%m%d')}_dai{no}kai_navi.md"
    p = NOTES / name
    if not p.exists():
        p.write_text(talk_note.dump(note), encoding="utf-8")
    return name


def save_note(p: Path, note: dict):
    BACKUP.mkdir(exist_ok=True)
    # 上書き前の写しを残す。その場で直すモードは数秒ごとに自動保存するので、写しは10分に1回まで
    olds = sorted(BACKUP.glob(f"{p.stem}_*.md"), key=lambda x: x.stat().st_mtime)
    if not olds or (dt.datetime.now().timestamp() - olds[-1].stat().st_mtime) > 600:
        shutil.copy2(p, BACKUP / f"{p.stem}_{dt.datetime.now():%Y%m%d_%H%M%S}.md")
    old = talk_note.parse(p.read_text(encoding="utf-8"))
    note.setdefault("head", old["head"])
    # コピー札を知らない画面(edit.html)から保存しても消えないよう、同じ題名の話題から引き継ぐ
    old_cp = {s["title"]: s.get("copies", []) for s in old["secs"]}
    for s in note.get("secs", []):
        if "copies" not in s:
            s["copies"] = old_cp.get(s.get("title", ""), [])
    p.write_text(talk_note.dump(note), encoding="utf-8")


def home_html() -> str:
    rows = []
    for name, n in list_notes():
        fm = n["fm"]
        total = sum(s["min"] for s in n["secs"])
        topics = " / ".join(s["title"] for s in n["secs"])
        q = html.escape(name)
        rows.append(f"""<div class="card"><div><b>{html.escape(fm.get('title', ''))}</b>
<span class="sub">{html.escape(fm.get('date', ''))} {html.escape(fm.get('start', ''))}〜 ・ {total}分</span>
<div class="sub">{html.escape(topics)}</div></div>
<div class="btns"><a class="main" href="/navi?n={q}"><img class="ic" src="/icon/navi.png" alt="">進行ナビ</a>
<a href="/edit?n={q}"><img class="ic" src="/icon/edit.png" alt="">編集</a>
<button onclick="demo('{q}')" title="今日見せる画面だけを、新しい窓にまとめて開く"><img class="ic" src="/icon/demo.png" alt="">デモの窓</button>
<button class="del" data-n="{q}" data-title="{html.escape(fm.get('title', ''), quote=True)}" onclick="delNote(this)" title="この回を消す(ごみ箱へ)"><img class="ic" src="/icon/trash.png" alt="">消す</button></div></div>""")
    return (HERE / "home.html").read_text(encoding="utf-8").replace("__ROWS__", "\n".join(rows) or "<p>まだ回がありません</p>")


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, body, ctype="text/html; charset=utf-8", code=200):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def jsend(self, obj, code=200):
        self.send(json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8", code)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/":
            return self.send(home_html())
        if u.path == "/api/ping":
            return self.jsend({"app": "talk_navi"})
        m = re.fullmatch(r"/icon/(\w+)\.png", u.path)
        if m:
            p = HERE / "assets" / "icons" / f"{m.group(1)}.png"
            return self.send(p.read_bytes(), "image/png") if p.is_file() else self.send(b"", "image/png", 404)
        if u.path == "/navi":
            p = note_path(q.get("n", ""))
            return self.send(talk_note.render(p.read_text(encoding="utf-8"), p.name)) if p else self.send("ノートが見つかりません", code=404)
        if u.path == "/edit":
            return self.send((HERE / "edit.html").read_text(encoding="utf-8"))
        if u.path == "/api/note":
            p = note_path(q.get("n", ""))
            return self.jsend(talk_note.parse(p.read_text(encoding="utf-8"))) if p else self.jsend({"error": "not found"}, 404)
        self.send("not found", code=404)

    def do_POST(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        data = json.loads(body or b"{}")
        if u.path == "/api/new":
            return self.jsend({"n": new_note()})
        if u.path == "/api/quit":
            self.jsend({"ok": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        p = note_path(q.get("n", ""))
        if not p:
            return self.jsend({"error": "not found"}, 404)
        if u.path == "/api/note":
            save_note(p, data)
            return self.jsend({"ok": True})
        if u.path == "/api/memo":
            note = talk_note.parse(p.read_text(encoding="utf-8"))
            i = int(data.get("i", -1))
            if not 0 <= i < len(note["secs"]):
                return self.jsend({"error": "bad index"}, 400)
            note["secs"][i]["memo"] = str(data.get("text", ""))
            save_note(p, note)
            return self.jsend({"ok": True})
        if u.path == "/api/delete":
            # 消すのではなく Obsidian のごみ箱(.trash)へ移す。Obsidian の「ごみ箱」から戻せる
            TRASH.mkdir(exist_ok=True)
            dest = TRASH / p.name
            if dest.exists():
                dest = TRASH / f"{p.stem}_{dt.datetime.now():%Y%m%d_%H%M%S}.md"
            shutil.move(str(p), str(dest))
            return self.jsend({"ok": True})
        if u.path == "/api/demo":
            urls = talk_note.demo_urls(talk_note.parse(p.read_text(encoding="utf-8")))
            if urls:
                screens.show(urls[0], urls)
            return self.jsend({"ok": True, "count": len(urls)})
        if u.path == "/api/show":
            # 進行ナビの画面の札・Ctrl+番号 → デモの窓のそのタブへ切り替える(無ければ窓を作る・足す)
            url = str(data.get("url", ""))
            if not re.match(r"^https?://\S+$", url):
                return self.jsend({"error": "bad url"}, 400)
            urls = talk_note.demo_urls(talk_note.parse(p.read_text(encoding="utf-8")))
            return self.jsend(screens.show(url, urls))
        self.jsend({"error": "not found"}, 404)


def running() -> bool:
    """相談会ナビ自身がもう動いているか(同じ番号を別のアプリが使っている時は False)。"""
    with socket.socket() as s:
        s.settimeout(0.3)
        if s.connect_ex(("127.0.0.1", PORT)) != 0:
            return False
    try:
        with urllib.request.urlopen(BASE + "/api/ping", timeout=1) as r:
            return json.loads(r.read()).get("app") == "talk_navi"
    except Exception:
        return False


def main():
    if running():
        build.open_app(BASE + "/")
        return
    NOTES.mkdir(parents=True, exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    if "--open" in sys.argv:
        threading.Timer(0.4, lambda: build.open_app(BASE + "/")).start()
    srv.serve_forever()


if __name__ == "__main__":
    main()
