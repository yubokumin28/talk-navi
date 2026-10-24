"""進行ノート(Obsidian の .md)を読み書きし、進行ナビの HTML を組み立てる部品。

build.py(コマンドで使う)と server.py(デスクトップのアイコンから使う)の両方がここを使う。

ノートの形:
  ---(title / date / start / end / theme / chara)---
  # 題名
  ## 話題 | 分
  - 要点(3つまで)
    - 🔗 画面の名前 URL   … 要点のすぐ下に字下げして書くと「その要点で見せる画面」
  🔗 画面の名前 URL       … 字下げ無しは「話題全体で見せる画面」
  📋 名前 | コピーする文   … 進行ナビにコピー札が出る(押すと文がクリップボードへ。参加者に渡す指示文など)
  > メモ: 話す人の手書きメモ(画面には出ない。N キーの窓と編集画面だけで見える)
"""
import base64
import io
import json
import re
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "template.html"
FM_ORDER = ["type", "date", "title", "start", "end", "theme", "chara"]
RE_SEC = re.compile(r"^##\s+(.+?)(?:\s*[|｜]\s*(\d+)\s*分?)?$")
RE_LINK = re.compile(r"^(?:[-*]\s+)?🔗\s*(.+?)\s+(\S+://\S+)$")
RE_COPY = re.compile(r"^(?:[-*]\s+)?📋\s*(.+?)\s*[|｜]\s*(.+)$")
RE_MEMO = re.compile(r"^>\s?(?:メモ[:：]\s?)?(.*)$")
RE_POINT = re.compile(r"^[-*・]\s+(.+)$")


def parse(md: str) -> dict:
    fm, body = {}, md
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", md, re.S)
    if m:
        body = md[m.end():]
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip().strip("\"'")
    head, secs = [], []
    for raw in body.splitlines():
        s = raw.strip()
        h = RE_SEC.match(s)
        if h and not s.startswith("###"):
            secs.append({"title": h.group(1).strip(), "min": int(h.group(2) or 10),
                         "points": [], "links": [], "copies": [], "memo": []})
            continue
        if not secs:
            if s and not s.startswith("# "):
                head.append(raw)  # %% の説明書きなどは残す
            continue
        cur = secs[-1]
        u = RE_LINK.match(s)
        if u:
            # 字下げされていて、すぐ上に要点がある → その要点の画面(pt = 要点の番号、0から)
            pt = len(cur["points"]) - 1 if raw[:1] in (" ", "\t") and cur["points"] else None
            cur["links"].append({"name": u.group(1).strip(), "url": u.group(2), "pt": pt})
            continue
        cp = RE_COPY.match(s)
        if cp:
            cur["copies"].append({"name": cp.group(1).strip(), "text": cp.group(2).strip()})
            continue
        mm = RE_MEMO.match(s)
        if mm:
            cur["memo"].append(mm.group(1))
            continue
        b = RE_POINT.match(s)
        if b:
            cur["points"].append(b.group(1).strip())
    for c in secs:
        c["memo"] = "\n".join(c["memo"]).strip()
    return {"fm": fm, "head": head, "secs": secs}


def dump(note: dict) -> str:
    fm = note.get("fm", {})
    keys = FM_ORDER + [k for k in fm if k not in FM_ORDER]
    out = ["---"]
    for k in keys:
        v = str(fm.get(k, "")).strip()
        if v:
            out.append(f'{k}: "{v}"' if k in ("start", "end") else f"{k}: {v}")
    out += ["---", "", f"# {fm.get('title', '')}", ""]
    if note.get("head"):
        out += note["head"] + [""]
    for s in note.get("secs", []):
        title = s.get("title", "").strip() or "(題名なし)"
        out.append(f"## {title} | {int(s.get('min') or 10)}")
        links = [k for k in s.get("links", []) if k.get("url", "").strip()]
        points = s.get("points", [])
        kept = {i for i, p in enumerate(points) if p.strip()}

        def link_line(k, indent=""):
            url = k["url"].strip()
            name = k.get("name", "").strip() or re.sub(r"^\w+://", "", url).split("/")[0]
            return f"{indent}🔗 {name} {url}" if not indent else f"{indent}- 🔗 {name} {url}"

        for i, p in enumerate(points):
            if i in kept:
                out.append(f"- {p.strip()}")
                out += [link_line(k, "  ") for k in links if k.get("pt") == i]
        # 要点に付いていない画面(消えた要点に付いていた画面もここへ回す)
        out += [link_line(k) for k in links if k.get("pt") not in kept]
        out += [f"📋 {c.get('name', '').strip() or 'コピー'} | {c['text'].strip()}"
                for c in s.get("copies", []) if c.get("text", "").strip()]
        memo = [x.rstrip() for x in s.get("memo", "").splitlines()]
        if any(x.strip() for x in memo):
            out.append(f"> メモ: {memo[0]}")
            out += [f"> {x}" for x in memo[1:]]
        out.append("")
    return "\n".join(out)


def demo_urls(note: dict) -> list:
    urls = []
    for s in note["secs"]:
        for link in s["links"]:
            if link["url"] not in urls:
                urls.append(link["url"])
    return urls


_chara_cache = None


def chara_json() -> str:
    """assets の kun_point*.png など全部を WebP にして JSON にする(PNG のままだと重い)。"""
    global _chara_cache
    if _chara_cache is None:
        chara = {}
        for who in ("kun", "chan"):
            chara[who] = {}
            for kind in ("point", "joy"):
                imgs = []
                for p in sorted((HERE / "assets").glob(f"{who}_{kind}*.png")):
                    buf = io.BytesIO()
                    Image.open(p).save(buf, "WEBP", quality=82, method=6)
                    imgs.append("data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode())
                chara[who][kind] = imgs
        if min(len(chara[w][k]) for w in chara for k in chara[w]) == 0:
            chara = {}
        _chara_cache = chara
    return json.dumps(_chara_cache)


def icons_json() -> str:
    """進行ナビの下のボタンに使うアイコン(assets/icons)。1つの HTML で完結させるため埋め込む。"""
    out = {}
    for name in ("prev", "next", "edit", "home", "help", "memo"):
        p = HERE / "assets" / "icons" / f"{name}.png"
        if p.is_file():
            buf = io.BytesIO()
            Image.open(p).resize((64, 64), Image.LANCZOS).save(buf, "WEBP", quality=90)
            out[name] = "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()
    return json.dumps(out)


def render(md: str, note_name: str = "") -> str:
    fm = parse(md)["fm"]
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("__NAVI_MD__", md.replace("</script", "<\\/script"))
    html = html.replace("__MASCOT__", "")
    html = html.replace("__CHARA__", "{}" if fm.get("chara") == "off" else chara_json())
    html = html.replace("__NOTE__", note_name)
    html = html.replace("__ICONS__", icons_json())
    return html
