"""Мастерская для Windows: запускает сервер и открывает её в браузере.

Мастерская.exe                 — сервер + окно браузера http://localhost:8800
Мастерская.exe скрипт.py ...   — служебный режим: выполнить скрипт проекта (так считается смета)
"""
import os
import runpy
import socket
import sys
import threading
import time
import webbrowser

BASE = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
URL = "http://localhost:8800/"

for st in (sys.stdout, sys.stderr):
    try:
        st.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".py"):
    script = os.path.abspath(sys.argv[1])
    sys.argv = sys.argv[1:]
    sys.path.insert(0, os.path.dirname(script))
    runpy.run_path(script, run_name="__main__")
    sys.exit(0)


def port_open():
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", 8800)) == 0


def open_when_ready():
    for _ in range(300):
        if port_open():
            break
        time.sleep(0.1)
    if not os.environ.get("MASTERSKAYA_NO_BROWSER"):
        webbrowser.open(URL)


if __name__ == "__main__":
    if os.name == "nt":
        os.system("title Мастерская — не закрывайте это окно, пока работаете")
    if port_open():
        print("Мастерская уже запущена — открываю браузер.")
        webbrowser.open(URL)
        time.sleep(2)
        sys.exit(0)
    app = os.path.join(BASE, "Мастерская")
    sys.path.insert(0, app)
    os.chdir(app)
    threading.Thread(target=open_when_ready, daemon=True).start()
    try:
        import server
        server.main()
    except Exception:
        import traceback
        traceback.print_exc()
        input("\nОшибка запуска. Нажмите Enter, чтобы закрыть окно.")
