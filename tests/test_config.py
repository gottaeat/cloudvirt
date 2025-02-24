import unittest

import yaml
import os

from cloudvirt import config


def get_testfile(name):
    return os.path.join(os.path.dirname(__file__), name)

class ParseConfig(unittest.TestCase):
    def test_parse_vmspec_yaml(self):
        filename = get_testfile("vmspec_config_1.yml")
        c = config.ConfigYAML(filename, None, None)
        c.run()
        self.assertEqual(c.vmspec.isolated_port, False)
