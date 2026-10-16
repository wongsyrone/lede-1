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
- The script adds `services/trojan` to Nikki's existing scoped business-traffic
  bypass and sends its DNS, including dnsmasq's public forwarding, through Mihomo.
  It does not create a cgroup-only rule: upstream filters missing cgroups,
  so such a rule could become an unconditional bypass when Trojan is absent.
  Unknown/custom access-control layouts require manual integration; the script
  does not rewrite them. Kernel cgroups and socket cgroup support are selected.

## Standalone Trojan

Keep `CONFIG_PACKAGE_trojan=y`, `/etc/config/trojan`, `/etc/trojan.json` and the
service's enabled/disabled state. Do not restore an old executable or init script
over the version shipped in new firmware. Do not change an existing LAN-IP:1081
listener to loopback without considering its existing clients.

The offline migration tool creates a private entry for the verified existing
listener in `/etc/nikki/guard/providers/trojan.yaml`, for example:

```yaml
proxies:
  - name: standalone-trojan
    type: socks5
    server: 192.0.2.1 # Use an address owned by this router.
    port: 1081
    udp: true
```

Do not also put this managed entry in `user.yaml`: the unmanaged duplicate could
remain selectable after the service is withdrawn. The `Native Trojan` group
requires this independent implementation and rejects traffic when unavailable.
Ordinary groups may select other healthy exits according to their own policy.

`nikki-service-guard` prepares RAM providers at S90, gates the native Trojan
process at S95, and waits for Nikki's encrypted bootstrap resolver at S99.
procd owns finite crash recovery. The watcher checks service notifications and
cgroup identity, renders Nikki's upstream rules under its native lock, and uses
the provider API to admit or withdraw local listeners without a core restart.
It derives native domains from the unchanged Trojan JSON and excludes them from
fake-IP using a dynamic rule provider. Address validation reads the effective
IPv4/IPv6 CIDRs after Nikki's UCI mixin; the profile's original pool may differ.

The normal public DNS pools use encrypted transport. While Nikki remains
enabled, its separate DNS guard keeps managed LAN port 53 captured and blocks
plaintext public forwarding during a core failure or stop. An explicit user
disable permits the base-network dnsmasq upstreams again. Local `.lan`/`.local`
and private reverse zones must terminate in dnsmasq; the migration tool adds
the required local boundaries. Application DoH is outside port 53 interception.

The guard's supported profile structure is explicit; it does not convert an
arbitrary third-party profile or overwrite a saved older/custom profile during
sysupgrade. Adopt this profile's managed providers, policy ordering and
`SAFE_PATHS` entry when integrating an existing custom profile. Keep all private
sources outside Git, CI and firmware artifacts.

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

Also run the service guard's tests with the same native ucode and Mihomo.
These host checks do not start transparent routing, test nft in the kernel,
establish Trojan connections or exercise sysupgrade. VMware boot,
WAN/LAN/DNS/ZeroTier, SOCKS TCP/UDP, cgroup restart ordering and offline rule
loading remain separate acceptance gates. Do not flash based only on `-t`.
