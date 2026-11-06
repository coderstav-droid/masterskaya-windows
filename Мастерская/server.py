"""Мастерская — совместная правка проекта котельной в реальном времени (Станислав + Claude).

Запуск: python3 server.py            (или двойной клик по «Запустить Мастерскую.command»)
Открыть: http://localhost:8800 на Mac; с телефона — ссылка с ключом, которую сервер печатает при старте.

Источник правды — котельная_проект.json в папке проекта. Правки из браузера сохраняются в него, правки Claude —
тоже; сервер следит за файлом и сразу рассылает изменения всем открытым окнам (SSE). Каждое сохранение кладётся
в историю (история/), поэтому любую правку можно отменить. Чат — chat.jsonl: Claude читает его и отвечает туда же.
"""
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.join(os.path.dirname(HERE), "Дом 120")
sys.path.insert(0, PROJ_DIR)
import proekt  # noqa: E402
import trassa  # noqa: E402
import uzly_ppr as U  # noqa: E402

PORT = 8800
STATIC = os.path.join(HERE, "static")
HIST = os.path.join(HERE, "история")
CHAT = os.path.join(HERE, "chat.jsonl")
KEYF = os.path.join(HERE, ".ключ")
KAT = os.path.join(HERE, "katalog_uzlov.json")   # каталог узлов-заготовок: пополняем вместе со временем
os.makedirs(HIST, exist_ok=True)
KEY = open(KEYF).read().strip() if os.path.exists(KEYF) else secrets.token_urlsafe(8)
open(KEYF, "w").write(KEY)
LOCK = threading.Lock()
MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css",
        ".json": "application/json", ".glb": "model/gltf-binary", ".png": "image/png", ".svg": "image/svg+xml",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".pdf": "application/pdf"}


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.168.0.1", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def jsonable(v):
    if isinstance(v, tuple):
        return [jsonable(x) for x in v]
    if isinstance(v, list):
        return [jsonable(x) for x in v]
    if isinstance(v, dict):
        return {k: jsonable(x) for k, x in v.items()}
    if isinstance(v, float):
        return round(v, 5)
    return v


def items_now():
    """Детали и трубы последней сборки (proekt.build) — для окна."""
    items = []
    for it in U.placed():
        d = {k: it[k] for k in ("t", "sys", "cid", "op") if k in it}
        if it["t"] == "pipe":
            d.update(a=it["a"], b=it["b"], d=it["d"], L=it["L"], pipe=it["pipe"])
        else:
            p = U.PARTS[it["key"]]
            d.update(key=it["key"], kind=p["kind"])
            if "c" in it:
                d.update(c=it["c"], d=it["d"], d2=it["d2"], dm=it.get("dm"), dia=p["d"], db=p.get("db", p["d"]))
            else:
                d.update(s=it["s"], d=it["d"], L=it["L"], flip=it["flip"], a=p["a"], b=p["b"],
                         t_=p.get("t"), dia=p.get("d"), h=p.get("handle"))
        items.append(d)
    return items


def variants_of(data, eid, d):
    """Варианты трасс при переносе: [{name, hint, length, corners, items, data}]. Если ни один не собрался —
    причина из «резинки», чтобы сказать человеку, что мешает."""
    vs = trassa.variants(data, eid, d)
    out = []
    for v in vs:
        proekt.build(v["data"])
        out.append(dict(name=v["name"], hint=v["hint"], length=v["length"], corners=v["corners"], items=items_now(),
                        data=v["data"]))
    why = ""
    if not out:
        import copy
        t = copy.deepcopy(data)
        proekt.move_equipment(t, eid, d)
        er = proekt.build(t)
        why = er[0]["msg"] if er else ""
    proekt.build(data)
    return out, why


