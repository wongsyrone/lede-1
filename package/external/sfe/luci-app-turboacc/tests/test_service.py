#!/usr/bin/env python3
"""Exercise capability detection and first-boot configuration without a router."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

package = Path(__file__).resolve().parents[1]
repo = package.parents[3]
lua = repo / "staging_dir/hostpkg/bin/lua"


class TurboaccService(unittest.TestCase):
    def test_rpc_detects_both_firewalls(self):
        driver = r"""
local script, module, fw4 = arg[1], arg[2], arg[3] == "1"
package.preload["luci.jsonc"] = function() return {
    stringify = function(t)
        return t and t.hasFLOWOFFLOADING ~= nil
            and (tostring(t.hasFLOWOFFLOADING) .. "," .. tostring(t.hasBRCMFULLCONENAT)) or "{}"
    end,
    new = function() return {
        parse = function() return true end, get = function() return {} end
    } end
} end
package.preload["nixio.fs"] = function() return {
    access = function(path)
        return path == "/lib/modules/test/" .. module or (fw4 and path == "/sbin/fw4")
    end,
    readfile = function() return "cubic" end
} end
package.preload["luci.util"] = function() return {
    ubus = function() return {kernel = "test"} end, trim = function(s) return s end
} end
package.preload["luci.sys"] = function() return {call = function() return 1 end} end
local read = false
io.read = function() if not read then read = true; return "{}" end end
arg = {"call", "getSystemFeatures"}
dofile(script)
"""
        for module, fw4 in (
            ("nft_flow_offload.ko", "1"), ("xt_FLOWOFFLOAD.ko", "0"),
            ("absent", "1"), ("absent", "0"),
        ):
            with self.subTest(module=module, fw4=fw4):
                result = subprocess.run(
                    [str(lua), "-", str(package / "root/usr/libexec/rpcd/luci.turboacc"), module, fw4],
                    input=driver, text=True, capture_output=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.splitlines()[0],
                                 f"{str(module != 'absent').lower()},{str(fw4 == '1').lower()}")

    def test_first_boot_detects_nft_modules_and_preserves_user_settings(self):
        for customized in ("0", "1"):
            with self.subTest(customized=customized), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for path in ("bin", "etc/config", "etc/init.d", "lib/modules/test"):
                    (root / path).mkdir(parents=True, exist_ok=True)
                for module in ("nft_flow_offload.ko", "nft_fullcone.ko"):
                    (root / "lib/modules/test" / module).touch()
                for name, text in {
                    "uname": "#!/bin/sh\necho test\n",
                    "uci": '#!/bin/sh\nif [ "$2" = get ]; then echo "$CUSTOMIZED"; else echo "$*" >> "$CALLS"; fi\n',
                }.items():
                    binary = root / "bin" / name
                    binary.write_text(text)
                    binary.chmod(0o755)
                service = root / "etc/init.d/turboacc"
                service.write_text("#!/bin/sh\nexit 0\n")
                service.chmod(0o755)
                config = root / "etc/config/turboacc"
                config.write_text("user configuration\n")
                (root / "etc/openwrt_release").write_text("DISTRIB_TARGET='x86/64'\n")
                source = (package / "root/etc/uci-defaults/turboacc").read_text()
                for prefix in ("/etc/", "/lib/modules/"):
                    source = source.replace(prefix, str(root) + prefix)
                environment = dict(
                    os.environ, PATH=str(root / "bin") + ":/usr/bin:/bin",
                    CUSTOMIZED=customized, CALLS=str(root / "calls"),
                )
                result = subprocess.run(
                    ["sh"], input=source, env=environment, text=True, capture_output=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                if customized == "1":
                    self.assertEqual(config.read_text(), "user configuration\n")
                    self.assertFalse((root / "calls").exists())
                else:
                    calls = (root / "calls").read_text()
                    self.assertIn("turboacc.config.fastpath=flow_offloading", calls)
                    self.assertIn("turboacc.config.fullcone=1", calls)


if __name__ == "__main__":
    unittest.main()
