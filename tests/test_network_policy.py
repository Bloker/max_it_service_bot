import unittest

from app.network.policy.corporate_policy import CorporateTargetPolicy
from app.network.policy.target_validator import normalize_target, validate_target_format
from config.config import NetworkPolicyConfig


class NetworkPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        cfg = NetworkPolicyConfig(
            allowed_subnets=('10.0.0.0/8',),
            allowed_domain_suffixes=('.corp.local',),
            allowed_hosts=('intra.local',),
            allowed_device_types=('router', 'switch'),
        )
        self.policy = CorporateTargetPolicy(cfg)

    def test_target_normalization_and_validation(self) -> None:
        self.assertEqual(normalize_target('  EXAMPLE.CORP.LOCAL '), 'example.corp.local')
        self.assertEqual(validate_target_format('10.1.1.1'), (True, ''))
        self.assertEqual(validate_target_format(''), (False, 'Укажите хост или IP.'))

    def test_policy_allows_only_corporate_targets(self) -> None:
        self.assertTrue(self.policy.is_allowed_target('10.1.2.3')[0])
        self.assertTrue(self.policy.is_allowed_target('srv.corp.local')[0])
        self.assertTrue(self.policy.is_allowed_target('intra.local')[0])

        self.assertFalse(self.policy.is_allowed_target('8.8.8.8')[0])
        self.assertFalse(self.policy.is_allowed_target('example.com')[0])

    def test_device_type_policy(self) -> None:
        self.assertTrue(self.policy.is_allowed_device_type('router'))
        self.assertTrue(self.policy.is_allowed_device_type('SWITCH'))
        self.assertFalse(self.policy.is_allowed_device_type('laptop'))


if __name__ == '__main__':
    unittest.main()