def state():
    """Собирает проект и отдаёт всё, что нужно интерфейсу: данные, ошибки, геометрию, итоги."""
    with LOCK:
        data = proekt.load()
        errors = proekt.build(data)
        r = U.analyse()
        items = []
        for it in U.placed():
            d = {k: it[k] for k in ("t", "sys", "cid", "op") if k in it}
            if it["t"] == "pipe":
                d.update(a=it["a"], b=it["b"], d=it["d"], L=it["L"], pipe=it["pipe"])
            else:
                p = U.PARTS[it["key"]]
                d.update(key=it["key"], kind=p["kind"])
                if "c" in it:
                    d.update(c=it["c"], d=it["d"], d2=it["d2"], dm=it.get("dm"), dia=p["d"], db=p.get("db", p["d"]))
                else:
                    d.update(s=it["s"], d=it["d"], L=it["L"], flip=it["flip"], a=p["a"], b=p["b"],
                             t_=p.get("t"), dia=p.get("d"), h=p.get("handle"))
            items.append(d)
        bom, total = [], 0.0
        for k in U.PARTS:
            q = r["bom"].get(k)
            if q:
                p = U.PARTS[k]
                s = q * p["price"]
                total += s
                bom.append(dict(key=k, name=p["name"], art=p["art"], qty=q, price=p["price"], sum=round(s),
                                unit="м" if p["kind"] in ("pipe", "insul") else "шт", est=p["src"].startswith("оценка")))
        cat = [dict(key=k, name=p["name"], kind=p["kind"], a=p["a"], b=p["b"], L=p["L"], price=p["price"])
               for k, p in U.PARTS.items() if p["kind"] not in ("pipe", "clamp", "sleeve", "insul", "aux")]
        return jsonable(dict(project=data, errors=errors, items=items, bom=bom, total=round(total),
                             joints=sum(r["joints"].values()), nuts=sum(r["nuts"].values()), clamps=r["clamps"],
                             sleeves=len(r["sleeves"]), catalog=cat, mtime=os.path.getmtime(proekt.FILE),
                             dirs=list(proekt.DIRS)))


def snaps():
    return sorted(f for f in os.listdir(HIST) if f.endswith(".json"))


def snapshot_if_changed(author):
    """Правка файла мимо окна (Claude правит котельная_проект.json) — тоже в историю, иначе «Отменить» её потеряет."""
    hs = snaps()
    cur = open(proekt.FILE, encoding="utf-8").read()
    if not hs or open(os.path.join(HIST, hs[-1]), encoding="utf-8").read() != cur:
        snapshot(author)


