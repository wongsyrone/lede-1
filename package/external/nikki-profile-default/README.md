# Nikki Router Profile

This package ships public classification rules, an empty private-node file and
initial MRS data. It does not ship credentials, subscriptions, corporate rules,
desktop process rules or device-specific addresses. Nikki remains disabled by
default; an empty node file does not provide working proxy service.

- Nikki owns listeners, TUN, DNS interception and routing. The profile does not
  install another firewall generator or replace `/etc/config/nikki`.
- Initial MRS files are downloaded by OpenWrt from the immutable revision in
  `rules.mk`, with a separate SHA-256 for every file. Runtime updates use the
  corresponding upstream `meta` paths and replace the same cache filenames.
- The profile, private-node file and five local rule files are conffiles. Nikki's
  upstream keep.d also preserves profiles and provider data on later upgrades.
- The first-boot script only replaces an empty/default-placeholder selection
  while Nikki is disabled. It leaves enabled/user-selected profiles, credentials
  and unrelated UCI settings alone. The default API binds to localhost.
- The script adds `services/trojan` only to Nikki's existing scoped DNS/proxy
  bypass. It does not create a cgroup-only rule: upstream filters missing cgroups,
  so such a rule could become an unconditional bypass when Trojan is absent.
  Unknown/custom access-control layouts require manual integration; the script
  does not rewrite them. Kernel cgroups and socket cgroup support are selected.

## Standalone Trojan

Keep `CONFIG_PACKAGE_trojan=y`, `/etc/config/trojan`, `/etc/trojan.json` and the
service's enabled/disabled state. Do not restore an old executable or init script
over the version shipped in new firmware. Do not change an existing LAN-IP:1081
listener to loopback without considering its existing clients.

For an existing listener, add a private SOCKS5 node to `user.yaml`, for example:

```yaml
proxies:
  - name: standalone-trojan
    type: socks5
    server: 192.0.2.1 # Replace with the service's actual listening address.
    port: 1081
    udp: true
```

For subscription bootstrap, define the SOCKS node in the private profile's
top-level `proxies` (or Nikki's `nikki-proxies` mixin) and use its name as the
subscription's `proxy`. It must be available before subscriptions are fetched.
Keep private profiles outside Git and select them through Nikki rather than
adding credentials to this package.

Trojan boots at S95 and Nikki at S99. Verify the actual Trojan cgroup before
enabling Nikki, and keep Trojan's bootstrap DNS independent of Nikki.

`shortcut:` Nikki resolves service cgroups while generating firewall rules;
after stopping/restarting Trojan, stop/restart Nikki around that operation until
upstream supports cgroup lifecycle updates. Do not assume an old nft cgroup ID
continues matching a recreated service. This ordering must be tested in a VM.
No daemon watcher or fork of Nikki's firewall implementation is added here.

## Checks

Run the small first-boot tests with a native libuci CLI:

```sh
UCI=/path/to/native/uci python3 package/external/nikki-profile-default/tests/test_defaults.py
ruby package/external/nikki-profile-default/tests/test_profile.rb
```

Set `RULES_DIR` to downloaded `nikki-rule-<revision>-<name>.mrs` files to verify
all snapshot hashes in the Ruby check. The YAML labels intentionally preserve
the original classification names, including Chinese text and emoji.

The mixin test needs a built/extracted package, native ucode with the real UCI
module, yq and Mihomo. It executes the upstream mixin and firewall template with
real UCI configuration; only ubus interface status, host users/cgroups and the
fw4 hex formatter are test fixtures:

```sh
UCI=/path/to/uci UCODE=/path/to/ucode YQ=/path/to/yq MIHOMO=/path/to/mihomo \
  PKG_ROOT=/path/to/extracted-package PYTHONDONTWRITEBYTECODE=1 \
  python3 package/external/nikki-profile-default/tests/test_mixin.py
```

These checks do not start transparent routing, test nft in the kernel, establish
Trojan connections or exercise sysupgrade. VMware boot, WAN/LAN/DNS/ZeroTier,
SOCKS TCP/UDP, subscription bootstrap, cgroup restart ordering and offline rule
loading remain separate acceptance gates. Do not flash based only on `-t`.
