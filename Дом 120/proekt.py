"""Проект котельной в файле: узлы и цепочки как данные (котельная_проект.json) — для правки в Мастерской.

Формат цепочки:
  {"id": "c1", "title": "Т1 подача котла", "start": [x, y, z], "dir": "низ", "open": "НР3/4", "sys": "Т1",
   "pipe": "gf", "port": "котёл 3/4\" НР", "from": null,
   "ops": [{"op": "add", "key": "КранГ3/4"},
           {"op": "to", "p": [x, y, z], "then": "С"},          # труба до точки, в ней угольник на «С»
           {"op": "tee", "p": [...], "branch": "Ю", "key": "Тр32×20", "title": "...", "chain": "c3"},
           {"op": "finish", "p": [...], "port": "НР3/4", "keys": ["МкНр32×3/4", "КранГ3/4"], "wall": false}]}
Ответвление тройника — отдельная цепочка с "from": ["c1", <номер операции tee>].
Оборудование: "equipment": [{"id": "kotel", "name": ..., "off": [dx, dy, dz], "ports": [["c1", "start"], ["c2", "end"]]}]
— смещение изделия от места в модели и какие концы цепочек к нему подключены (их трассы тянутся за изделием).
Направления: В (+x), З (−x), С (−y, к северной стене), Ю (+y), верх, низ. Координаты — метры плана котельной.
"""
import json
import os

import uzly_ppr as U

HERE = os.path.dirname(os.path.abspath(__file__))
FILE = os.path.join(HERE, "котельная_проект.json")
DIRS = {"В": (1, 0, 0), "З": (-1, 0, 0), "С": (0, -1, 0), "Ю": (0, 1, 0), "верх": (0, 0, 1), "низ": (0, 0, -1)}


def dname(v):
    v = tuple(round(x) for x in v)
    for k, d in DIRS.items():
        if d == v:
            return k
    return list(v)


def dvec(s):
    return DIRS[s] if isinstance(s, str) else tuple(s)


def r3(p):
    return [round(float(x), 4) for x in p]


# ------------------------------------------------------------------ из кода (build_ppr) в файл
def export_from_code():
    """Записывает действия Chain при сборке узлов из кода и превращает их в данные проекта."""
    log, ids = {}, {}
    orig = {k: getattr(U.Chain, k) for k in ("__init__", "add", "to", "tee", "finish")}

    def init(self, node, title, start, d, open_end, sys, pipe="gf", port=""):
        orig["__init__"](self, node, title, start, d, open_end, sys, pipe, port)
        cid = f"c{len(ids) + 1}"
        ids[id(self)] = cid
        log[cid] = dict(id=cid, node=node, title=title, start=r3(start), dir=dname(d), open=open_end, sys=sys,
                        pipe=pipe, port=port, ops=[], **({"from": self._from} if hasattr(self, "_from") else {}))

    busy = []

    def add(self, *keys):
        if not busy:
            for k in keys:
                log[ids[id(self)]]["ops"].append({"op": "add", "key": k})
        return orig["add"](self, *keys)

    def to(self, c, then=None):
        op = {"op": "to", "p": r3(c)}
        if then is not None:
            op["then"] = dname(then)
        log[ids[id(self)]]["ops"].append(op)
        return orig["to"](self, c, then)

    def tee(self, c, branch, key=None, main=None, title="", sys=None, pipe=None):
        me = ids[id(self)]
        n = len(log[me]["ops"])
        op = {"op": "tee", "p": r3(c), "branch": dname(branch), "title": title}
        if key:
            op["key"] = key
        if main:
            op["main"] = dname(main)
        log[me]["ops"].append(op)
        br = orig["tee"](self, c, branch, key, main, title, sys, pipe)
        cid = ids[id(br)]
        log[cid]["from"] = [me, n]
        op["chain"] = cid
        return br

    def finish(self, port_pt, port_end, keys=(), wall=False, note=""):
        log[ids[id(self)]]["ops"].append({"op": "finish", "p": r3(port_pt), "port": port_end, "keys": list(keys),
                                          "wall": wall, "note": note})
        busy.append(1)
        try:
            return orig["finish"](self, port_pt, port_end, keys, wall, note)
        finally:
            busy.pop()

    try:
        U.Chain.__init__, U.Chain.add, U.Chain.to, U.Chain.tee, U.Chain.finish = init, add, to, tee, finish
        U.seed_ppr()
    finally:
        for k, f in orig.items():
            setattr(U.Chain, k, f)
    nodes = []
    for ch in log.values():
        if not nodes or nodes[-1]["name"] != ch["node"]:
            if not any(n["name"] == ch["node"] for n in nodes):
                nodes.append({"name": ch["node"], "chains": []})
        nd = next(n for n in nodes if n["name"] == ch["node"])
        ch = dict(ch)
        ch.pop("node")
        if "from" in ch and ch["from"] is not None:
            ch["title"] = ch["title"]
        nd["chains"].append(ch)
    return {"object": "Дом 120 — котельная", "variant": "PPR", "nodes": nodes}


