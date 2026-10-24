"""緑背景(#00FF00)で横に並んだキャラ絵から、背景を抜いて1体ずつの透過PNGにする。

使い方:
  python cutout.py <絵.png> <左から順に名前を並べる>
例:  python cutout.py assets/kun_sheet.png kun_point kun_joy
     python cutout.py assets/kun_sheet2.png kun_point2 kun_point3 kun_point4
出力: assets/<名前>.png(高さ600px)
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
OUT_H = 600


def key_green(img: Image.Image) -> Image.Image:
    a = np.asarray(img.convert("RGB")).astype(np.float32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    spill = g - np.maximum(r, b)
    # 緑の強さで透明度を決める(縁は半透明にしてギザギザを防ぐ)
    alpha = np.clip(255 - (spill - 40) * 255 / 60, 0, 255)
    alpha[spill < 40] = 255
    # 縁に残る緑のにじみを消す
    g2 = np.where(spill > 0, np.maximum(r, b), g)
    rgba = np.dstack([r, g2, b, alpha]).clip(0, 255).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def split_n(img: Image.Image, n: int):
    al = np.asarray(img)[..., 3]
    cols = (al > 128).sum(axis=0) > 3
    runs, start = [], None
    for x, on in enumerate(list(cols) + [False]):
        if on and start is None:
            start = x
        elif not on and start is not None:
            runs.append((start, x))
            start = None
    runs = sorted(runs, key=lambda r: r[1] - r[0], reverse=True)[:n]
    return sorted(runs)


def crop(img: Image.Image, x0: int, x1: int) -> Image.Image:
    part = img.crop((x0, 0, x1, img.height))
    box = part.getchannel("A").point(lambda v: 255 if v > 128 else 0).getbbox()
    part = part.crop(box)
    pad = 8
    canvas = Image.new("RGBA", (part.width + pad * 2, part.height + pad * 2), (0, 0, 0, 0))
    canvas.paste(part, (pad, pad))
    w = round(canvas.width * OUT_H / canvas.height)
    return canvas.resize((w, OUT_H), Image.LANCZOS)


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    src, names = Path(sys.argv[1]), sys.argv[2:]
    img = key_green(Image.open(src))
    runs = split_n(img, len(names))
    if len(runs) < len(names):
        print(f"止めました: {len(names)}体に分けられませんでした(見つかった塊 {len(runs)} 個)。キャラの間が近すぎる可能性")
        sys.exit(1)
    for name, (x0, x1) in zip(names, runs):
        out = HERE / "assets" / f"{name}.png"
        im = crop(img, x0, x1)
        im.save(out, optimize=True)
        al = np.asarray(im)[..., 3]
        print(f"作りました: {out.name}  {im.width}x{im.height}  透明の割合 {round((al == 0).mean() * 100)}%")


if __name__ == "__main__":
    main()
