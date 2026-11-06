"""Варианты прокладки трасс при переносе оборудования (для Мастерской).

Изделие сдвигается на d = [dx, dy, dz]. Каждая подключённая к нему цепочка — путь из точек от патрубка изделия
до «якоря» (первый тройник, начало ответвления или другой конец цепочки — их не трогаем). Каждую составляющую
сдвига (по x, y, z) должен «съесть» какой-то участок пути:
  • участок, параллельный этой оси, удлиняется или укорачивается (труба продолжает идти, где шла — например вдоль стены);
  • или на участке другой оси ставится «ступенька» из двух угольников — у изделия или у якоря.
Перебираем такие решения, проверяем геометрию (участки не короче, чем нужно угольникам и деталям) и оцениваем:
длина трубы, число угольников, насколько трасса прижата к стенам. Из лучших собираем варианты для всего изделия:
«Вдоль стены», «Напрямую», «Как было» (резинка proekt.move_equipment).
"""
import copy
import itertools
import json

import proekt
import uzly_ppr as U

MIN_SEG = 0.07      # минимальный участок между угольниками, м (PPR 25–32 с раструбами)
JOG_GAP = 0.09      # отступ ступеньки от детали или угольника


def _ax(v):
    a = max(range(3), key=lambda i: abs(v[i]))
    return a if abs(v[a]) > 1e-6 and all(abs(v[i]) < 1e-4 for i in range(3) if i != a) else None


def _sub(a, b):
    return [a[i] - b[i] for i in range(3)]


def _len(v):
    return sum(x * x for x in v) ** 0.5


def _parts_len(keys):
    return sum(U.PARTS[k]["L"] for k in keys if k in U.PARTS)


def _chains(data):
    return {c["id"]: c for n in data["nodes"] for c in n["chains"]}


def _run(C, cid, end):
    """Путь от патрубка изделия до якоря: список {p, opi, kind}. kind: start/finish/to/tee/anchor."""
    ch = C[cid]
    refs = []
    if ch.get("from"):
        f = ch["from"]
        refs.append(dict(p=list(C[f[0]]["ops"][f[1]]["p"]), opi=-1, kind="anchor"))
    else:
        refs.append(dict(p=list(ch["start"]), opi=-1, kind="start"))
    for i, o in enumerate(ch["ops"]):
        if "p" in o:
            refs.append(dict(p=list(o["p"]), opi=i, kind=o["op"]))
    if end == "end":
        refs.reverse()
    a = next((k for k in range(1, len(refs)) if refs[k]["kind"] != "to"), len(refs) - 1)
    return refs[:a + 1]


def _adds_between(ch, oa, ob):
    """Длина деталей (add) между двумя точками в порядке операций."""
    lo, hi = min(oa, ob), max(oa, ob)
    return _parts_len([o["key"] for o in ch["ops"][lo + 1:hi] if o["op"] == "add"])


def _start_adds(ch):
    keys = []
    for o in ch["ops"]:
        if "p" in o:
            break
        if o["op"] == "add":
            keys.append(o["key"])
    return _parts_len(keys)


def _clear(ch, run, s, near, rev):
    """Сколько места занято деталями у точки ref s (near=True) или ref s+1 на участке s."""
    A, B = run[s], run[s + 1]
    gap = JOG_GAP
    if rev:          # путь идёт против порядка операций: детали участка стоят у B (раньше в операциях)
        if not near:
            gap += _adds_between(ch, A["opi"], B["opi"]) if B["opi"] >= 0 else _start_adds(ch)
    else:
        if near:
            gap += _adds_between(ch, A["opi"], B["opi"]) if A["opi"] >= 0 else _start_adds(ch)
    if near and A["kind"] == "finish":
        gap += _parts_len(ch["ops"][A["opi"]].get("keys", []))
    if not near and B["kind"] in ("anchor", "tee", "start"):
        gap += 0.04
    if near and A["kind"] == "start":
        gap += 0.04
    if not near and B["kind"] == "finish":
        gap += _parts_len(ch["ops"][B["opi"]].get("keys", []))
    return gap


def _slide_axis(C, ch):
    """Ось, вдоль которой тройник ответвления может съехать по основной трубе (до и после него — одна ось)."""
    if not ch.get("from"):
        return None
    par, ti = C[ch["from"][0]], ch["from"][1]
    pts = ([par["start"]] if not par.get("from") else []) + [o["p"] for o in par["ops"][:ti] if "p" in o]
    nxt = next((o["p"] for o in par["ops"][ti + 1:] if "p" in o), None)
    tp = par["ops"][ti]["p"]
    if not pts or nxt is None or par["ops"][ti].get("main"):
        return None
    a, b = _ax(_sub(tp, pts[-1])), _ax(_sub(nxt, tp))
    return a if a is not None and a == b else None