# ------------------------------------------------------------------ из файла — сборка
def load(path=FILE):
    return json.load(open(path, encoding="utf-8"))


def dumps(data):
    """JSON проекта: по строке на операцию — удобно читать и сравнивать правки."""
    j = lambda o: json.dumps(o, ensure_ascii=False)
    L = ["{", f' "object": {j(data.get("object", ""))},', f' "variant": {j(data.get("variant", "PPR"))},']
    if data.get("room"):
        L.append(f' "room": {j(data["room"])},')
    L.append(' "nodes": [')
    for ni, nd in enumerate(data["nodes"]):
        L.append(f'  {{"name": {j(nd["name"])}, "chains": [')
        for ci, ch in enumerate(nd["chains"]):
            head = {k: v for k, v in ch.items() if k != "ops"}
            L.append(f"   {{{j(head)[1:-1]}, \"ops\": [")
            L += [f"    {j(op)}" + ("," if oi < len(ch["ops"]) - 1 else "") for oi, op in enumerate(ch["ops"])]
            L.append("   ]}" + ("," if ci < len(nd["chains"]) - 1 else ""))
        L.append("  ]}" + ("," if ni < len(data["nodes"]) - 1 else ""))
    L.append(" ]" + ("," if data.get("equipment") else ""))
    if data.get("equipment"):
        L.append(' "equipment": [')
        L += [f"  {j(e)}" + ("," if i < len(data["equipment"]) - 1 else "") for i, e in enumerate(data["equipment"])]
        L.append(" ]")
    L.append("}")
    return "\n".join(L) + "\n"


def save(data, path=FILE):
    tmp = path + ".tmp"
    txt = dumps(data)
    json.loads(txt)
    open(tmp, "w", encoding="utf-8").write(txt)
    os.replace(tmp, path)


