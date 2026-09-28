#!/usr/bin/env python3
"""So WalkRequest (client gửi) với ObjectWalkedExtended (server trả).

Mục đích: xem server xác thực đường đi thế nào, và tái hiện đúng phép tính
của MUnique.OpenMU.GameLogic.PlugIns.SpeedHackDetectPlugIn.

Dùng:
    ./mu-walk-analyze.py /tmp/mu-packets.jsonl
    ./mu-walk-analyze.py /tmp/mu-packets.jsonl --step-delay 333
"""
import argparse
import json

# packetByte -> Direction, theo GameServer/DirectionExtensions.ParseAsDirection
# (Direction = packetByte + 1) và GameLogic/DirectionExtensions.CalculateTargetPoint.
# Lưu ý: trục toạ độ MU xoay 45 độ so với trực giác — "South" là (x+1, y-1).
DIRS = {
    0: ("W ", (-1, -1)),
    1: ("SW", ( 0, -1)),
    2: ("S ", ( 1, -1)),
    3: ("SE", ( 1,  0)),
    4: ("E ", ( 1,  1)),
    5: ("NE", ( 0,  1)),
    6: ("N ", (-1,  1)),
    7: ("NW", (-1,  0)),
}

# Hằng số lấy từ SpeedHackDetectPlugIn + SpeedHackDetectConfiguration
NORMAL_STEP_DELAY_MS = 300.0
BASE_STEP_DELAY_MARGIN_MS = 50.0
MIN_STEP_DELAY_MS = 50.0
WALK_SPEED_TOLERANCE_MS = 900
MAX_ALLOWED_WALK_START_OFFSET = 5
RECENT_WALKS_MAX = 5
RECENT_WALKS_MIN_FOR_CHECK = 3
HISTORY_RESET_SECONDS = 2.0


def parse_walk_request(raw):
    """C1 [len] D4 SourceX SourceY [rot<<4 | stepCount] directions(4bit moi buoc)"""
    if len(raw) < 6:
        return None
    step_count = raw[5] & 0x0F
    dirs = []
    for i in range(step_count):
        idx = 6 + i // 2
        if idx >= len(raw):
            break
        b = raw[idx]
        dirs.append((b >> 4) if i % 2 == 0 else (b & 0x0F))
    return {
        "src": (raw[3], raw[4]),
        "steps": step_count,
        "rot": (raw[5] >> 4) & 0x0F,
        "dirs": dirs,
    }


def parse_object_walked_extended(raw):
    """C1 [len] D4 [objId BE] SourceX SourceY TargetX TargetY [rot<<4 | stepCount]"""
    if len(raw) < 10:
        return None
    return {
        "obj": (raw[3] << 8) | raw[4],
        "src": (raw[5], raw[6]),
        "target": (raw[7], raw[8]),
        "rot": (raw[9] >> 4) & 0x0F,
        "steps": raw[9] & 0x0F,
    }


def apply_dirs(src, dirs):
    x, y = src
    for d in dirs:
        dx, dy = DIRS.get(d, ("? ", (0, 0)))[1]
        x, y = (x + dx) & 0xFF, (y + dy) & 0xFF
    return (x, y)


