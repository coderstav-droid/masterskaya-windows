"""Коммерческая смета монтажа ОВ/ВК: материалы (из спецификации) + работы (по прайсу) + накладные пункты.

Запуск:  python3 smeta.py input.json [выход_без_расширения]
Пишет <выход>.md и <выход>.csv; если установлен openpyxl — ещё <выход>.xlsx
(без него: uv run --with openpyxl python3 smeta.py ...).

Формат input.json:
{
  "object": "Жилой дом 120 м², Михайловск",
  "customer": "ООО ...",                       # необязательно
  "date": "01.11.2026",
  "region_k": 0.8,                             # коэффициент к прайсу работ (Москва = 1,0)
  "complexity_k": 1.0,                         # 1,1–1,3: высота, стеснённость, сталь на сварке, зима
  "price_file": "../references/smeta_raboty_2026.json",   # необязательно
  "materials": [ {"name": "Котёл Navien NGB210-20H SYS", "art": "...", "unit": "шт", "qty": 1, "price": 52000,
                  "src": "Терем 10.2026", "group": "1. Котёл"} ],   # group — узел комплектовки (подзаголовок)
  "materials_markup": 0.0,                     # наценка на материалы подрядчика, доля (0,1 = 10 %)
  "works": [ {"code": "K-01", "qty": 1}, {"code": "O-01", "qty": 7},
             {"name": "Своя работа", "unit": "шт", "qty": 1, "price": 3000} ],
  "extra": [ {"name": "Расходные материалы (крепёж, герметики, ~3 % от материалов)", "pct_materials": 0.03},
             {"name": "Транспортные расходы", "sum": 5000} ],
  "notes": ["Не входит: ...", "..."],         # необязательно — примечания в конце сметы
  "vat": false,                                # ИП на ПСН — без НДС
  "advance_pct": 50                            # аванс, % — в текст условий
}
Правила (практика):
- Материалы — только из спецификации с источником цены; «уточнить» — если цены нет.
- Работы — коды из прайса; если работы нет в прайсе — строка со своим name/price.
- Цены материалов и работ — на дату; в смете пометка «действительна 14 дней».
"""
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def rub(x):
    return f"{x:,.0f}".replace(",", " ")


def build(inp):
    pf = inp.get("price_file") or os.path.join(HERE, "..", "references", "smeta_raboty_2026.json")
    if not os.path.isabs(pf):
        pf = os.path.normpath(os.path.join(HERE, pf)) if not os.path.exists(pf) else pf
    prices = json.load(open(pf, encoding="utf-8"))["items"]
    rk = float(inp.get("region_k", 1.0)) * float(inp.get("complexity_k", 1.0))
    mk = 1.0 + float(inp.get("materials_markup", 0.0))

    mats, works, warn = [], [], []
    for m in inp.get("materials", []):
        price = m.get("price")
        if price in (None, ""):
            warn.append(f"Нет цены: {m['name']} — уточнить у поставщика")
            price = 0
        p = round(float(price) * mk, 2)
        mats.append(dict(name=m["name"], art=m.get("art", ""), unit=m.get("unit", "шт"), qty=m["qty"], price=p,
                         sum=round(p * float(m["qty"]), 2), src=m.get("src", ""), group=m.get("group", "")))
    for w in inp.get("works", []):
        if "code" in w:
            if w["code"] not in prices:
                warn.append(f"Нет кода работы {w['code']} в прайсе")
                continue
            name, unit, base = prices[w["code"]]
            code = w["code"]
        else:
            name, unit, base, code = w["name"], w.get("unit", "шт"), w["price"], "—"
        p = round(float(base) * (rk if "code" in w else 1.0), -1)
        works.append(dict(code=code, name=w.get("note") and f"{name} ({w['note']})" or name, unit=unit, qty=w["qty"],
                          price=p, sum=round(p * float(w["qty"]), 2)))
    sm = sum(m["sum"] for m in mats)
    sw = sum(w["sum"] for w in works)
    extra = []
    for e in inp.get("extra", []):
        s = e["sum"] if "sum" in e else sm * float(e.get("pct_materials", 0)) + sw * float(e.get("pct_works", 0))
        extra.append(dict(name=e["name"], sum=round(s, 2)))
    se = sum(e["sum"] for e in extra)
    total = sm + sw + se
    vat = round(total * 0.2 / 1.0, 2) if inp.get("vat") else 0.0
    return dict(mats=mats, works=works, extra=extra, sm=sm, sw=sw, se=se, total=total, vat=vat,
                grand=total + vat, warn=warn, rk=rk)


