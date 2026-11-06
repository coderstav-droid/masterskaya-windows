"""Котельная «Дом 120» — узлы обвязки поштучно (вариант на полипропилене). Без Blender: чистый Python.

Каждый узел — цепочка деталей от патрубка оборудования до патрубка оборудования. Сборщик Chain ставит детали
по оси одну за другой и ПРОВЕРЯЕТ КАЖДЫЙ СТЫК: резьба НР входит только в ВР или накидную гайку того же
размера, труба PPR — только в раструб того же диаметра. Пропущенный переход (ниппель, футорка, МкНр, американка)
даёт ошибку — смета и модель без переходов не соберутся.

Из одного описания строятся: 3D-модель (kotelnaya_3d_v4.py), пособие «узлы в разборе» и смета
(smeta_kotelnaya_full.py): трубы по метрам, фитинги, хомуты, гильзы, прокладки, лён и паста по числу резьб.

Материал сейчас один — PPR (RTP). Другие варианты (нержавейка, PEX) добавляются своим каталогом деталей
и своими функциями узлов с теми же точками подключения оборудования.

Обозначения концов деталей: s25 — раструб PPR Ø25, p25 — труба PPR Ø25, НР3/4 / ВР3/4 — резьба,
Г3/4 — накидная гайка (американка), pe32 — труба ПНД Ø32.
Координаты — план котельной: x — на восток, y — на юг, z — вверх, метры.
"""
import math
import os
from collections import Counter, OrderedDict, defaultdict

# ------------------------------------------------------------------ помещение и оборудование (как в модели)
X0, X1, Y0, Y1, H = 0.40, 2.14, 0.40, 2.24, 2.80
try:   # размеры помещения берутся из проекта (Мастерская может их менять)
    import json as _json, os as _os
    _r = _json.load(open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "котельная_проект.json"),
                         encoding="utf-8")).get("room")
    if _r:
        X0, X1, Y0, Y1, H = _r["x0"], _r["x1"], _r["y0"], _r["y1"], _r["h"]
except (OSError, ValueError, KeyError):
    pass
BXP, BZ0 = 0.545, 1.05                     # ось патрубков котла, низ котла
OUTS = {"sup": 0.64, "dsup": 0.72, "gas": 0.82, "dret": 0.90, "ret": 0.98}
PORT_Z = BZ0 - 0.02                        # торец патрубков котла 3/4" НР
YP = 0.50                                  # ось гидрострелки, коллектора, групп
HX, HR = 1.20, 0.068                       # гидрострелка
HP_IN, HP_OUT = 1.10, 0.72                 # её патрубки к котлу (1" ВР)
GZ1 = 1.33                                 # верх насосных групп
G_OUT = {"7.1": (1.4675, 1.3425), "7.2": (1.7625, 1.6375)}   # (подача, обратка) выходы групп 1" ВР
EX, EY, EZ0 = 0.545, 1.34, 1.11            # бак WRV 8 (штуцер 3/4" НР вниз)
TX, TY, TR, TH = 1.815, 1.905, 0.300, 1.45  # бойлер
WXD, WYD, WZ0D, WZ1D = 1.10, 2.06, 0.73, 1.17   # бак WDV 18 (штуцер 3/4" НР вверх)
FD = (1.20, 1.80)                          # трап
YC = 2.15                                  # ось холодной воды вдоль южной стены
ZC = 1.45                                  # высота горизонтали ХВС


def tank_x(y):
    return TX - math.sqrt(TR * TR - (y - TY) ** 2)


def tank_y(x):
    return TY - math.sqrt(TR * TR - (x - TX) ** 2)


# ------------------------------------------------------------------ резьбы и размеры
THREAD_OD = {"1/4": 0.0135, "1/2": 0.0210, "3/4": 0.0264, "1": 0.0332, "1 1/4": 0.0419}
SOCKET = {20: 0.0145, 25: 0.016, 32: 0.018}          # глубина раструба PPR
FACE = {20: 0.025, 25: 0.028, 32: 0.0355}           # центр угольника → торец раструба (SLT AQUA, из BIM)
FACE_T = {20: 0.026, 25: 0.030, 32: 0.036}           # центр тройника → торец раструба (SLT AQUA)
STEP = {("gf", 20): 0.50, ("gf", 25): 0.60, ("gf", 32): 0.65, ("pn20", 20): 0.60, ("pn20", 25): 0.75,
        ("pn20", 32): 0.90}                           # шаг опор (RTP, табл. 16, горячая/холодная)
HOT = {"Т1", "Т11", "ЗП", "Т3", "Т4"}                  # красная изоляция, остальное — синяя
STUB = 0.022                                          # минимальный отрезок трубы между раструбами

T, R, A, AQ, IN = "каталог Терем", "каталог RTP", "оценка — уточнить", "каталог Aquario", "в комплекте"

# ------------------------------------------------------------------ каталог деталей
# kind — как рисовать; a, b — концы; L — длина по оси, м; extra — вложенные позиции сметы
PARTS = OrderedDict()


