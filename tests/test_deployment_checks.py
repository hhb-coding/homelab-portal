"""Regression checks for the systemd duration that broke rollback verification."""
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

with patch.dict(os.environ, PORTAL_DEPLOY_TARGET='test'):
    spec = importlib.util.spec_from_file_location('deploy_support', Path(__file__).resolve().parents[1]/'tools/deployment/deploy-support.py')
    support = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(support)

class DeploymentChecks(unittest.TestCase):
    def test_systemd_monotonic_duration(self):
        parse = support.monotonic_usec
        self.assertEqual(parse('3d 11h 13min 53.422345s'), 299633422345)
        self.assertGreater(parse('3d 11h 38min 53.422303s'), parse('3d 11h 13min 53.422345s'))
        self.assertEqual(parse('123456'), 123456)
        self.assertEqual(parse('1s 5ms 2us'), 1005002)
        for invalid in ('', 'n/a', '3d junk', '-1s'):
            with self.assertRaises(ValueError): parse(invalid)
