#!/usr/bin/env python3
"""Dieu khien client MuMain qua control socket (build voi ENABLE_CONTROL_SOCKET=ON).

Chay client truoc:
    MU_CONTROL_SOCKET=/tmp/mu.sock ./Main /u127.0.0.1 /p44405

Roi:
    ./mu-drive.py                              # demo: login -> vao world -> screenshot
    ./mu-drive.py ping
    ./mu-drive.py state
    ./mu-drive.py raw '{"cmd":"say","text":"hello"}'
"""
import json
import os
import socket
import sys
import time

SOCK = os.environ.get("MU_CONTROL_SOCKET", "/tmp/mu.sock")


def call(cmd, timeout=150, **kw):
    """Gui 1 lenh, doc dung 1 dong phan hoi JSON."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(SOCK)
    s.sendall((json.dumps({"cmd": cmd, **kw}) + "\n").encode())
    buf = b""
    while not buf.endswith(b"\n"):
        chunk = s.recv(65536)
        if not chunk:
            break
        buf += chunk
    s.close()
    return json.loads(buf.decode().strip())


def show(label, resp):
    ok = resp.get("ok")
    mark = "OK " if ok else "ERR"
    body = resp.get("result") if ok else f'{resp.get("error")}: {resp.get("message")}'
    print(f"[{mark}] {label:<14} {json.dumps(body, ensure_ascii=False)[:400]}")
    return resp


def demo(account="test400", password="test400", char=None):
    show("ping", call("ping"))
    show("scene", call("scene"))

    # LUU Y: tham so `server` la TEN server group, khong phai index.
    # Bo han di thi lay group dau tien.
    r = show("login", call("login", account=account, password=password))
    if not r.get("ok"):
        return 1

    chars = r["result"].get("characters", [])
    if not chars:
        print("  tai khoan khong co nhan vat nao")
        return 1
    name = char or chars[0]["name"]

    show("select-char", call("select-char", name=name))
    time.sleep(3)

    st = call("state")
    if st.get("ok"):
        d = st["result"]
        print(f"  -> {d.get('character')} | class={d.get('class')} lv{d.get('level')} "
              f"| {d.get('map_name')} {d.get('position')} "
              f"| HP {d.get('hp')}/{d.get('max_hp')} | zen {d.get('zen')}")
        for o in (d.get("nearby") or [])[:5]:
            print(f"     nearby: {o.get('kind'):8} {o.get('name')}")

    out = os.path.abspath("mu-screenshot.jpg")
    show("screenshot", call("screenshot", out=out, quality=92))
    return 0


if __name__ == "__main__":
    if not os.path.exists(SOCK):
        sys.exit(f"khong thay socket {SOCK} — client da chay voi MU_CONTROL_SOCKET chua?")
    args = sys.argv[1:]
    if not args:
        sys.exit(demo())
    if args[0] == "raw":
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(150)
        s.connect(SOCK)
        s.sendall((args[1].rstrip("\n") + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            c = s.recv(65536)
            if not c:
                break
            buf += c
        print(buf.decode().strip())
    else:
        print(json.dumps(call(args[0]), indent=2, ensure_ascii=False))