def part(key, name, art, price, src, kind, a, b, L, **kw):
    PARTS[key] = dict(key=key, name=name, art=art, price=price, src=src, kind=kind, a=a, b=b, L=L, **kw)


for d in (20, 25, 32):
    part(f"Уг{d}", f"Угольник PPR {d}×90°", {20: "RTP 10830", 25: "RTP 10831", 32: "RTP, белый"}[d],
         {20: 8.82, 25: 15.06, 32: 25}[d], R if d < 32 else A, "elbow", f"s{d}", f"s{d}", 0, d=d)
    part(f"Мфт{d}", f"Муфта PPR {d} соединительная", {20: "RTP 10595", 25: "RTP 10927", 32: "RTP 10928"}[d],
         {20: 7.38, 25: 11.21, 32: 20.46}[d], R, "coupling", f"s{d}", f"s{d}", 0.036 + d * 0.0006, d=d)
part("Тр20", "Тройник PPR 20×20×20", "RTP 10978", 11.25, R, "tee", "s20", "s20", 0, d=20, db=20)
part("Тр25", "Тройник PPR 25×25×25", "RTP 10737", 19.94, R, "tee", "s25", "s25", 0, d=25, db=25)
part("Тр32×20", "Тройник переходной PPR 32×20×32", "RTP 10768", 35.02, R, "tee", "s32", "s32", 0, d=32, db=20)
part("Тр32×25", "Тройник переходной PPR 32×25×32", "RTP, тройник 32×25×32", 38, A, "tee", "s32", "s32", 0, d=32, db=25)
part("Пер25×20", "Муфта переходная PPR 25×20 (внутр./внутр.)", "RTP 15050", 12.59, R, "ppr_reducer", "s25", "s20",
     0.045, d=25, d2=20)
part("КранPPR25", "Кран шаровой PPR 25 (латунный шар, ручка-рычаг)", "RTP, кран шаровой PPR 25", 520, A,
     "ppr_valve", "s25", "s25", 0.0775, d=25)

# муфты комбинированные: МкНр — наружная резьба, МкВр — внутренняя
for d, t, art, pr, src in ((20, "1/2", "RTP 10662", 115.70, R), (20, "3/4", "RTP 10663", 181.08, R),
                           (25, "1/2", "RTP, МкНр 25×1/2", 135, A),
                           (25, "3/4", "RTP 10665", 171.03, R), (25, "1", "RTP 46972", 391.26, R),
                           (32, "3/4", "RTP, МкНр 32×3/4", 190, A), (32, "1", "RTP 14631", 702.18, R)):
    part(f"МкНр{d}×{t}", f"Муфта комбинированная PPR {d}×{t}\" НР (МкНр)", art, pr, src, "mk", f"s{d}", f"НР{t}",
         0.058, d=d, t=t)
for d, t, art, pr in ((20, "1/2", "RTP 10652", 93.02), (20, "3/4", "RTP 10653", 136.62), (25, "1/2", "RTP 10654", 112.06),
                      (25, "3/4", "RTP 10655", 130.02), (25, "1", "RTP 46970", 313), (32, "3/4", "RTP 10657", 138.61)):
    part(f"МкВр{d}×{t}", f"Муфта комбинированная PPR {d}×{t}\" ВР (МкВр)", art, pr, R, "mk", f"s{d}", f"ВР{t}",
         0.050, d=d, t=t)
# американки PPR (разъёмные): «Н» — хвостовик НР, «Г» — накидная гайка
for d, t, art, pr, end, src in ((20, "1/2", "RTP 10640", 269.43, "НР", R), (20, "3/4", "RTP 10616", 250.57, "Г", R),
                                (25, "3/4", "RTP 10619", 382.54, "Г", R), (25, "3/4н", "RTP 10644", 417.56, "НР", R),
                                (25, "1/2", "RTP, американка 25×1/2\" НР", 330, "НР", A),
                                (25, "1/2г", "RTP, американка 25×1/2\" гайка", 310, "Г", A),
                                (32, "1", "RTP 10646", 552.38, "НР", R),
                                (32, "1г", "RTP, американка 32×1\" гайка", 590, "Г", A)):
    tt = t.rstrip("нг")
    part(f"Ам{d}×{t}", f"Американка PPR {d}×{tt}\" " + ("НР (хвостовик)" if end == "НР" else "накидная гайка ВР"),
         art, pr, src, "am_ppr", f"s{d}", f"{end}{tt}", 0.072 if end == "НР" else 0.062, d=d, t=tt)

# латунь
part("КранГ3/4", "Кран шаровой 3/4\" с накидной гайкой (ВР × гайка), ручка-бабочка", "Stout SVB-0009-000020", 1443, T,
     "valve_nut", "Г3/4", "ВР3/4", 0.072, t="3/4", handle="butterfly")
part("КранГ1", "Кран шаровой 1\" с накидной гайкой (ВР × гайка)", "Stout SVB-0009-000025", 2100, A,
     "valve_nut", "Г1", "ВР1", 0.085, t="1", handle="butterfly")
