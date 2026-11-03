"""Русский графический интерфейс. Все операции выполняются вне потока Tk."""

from __future__ import annotations

from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from . import __version__
from .backend import DefenderBackend

BG = "#10171e"
CARD = "#1c2732"
FG = "#edf4fa"
MUTED = "#a8bac9"
GREEN = "#64dcaf"
RED = "#ff8c8c"


class DefenderApp(tk.Tk):
    def __init__(self, backend=None):
        super().__init__()
        self.backend = backend or DefenderBackend()
        self.events = queue.Queue()
        self.busy = False
        self.controls = []
        self.log_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "DefenderPilot" / "logs"
        self.logger = logging.getLogger("defenderpilot")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        self.log_error = None
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(self.log_dir / "defenderpilot.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
            self.logger.addHandler(handler)
        except OSError as exc:
            self.log_error = str(exc)
        self.title(f"DefenderPilot {__version__}")
        self.geometry("1000x740")
        self.minsize(840, 660)
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self._build()
        if self.log_error:
            self.log("Файловый журнал недоступен: " + self.log_error)
        self.log("DefenderPilot запущен. Действия выполняются только по нажатию кнопок.")
        self.after(100, self.drain)
        self.after(200, lambda: self.run("status"))
        self.after(30000, self.poll)

    def label(self, parent, text="", **options):
        settings = {"text": text, "bg": BG, "fg": FG, "font": ("Segoe UI", 11), "anchor": "w", "justify": "left"}
        settings.update(options)
        return tk.Label(parent, **settings)

    def button(self, parent, title, command, accent=False):
        button = tk.Button(parent, text=title, command=command, bg=GREEN if accent else CARD,
                           fg=BG if accent else FG, activebackground="#91e7c6", activeforeground=BG,
                           font=("Segoe UI", 11, "bold"), relief="flat", bd=0, padx=16, pady=12,
                           cursor="hand2", anchor="w", disabledforeground="#778796")
        button.pack(fill="x", pady=(0, 9))
        self.controls.append(button)
        return button

    def _build(self):
        outer = tk.Frame(self, bg=BG, padx=28, pady=24)
        outer.pack(fill="both", expand=True)
        self.label(outer, "DefenderPilot", font=("Segoe UI", 26, "bold")).pack(anchor="w")
        self.label(outer, "Восстановление и управление Microsoft Defender", fg=MUTED).pack(anchor="w", pady=(3, 20))
        cards = tk.Frame(outer, bg=BG)
        cards.pack(fill="x", pady=(0, 18))
        self.status_vars = {}
        for col, (key, title) in enumerate((("realtime", "ЗАЩИТА"), ("antivirus", "АНТИВИРУС"), ("tamper", "ОТ ПОДДЕЛКИ"), ("service", "СЛУЖБА"))):
            cards.columnconfigure(col, weight=1, uniform="status")
            frame = tk.Frame(cards, bg=CARD, padx=15, pady=13)
            frame.grid(row=0, column=col, sticky="nsew", padx=(0, 8 if col < 3 else 0))
            self.label(frame, title, bg=CARD, fg=MUTED, font=("Segoe UI", 9, "bold")).pack(anchor="w")
            variable = tk.StringVar(value="Проверка…")
            widget = self.label(frame, textvariable=variable, bg=CARD, font=("Segoe UI", 13, "bold"))
            widget.pack(anchor="w", pady=(7, 0))
            self.status_vars[key] = (variable, widget)
        self.details = tk.StringVar(value="Получение сведений о Defender…")
        self.label(outer, textvariable=self.details, fg=MUTED, wraplength=900, font=("Segoe UI", 10)).pack(fill="x", pady=(0, 16))
        content = tk.Frame(outer, bg=BG)
        content.pack(fill="both", expand=True)
        left = tk.Frame(content, bg=BG, width=285)
        left.pack(side="left", fill="y", padx=(0, 20))
        self.button(left, "Включить защиту", lambda: self.request("enable"), accent=True)
        self.button(left, "Временно отключить", lambda: self.request("disable"))
        self.button(left, "Восстановить компоненты", lambda: self.request("repair"))
        self.button(left, "Обновить базы", lambda: self.request("update"))
        self.button(left, "Обновить состояние", lambda: self.run("status"))
        self.button(left, "Безопасность Windows ↗", self.open_security)
        self.label(left, "Отключается защита в реальном времени.\nWindows может включить её снова.\nДля изменений нужны права администратора.",
                   fg=MUTED, wraplength=285, font=("Segoe UI", 10)).pack(anchor="w", pady=(8, 0))
        right = tk.Frame(content, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        self.label(right, "Журнал операций", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 10))
        self.output = scrolledtext.ScrolledText(right, bg="#0b1117", fg="#cfdae3", insertbackground=FG,
                                               relief="flat", bd=0, font=("Consolas", 10), wrap="word", state="disabled")
        self.output.pack(fill="both", expand=True)
        utilities = tk.Frame(right, bg=BG)
        utilities.pack(fill="x", pady=(9, 0))
        tk.Button(utilities, text="Копировать журнал", command=self.copy_log, bg=CARD, fg=FG, bd=0, padx=10, pady=6).pack(side="left")
        tk.Button(utilities, text="Папка журналов", command=self.open_logs, bg=CARD, fg=FG, bd=0, padx=10, pady=6).pack(side="left", padx=8)
        self.activity = tk.StringVar(value="Готово")
        self.label(outer, textvariable=self.activity, fg=MUTED, wraplength=900, font=("Segoe UI", 10)).pack(fill="x", pady=(16, 7))
        self.progress = ttk.Progressbar(outer, mode="indeterminate")
        self.progress.pack(fill="x")

    def request(self, action):
        if self.busy:
            return
        prompts = {
            "enable": ("Включить защиту?", "Будут включены защита в реальном времени, поведенческий анализ, проверка загрузок и скриптов. Продолжить?"),
            "disable": ("Временно отключить защиту?", "Защита в реальном времени перестанет проверять открываемые файлы. Windows может автоматически включить её снова.\n\nОтключить?"),
            "repair": ("Восстановить компоненты?", "Будут запущены DISM и SFC, затем включение защиты. Проверка может занять более часа и использовать интернет. Дождитесь её окончания.\n\nПродолжить?"),
        }
        if action in prompts and not messagebox.askyesno(*prompts[action], parent=self):
            return
        self.run(action)

    def run(self, action):
        if self.busy:
            return
        self.busy = True
        for widget in self.controls:
            widget.configure(state="disabled")
        title = {"status": "Проверка состояния", "enable": "Включение защиты", "disable": "Временное отключение", "repair": "Восстановление компонентов", "update": "Обновление баз"}[action]
        self.activity.set(title + "…")
        self.progress.start(12)
        if action != "status":
            self.log(title)

        def worker():
            try:
                result = self.backend.run(action, lambda line: self.events.put(("log", line)))
                self.events.put(("result", (action, result)))
            except Exception as exc:
                self.events.put(("error", (action, str(exc))))

        threading.Thread(target=worker, daemon=True).start()

    def drain(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "log":
                    self.log(payload)
                elif kind == "result":
                    action, result = payload
                    self.render_status(result.get("status") or {})
                    message = result.get("message", "Ответ без описания результата.")
                    if action != "status" or not result.get("ok"):
                        self.log(message)
                    for warning in result.get("warnings") or []:
                        self.log("Замечание: " + str(warning))
                    if result.get("reboot_required"):
                        self.log("Windows сообщает о необходимости перезагрузки. Перезагрузите компьютер вручную.")
                    self.finish(message)
                    if action != "status":
                        dialog = messagebox.showinfo if result.get("ok") else messagebox.showwarning
                        dialog("DefenderPilot", message, parent=self)
                elif kind == "error":
                    action, error = payload
                    self.render_status({})
                    self.log("Ошибка: " + error)
                    self.finish("Операция не завершена. Проверьте журнал.")
                    if action != "status":
                        messagebox.showerror("DefenderPilot", error, parent=self)
        except queue.Empty:
            pass
        self.after(100, self.drain)

    def render_status(self, status):
        for key, (variable, widget) in self.status_vars.items():
            value = status.get(key)
            if key == "service":
                text = {"Running": "Работает", "Stopped": "Остановлена"}.get(value, value or "Неизвестно")
                color = GREEN if value == "Running" else MUTED if value is None else RED
            elif value is True:
                text, color = "Включена" if key != "antivirus" else "Включён", GREEN
            elif value is False:
                text, color = "Отключена" if key != "antivirus" else "Отключён", RED
            else:
                text, color = "Неизвестно", MUTED
            variable.set(text)
            widget.configure(fg=color)
        if status.get("available"):
            self.details.set(f"Базы: {status.get('signature') or '—'}   •   Обновлены: {status.get('signature_updated') or '—'}   •   Режим: {status.get('mode') or '—'}")
        else:
            self.details.set("Состояние Defender недоступно. " + str(status.get("error") or "Проверьте журнал и компоненты Windows."))

    def finish(self, message):
        self.busy = False
        self.progress.stop()
        self.progress["value"] = 0
        self.activity.set(message)
        for widget in self.controls:
            widget.configure(state="normal")

    def poll(self):
        if not self.busy:
            self.run("status")
        self.after(30000, self.poll)

    def log(self, text):
        line = f"[{datetime.now():%H:%M:%S}] {text}"
        self.logger.info(line)
        self.output.configure(state="normal")
        self.output.insert("end", line + "\n")
        # Окно не накапливает неограниченный вывод DISM.
        if int(self.output.index("end-1c").split(".")[0]) > 4000:
            self.output.delete("1.0", "1000.0")
        self.output.see("end")
        self.output.configure(state="disabled")

    def copy_log(self):
        self.clipboard_clear()
        self.clipboard_append(self.output.get("1.0", "end-1c"))

    def open_security(self):
        try:
            os.startfile("windowsdefender://threatsettings")
        except OSError as exc:
            messagebox.showerror("DefenderPilot", str(exc), parent=self)

    def open_logs(self):
        try:
            os.startfile(self.log_dir)
        except OSError as exc:
            messagebox.showerror("DefenderPilot", str(exc), parent=self)

    def close(self):
        if self.busy:
            messagebox.showinfo("DefenderPilot", "Дождитесь завершения текущей операции. Прерывать восстановление компонентов не следует.", parent=self)
            return
        for handler in list(self.logger.handlers):
            handler.close()
            self.logger.removeHandler(handler)
        self.destroy()


def launch():
    DefenderApp().mainloop()
