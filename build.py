"""Obsidian の進行ノート(.md)から、画面共有用の進行ナビ HTML を1枚作る(コマンドで使う)。
手で使う時はデスクトップの「相談会ナビ」(server.py)から開く。

使い方:
  python build.py <ノート.md> [--open] [--demo]
    --open  進行ナビをタブの無い専用の窓で開く
    --demo  ノートの「🔗 名前 URL」の画面だけを、新しい窓1つに順番どおり並べて開く(Ctrl+番号で切り替え)
出力: このフォルダ\<ノートの date>\navi.html
ノートの書き方は talk_note.py の先頭。
"""
import subprocess
import sys
import webbrowser
from pathlib import Path

import talk_note

HERE = Path(__file__).resolve().parent


def chrome_path() -> str:
    for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
        if Path(p).is_file():
            return p
    return ""


def open_app(url: str):
    """タブの無い専用の窓で開く(画面共有でこの窓だけを選びやすい)。"""
    chrome = chrome_path()
    if chrome:
        subprocess.Popen([chrome, f"--app={url}", "--window-size=1280,800"])
    else:
        webbrowser.open(url)


def open_demo(urls: list):
    """今日使う画面だけを、新しい窓1つに順番どおり並べる(いつものタブと混ざらない)。"""
    chrome = chrome_path()
    if chrome:
        subprocess.Popen([chrome, "--new-window", *urls])
    else:
        for u in urls:
            webbrowser.open(u)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        sys.exit(1)
    md = Path(args[0]).read_text(encoding="utf-8")
    note = talk_note.parse(md)
    if not note["secs"]:
        print("止めました: 「## 話題 | 分」の行が1つもありません")
        sys.exit(1)
    fm = note["fm"]
    out_dir = HERE / (fm.get("date") or "nodate")
    out_dir.mkdir(exist_ok=True)
    out = out_dir / "navi.html"
    out.write_text(talk_note.render(md), encoding="utf-8")

    print(f"作りました: {out}")
    print(f"{fm.get('title', '')} {fm.get('date', '')}  話題 {len(note['secs'])} 個・予定 {sum(s['min'] for s in note['secs'])} 分")
    for i, s in enumerate(note["secs"], 1):
        n = len(s["points"])
        flag = "  ← 要点が4つ以上(3つまでが見やすい)" if n > 3 else ("  ← 要点が0" if n == 0 else "")
        print(f"  {i}. {s['title']}  {s['min']}分  要点{n}{flag}")
    urls = talk_note.demo_urls(note)
    if urls:
        print(f"デモの窓に並べる画面 {len(urls)} 個(Ctrl+番号で切り替え)")
        if len(urls) > 8:
            print("  ← 9個目からは Ctrl+番号 で選べない(Chrome は Ctrl+9 が最後のタブ)。8個までに絞るのがおすすめ")

    if "--demo" in sys.argv and urls:
        open_demo(urls)
        print("デモの窓を開きました")
    if "--open" in sys.argv:
        open_app(out.as_uri())
        print("進行ナビの窓を開きました")


if __name__ == "__main__":
    main()
