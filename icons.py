"""緑背景に格子状に並んだアイコン絵(ChatGPT で作る)を、1個ずつの透過PNGに切り分ける。

使い方:
  python icons.py <絵.png> <列数> <行数> <名前を左上から右へ順に>
例:  python icons.py assets/icon_sheet.png 4 3 navi edit demo new trash quit prev next home help save memo
出力: assets/icons/<名前>.png(128x128)
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from cutout import key_green

HERE = Path(__file__).resolve().parent
SIZE = 128


def runs(mask_1d, n):
    """塊の並び(開始, 終わり)を大きい順に n 個、位置の順で返す。"""
    out, start = [], None
    for i, on in enumerate(list(mask_1d) + [False]):
        if on and start is None:
            start = i
        elif not on and start is not None:
            out.append((start, i))
            start = None
    out = sorted(out, key=lambda r: r[1] - r[0], reverse=True)[:n]
    return sorted(out)


def main():
    if len(sys.argv) < 5:
        print(__doc__)
        sys.exit(1)
    src, cols, rows, names = Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), sys.argv[4:]
    img = key_green(Image.open(src))
    al = np.asarray(img)[..., 3] > 128
    xs = runs(al.sum(axis=0) > 2, cols)
    ys = runs(al.sum(axis=1) > 2, rows)
    if len(xs) < cols or len(ys) < rows:
        print(f"止めました: 格子が見つかりません(列 {len(xs)}/{cols}・行 {len(ys)}/{rows})")
        sys.exit(1)
    out_dir = HERE / "assets" / "icons"
    out_dir.mkdir(parents=True, exist_ok=True)
    k = 0
    for (y0, y1) in ys:
        for (x0, x1) in xs:
            if k >= len(names):
                break
            cell = img.crop((x0, y0, x1, y1))
            box = cell.getchannel("A").point(lambda v: 255 if v > 128 else 0).getbbox()
            if box:
                cell = cell.crop(box)
            side = max(cell.size)
            sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
            sq.paste(cell, ((side - cell.width) // 2, (side - cell.height) // 2), cell)
            sq.resize((SIZE, SIZE), Image.LANCZOS).save(out_dir / f"{names[k]}.png", optimize=True)
            k += 1
    print(f"作りました: {k} 個 → {out_dir}")


if __name__ == "__main__":
    main()