def _options(ch, run, d, rev, slide=None):
    """Все решения для одной цепочки: список (points_after, inserts, label_bits).
    points_after — новые координаты ref 0..n; inserts — [(после какого ref по пути, [точки ступеньки])]."""
    n = len(run) - 1
    segs = [(_ax(_sub(run[k + 1]["p"], run[k]["p"])), _len(_sub(run[k + 1]["p"], run[k]["p"]))) for k in range(n)]
    comps = [i for i in range(3) if abs(d[i]) > 1e-6]
    per = []
    for i in comps:
        ch_i = [("stretch", s) for s in range(n) if segs[s][0] == i]
        if slide == i and run[-1]["kind"] == "anchor":
            ch_i.append(("stretch", n))          # тройник съезжает по основной трубе
        ch_i += [("jog_near", s) for s in range(n) if segs[s][0] not in (i, None)]
        ch_i += [("jog_far", s) for s in range(n) if segs[s][0] not in (i, None)]
        ch_i += [("jog_mid", s) for s in range(n) if segs[s][0] not in (i, None)]
        per.append(ch_i)
    out = []
    for combo in itertools.product(*per):
        jog_segs = [s for (k, s) in combo if k != "stretch"]
        if len(jog_segs) != len(set(jog_segs)):
            continue
        pts = [list(r["p"]) for r in run]
        cut = {}
        for i, (kind, s) in zip(comps, combo):
            cut[i] = s
            for k in range(0, s + 1):
                pts[k][i] = round(pts[k][i] + d[i], 4)
        ins = []
        ok = True
        for i, (kind, s) in zip(comps, combo):
            if kind == "stretch":
                continue
            ax = segs[s][0]
            A, B = pts[s], pts[s + 1]
            L = abs(B[ax] - A[ax])
            sg = 1 if B[ax] > A[ax] else -1
            gn, gf = _clear(ch, run, s, True, rev), _clear(ch, run, s, False, rev)
            if L < gn + gf + 0.02:
                ok = False
                break
            t = gn if kind == "jog_near" else (L - gf if kind == "jog_far" else round(gn + (L - gn - gf) / 2, 3))
            m2 = list(A)
            m2[ax] = round(A[ax] + sg * t, 4)
            m1 = list(m2)
            m1[i] = round(m1[i] - d[i], 4)
            ins.append((s, [m2, m1]))
        if not ok:
            continue
        # проверка: все участки по одной оси и не короче нужного
        path = []
        for k in range(n + 1):
            path.append(pts[k])
            for (s, mm) in ins:
                if s == k:
                    path += mm
        good = True
        for a, b in zip(path, path[1:]):
            v = _sub(b, a)
            if _ax(v) is None or _len(v) < 0.022:
                good = False
                break
        if not good:
            continue
        # углы, где путь поворачивает, должны отстоять друг от друга
        corners = [k for k in range(1, len(path) - 1) if _ax(_sub(path[k], path[k - 1])) != _ax(_sub(path[k + 1], path[k]))]
        for c1, c2 in zip(corners, corners[1:]):
            if _len(_sub(path[c2], path[c1])) < MIN_SEG:
                good = False
        # участок не должен развернуться назад (стянуть деталь через угол)
        for k in range(n):
            a0 = _sub(run[k + 1]["p"], run[k]["p"])
            a1 = _sub(pts[k + 1], pts[k])
            if sum(a0[j] * a1[j] for j in range(3)) <= 0:
                good = False
        if good:
            out.append(dict(pts=pts, ins=ins, path=path, corners=len(corners), combo=combo))
    return out


def _wall_dist(room, path):
    if not room:
        return 0.0
    tot, Lsum = 0.0, 0.0
    for a, b in zip(path, path[1:]):
        L = _len(_sub(b, a))
        m = [(a[i] + b[i]) / 2 for i in range(3)]
        w = min(m[0] - room["x0"], room["x1"] - m[0], m[1] - room["y0"], room["y1"] - m[1])
        tot += max(w, 0) * L
        Lsum += L
    return tot / Lsum if Lsum else 0.0


def _apply(data, cid, end, run, opt):
    """Записывает решение в цепочку: координаты точек и ступеньки как новые операции «to»."""
    C = _chains(data)
    ch = C[cid]
    for r, p in zip(run, opt["pts"]):
        if r["kind"] == "anchor":
            if p != r["p"]:                   # тройник съехал по основной трубе
                f = ch["from"]
                C[f[0]]["ops"][f[1]]["p"] = p
            continue
        if r["opi"] < 0:
            ch["start"] = p
        else:
            ch["ops"][r["opi"]]["p"] = p
    # ступеньки: вставить перед той из двух точек участка, что позже в операциях
    inserts = []
    for s, mm in opt["ins"]:
        A, B = run[s], run[s + 1]
        later = max(A["opi"], B["opi"])
        seq = mm if later == B["opi"] else mm[::-1]     # в порядке операций
        inserts.append((later, seq))
    for later, seq in sorted(inserts, key=lambda x: -x[0]):
        for p in reversed(seq):
            ch["ops"].insert(later, {"op": "to", "p": p})
        for c in C.values():                              # индексы тройников в ссылках ответвлений
            if c.get("from") and c["from"][0] == cid and c["from"][1] >= later:
                c["from"][1] += len(seq)
    _fix_then(data, ch)


