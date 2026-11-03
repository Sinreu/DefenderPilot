"""Точка входа приложения и запрос прав администратора."""

import ctypes
import os
import subprocess
import sys


def main():
    if os.name != "nt":
        print("DefenderPilot поддерживает только Windows 10/11.")
        return 1
    if not ctypes.windll.shell32.IsUserAnAdmin():
        args = sys.argv[1:] if getattr(sys, "frozen", False) else [os.path.abspath(__file__), *sys.argv[1:]]
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, subprocess.list2cmdline(args), None, 1
        )
        if result <= 32:
            ctypes.windll.user32.MessageBoxW(
                None, "Для управления Defender нужны права администратора. Запрос UAC отменён или завершился ошибкой.",
                "DefenderPilot", 0x10
            )
            return 1
        return 0
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    from defenderpilot.gui import launch
    launch()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
