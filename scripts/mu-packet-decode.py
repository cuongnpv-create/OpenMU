#!/usr/bin/env python3
"""Giải mã dump packet MU Online bằng chính định nghĩa XML của OpenMU.

Đọc file JSON Lines do MuProxy sinh ra, tra opcode -> tên packet + mô tả
trong src/Network/Packets/*.xml của OpenMU, in ra bảng đọc được.

Dùng:
    ./mu-packet-decode.py /tmp/mu-packets.jsonl --openmu ~/OpenMU
    ./mu-packet-decode.py /tmp/mu-packets.jsonl --openmu ~/OpenMU --fields
    ./mu-packet-decode.py /tmp/mu-packets.jsonl --openmu ~/OpenMU --stats
    ./mu-packet-decode.py /tmp/mu-packets.jsonl --openmu ~/OpenMU --grep Walk
"""
import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

NS = {"p": "http://www.munique.net/OpenMU/PacketDefinitions"}

XML_FILES = [
    "src/Network/Packets/ConnectServer/ConnectServerPackets.xml",
    "src/Network/Packets/ClientToServer/ClientToServerPackets.xml",
    "src/Network/Packets/ServerToClient/ServerToClientPackets.xml",
    "src/Network/Packets/ChatServer/ChatServerPackets.xml",
]


def text(node, tag):
    el = node.find(f"p:{tag}", NS)
    return el.text.strip() if el is not None and el.text else None


def load_defs(openmu_root):
    """(direction, code, subcode) -> danh sách định nghĩa packet."""
    defs = defaultdict(list)
    loaded = 0
    for rel in XML_FILES:
        path = os.path.join(openmu_root, rel)
        if not os.path.exists(path):
            continue
        root = ET.parse(path).getroot()
        for pk in root.iterfind(".//p:Packet", NS):
            code = text(pk, "Code")
            if code is None:
                continue
            entry = {
                "name": text(pk, "Name"),
                "header": text(pk, "HeaderType"),
                "code": int(code, 16),
                "subcode": int(text(pk, "SubCode"), 16) if text(pk, "SubCode") else None,
                "length": int(text(pk, "Length")) if text(pk, "Length") else None,
                "direction": text(pk, "Direction"),
                "sent_when": text(pk, "SentWhen"),
                "fields": [
                    {
                        "index": int(text(f, "Index") or 0),
                        "type": text(f, "Type"),
                        "name": text(f, "Name"),
                    }
                    for f in pk.iterfind("p:Fields/p:Field", NS)
                ],
                "file": os.path.basename(path),
            }
            defs[(entry["direction"], entry["code"], entry["subcode"])].append(entry)
            loaded += 1
    return defs, loaded


def parse_frame(raw):
    """Tách header MU. Trả về (type, length, code, subcode, payload_offset)."""
    if not raw:
        return None
    t = raw[0]
    if t in (0xC1, 0xC3):          # header 1 byte length
        if len(raw) < 3:
            return None
        return t, raw[1], raw[2], (raw[3] if len(raw) > 3 else None), 3
    if t in (0xC2, 0xC4):          # header 2 byte length (big endian)
        if len(raw) < 4:
            return None
        return t, (raw[1] << 8) | raw[2], raw[3], (raw[4] if len(raw) > 4 else None), 4
    return None


def lookup(defs, direction, code, subcode, length):
    """Ưu tiên khớp subcode, rồi khớp đúng Length."""
    for sc in (subcode, None):
        cands = defs.get((direction, code, sc), [])
        if not cands:
            continue
        exact = [c for c in cands if c["length"] == length]
        if exact:
            return exact[0]
        # Định nghĩa không cố định độ dài (Length rỗng) là ứng viên tốt nhất
        flex = [c for c in cands if c["length"] is None]
        if flex:
            return flex[0]
        return cands[0]
    return None