def _fix_then(data, ch):
    """«then» у точек = направление на следующую точку, если поворот; иначе прямо."""
    C = _chains(data)
    if ch.get("from"):
        f = ch["from"]
        prev, din = C[f[0]]["ops"][f[1]]["p"], proekt.dvec(C[f[0]]["ops"][f[1]]["branch"])
    else:
        prev, din = ch["start"], proekt.dvec(ch["dir"])
    pidx = [i for i, o in enumerate(ch["ops"]) if "p" in o]
    for j, i in enumerate(pidx):
        o = ch["ops"][i]
        v = _sub(o["p"], prev)
        a = _ax(v)
        if a is not None:
            din = tuple((1 if v[a] > 0 else -1) if k == a else 0 for k in range(3))
        if o["op"] == "to" and j + 1 < len(pidx):
            w = _sub(ch["ops"][pidx[j + 1]]["p"], o["p"])
            b = _ax(w)
            if b is not None:
                dout = tuple((1 if w[b] > 0 else -1) if k == b else 0 for k in range(3))
                if dout != din:
                    o["then"] = proekt.dname(dout)
                else:
                    o.pop("then", None)
        if o["op"] == "tee" and o.get("main"):
            pass
        prev = o["p"]


def _rubber_one(data, cid, end, d):
    C = _chains(data)
    ch = C[cid]
    pts = ([(ch["start"], None)] if not ch.get("from") else []) + \
          [(o["p"], o.get("chain") if o["op"] == "tee" else None) for o in ch["ops"] if "p" in o]
    if ch.get("from"):
        pts = [(list(C[ch["from"][0]]["ops"][ch["from"][1]]["p"]), None)] + pts
    if end == "end":
        pts = pts[::-1]
    proekt._rubber(data, pts, d)


def _sig(data, eid):
    C = _chains(data)
    eq = next(e for e in data["equipment"] if e["id"] == eid)
    return json.dumps([C[c]["start"] if not C[c].get("from") else None for c, _ in eq.get("ports", [])] +
                      [[o.get("p") for o in C[c]["ops"]] for c, _ in eq.get("ports", [])])


def variants(data, eid, d):
    """Список вариантов: [{name, hint, data, length, corners}] — data уже с перенесённым изделием."""
    out = []
    base = copy.deepcopy(data)
    rub = copy.deepcopy(data)
    through = proekt.move_equipment(rub, eid, d)
    eq = next(e for e in data["equipment"] if e["id"] == eid)
    ports = eq.get("ports", [])
    room = data.get("room")
    per_chain = []
    C = _chains(base)
    for cid, end in ports:
        run = _run(C, cid, end)
        opts = _options(C[cid], run, d, rev=(end == "end"), slide=_slide_axis(C, C[cid]))
        good = []
        for o in opts:
            o["L"] = sum(_len(_sub(b, a)) for a, b in zip(o["path"], o["path"][1:]))
            o["wall"] = _wall_dist(room, o["path"])
            t = copy.deepcopy(base)
            _apply(t, cid, end, run, o)
            if not any(e["chain"] == cid for e in proekt.build(t)):
                good.append(o)
        per_chain.append((cid, end, run, good))

    def pick(score):
        dd = copy.deepcopy(base)
        e2 = next(e for e in dd["equipment"] if e["id"] == eid)
        e2["off"] = [round(e2.get("off", [0, 0, 0])[i] + d[i], 4) for i in range(3)]
        Lt, ct = 0.0, 0
        for cid, end, run, opts in per_chain:
            if not opts:                      # места на ступеньку нет — эту трассу тянем резинкой
                _rubber_one(dd, cid, end, d)
                continue
            best = min(opts, key=score)
            # пересчитать ссылки на точки в копии: run хранит индексы, они те же
            _apply(dd, cid, end, run, best)
            Lt += best["L"]
            ct += best["corners"]
        return dd, Lt, ct

    cand = []
    if any(opts for *_, opts in per_chain):
        w = pick(lambda o: (round(o["wall"], 2), o["corners"], o["L"]))
        s = pick(lambda o: (o["L"] + 0.12 * o["corners"], o["wall"]))
        f = pick(lambda o: (o["corners"], o["L"]))
        for name, hint, r in (("Вдоль стены", "трубы держатся у стен", w), ("Напрямую", "короче всего", s),
                              ("Меньше углов", "меньше угольников", f)):
            if r:
                cand.append(dict(name=name, hint=hint, data=r[0], length=round(r[1], 2), corners=r[2]))
    cand.append(dict(name="Как было", hint="участки тянутся, форма трассы та же" +
                     (" — дотянулось до другого конца, проверьте стык" if through else ""),
                     data=rub, length=None, corners=None))
    # без повторов и без ошибок сборки
    seen = set()
    for v in cand:
        sg = _sig(v["data"], eid)
        if sg in seen:
            continue
        seen.add(sg)
        v["errors"] = proekt.build(v["data"])
        if not v["errors"]:
            out.append(v)
    proekt.build(data)
    return out