part("Кран1ВН", "Кран шаровой полнопроходной 1\" ВР/НР, ручка-рычаг", "Stout SVB-0004-200025", 1927, T,
     "valve", "ВР1", "НР1", 0.090, t="1", handle="lever")
part("КранАм1", "Кран шаровой полнопроходной 1\" ВР/НР с американкой, ручка-бабочка", "Stout SVB-0007-000025", 2264, T,
     "valve", "ВР1", "НР1", 0.100, t="1", handle="butterfly")
part("Нип1", "Ниппель НН 1\" никелированный", "Stout SFT-0004-000011", 409, T, "nipple", "НР1", "НР1", 0.044, t="1")
part("Кран1/2ВВ", "Кран шаровой полнопроходной 1/2\" ВР/ВР", "Stout SVB-0002-000015", 677, T,
     "valve", "ВР1/2", "ВР1/2", 0.058, t="1/2", handle="butterfly")
part("КранФС", "Кран шаровой с фильтром и накидной гайкой для счётчика 1/2\" ВР × 3/4\" гайка", "—", 950, A,
     "valve_filter", "ВР1/2", "Г3/4", 0.080, t="1/2", t2="3/4", handle="butterfly")
part("Счётчик15", "Счётчик холодной воды универсальный Ду15, L 110, 3/4\" НР (гориз./верт.)", "—", 1300, A,
     "meter", "НР3/4", "НР3/4", 0.110, t="3/4")
part("ПрисСч", "Присоединитель счётчика: гайка 3/4\" + штуцер 1/2\" НР + прокладка", "—", 90, A,
     "meter_conn", "Г3/4", "НР1/2", 0.034, t="3/4", t2="1/2")
part("Обр1/2", "Клапан обратный пружинный 1/2\" ВР/ВР, латунное седло", "Stout SVC-0011-000015", 1253, T,
     "check", "ВР1/2", "ВР1/2", 0.052, t="1/2")
part("Нип1/2", "Ниппель НН 1/2\" никелированный", "Stout SFT-0004-001212", 109, T, "nipple", "НР1/2", "НР1/2", 0.036, t="1/2")
part("Ред1/2", "Редуктор давления 1/2\" ВР/ВР с выходом под манометр", "Stout SVS-1010-000015", 2552, T,
     "reducer", "ВР1/2", "ВР1/2", 0.078, t="1/2", extra=["Ман10"])
part("Ман10", "Манометр аксиальный Dn50, 1/4\", 0–10 бар (на редуктор)", "Stout SIM-1009-501008", 339, T, "aux", "", "", 0)
part("КомПНД32×1", "Муфта компрессионная ПНД 32 × 1\" НР (латунь)", "Stout SFH-0002-000321", 1100, T,
     "pe_compr", "pe32", "НР1", 0.075, t="1")
part("Фильтр1", "Фильтр сетчатый косой 1\" ВР/ВР, 500 мкм", "Stout SFW-0001-000025", 1684, T,
     "filter", "ВР1", "ВР1", 0.090, t="1")
part("Предохр6", "Клапан предохранительный 6 бар, вход 1/2\" НР, сброс 3/4\" ВР вниз", "Stout SVS-0030-006015", 1374, T,
     "safety", "НР1/2", "end", 0.055, t="1/2", extra=["Воронка", "Шланг16", "Ёлочка"])
part("КрБак3/4", "Кронштейн настенный для расширительного бака 3/4\" (НР × ВР под бак, пластина с 2 дюбелями) — бак вкручивается в кронштейн",
     "—", 450, A, "tank_bracket", "НР3/4", "ВР3/4", 0.050, t="3/4")
part("ГрБез6", "Группа безопасности бойлера: клапан предохранительный 6 бар, воздухоотводчик автоматический, манометр 0–10 бар, "
     "вход 1/2\" ВР", "—", 2900, A, "safety_group", "ВР1/2", "end", 0.105, t="1/2", extra=["Воронка", "Шланг16", "Ёлочка"])
part("Воронка", "Воронка сливная с разрывом струи 3/4\"", "—", 450, A, "aux", "", "", 0)
part("Шланг16", "Шланг ПВХ армированный 16 мм от воронки в трап, 1,2 м", "—", 120, A, "aux", "", "", 0)
part("Ёлочка", "Штуцер-ёлочка 3/4\" НР × 16 с хомутом", "—", 150, A, "aux", "", "", 0)
part("Слив1/2", "Кран сливной 1/2\" НР со штуцером под шланг", "—", 350, A, "drain", "НР1/2", "end", 0.060, t="1/2")
part("НасосРЦ", "Насос рециркуляции ГВС, латунный корпус, 1\" НР, L 130", "Aquario AC 154-130HW, арт. 5154", 7489, AQ,
     "pump", "НР1", "НР1", 0.130, t="1")
part("ШтНас", "Штуцер насоса: гайка 1\" + хвостовик 1/2\" НР + прокладка", "из комплекта насоса", 0, IN,
     "pump_conn", "Г1", "НР1/2", 0.040, t="1", t2="1/2")
