"""デモの窓(今日見せる画面だけを並べた Chrome の窓)を1つだけ持ち、札を押されたらその画面のタブへ切り替える。

window.open で名前付きのタブを使い回す案は、Google・ChatGPT のページ側の設定で名前が消え、
開くたびにタブが増えた(2026-10-23 本物の Chrome で実測)。そこで相談会ナビ(server.py)が
デモの窓を前に出し、Chrome のタブ切り替えキー(Ctrl+番号)を代わりに押す形にした。

  show(url, urls)  … url の画面を出す。デモの窓が無ければ urls を並べて作る。窓に無い画面は末尾に足す
"""
import ctypes
import json
import subprocess
import threading
import time
from ctypes import wintypes
from pathlib import Path

import build

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

VK_CONTROL, VK_MENU, VK_TAB = 0x11, 0x12, 0x09
KEYUP = 0x0002
SW_RESTORE = 9

_lock = threading.Lock()
_demo = {"hwnd": 0, "urls": []}  # 今のデモの窓と、そこへ順に開いた URL(タブの並び)


def _exe(hwnd) -> str:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(520)
        n = wintypes.DWORD(520)
        kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n))
        return buf.value.lower()
    finally:
        kernel32.CloseHandle(h)


def title(hwnd) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def chrome_windows() -> set:
    """見えている Chrome の窓(題名のある最上位の窓)。"""
    found = set()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd) and title(hwnd):
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, cls, 64)
            if cls.value == "Chrome_WidgetWin_1" and _exe(hwnd).endswith("chrome.exe"):
                found.add(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    return found


def _key(vk, up=False):
    user32.keybd_event(vk, 0, KEYUP if up else 0, 0)


def _is_front(hwnd, wait=1.0) -> bool:
    for _ in range(int(wait / 0.05)):
        if user32.GetForegroundWindow() == hwnd:
            return True
        time.sleep(0.05)
    return False


def front(hwnd) -> bool:
    """窓を一番前に出す。Windows は裏のアプリが前に出すのを嫌うので、2段構えにする。
    ①今前にいる窓の入力に一時的に相乗りする ②だめなら Alt を押している間に出す(Alt 中は前に出すのを許される)。"""
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    msg = wintypes.MSG()
    user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)  # この作業の流れに入力の受け口を作る(無いと相乗りできない)
    fg = user32.GetForegroundWindow()
    me = kernel32.GetCurrentThreadId()
    other = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = bool(other and other != me and user32.AttachThreadInput(me, other, True))
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(me, other, False)
    if _is_front(hwnd, 0.5):
        return True
    _key(VK_MENU)
    user32.SetForegroundWindow(hwnd)
    _key(VK_MENU, True)
    return _is_front(hwnd)


def _ctrl(vk, times=1):
    _key(VK_CONTROL)
    for _ in range(times):
        _key(vk)
        _key(vk, True)
        time.sleep(0.03)
    _key(VK_CONTROL, True)


def _goto_tab(i: int):
    """i 番目(0から)のタブへ。Ctrl+9 は「最後のタブ」なので、9枚目からは Ctrl+8 の後に Ctrl+Tab で進む。"""
    if i < 8:
        _ctrl(0x31 + i)
    else:
        _ctrl(0x38)
        time.sleep(0.05)
        _ctrl(VK_TAB, i - 7)


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


def place_beside(hwnd, navi) -> None:
    """デモの窓を、進行ナビの窓と同じ画面の反対側の半分に置く(画面を左右半分にして使う前提)。"""
    if not navi or user32.IsIconic(navi):
        return
    mi = _MONITORINFO(ctypes.sizeof(_MONITORINFO))
    user32.GetMonitorInfoW(user32.MonitorFromWindow(navi, 2), ctypes.byref(mi))  # 2 = 一番近い画面
    w, r = mi.rcWork, wintypes.RECT()
    user32.GetWindowRect(navi, ctypes.byref(r))
    half = (w.right - w.left) // 2
    navi_on_left = (r.left + r.right) // 2 < w.left + half
    x = w.left + half if navi_on_left else w.left
    if user32.IsZoomed(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetWindowPos(hwnd, 0, x, w.top, half, w.bottom - w.top, 0x0004 | 0x0040)  # NOZORDER | SHOWWINDOW


def _open_window(urls: list) -> int:
    before = chrome_windows()
    build.open_demo(urls)
    for _ in range(100):  # 最大10秒
        time.sleep(0.1)
        new = chrome_windows() - before
        if new:
            return new.pop()
    return 0


def locked() -> bool:
    """PC がロック中か(前面がロック画面のアプリ)。ロック中は窓を前に出すこともキーを送ることもできない(2026-10-23 実測)。"""
    fg = user32.GetForegroundWindow()
    return bool(fg) and _exe(fg).endswith("lockapp.exe")


LOG = Path(__file__).resolve().parent / "backups" / "screens.log"


def show(url: str, urls: list) -> dict:
    r = _show(url, urls)
    # 札を押した結果を1行ずつ残す(押した後に切り替わったかを後から確かめるため)
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{url}\t{json.dumps(r, ensure_ascii=False)}\n")
    return r


def _show(url: str, urls: list) -> dict:
    if locked():
        return {"ok": False, "why": "PC がロック中なので画面を出せません"}
    with _lock:
        h = _demo["hwnd"]
        if not (h and user32.IsWindow(h) and h in chrome_windows()):
            navi = user32.GetForegroundWindow()  # 札を押した直後なので、前面は進行ナビの窓
            order = list(urls) if url in urls else list(urls) + [url]
            h = _open_window(order)
            if not h:
                return {"ok": False, "why": "デモの窓を開けませんでした"}
            _demo.update(hwnd=h, urls=order)
            place_beside(h, navi if navi in chrome_windows() else 0)
            time.sleep(0.6)  # 窓ができた直後はキーを取りこぼすことがある
        if not front(h):
            return {"ok": False, "why": "デモの窓を前に出せませんでした"}
        if url in _demo["urls"]:
            _goto_tab(_demo["urls"].index(url))
        else:
            # デモの窓が一番最後に触った窓になっているので、Chrome に URL を渡すとこの窓の末尾に入る
            subprocess.Popen([build.chrome_path(), url])
            _demo["urls"].append(url)
        # 切り替えの直後に題名を読むと、1つ前のタブの題名が返る(2026-10-24 の記録で毎回1つずれていた)
        time.sleep(0.5)
        return {"ok": True, "tab": _demo["urls"].index(url) + 1, "title": title(h)}