def chebyshev(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def euclid(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("--self-id", type=int)
    ap.add_argument("--step-delay", type=float, default=333.3,
                    help="StepDelay ms cua nhan vat (100/speed*40; speed 12 -> 333.3)")
    args = ap.parse_args()

    events = []
    with open(args.dump) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            raw = bytes.fromhex(r["hex"])
            if len(raw) < 3 or raw[0] != 0xC1 or raw[2] != 0xD4:
                continue
            if r["dir"] == "c2s":
                p = parse_walk_request(raw)
                if p:
                    events.append(("req", r["ms"], p))
            else:
                p = parse_object_walked_extended(raw)
                if p:
                    events.append(("ack", r["ms"], p))

    reqs = [e for e in events if e[0] == "req"]
    acks = [e for e in events if e[0] == "ack"]
    if not reqs:
        print("khong co WalkRequest nao trong dump")
        return

    self_id = args.self_id
    if self_id is None:
        votes = {}
        for _, t, _ in reqs:
            for _, t2, a in acks:
                if 0 <= t2 - t <= 60:
                    votes[a["obj"]] = votes.get(a["obj"], 0) + 1
        self_id = max(votes, key=votes.get) if votes else None

    print(f"ObjectId nhan vat : {self_id}")
    print(f"StepDelay gia dinh: {args.step_delay:.1f}ms\n")
    print("=" * 104)

    history = []      # tái hiện SpeedHackState.RecentWalks
    last_walk_time = None
    for _, t, p in reqs:
        want = apply_dirs(p["src"], p["dirs"])
        trail = "".join(DIRS.get(d, ("?", None))[0].strip() + " " for d in p["dirs"]).strip()

        ack = None
        for _, t2, a in acks:
            if a["obj"] == self_id and 0 <= t2 - t <= 300:
                ack = (t2, a)
                break

        print(f"{t:>9.1f} --> WalkRequest  tu {str(p['src']):<11} {p['steps']:>2} buoc [{trail}]  => client muon {want}")
        if ack:
            t2, a = ack
            ok_target = "khop" if a["target"] == want else f"SERVER SUA -> {a['target']}"
            ok_src = "khop" if a["src"] == p["src"] else f"server dang o {a['src']}"
            print(f"{t2:>9.1f} <-- ObjectWalkedExtended (+{t2 - t:.1f}ms) src={a['src']} target={a['target']} "
                  f"steps={a['steps']} rot={a['rot']}")
            print(f"{'':>9}     diem xuat phat: {ok_src}   |   dich: {ok_target}")
        else:
            print(f"{'':>9} <-- (khong co phan hoi trong 300ms)")

        # ---- tái hiện IsWalkRequestValidAsync ----
        now = t / 1000.0
        if last_walk_time is not None and now - last_walk_time > HISTORY_RESET_SECONDS:
            history.clear()
        history.append((now, p["src"]))
        last_walk_time = now
        while len(history) > RECENT_WALKS_MAX:
            history.pop(0)

        if len(history) >= RECENT_WALKS_MIN_FOR_CHECK:
            cumulative = sum(chebyshev(history[i][1], history[i - 1][1]) for i in range(1, len(history)))
            elapsed_ms = (now - history[0][0]) * 1000.0
            if cumulative > 0:
                scaling = args.step_delay / NORMAL_STEP_DELAY_MS
                margin = BASE_STEP_DELAY_MARGIN_MS * scaling
                check_delay = max(min(MIN_STEP_DELAY_MS, args.step_delay), args.step_delay - margin)
                expected = cumulative * check_delay
                deficit = expected - elapsed_ms
                tol = WALK_SPEED_TOLERANCE_MS * scaling
                verdict = "*** SPEEDHACK ***" if deficit > tol else "hop le"
                print(f"{'':>9}     speedcheck: {cumulative} o / {elapsed_ms:.0f}ms "
                      f"| toi thieu {expected:.0f}ms | thieu {deficit:+.0f}ms (nguong {tol:.0f}) -> {verdict}")
        print()

    print("=" * 104)
    mine = sum(1 for _, _, a in acks if a["obj"] == self_id)
    print(f"tong: {len(reqs)} WalkRequest | {len(acks)} ObjectWalkedExtended "
          f"({mine} cua minh, {len(acks) - mine} cua object khac)")
    steps_nonzero = sum(1 for _, _, a in acks if a["steps"] != 0)
    print(f"so ObjectWalked co StepCount != 0: {steps_nonzero}/{len(acks)}  "
          f"(SendWalkDirections tat -> server khong echo duong di)")


if __name__ == "__main__":
    main()