def to_md(inp, r):
    L = [f"# Смета на монтаж — {inp.get('object', '')}", ""]
    if inp.get("customer"):
        L.append(f"Заказчик: {inp['customer']}  ")
    L += [f"Дата: {inp.get('date', '')}. Цены действительны 14 дней. Коэффициент к прайсу работ: {r['rk']:.2f}.", ""]
    L += ["## 1. Материалы и оборудование", "", "| № | Наименование | Артикул | Ед. | Кол. | Цена, ₽ | Сумма, ₽ | Источник цены |",
          "|---|---|---|---|---|---|---|---|"]
    grp = None
    for i, m in enumerate(r["mats"], 1):
        if m["group"] and m["group"] != grp:
            grp = m["group"]
            gs = sum(x["sum"] for x in r["mats"] if x["group"] == grp)
            L.append(f"| | **{grp}** | | | | | *{rub(gs)}* | |")
        L.append(f"| {i} | {m['name']} | {m['art']} | {m['unit']} | {m['qty']} | {rub(m['price'])} | {rub(m['sum'])} | {m['src']} |")
    L += [f"| | **Итого материалы** | | | | | **{rub(r['sm'])}** | |", "", "## 2. Работы", "",
          "| № | Код | Наименование работ | Ед. | Кол. | Цена, ₽ | Сумма, ₽ |", "|---|---|---|---|---|---|---|"]
    for i, w in enumerate(r["works"], 1):
        L.append(f"| {i} | {w['code']} | {w['name']} | {w['unit']} | {w['qty']} | {rub(w['price'])} | {rub(w['sum'])} |")
    L += [f"| | | **Итого работы** | | | | **{rub(r['sw'])}** |", ""]
    if r["extra"]:
        L += ["## 3. Прочие затраты", ""] + [f"- {e['name']}: {rub(e['sum'])} ₽" for e in r["extra"]] + [""]
    L += ["## Итого", "", f"- Материалы и оборудование: {rub(r['sm'])} ₽", f"- Работы: {rub(r['sw'])} ₽"]
    if r["extra"]:
        L.append(f"- Прочие затраты: {rub(r['se'])} ₽")
    if inp.get("vat"):
        L += [f"- НДС 20 %: {rub(r['vat'])} ₽"]
    L += [f"- **ВСЕГО: {rub(r['grand'])} ₽**" + ("" if inp.get("vat") else " (без НДС)"), ""]
    L += ["Условия: " + (f"аванс {inp.get('advance_pct', 50)} % до начала работ, " if inp.get("advance_pct", 50) else "")
          + "окончательный расчёт по акту выполненных работ. Объёмы уточняются по факту; материалы заказчика — "
          "без гарантии на материал."]
    if inp.get("notes"):
        L += ["", "Примечания:"] + [f"- {n}" for n in inp["notes"]]
    if r["warn"]:
        L += ["", "Замечания:"] + [f"- {w}" for w in r["warn"]]
    return "\n".join(L) + "\n"


def to_csv(path, r):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Раздел", "Код/артикул", "Наименование", "Ед.", "Кол.", "Цена", "Сумма"])
        for m in r["mats"]:
            w.writerow([m["group"] or "Материалы", m["art"], m["name"], m["unit"], m["qty"], m["price"], m["sum"]])
        for x in r["works"]:
            w.writerow(["Работы", x["code"], x["name"], x["unit"], x["qty"], x["price"], x["sum"]])
        for e in r["extra"]:
            w.writerow(["Прочее", "", e["name"], "", "", "", e["sum"]])
        w.writerow(["ИТОГО", "", "", "", "", "", r["grand"]])