# трубы и мелочь
part("ТрубаGF20", "Труба PPR/GF/PPR 20×2,8 PN20 (армированная стекловолокном)", "RTP 10327", 78.95, R, "pipe", "", "", 0)
part("ТрубаGF25", "Труба PPR/GF/PPR 25×3,5 PN20 (армированная стекловолокном)", "RTP 10329", 116.77, R, "pipe", "", "", 0)
part("ТрубаGF32", "Труба PPR/GF/PPR 32×4,4 PN20 (армированная стекловолокном)", "RTP 10331", 184.89, R, "pipe", "", "", 0)
part("ТрубаPN20", "Труба PPR 20×3,4 PN20 (холодная вода)", "RTP 10301", 74.02, R, "pipe", "", "", 0)
part("ТрубаPN25", "Труба PPR 25×4,2 PN20 (холодная вода)", "RTP 10304", 126.88, R, "pipe", "", "", 0)
part("Хомут20", "Хомут металлический с резинкой 1/2\" (20–25) + шпилька + дюбель", "RTP 29189", 42.75, R, "clamp", "", "", 0)
part("Хомут25", "Комплект хомут + шпилька + дюбель 3/4\" (25–29)", "Stout SAC-0020-100034", 68, T, "clamp", "", "", 0)
part("Хомут32", "Комплект хомут + шпилька + дюбель 1\" (32–37)", "Stout SAC-0020-100001", 73, T, "clamp", "", "", 0)
part("Гильза", "Гильза из трубы ПП Ø40–50, L 0,25 м (проход через стену)", "—", 60, A, "sleeve", "", "", 0)
part("Изол20", "Теплоизоляция для трубы 20, толщина 9 мм", "Energoflex Super 22/9", 60, A, "insul", "", "", 0)
part("Изол25", "Теплоизоляция для трубы 25, толщина 9 мм", "Energoflex Super 28/9", 75, A, "insul", "", "", 0)
# цветная изоляция на все трубы котельной: красная — подающие и горячие, синяя — обратные и холодная вода
for d, dd in ((20, 22), (25, 28), (32, 35)):
    for c, cn in (("К", "красная"), ("С", "синяя")):
        part(f"Изол{c}{d}", f"Теплоизоляция в цветной оболочке для трубы {d}, 6 мм, {cn} (трубки по 2 м)",
             f"Energoflex Super Protect {dd}/6 {cn}", {20: 55, 25: 65, 32: 80}[d], A, "insul", "", "", 0)
for t, pr in (("1/2", 6), ("3/4", 8), ("1", 12)):
    part(f"Пркл{t}", f"Прокладка паронитовая {t}\" под накидную гайку (запасная)", "—", pr, A, "aux", "", "", 0)

PIPE_KEY = {("gf", 20): "ТрубаGF20", ("gf", 25): "ТрубаGF25", ("gf", 32): "ТрубаGF32", ("pn20", 20): "ТрубаGF20",
            ("pn20", 25): "ТрубаPN25"}          # короткие вставки Ø20 на вводе — из остатка армированной 20
CLAMP_KEY = {20: "Хомут20", 25: "Хомут25", 32: "Хомут32"}
SYS_NAME = {"Т1": "подача отопления", "Т2": "обратка отопления", "Т11": "подача ТП", "Т21": "обратка ТП",
            "Т3": "ГВС", "Т4": "рециркуляция ГВС", "В1": "холодная вода", "ЗП": "загрузка бойлера, подача",
            "ЗО": "загрузка бойлера, обратка"}


# ------------------------------------------------------------------ сборщик цепочек
def _add(a, b, k=1.0):
    return tuple(a[i] + b[i] * k for i in range(3))


def _sub(a, b):
    return tuple(a[i] - b[i] for i in range(3))


def _dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def _len(a):
    return math.sqrt(_dot(a, a))


def _kind(end):
    for p in ("НР", "ВР", "Г"):
        if end.startswith(p):
            return p, end[len(p):]
    return end[:1], end[1:] if end[:1] in "sp" else end


def compatible(open_end, new_end):
    """Можно ли соединить открытый конец цепочки с концом новой детали."""
    ko, so = _kind(open_end)
    kn, sn = _kind(new_end)
    if ko in ("НР",) and kn in ("ВР", "Г"):
        return so == sn
    if ko in ("ВР", "Г") and kn == "НР":
        return so == sn
    if ko == "p" and kn == "s" or ko == "s" and kn == "p":
        return so == sn
    if open_end == new_end == "pe32":
        return True
    return False


class ChainError(Exception):
    pass


NODES = OrderedDict()     # имя узла → список цепочек


