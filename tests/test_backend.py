import unittest

from defenderpilot.backend import BackendError, MARKER, parse_result, DefenderBackend


class ResultTests(unittest.TestCase):
    def test_native_output_before_json(self):
        output = 'DISM 100%\n' + MARKER + '{"ok":true,"status":{"realtime":false,"tamper":null}}\n'
        result = parse_result(output, 0)
        self.assertTrue(result['ok'])
        self.assertIs(result['status']['realtime'], False)
        self.assertIsNone(result['status']['tamper'])

    def test_nonzero_exit_never_succeeds(self):
        self.assertFalse(parse_result(MARKER + '{"ok":true}', 1)['ok'])

    def test_missing_or_malformed_response_fails(self):
        for output in ('Operation completed', MARKER + '{', MARKER + '[]', MARKER + '{"ok":"true"}'):
            with self.subTest(output=output), self.assertRaises(BackendError):
                parse_result(output, 0)

    def test_only_final_response_is_used(self):
        result = parse_result(MARKER + '{"ok":true}\n' + MARKER + '{"ok":false}', 0)
        self.assertFalse(result['ok'])

    def test_arbitrary_actions_rejected_before_process_start(self):
        with self.assertRaises(ValueError):
            DefenderBackend().run('status; Remove-Item C:\\', lambda line: None)


if __name__ == '__main__':
    unittest.main()