def read_field(raw, off, f):
    i = off + f["index"]
    t = (f["type"] or "").lower()
    try:
        if t == "byte":
            return raw[i]
        if t == "boolean":
            return bool(raw[i])
        if t == "shortlittleendian":
            return int.from_bytes(raw[i:i + 2], "little")
        if t == "shortbigendian":
            return int.from_bytes(raw[i:i + 2], "big")
        if t == "integerlittleendian":
            return int.from_bytes(raw[i:i + 4], "little")
        if t == "integerbigendian":
            return int.from_bytes(raw[i:i + 4], "big")
        if t == "longlittleendian":
            return int.from_bytes(raw[i:i + 8], "little")
        if t == "string":
            return raw[i:].split(b"\0")[0].decode("latin-1", "replace")
    except (IndexError, ValueError):
        return None
    return None


def hexdump(raw, width=16):
    out = []
    for o in range(0, len(raw), width):
        chunk = raw[o:o + width]
        h = " ".join(f"{b:02X}" for b in chunk).ljust(width * 3 - 1)
        a = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        out.append(f"      {o:04X}  {h}  |{a}|")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dump", help="file .jsonl do MuProxy sinh ra")
    ap.add_argument("--openmu", required=True, help="thư mục gốc repo OpenMU")
    ap.add_argument("--fields", action="store_true", help="in các field đã parse")
    ap.add_argument("--hex", action="store_true", help="in hexdump đầy đủ")
    ap.add_argument("--stats", action="store_true", help="chỉ in thống kê")
    ap.add_argument("--grep", help="chỉ hiện packet có tên khớp (không phân biệt hoa thường)")
    ap.add_argument("--channel", choices=["CS", "GS"], help="lọc theo kênh")
    args = ap.parse_args()

    defs, n = load_defs(args.openmu)
    if not n:
        sys.exit(f"khong doc duoc dinh nghia packet trong {args.openmu}")
    print(f"# nap {n} dinh nghia packet tu OpenMU\n", file=sys.stderr)

    counts = Counter()
    unknown = Counter()
    shown = 0

    with open(args.dump) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if args.channel and rec["ch"] != args.channel:
                continue
            raw = bytes.fromhex(rec["hex"])
            frame = parse_frame(raw)
            if frame is None:
                continue
            ptype, plen, code, subcode, off = frame
            direction = "ClientToServer" if rec["dir"] == "c2s" else "ServerToClient"
            d = lookup(defs, direction, code, subcode, len(raw))

            name = d["name"] if d else f"UNKNOWN_{code:02X}" + (f"_{subcode:02X}" if subcode is not None else "")
            counts[(rec["dir"], name)] += 1
            if not d:
                unknown[(rec["dir"], code, subcode)] += 1

            if args.stats:
                continue
            if args.grep and args.grep.lower() not in name.lower():
                continue

            arrow = "-->" if rec["dir"] == "c2s" else "<--"
            sub = f" {subcode:02X}" if d and d["subcode"] is not None else ""
            print(f"{rec['ms']:>9.1f} {rec['ch']} {arrow} {ptype:02X} {code:02X}{sub}  {name}  ({len(raw)}B)")

            if args.fields and d and d["fields"]:
                for f in d["fields"]:
                    if f["index"] < off:
                        continue      # field của phần header
                    v = read_field(raw, 0, f)
                    if v is not None:
                        print(f"          . {f['name']:<28} = {v}")
            if args.hex:
                print(hexdump(raw))
            shown += 1

    if args.stats or shown == 0:
        print("\n=== thong ke ===")
        for (dirn, name), c in counts.most_common(40):
            arrow = "-->" if dirn == "c2s" else "<--"
            print(f"  {arrow} {c:>5}  {name}")
        if unknown:
            print("\n=== opcode khong tra duoc ===")
            for (dirn, code, sc), c in unknown.most_common(20):
                arrow = "-->" if dirn == "c2s" else "<--"
                s = f" sub={sc:02X}" if sc is not None else ""
                print(f"  {arrow} {c:>5}  code={code:02X}{s}")


if __name__ == "__main__":
    main()