class Chain:
    def __init__(self, node, title, start, d, open_end, sys, pipe="gf", port=""):
        self.node, self.title, self.sys, self.pipe = node, title, sys, pipe
        self.pos, self.d, self.open = tuple(start), tuple(d), open_end
        self.items = []           # по порядку: детали, трубы, угольники, тройники
        self.port0 = port
        NODES.setdefault(node, []).append(self)

    # --- служебное
    def _dia(self):
        k, s = _kind(self.open)
        if k not in ("s", "p"):
            raise ChainError(f"{self.title}: труба после резьбы {self.open} — нужен переход (МкНр/МкВр/американка)")
        return int(s)

    def _pipe(self, to, note=""):
        L = _len(_sub(to, self.pos))
        if L < 1e-6:
            return
        v = _sub(to, self.pos)
        if _dot(v, self.d) < 0.999 * L:
            along = _dot(v, self.d)
            if along < 0 and abs(along) > 0.999 * L:
                raise ChainError(f"{self.title}: не хватает места — детали уже заходят на {L * 1000:.0f} мм дальше этой "
                                 "точки. Отодвиньте точку по ходу трубы или уберите деталь")
            raise ChainError(f"{self.title}: точка не на оси трубы — труба идёт по направлению {tuple(self.d)}, "
                             "а точка смещена вбок. Поправьте координаты или добавьте поворот")
        d = self._dia()
        if L < STUB - 1e-6:
            raise ChainError(f"{self.title}: отрезок трубы {L * 1000:.0f} мм — короче {STUB * 1000:.0f} мм, не вварить. "
                             f"Отодвиньте точку на {(STUB - L) * 1000 + 1:.0f} мм")
        self.items.append(dict(t="pipe", a=self.pos, b=to, d=d, sys=self.sys, pipe=self.pipe, L=L, note=note))
        self.pos, self.open = to, f"p{d}"

    def _place(self, key):
        p = PARTS[key]
        a, b = p["a"], p["b"]
        flip = False
        if not compatible(self.open, a):
            if b != "end" and compatible(self.open, b):
                flip, a, b = True, b, a
            elif self.open.startswith("s") and a.startswith("s") and self.open[1:] == a[1:] or \
                    self.open.startswith("s") and b.startswith("s") and self.open[1:] == b[1:]:
                self._pipe(_add(self.pos, self.d, STUB), "отрезок")
                return self._place(key)
            else:
                raise ChainError(f"{self.title}: {self.open} не стыкуется с «{p['name']}» ({p['a']}/{p['b']}) — "
                                 "не хватает перехода")
        self.items.append(dict(t="part", key=key, s=self.pos, d=self.d, L=p["L"], flip=flip, sys=self.sys,
                               joint=(self.open, a)))
        self.pos, self.open = _add(self.pos, self.d, p["L"]), b

    # --- то, чем описываются узлы
    def add(self, *keys):
        for k in keys:
            self._place(k)
        return self

    def to(self, c, then=None):
        """Труба до точки c (на оси). then — новое направление: в точке c ставится угольник."""
        if then is None:
            self._pipe(c)
            return self
        d = self._dia()
        fe = FACE[d]
        if not self.open.startswith("p"):
            self._pipe(_sub(c, tuple(x * fe for x in self.d)))
        else:
            self._pipe(_sub(c, tuple(x * fe for x in self.d)))
        self.items.append(dict(t="part", key=f"Уг{d}", c=c, d=self.d, d2=tuple(then), sys=self.sys, L=0,
                               joint=(self.open, f"s{d}")))
        self.d, self.pos, self.open = tuple(then), _add(c, then, fe), f"s{d}"
        return self

    def tee(self, c, branch, key=None, main=None, title="", sys=None, pipe=None):
        """Тройник в точке c: основная линия идёт дальше (или поворачивает в main), ответвление — в branch."""
        d = self._dia()
        key = key or f"Тр{d}"
        db = PARTS[key].get("db", d)
        fe = FACE_T[d]
        self._pipe(_sub(c, tuple(x * fe for x in self.d)))
        self.items.append(dict(t="part", key=key, c=c, d=self.d, d2=tuple(branch), dm=tuple(main or self.d),
                               sys=self.sys, L=0, joint=(self.open, f"s{d}")))
        if main:
            self.d = tuple(main)
        self.pos, self.open = _add(c, self.d, fe), f"s{d}"
        br = Chain(self.node, title or f"{self.title} — ответвление", _add(c, branch, FACE_T[db]), branch, f"s{db}",
                   sys or self.sys, pipe or self.pipe)
        return br

    def finish(self, port_pt, port_end, keys=(), wall=False, note=""):
        """Довести цепочку до патрубка оборудования port_pt: труба, затем детали keys вплотную к патрубку."""
        Ls = sum(PARTS[k]["L"] for k in keys)
        stop = _add(port_pt, self.d, -Ls)
        if keys:
            first = PARTS[keys[0]]
            if self.open.startswith("s") and (first["a"].startswith("s") or first["b"].startswith("s")):
                # раструб к раструбу через трубу
                if _len(_sub(stop, self.pos)) < STUB:
                    raise ChainError(f"{self.title}: не хватает места до патрубка ({_len(_sub(stop, self.pos)) * 1000:.0f} мм)")
            if _dot(_sub(stop, self.pos), self.d) < -1e-6:
                raise ChainError(f"{self.title}: детали не помещаются до патрубка, перенесите поворот")
            self._pipe(stop)
            self.add(*keys)
        else:
            self._pipe(port_pt)
        if port_end and not compatible(self.open, port_end):
            raise ChainError(f"{self.title}: конец {self.open} не подходит к патрубку {port_end}")
        self.port1 = port_end
        self.wall_out = wall
        self.note = note
        return self


