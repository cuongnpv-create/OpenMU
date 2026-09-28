# -*- coding: utf-8 -*-
"""Sinh ban dich tieng Viet cho ten item/quai/map theo bang thuat ngu glossary.py.
Dung: python3 render.py item|monster > out.sql   (doc ten tu stdin, moi dong mot ten)
Nguyen tac: chi dich TU CHI LOAI, giu nguyen ten set/danh tu rieng bang tieng Anh,
de nguoi choi doi chieu duoc voi ten client hien thi."""
import re, sys, json
from glossary import TYPE, QUAL, MTYPE, SKIP, OVERRIDE

def render(name, types):
    if name in OVERRIDE:
        return OVERRIDE[name]
    m = re.match(r"^(.*?)(\s*(?:\(.*\)|\d+))?$", name.strip())
    core, tail = m.group(1).strip(), (m.group(2) or "")
    toks = core.split()
    idx = [i for i, t in enumerate(toks) if t in types]
    rest_src = toks
    head = None
    if idx:
        head_i = idx[0] if idx[0] == 0 else idx[-1]   # "Cape of X" dau, "X Armor" cuoi
        head = types[toks[head_i]]
        rest_src = [t for i, t in enumerate(toks) if i != head_i]
    rest  = [t for t in rest_src if t not in SKIP]
    keep  = [t for t in rest if t not in QUAL]
    quals = [QUAL[t] for t in rest if t in QUAL]
    if head is None and not quals:
        return None                                    # thuan danh tu rieng -> giu nguyen
    out = " ".join(([head] if head else []) + keep + quals) + tail
    return out if out != name else None

if __name__ == "__main__":
    types = MTYPE if sys.argv[1] == "monster" else TYPE
    names = sorted({l.rstrip("\n") for l in sys.stdin if l.strip()})
    res = {n: r for n in names if (r := render(n, types))}
    json.dump(res, sys.stdout, ensure_ascii=False, indent=1)