def to_xlsx(path, inp, r):
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    except ImportError:
        return False
    wb = Workbook()
    ws = wb.active
    ws.title = "Смета"
    thin = Side(style="thin", color="999999")
    B = Border(left=thin, right=thin, top=thin, bottom=thin)
    head = PatternFill("solid", fgColor="E8EEF6")
    ws.append([f"Смета на монтаж — {inp.get('object', '')}"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([f"Дата: {inp.get('date', '')}" + (f".  Заказчик: {inp['customer']}" if inp.get("customer") else "")])
    ws.append([])
    row0 = ws.max_row + 1

    def section(title, rows, cols):
        ws.append([title])
        ws.cell(ws.max_row, 1).font = Font(bold=True)
        ws.append(cols)
        for c in range(1, len(cols) + 1):
            cell = ws.cell(ws.max_row, c)
            cell.fill, cell.font, cell.border = head, Font(bold=True), B
        first = ws.max_row + 1
        for rr in rows:
            if isinstance(rr, str):          # подзаголовок узла
                ws.append(["", "", rr])
                ws.cell(ws.max_row, 3).font = Font(bold=True, italic=True)
                ws.cell(ws.max_row, 3).fill = PatternFill("solid", fgColor="F4F4F4")
                continue
            ws.append(rr)
            for c in range(1, len(cols) + 1):
                ws.cell(ws.max_row, c).border = B
            n = ws.max_row
            ws.cell(n, 7).value = f"=E{n}*F{n}"
        last = ws.max_row
        ws.append(["", "", "Итого", "", "", "", f"=SUM(G{first}:G{last})"])
        ws.cell(ws.max_row, 3).font = ws.cell(ws.max_row, 7).font = Font(bold=True)
        tot = ws.max_row
        ws.append([])
        return tot

    cols = ["№", "Артикул / код", "Наименование", "Ед.", "Кол.", "Цена, ₽", "Сумма, ₽", "Источник"]
    mrows, grp = [], None
    for i, m in enumerate(r["mats"], 1):
        if m["group"] and m["group"] != grp:
            grp = m["group"]
            mrows.append(grp)
        mrows.append([i, m["art"], m["name"], m["unit"], m["qty"], m["price"], None, m["src"]])
    t1 = section("1. Материалы и оборудование", mrows, cols)
    t2 = section("2. Работы", [[i, w["code"], w["name"], w["unit"], w["qty"], w["price"], None, ""]
                               for i, w in enumerate(r["works"], 1)], cols)
    refs = [f"G{t1}", f"G{t2}"]
    if r["extra"]:
        ws.append(["3. Прочие затраты"])
        ws.cell(ws.max_row, 1).font = Font(bold=True)
        for e in r["extra"]:
            ws.append(["", "", e["name"], "", "", "", e["sum"]])
            refs.append(f"G{ws.max_row}")
        ws.append([])
    ws.append(["", "", "ВСЕГО" + ("" if inp.get("vat") else " (без НДС)"), "", "", "", "=" + "+".join(refs)])
    tr = ws.max_row
    ws.cell(tr, 3).font = ws.cell(tr, 7).font = Font(bold=True, size=12)
    if inp.get("vat"):
        ws.append(["", "", "НДС 20 %", "", "", "", f"=G{tr}*0.2"])
        ws.append(["", "", "ВСЕГО с НДС", "", "", "", f"=G{tr}*1.2"])
    if inp.get("notes"):
        ws.append([])
        ws.append(["", "", "Примечания:"])
        ws.cell(ws.max_row, 3).font = Font(bold=True)
        for n in inp["notes"]:
            ws.append(["", "", "– " + n])
    for col_, w_ in zip("ABCDEFGH", [5, 18, 62, 6, 8, 12, 14, 22]):
        ws.column_dimensions[col_].width = w_
    for row in ws.iter_rows(min_row=row0):
        for c in row:
            if c.column in (6, 7):
                c.number_format = '# ##0'
            if c.column == 3:
                c.alignment = Alignment(wrap_text=True, vertical="top")
    wb.save(path)
    return True


def main():
    inp = json.load(open(sys.argv[1], encoding="utf-8"))
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(sys.argv[1])[0] + "_смета"
    r = build(inp)
    md = to_md(inp, r)
    open(out + ".md", "w", encoding="utf-8").write(md)
    to_csv(out + ".csv", r)
    x = to_xlsx(out + ".xlsx", inp, r)
    print(md)
    print(f"Файлы: {out}.md, {out}.csv" + (f", {out}.xlsx" if x else " (xlsx: нужен openpyxl)"))


if __name__ == "__main__":
    main()