# ------------------------------------------------------------------ узлы котельной (вариант PPR)
def seed_ppr():
    """Исходное описание узлов в коде — из него один раз создан котельная_проект.json."""
    NODES.clear()
    dn = (0, 0, -1)
    up = (0, 0, 1)
    E, W_, N, S = (1, 0, 0), (-1, 0, 0), (0, -1, 0), (0, 1, 0)

    # 1. Котёл: подача Т1 → гидрострелка
    c = Chain("1. Котёл → гидрострелка (Т1/Т2) и бак WRV", "Т1 подача котла", (BXP, OUTS["sup"], PORT_Z), dn,
              "НР3/4", "Т1", "gf", port="котёл 3/4\" НР")
    c.add("КранГ3/4", "МкНр32×3/4").to((BXP, OUTS["sup"], 0.84), N).to((BXP, YP, 0.84), E).to((0.96, YP, 0.84), up)
    c.to((0.96, YP, HP_IN), E).finish((HX - HR - 0.03, YP, HP_IN), "ВР1", ["Ам32×1"])
    # обратка Т2: гидрострелка → фильтр → тройник на бак → котёл
    c = Chain("1. Котёл → гидрострелка (Т1/Т2) и бак WRV", "Т2 обратка котла", (HX - HR - 0.03, YP, HP_OUT), W_,
              "ВР1", "Т2", "gf", port="гидрострелка 1\" ВР")
    c.add("Ам32×1").to((1.00, YP, HP_OUT)).add("Ам32×1", "Фильтр1", "Ам32×1")
    c.to((0.66, YP, HP_OUT), S).to((0.66, OUTS["ret"], HP_OUT), W_).to((BXP, OUTS["ret"], HP_OUT), up)
    br = c.tee((BXP, OUTS["ret"], 0.82), S, key="Тр32×20", title="Подключение бака WRV 8")
    c.finish((BXP, OUTS["ret"], PORT_Z), "НР3/4", ["МкНр32×3/4", "КранГ3/4"])
    br.to((BXP, EY, 0.82), up).finish((EX, EY, EZ0 - 0.012), "НР3/4", ["МкНр20×3/4", "КранГ3/4"])

    # 2. Загрузка бойлера (от трёхходового клапана котла)
    n2 = "2. Загрузка бойлера от котла"
    c = Chain(n2, "Подача на змеевик", (BXP, OUTS["dsup"], PORT_Z), dn, "НР3/4", "ЗП", "gf", port="котёл 3/4\" НР")
    c.add("КранГ3/4", "МкНр25×3/4").to((BXP, OUTS["dsup"], 0.84), W_).to((0.465, OUTS["dsup"], 0.84), dn)
    c.to((0.465, OUTS["dsup"], 0.26), S).to((0.465, 2.175, 0.26), E).to((1.27, 2.175, 0.26), N)
    c.to((1.27, 1.84, 0.26), up).to((1.27, 1.84, 0.84), E)
    c.finish((tank_x(1.84) - 0.035, 1.84, 0.84), "НР1", ["МкНр25×1", "КранГ1"])
    c = Chain(n2, "Обратка со змеевика", (tank_x(1.98) - 0.035, 1.98, 0.36), W_, "НР1", "ЗО", "gf",
              port="змеевик 1\" НР")
    c.add("КранГ1", "МкНр25×1").to((1.22, 1.98, 0.36), S).to((1.22, 2.175, 0.36), W_)
    c.to((0.465, 2.175, 0.36), N).to((0.465, OUTS["dret"], 0.36), up).to((0.465, OUTS["dret"], 0.84), E)
    c.to((BXP, OUTS["dret"], 0.84), up).finish((BXP, OUTS["dret"], PORT_Z), "НР3/4", ["МкНр25×3/4", "КранГ3/4"])

    # 3. Выходы насосных групп (краны с термометрами — в самих группах)
    n3 = "3. Выходы насосных групп в дом"
    for tag, (xs, xr), zs, zr, ss, sr in (("7.1", G_OUT["7.1"], 2.56, 2.64, "Т1", "Т2"),
                                          ("7.2", G_OUT["7.2"], 2.40, 2.48, "Т11", "Т21")):
        for x, zt, sy, nm in ((xs, zs, ss, "подача"), (xr, zr, sr, "обратка")):
            c = Chain(n3, f"Группа {tag} — {nm}", (x, YP, GZ1 + 0.03), up, "ВР1", sy, "gf", port="группа 1\" ВР")
            c.add("Ам32×1").to((x, YP, zt), E).finish((X1 + 0.03, YP, zt), "", wall=True, note="в дом")

    # 4. Ввод воды: ПНД из пола → кран → узел учёта → редуктор → разводка
    n4 = "4. Ввод воды и узел учёта"
    c = Chain(n4, "Ввод В1 (стояк узла учёта)", (0.66, YC, 0.20), up, "pe32", "В1", "pn20", port="ПНД 32 из скважины")
    c.add("КомПНД32×1", "Кран1ВН", "МкВр25×1").to((0.66, YC, 0.45)).add("Пер25×20")
    c.add("МкНр20×1/2", "КранФС", "Счётчик15", "ПрисСч", "Обр1/2", "Нип1/2", "Ред1/2", "Ам20×1/2", "Пер25×20")
    c.to((0.66, YC, ZC), E)
    br = c.tee((0.92, YC, ZC), up, title="В1 в дом")
    br.to((0.92, YC, 1.62)).add("КранPPR25").to((0.92, YC, 2.32), E).finish((X1 + 0.03, YC, 2.32), "", wall=True,
                                                                             note="в дом")
    br = c.tee((WXD, YC, ZC), N, title="Бак ГВС WDV 18")
    br.to((WXD, WYD, ZC), dn).finish((WXD, WYD, WZ1D + 0.02), "НР3/4", ["МкНр25×3/4", "КранГ3/4"])
    # 5. Холодная вода на бойлер с группой безопасности
    c.to((1.35, YC, ZC), dn).to((1.35, YC, 1.36)).add("КранPPR25")
    sv = c.tee((1.35, YC, 0.62), N, key="Тр25", title="Предохранительный клапан 6 бар")
    sv.to((1.35, YC - 0.07, 0.62)).add("МкВр25×1/2", "Предохр6")
    c.to((1.35, YC, 0.17), N)
    dr = c.tee((1.35, 1.95, 0.17), W_, title="Слив бойлера")
    dr.add("МкВр25×1/2", "Слив1/2")
    c.to((1.35, 1.76, 0.17), E).finish((tank_x(1.76) - 0.035, 1.76, 0.17), "НР3/4", ["Ам25×3/4"])
    for ch in NODES[n4]:
        pass

    # 6. ГВС и рециркуляция
    n6 = "5. ГВС и рециркуляция"
    c = Chain(n6, "Т3 горячая вода в дом", (TX, TY, TH + 0.04), up, "НР3/4", "Т3", "gf", port="бойлер ГВС 3/4\" НР")
    c.add("КранГ3/4", "МкНр25×3/4").to((TX, TY, 2.22), E).finish((X1 + 0.03, TY, 2.22), "", wall=True, note="в дом")
    rx, ry = 1.85, 1.45
    c = Chain(n6, "Т4 рециркуляция из дома", (X1 + 0.03, 1.78, 2.14), W_, "p20", "Т4", "gf", port="из дома")
    c.wall_in = True
    c.to((rx, 1.78, 2.14), N).to((rx, ry, 2.14), dn).to((rx, ry, 1.97))
    c.add("МкНр20×1/2", "Кран1/2ВВ", "ШтНас", "НасосРЦ", "ШтНас", "Обр1/2", "Нип1/2", "Кран1/2ВВ", "МкНр20×1/2")
    c.to((rx, ry, 1.00), S).finish((rx, tank_y(rx) - 0.035, 1.00), "НР3/4", ["Ам20×3/4"])
    return NODES


