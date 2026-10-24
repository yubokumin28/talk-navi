"""デスクトップに「相談会ナビ」のアイコンを置く(遊牧民くんの絵のアイコン)。何度実行しても上書きされるだけ。

  python make_shortcut.py
"""
import base64
import subprocess
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
# この make_shortcut.py を動かした Python の隣の pythonw.exe(黒い窓を出さずに起動する)
_w = Path(sys.executable).with_name("pythonw.exe")
PYTHONW = str(_w if _w.is_file() else Path(sys.executable))


def make_icon() -> Path:
    src = Image.open(HERE / "assets" / "kun_joy.png").convert("RGBA")
    side = max(src.size)
    sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    sq.paste(src, ((side - src.width) // 2, (side - src.height) // 2), src)
    ico = HERE / "assets" / "app.ico"
    sq.save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return ico


def main():
    ico = make_icon()
    ps = f"""
$d=[Environment]::GetFolderPath('Desktop')
$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d '相談会ナビ.lnk'))
$s.TargetPath='{PYTHONW}'
$s.Arguments='"{HERE / "server.py"}" --open'
$s.WorkingDirectory='{HERE}'
$s.IconLocation='{ico},0'
$s.Description='相談会の進行ナビ(編集・メモ・画面共有)'
$s.Save()
Test-Path (Join-Path $d '相談会ナビ.lnk')
"""
    # 日本語を含むので、PowerShell には UTF-16 の Base64 で渡す(.ps1 に日本語を書かない決まり)
    enc = base64.b64encode(ps.encode("utf-16-le")).decode()
    r = subprocess.run(["powershell", "-NoProfile", "-EncodedCommand", enc], capture_output=True, text=True)
    ok = "True" in r.stdout
    print("デスクトップに「相談会ナビ」を置きました" if ok else f"置けませんでした: {r.stderr.strip()[:300]}")


if __name__ == "__main__":
    main()
