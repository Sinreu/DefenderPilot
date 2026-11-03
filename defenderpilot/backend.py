"""Запуск фиксированного набора команд PowerShell; произвольных команд из UI нет."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import threading
from typing import Callable

MARKER = "DEFENDERPILOT_RESULT:"
ACTIONS = frozenset({"status", "enable", "disable", "repair", "update"})


class BackendError(RuntimeError):
    pass


def parse_result(output: str, returncode: int) -> dict:
    """Доверяем только финальному JSON; отсутствие ответа не считается успехом."""
    result = None
    for line in output.splitlines():
        if line.startswith(MARKER):
            try:
                result = json.loads(line[len(MARKER):])
            except json.JSONDecodeError as exc:
                raise BackendError("Повреждён ответ PowerShell.") from exc
    if not isinstance(result, dict) or type(result.get("ok")) is not bool:
        raise BackendError(f"PowerShell не вернул результат (код {returncode}). Проверьте журнал.")
    if returncode != 0:
        result["ok"] = False
        result.setdefault("message", f"PowerShell завершился с кодом {returncode}.")
    return result


def powershell_path() -> Path:
    root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    # 32-битный Python на 64-битной Windows должен вызывать 64-битный PowerShell.
    system_dir = "Sysnative" if os.environ.get("PROCESSOR_ARCHITEW6432") else "System32"
    return root / system_dir / "WindowsPowerShell" / "v1.0" / "powershell.exe"


class DefenderBackend:
    def run(self, action: str, emit: Callable[[str], None]) -> dict:
        if action not in ACTIONS:
            raise ValueError("Неизвестная операция.")
        if os.name != "nt":
            raise BackendError("Поддерживается только Windows 10/11.")
        script = Path(__file__).with_name("defender.ps1")
        command = [str(powershell_path()), "-NoLogo", "-NoProfile", "-NonInteractive",
                   "-ExecutionPolicy", "RemoteSigned", "-File", str(script), "-Action", action]
        # Восстановление не прерываем таймером: DISM/SFC могут работать долго.
        timeout = {"status": 90, "repair": None, "update": 900}.get(action, 240)
        proc = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        timed_out = threading.Event()

        def expire():
            timed_out.set()
            proc.kill()

        timer = None
        if timeout is not None:
            timer = threading.Timer(timeout, expire)
            timer.daemon = True
            timer.start()
        lines = []
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                lines.append(line)
                if line.strip() and not line.startswith(MARKER):
                    emit(line.rstrip())
            proc.wait()
        finally:
            if timer is not None:
                timer.cancel()
            proc.stdout.close()
        if timed_out.is_set():
            raise BackendError("Превышено время ожидания. Операция могла продолжиться в Windows; проверьте её состояние перед повтором.")
        return parse_result("".join(lines), proc.returncode)