def build_ppr():
    """Узлы котельной: из файла проекта (его правят в Мастерской), а если файла нет — из кода."""
    import proekt
    if os.path.exists(proekt.FILE):
        global LAST_ERRORS
        LAST_ERRORS = proekt.build_file()
        return NODES
    return seed_ppr()


LAST_ERRORS = []


# ------------------------------------------------------------------ подсчёт: смета, хомуты, гильзы, резьбы
def _wall_dist(p, d):
    """Ближайшая стена, вдоль которой может идти труба (перпендикулярно направлению трубы)."""
    c = []
    if abs(d[0]) < 0.5:
        c += [(p[0] - X0, (-1, 0)), (X1 - p[0], (1, 0))]
    if abs(d[1]) < 0.5:
        c += [(p[1] - Y0, (0, -1)), (Y1 - p[1], (0, 1))]
    c = [t for t in c if t[0] > 0]
    return min(c, key=lambda t: t[0]) if c else (9, (0, 0))


def analyse(nodes=None):
    nodes = nodes or NODES
    bom = Counter()
    pipes = defaultdict(float)
    clamps, sleeves, insul = [], [], defaultdict(float)
    joints = Counter()           # резьбовые на льне по размеру
    nuts = Counter()             # соединения накидной гайкой → прокладка
    per_node = OrderedDict()
    for node, chains in nodes.items():
        nb = Counter()
        for ch in chains:
            for it in ch.items:
                if it["t"] == "pipe":
                    L = it["L"] + 2 * SOCKET[it["d"]]
                    key = PIPE_KEY[(it["pipe"], it["d"])]
                    pipes[key] += L
                    nb[key] += L
                    insul[f"Изол{'К' if it['sys'] in HOT else 'С'}{it['d']}"] += it["L"]
                    # хомуты: вдоль стены (≤ 0,30 м), шаг по таблице, не ближе 8 см к концам
                    d = tuple((it["b"][i] - it["a"][i]) / it["L"] for i in range(3))
                    step = STEP[(it["pipe"], it["d"])]
                    n = int((it["L"] - 0.16) / step) + 1 if it["L"] > 0.30 else 0
                    for k in range(n):
                        u = 0.08 + (it["L"] - 0.16) * ((k + 0.5) / n)
                        p = _add(it["a"], d, u)
                        dist, nw = _wall_dist(p, d)
                        if dist <= 0.17 and p[2] > 0.1:
                            clamps.append(dict(p=p, d=d, r=it["d"] / 2000, wall=(dist, nw), node=node))
                            bom[CLAMP_KEY[it["d"]]] += 1
                            nb[CLAMP_KEY[it["d"]]] += 1
                    # проход через стену
                    for lim, ax in ((X1, 0),):
                        if (it["a"][ax] - lim) * (it["b"][ax] - lim) < 0:
                            sleeves.append(dict(p=tuple(lim if i == ax else it["a"][i] for i in range(3)),
                                                d=d, r=it["d"] / 2000))
                            bom["Гильза"] += 1
                            nb["Гильза"] += 1
                else:
                    k = it["key"]
                    bom[k] += 1
                    nb[k] += 1
                    for e in PARTS[k].get("extra", []):
                        bom[e] += 1
                        nb[e] += 1
                    o, a = it["joint"]
                    ko, so = _kind(o)
                    ka, sa = _kind(a)
                    if {ko, ka} == {"НР", "ВР"}:
                        joints[so] += 1
                    elif "Г" in (ko, ka):
                        nuts[so] += 1
            if getattr(ch, "port0", "") and _kind(ch.open)[0] in ("НР", "ВР", "Г") or True:
                pass
        # стыки с оборудованием (первый и последний)
        for ch in chains:
            for end, port in ((None, None),):
                pass
        per_node[node] = nb
    # стыки цепочек с патрубками оборудования
    for node, chains in nodes.items():
        for ch in chains:
            first = next((i for i in ch.items if i["t"] == "part"), None)
            for o in [getattr(ch, "port1", "")]:
                last = ch.open
                ko, so = _kind(last)
                ka, sa = _kind(o or "")
                if {ko, ka} == {"НР", "ВР"}:
                    joints[so] += 1
                elif "Г" in (ko, ka):
                    nuts[so] += 1
    # трубы: + запас 10 % и до целых палок по 4 м; муфты на стыках палок
    for key, L in pipes.items():
        need = L * 1.10
        sticks = math.ceil(need / 4.0)
        bom[key] = sticks * 4
        d = int(key[-2:])
        bom[f"Мфт{d}"] += max(0, sticks - 1)
    for k, L in insul.items():
        bom[k] = math.ceil(L * 1.1 / 2) * 2
    for t, n in nuts.items():
        bom[f"Пркл{t}"] += n
    flax_g = sum(n * {"1/2": 1.0, "3/4": 1.5, "1": 2.0, "1 1/4": 2.5}.get(t, 1.5) for t, n in joints.items())
    return dict(bom=bom, pipes=dict(pipes), clamps=clamps, sleeves=sleeves, joints=joints, nuts=nuts,
                flax_g=flax_g, per_node=per_node, insul=dict(insul))