def build(data):
    """Собирает узлы из данных. Ошибки не останавливают сборку: цепочка обрывается на ошибочной операции."""
    U.NODES.clear()
    errors, objs, pending = [], {}, {}
    for nd in data["nodes"]:
        for ch in nd["chains"]:
            cid = ch["id"]
            if ch.get("from"):
                c = pending.get(tuple(ch["from"]))
                if c is None:
                    errors.append(dict(chain=cid, op=-1, msg="Не построено: ошибка в цепочке, от которой отходит"))
                    continue
                c.title = ch.get("title", c.title)
            else:
                c = U.Chain(nd["name"], ch["title"], tuple(ch["start"]), dvec(ch["dir"]), ch["open"], ch["sys"],
                            ch.get("pipe", "gf"), port=ch.get("port", ""))
            c.cid = cid
            objs[cid] = c
            for i, op in enumerate(ch["ops"]):
                n0 = len(c.items)
                try:
                    k = op["op"]
                    if k == "add":
                        c.add(op["key"])
                    elif k == "to":
                        c.to(tuple(op["p"]), dvec(op["then"]) if op.get("then") else None)
                    elif k == "tee":
                        br = c.tee(tuple(op["p"]), dvec(op["branch"]), op.get("key"),
                                   dvec(op["main"]) if op.get("main") else None, op.get("title", ""))
                        pending[(cid, i)] = br
                    elif k == "finish":
                        c.finish(tuple(op["p"]), op.get("port", ""), op.get("keys", []), op.get("wall", False),
                                 op.get("note", ""))
                    else:
                        raise U.ChainError(f"неизвестная операция {k}")
                except (U.ChainError, KeyError, TypeError, ValueError) as e:
                    msg = str(e)
                    if isinstance(e, KeyError):
                        msg = f"нет детали или поля {e} в каталоге"
                    errors.append(dict(chain=cid, op=i, msg=msg.replace(f"{c.title}: ", "")))
                    for it in c.items[n0:]:
                        it.update(cid=cid, op=i)
                    break
                for it in c.items[n0:]:
                    it.update(cid=cid, op=i)
    return errors


# ------------------------------------------------------------------ перенос оборудования: трассы тянутся «резинкой»
def _rubber(data, pts, d):
    """pts — точки от изделия вдоль трассы (ссылки на списки). Точка k сдвигается на cur; следующая — на cur без
    составляющей вдоль оси участка k→k+1 (этот участок просто удлиняется/укорачивается). Стоп, когда cur = 0."""
    cur = list(d)
    for k, (arr, tee) in enumerate(pts):
        if not any(abs(c) > 1e-9 for c in cur):
            break
        orig = list(arr)
        for i in range(3):
            arr[i] = round(arr[i] + cur[i], 4)
        if tee:                                   # ответвление тройника тянется за ним
            br = next(c for n in data["nodes"] for c in n["chains"] if c["id"] == tee)
            _rubber(data, [(list(orig), None)] + [(o["p"], o.get("chain") if o["op"] == "tee" else None)
                                                  for o in br["ops"] if "p" in o], cur)
        if k + 1 < len(pts):
            nxt = pts[k + 1][0]
            v = [nxt[i] - orig[i] for i in range(3)]
            cur[max(range(3), key=lambda i: abs(v[i]))] = 0.0
    return any(abs(c) > 1e-9 for c in cur)      # True — дотянули до другого конца (он тоже сдвинут)


def move_equipment(data, eid, d):
    """Сдвигает изделие на d = [dx, dy, dz] и подтягивает подключённые трассы. Возвращает цепочки, сдвинутые целиком."""
    eq = next(e for e in data["equipment"] if e["id"] == eid)
    eq["off"] = [round(eq.get("off", [0, 0, 0])[i] + d[i], 4) for i in range(3)]
    C = {c["id"]: c for n in data["nodes"] for c in n["chains"]}
    through = []
    for cid, end in eq.get("ports", []):
        ch = C[cid]
        pts = ([(ch["start"], None)] if not ch.get("from") else []) + \
              [(o["p"], o.get("chain") if o["op"] == "tee" else None) for o in ch["ops"] if "p" in o]
        if ch.get("from"):                        # ответвление: его начало — точка тройника (не двигаем, только ось)
            pts = [(list(C[ch["from"][0]]["ops"][ch["from"][1]]["p"]), None)] + pts
        if end == "end":
            pts = pts[::-1]
        if _rubber(data, pts, d):
            through.append(cid)
    return through


def build_file(path=FILE):
    return build(load(path))


if __name__ == "__main__":
    if not os.path.exists(FILE):
        save(export_from_code())
        print("Записан", FILE)
    errs = build_file()
    r = U.analyse()
    print("Ошибок:", len(errs), errs[:3])
    print("Трубы, м:", {k: round(v, 2) for k, v in r["pipes"].items()}, "хомутов", len(r["clamps"]))
