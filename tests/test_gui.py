"""Smoke-тесты с имитацией PowerShell. Защита на машине тестов не меняется."""

import os
import time
import unittest
from unittest.mock import patch


@unittest.skipUnless(os.environ.get('DEFENDERPILOT_GUI_TEST') == '1', 'Требуется графическая сессия Windows или Xvfb')
class GuiTests(unittest.TestCase):
    def setUp(self):
        from defenderpilot.gui import DefenderApp

        class FakeBackend:
            def __init__(self):
                self.actions = []

            def run(self, action, emit):
                self.actions.append(action)
                return {'ok': True, 'message': 'Проверено', 'status': {
                    'available': True, 'realtime': action != 'disable', 'antivirus': True,
                    'tamper': None, 'service': 'Running', 'signature': '1.2.3',
                }}

        self.backend = FakeBackend()
        self.app = DefenderApp(backend=self.backend)

    def tearDown(self):
        self.app.busy = False
        # Удаляем запланированные события перед уничтожением окна.
        for event in self.app.tk.call('after', 'info'):
            self.app.after_cancel(event)
        self.app.close()

    def wait_ready(self):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            self.app.update()
            if self.backend.actions and not self.app.busy:
                return
            time.sleep(0.02)
        self.fail('Операция не завершилась в GUI')

    def test_initial_status_and_unknown_tamper(self):
        self.wait_ready()
        self.assertEqual(self.backend.actions, ['status'])
        self.assertEqual(self.app.status_vars['realtime'][0].get(), 'Включена')
        self.assertEqual(self.app.status_vars['tamper'][0].get(), 'Неизвестно')

    def test_disable_waits_for_confirmation_and_renders_actual_result(self):
        self.wait_ready()
        with patch('defenderpilot.gui.messagebox.askyesno', return_value=False):
            self.app.request('disable')
        self.assertEqual(self.backend.actions, ['status'])
        with patch('defenderpilot.gui.messagebox.askyesno', return_value=True), patch('defenderpilot.gui.messagebox.showinfo'):
            self.app.request('disable')
            self.wait_ready()
        self.assertEqual(self.backend.actions, ['status', 'disable'])
        self.assertEqual(self.app.status_vars['realtime'][0].get(), 'Отключена')

    def test_failed_status_clears_previous_success(self):
        self.wait_ready()
        self.app.render_status({})
        self.assertEqual(self.app.status_vars['realtime'][0].get(), 'Неизвестно')


if __name__ == '__main__':
    unittest.main()
