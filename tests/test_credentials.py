import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import credentials


class CredentialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Path(self.temp.name) / 'credentials.json'
        self.patch = patch.object(credentials, 'CONFIG_PATH', self.config)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def configure(self, value):
        self.config.write_text(json.dumps(value))

    def test_reference_takes_priority_and_does_not_export(self):
        self.configure({'KEY': 'op://vault/item/key'})
        with patch.dict('os.environ', {'KEY': 'old-key'}), patch.object(credentials.subprocess, 'run') as run:
            run.return_value.stdout = 'resolved-key\n'
            self.assertEqual(credentials.get_credential('KEY'), 'resolved-key')
            self.assertEqual(credentials.os.environ['KEY'], 'old-key')
            self.assertEqual(run.call_args.args[0], ['op', 'read', '--', 'op://vault/item/key'])
            self.assertNotIn('shell', run.call_args.kwargs)

    def test_reference_failure_does_not_fallback_or_leak(self):
        self.configure({'KEY': 'op://vault/item/key'})
        failure = subprocess.CalledProcessError(1, ['op'], stderr='private-output')
        with patch.dict('os.environ', {'KEY': 'old-key'}), patch.object(credentials.subprocess, 'run', side_effect=failure):
            with self.assertRaises(credentials.CredentialError) as caught:
                credentials.get_credential('KEY')
            self.assertNotIn('private-output', str(caught.exception))
            self.assertIsNone(caught.exception.__cause__)

    def test_timeout_and_missing_cli(self):
        self.configure({'KEY': 'op://vault/item/key'})
        for failure in [FileNotFoundError(), subprocess.TimeoutExpired('op', 30)]:
            with self.subTest(failure=type(failure)), patch.object(credentials.subprocess, 'run', side_effect=failure):
                with self.assertRaises(credentials.CredentialError):
                    credentials.get_credential('KEY')

    def test_explicit_value_and_legacy_fallback(self):
        self.configure({'KEY': 'op://vault/item/key'})
        self.assertEqual(credentials.get_credential('KEY', 'explicit'), 'explicit')
        with patch.dict('os.environ', {'OTHER': 'legacy'}):
            self.assertEqual(credentials.get_credential('OTHER'), 'legacy')

    def test_presence_does_not_read_secrets(self):
        self.configure({'KEY': 'op://vault/item/key'})
        with patch.object(credentials.subprocess, 'run') as run:
            self.assertTrue(credentials.has_credential('KEY'))
            run.assert_not_called()

    def test_invalid_config_and_reference(self):
        for config in [[], {'KEY': 42}, {'KEY': 'op://vault/item'}]:
            self.configure(config)
            with self.subTest(config=config), self.assertRaises(credentials.CredentialError):
                credentials.get_credential('KEY')

    def test_empty_secret_rejected(self):
        self.configure({'KEY': 'op://vault/item/key'})
        with patch.object(credentials.subprocess, 'run') as run:
            run.return_value.stdout = '\n'
            with self.assertRaises(credentials.CredentialError):
                credentials.get_credential('KEY')

    def test_all_consumers_use_resolver(self):
        from job_searcher import AdzunaJobSearcher
        from notion_sync import NotionSync
        from resume_parser import ResumeParser
        from embedding_matcher import HybridMatcher, EmbeddingMatcher
        self.configure({'ADZUNA_APP_ID': 'op://vault/adzuna/id', 'ADZUNA_API_KEY': 'op://vault/adzuna/key', 'NOTION_TOKEN': 'op://vault/notion/token', 'NOTION_DATABASE_ID': 'database-id', 'OPENAI_API_KEY': 'op://vault/openai/key'})
        with patch.object(credentials.subprocess, 'run') as run:
            run.return_value.stdout = 'test-value\n'
            self.assertEqual(AdzunaJobSearcher().api_key, 'test-value')
            self.assertEqual(NotionSync().token, 'test-value')
            self.assertEqual(ResumeParser().openai_api_key, 'test-value')
            self.assertTrue(HybridMatcher({}).use_semantic)
            with patch.object(EmbeddingMatcher, '_init_local_model'):
                run.reset_mock()
                EmbeddingMatcher(use_local=True)
                run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