def snapshot(author):
    ts = time.strftime("%Y%m%d-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}"
    dst = os.path.join(HIST, f"{ts}_{author}.json")
    with open(proekt.FILE, encoding="utf-8") as f, open(dst, "w", encoding="utf-8") as g:
        g.write(f.read())
    hs = sorted(os.listdir(HIST))
    for old in hs[:-400]:
        os.remove(os.path.join(HIST, old))


def chat_read(after=0):
    if not os.path.exists(CHAT):
        return []
    out = []
    for i, line in enumerate(open(CHAT, encoding="utf-8")):
        if i >= after and line.strip():
            m = json.loads(line)
            m["n"] = i
            out.append(m)
    return out


def chat_add(who, text, ref=None):
    with LOCK:
        with open(CHAT, "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(who=who, text=text, t=time.strftime("%H:%M"), ref=ref), ensure_ascii=False) + "\n")


def kat_load():
    if not os.path.exists(KAT):
        return {"uzly": []}
    return json.load(open(KAT, encoding="utf-8"))


def kat_save(k):
    tmp = KAT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write('{\n "uzly": [\n' + ",\n".join("  " + json.dumps(u, ensure_ascii=False) for u in k["uzly"]) + "\n ]\n}\n")
    os.replace(tmp, KAT)


# ------------------------------------------------------------------ живые обновления
SUBS = []


def broadcast(ev, data=""):
    msg = f"event: {ev}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode()
    for q in list(SUBS):
        q.append(msg)


def watcher():
    last = {}
    while True:
        for name, path in (("project", proekt.FILE), ("chat", CHAT), ("katalog", KAT)):
            try:
                m = os.path.getmtime(path)
            except OSError:
                continue
            if last.get(name) not in (None, m):
                if name == "project":
                    with LOCK:
                        snapshot_if_changed("Claude")
                broadcast(name, m)
            last[name] = m
        time.sleep(0.4)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def allowed(self):
        if self.client_address[0] in ("127.0.0.1", "::1"):
            return True
        q = parse_qs(urlparse(self.path).query)
        ck = self.headers.get("Cookie", "")
        return q.get("k", [""])[0] == KEY or f"mk={KEY}" in ck

    def send(self, code, body, ctype="application/json", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if not self.allowed():
            return self.send(403, "Нужна ссылка с ключом — её печатает сервер при запуске", "text/plain; charset=utf-8")
        u = urlparse(self.path)
        p = u.path
        if p == "/api/state":
            return self.send(200, state())
        if p == "/api/chat":
            after = int(parse_qs(u.query).get("after", ["0"])[0])
            return self.send(200, chat_read(after))
        if p == "/api/katalog":
            return self.send(200, kat_load())
        if p == "/api/history":
            return self.send(200, snaps()[-60:])
        if p == "/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            q = []
            SUBS.append(q)
            try:
                self.wfile.write(b"event: hello\ndata: 1\n\n")
                self.wfile.flush()
                t0 = time.time()
                while True:
                    while q:
                        self.wfile.write(q.pop(0))
                        self.wfile.flush()
                    if time.time() - t0 > 15:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                        t0 = time.time()
                    time.sleep(0.2)
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                SUBS.remove(q)
            return
        if p.startswith("/files/"):
            f = os.path.join(PROJ_DIR, os.path.basename(p[7:]))
            if os.path.exists(f):
                return self.send(200, open(f, "rb").read(), MIME.get(os.path.splitext(f)[1], "application/octet-stream"))
            return self.send(404, "нет файла", "text/plain")
        f = os.path.normpath(os.path.join(STATIC, (p.lstrip("/") or "index.html")))
        if not f.startswith(STATIC) or not os.path.isfile(f):
            return self.send(404, "нет", "text/plain")
        extra = {"Set-Cookie": f"mk={KEY}; Path=/; Max-Age=31536000; SameSite=Lax"} if p in ("/", "/index.html") else None
        self.send(200, open(f, "rb").read(), MIME.get(os.path.splitext(f)[1], "application/octet-stream"), extra)

    def do_POST(self):
        if not self.allowed():
            return self.send(403, {"error": "нет доступа"})
        p = urlparse(self.path).path
        b = self.body()
        if p == "/api/project":
            data = b["project"]
            with LOCK:
                proekt.save(data)
                snapshot(b.get("author", "Станислав"))
            return self.send(200, state())
        if p == "/api/undo":
            hs = snaps()
            if len(hs) < 2:
                return self.send(200, {"ok": False, "msg": "Отменять нечего"})
            with LOCK:
                prev = os.path.join(HIST, hs[-2])
                with open(prev, encoding="utf-8") as f, open(proekt.FILE, "w", encoding="utf-8") as g:
                    g.write(f.read())
                os.rename(os.path.join(HIST, hs[-1]), os.path.join(HIST, hs[-1] + ".отменено"))
            return self.send(200, state())
        if p == "/api/move_eq":                     # перенос оборудования: трассы тянутся за ним
            with LOCK:
                data = proekt.load()
                th = proekt.move_equipment(data, b["id"], b["d"])
                proekt.save(data)
                snapshot(b.get("author", "Станислав"))
            st = state()
            st["through"] = th
            return self.send(200, st)
        if p == "/api/variants":                   # варианты трасс для переноса (без сохранения)
            with LOCK:
                vs, why = variants_of(proekt.load(), b["id"], b["d"])
            return self.send(200, jsonable({"variants": [{k: v[k] for k in ("name", "hint", "length", "corners", "items")}
                                                          for v in vs], "why": why}))
        if p == "/api/move_apply":                 # перенос с выбранным вариантом трассы
            with LOCK:
                data = proekt.load()
                vs, why = variants_of(data, b["id"], b["d"])
                v = next((x for x in vs if x["name"] == b.get("name")), vs[0] if vs else None)
                if v is None:
                    return self.send(200, {"ok": False, "why": why})
                proekt.save(v["data"])
                snapshot(b.get("author", "Станислав"))
            return self.send(200, state())
        if p == "/api/eq":                         # изделия из библиотеки: добавить / повернуть / удалить
            with LOCK:
                data = proekt.load()
                eqs = data.setdefault("equipment", [])
                if b.get("add"):
                    a = b["add"]
                    n = 1 + max([int(e["id"][3:]) for e in eqs if e["id"].startswith("lib") and e["id"][3:].isdigit()] or [0])
                    eqs.append(dict(id=f"lib{n}", name=a["name"], lib=a["lib"], pos=[round(x, 4) for x in a["pos"]],
                                    rot=a.get("rot", 0), off=[0, 0, 0], ports=[]))
                    new_id = f"lib{n}"
                else:
                    e = next(x for x in eqs if x["id"] == b["id"])
                    new_id = e["id"]
                    if b.get("delete"):
                        if e.get("ports"):
                            return self.send(200, {"ok": False, "why": "к изделию подключены трубы — сначала отключите их"})
                        eqs.remove(e)
                        new_id = None
                    if "rot" in b:
                        e["rot"] = (e.get("rot", 0) + b["rot"]) % 360
                proekt.save(data)
                snapshot(b.get("author", "Станислав"))
            st = state()
            st["new_id"] = new_id
            return self.send(200, st)
        if p == "/api/katalog":
            with LOCK:
                k = kat_load()
                if b.get("delete"):
                    k["uzly"] = [u for u in k["uzly"] if u["id"] != b["delete"]]
                else:
                    u = b["uzel"]
                    u.setdefault("id", "u" + time.strftime("%y%m%d%H%M%S"))
                    u.setdefault("author", b.get("author", "Станислав"))
                    k["uzly"] = [x for x in k["uzly"] if x["id"] != u["id"]] + [u]
                kat_save(k)
            return self.send(200, k)
        if p == "/api/chat":
            chat_add(b.get("who", "Станислав"), b["text"][:4000], b.get("ref"))
            return self.send(200, {"ok": True})
        if p == "/api/smeta":
            r = subprocess.run(([sys.executable, "smeta_kotelnaya_full.py"] if getattr(sys, "frozen", False) else ["uv", "run", "-q", "--with", "openpyxl", "python3", "smeta_kotelnaya_full.py"]),
                               cwd=PROJ_DIR, capture_output=True, text=True, timeout=300)
            md = os.path.join(PROJ_DIR, "Смета котельная Д120 — полная.md")
            tot = [l for l in open(md, encoding="utf-8") if "ВСЕГО" in l] if os.path.exists(md) else []
            return self.send(200, {"ok": r.returncode == 0, "total": tot[-1].strip() if tot else "",
                                   "xlsx": "/files/Смета котельная Д120 — полная.xlsx", "err": r.stderr[-800:]})
        self.send(404, {"error": "нет такого действия"})


def main():
    if not os.path.exists(proekt.FILE):
        proekt.save(proekt.export_from_code())
    snapshot_if_changed("начало")
    threading.Thread(target=watcher, daemon=True).start()
    ip = lan_ip()
    print(f"Мастерская запущена.\n  На этом компьютере:   http://localhost:{PORT}\n  С телефона:    http://{ip}:{PORT}/?k={KEY}\n"
          "Окно не закрывайте, пока работаете. Остановить — Ctrl+C.", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()


if __name__ == "__main__":
    main()