def placed(nodes=None):
    """Плоский список для 3D: детали с координатами и трубы."""
    out = []
    for node, chains in (nodes or NODES).items():
        for ch in chains:
            for it in ch.items:
                out.append(dict(it, node=node, chain=ch.title))
    return out


if __name__ == "__main__":
    build_ppr()
    print("Ошибки проекта:", LAST_ERRORS)
    r = analyse()
    for node, chains in NODES.items():
        print(f"\n== {node}")
        for ch in chains:
            seq = []
            for it in ch.items:
                if it["t"] == "pipe":
                    seq.append(f"труба {it['d']} {it['L'] * 1000:.0f}")
                else:
                    seq.append(it["key"])
            print(f"  {ch.title}: {ch.port0 or ''} → " + " → ".join(seq) + f" → {getattr(ch, 'port1', '') or 'в дом'}")
    print("\nТрубы, м:", {k: round(v, 2) for k, v in r["pipes"].items()})
    print("Резьбы на льне:", dict(r["joints"]), f"→ лён ≈ {r['flax_g']:.0f} г")
    print("Накидные гайки:", dict(r["nuts"]))
    print("Хомутов:", len(r["clamps"]), "Гильз:", len(r["sleeves"]))
    for k, v in sorted(r["bom"].items(), key=lambda t: list(PARTS).index(t[0])):
        print(f"  {PARTS[k]['name']:<75} {v}")
