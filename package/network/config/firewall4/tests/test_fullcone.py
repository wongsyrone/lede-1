#!/usr/bin/env python3
"""Run against a prepared firewall4 tree: test_fullcone.py SOURCE UCODE."""
from pathlib import Path
import re
import subprocess
import sys
import unittest

source, ucode = map(Path, sys.argv[1:3])
sys.argv[1:3] = []
templates = source / "root/usr/share/firewall4/templates"
ruleset = (templates / "ruleset.uc").read_text()


class FullconeTemplates(unittest.TestCase):
    def test_masquerade_modes(self):
        calls = re.findall(r'include\("zone-masq\.uc", (\{[^}\n]+\})\)', ruleset)
        self.assertEqual(len(calls), 2)
        for mode in (0, 1, 2):
            for family, call in zip((4, 6), calls):
                with self.subTest(mode=mode, family=family):
                    program = """{%%
let mode = %d;
let fw4 = {
    nfproto: function(family, pretty) { return family == 6 ? "ipv6" : "ipv4"; },
    ipproto: function(family) { return family == 6 ? "ip6" : "ip"; },
    default_option: function(name) { return mode; }
};
let zone = { name: "wan" }, saddrs = null, daddrs = null;
include(%s, %s);
%%}
""" % (mode, repr(str(templates / "zone-masq.uc")), call)
                    result = subprocess.run(
                        [str(ucode), "-S", "-T", "-"],
                        input=program, text=True, capture_output=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("masquerade", result.stdout)
                    self.assertEqual(
                        "masquerade fullcone" in result.stdout,
                        family == 4 and mode == 2,
                    )


if __name__ == "__main__":
    unittest.main()
