# Offline Native Sysupgrade Backup Preparation

This one-time tool prepares a **copy** of a native OpenWrt configuration backup.
It has no SSH, router-write, service-control or flash functionality. It needs
Python 3.9+ and a native libuci CLI; it never replaces UCI parsing with regex.

It supports the inspected legacy layouts of `10.0.0.1` (six ports) and
`10.0.1.1` (four ports). Each backup must match its selected LAN address, bridge
ports, PPPoE interface, modem address, SSH port and independently verified
ZeroTier identity digest. Do not derive the expected identity from whichever
archive happens to be supplied: verify it against the intended physical device.
The second router is deferred until an on-site recovery path is available.

## Preview and Confirm

Actual production backup export and deployment need separate authorization.
Once an authorized native backup is available, work in a private directory
outside Git, CI, build output and shared storage. Keep the original unchanged.

```sh
umask 077
python3 tools/migration/prepare_backup.py original.tar.gz \
  --device 10.0.0.1 --identity-sha256 VERIFIED_DEVICE_DIGEST \
  --uci /path/to/native/uci > reviewed-plan.json
```

Preview creates no output archive. The JSON lists every excluded, added and
modified path, protected files, the allowed behavior changes and the input/result
digests. It contains no configuration values, passwords or private key contents.
Review the listed paths and the corresponding private input locally.

After explicit confirmation of that concrete plan:

```sh
python3 tools/migration/prepare_backup.py original.tar.gz \
  --device 10.0.0.1 --identity-sha256 VERIFIED_DEVICE_DIGEST \
  --uci /path/to/native/uci --apply-plan reviewed-plan.json \
  --output prepared-10.0.0.1.tar.gz
```

The tool recomputes and compares the complete plan. Changed input, identity,
device or transformation fails confirmation. Output is a native tar.gz, mode
0600, published atomically without overwriting any existing path. The source
archive stays unchanged. An already prepared archive can be checked again;
it produces no further content changes. Normal subsequent sysupgrades should
use native keep.d/conffiles rather than requiring this tool again.

## Exact Scope

- Keep network configuration except removal of WAN's old loopback DNS entries.
  Keep PPPoE credentials, interface/device names, bridge ports, IPv6, modem,
  DHCP hosts, static MAC option/list representation and unrelated firewall rules.
- Set dnsmasq's upstream list to `119.29.29.29`/`114.114.114.114`, `noresolv=1`
  and `dns_redirect=0`. Preserve `option.conf` including the device's KMS record.
  Preserve the inspected UCI `confdir=/etc/dnsmasq.d` on the second router;
  other UCI include paths are refused.
  Remove only recognized old default-server and per-domain proxy fragments.
  Preserve address/host-record/CNAME/SRV records in `migration-local.conf`.
  Add `local=/lan/`, `local=/local/` and `bogus-priv` there so local names and
  private reverse lookups terminate without a Mihomo/dnsmasq forwarding loop.
  When Nikki is enabled, the guard captures public port 53 into Mihomo and
  blocks plaintext output during a core failure; these base upstreams are used
  directly again only after an explicit Nikki disable.
- Remove `setmefree`/`setmefree6` UCI sets and `20-setmefree.nft`, preserving
  SSH filtering and ZeroTier's nft fragment.
- Change the three existing named `zt_rule_allow*` protocols to UDP, retaining
  their current dynamic port values. Keep subnet forwarding/NAT, ZT UCI and
  every `/etc/zerotier/` entry, including identity bytes and permissions.
- Keep `/etc/config/trojan`, `/etc/trojan.json` and the native disabled-services
  hook exactly. Keep the existing Trojan LAN-IP:1081 listener. Do not restore
  old `/usr/sbin/trojan` or `/etc/init.d/trojan` over firmware-provided versions.
  Add only that verified local SOCKS listener to
  `/etc/nikki/guard/providers/trojan.yaml`, with mode 0600 and no remote secrets.
  An existing different provider is refused for separate review.
- Exclude saved config/init/binaries/rc links for pdnsd, transocks,
  transocks-wong, ipt2socks and v2ray, plus their recognized standalone config
  paths and v2ctl. Remove those explicit retention lines from sysupgrade.conf;
  retain Trojan configuration and unrelated retention entries.
- Leave Nikki disabled for base-network recovery. Existing Nikki configuration,
  unknown firewall/DNS includes, unknown first-boot/network/cron hooks and
  unreviewed saved programs require manual analysis and are refused.

The tool checks UCI semantic equality outside the allowed edits. It rejects
missing authentication/host-key/identity files, unsafe or duplicate tar paths,
non-directory parents, hard links, unknown symlinks, special files/modes,
truncated gzip/tar and excessive archive size/count. Safe native `rc.d` service
links and the native `etc/samba/smb.conf -> /var/etc/smb.conf` link are supported.
The inspected BusyBox history hook is retained only with its exact history-file
assignment; added commands are refused. It never extracts arbitrary archive paths
onto the host.

`shortcut:` layout checks deliberately target these two inspected legacy systems.
If a layout, include, hook or service changes, inspect the new input and extend
the narrow handling and tests; do not add a force switch or silently retain an
unexplained proxy/DNS dependency.

## Validation and Deployment Gates

```sh
UCI=/path/to/native/uci PYTHONDONTWRITEBYTECODE=1 \
  python3 tools/migration/test_prepare_backup.py
```

Tests use fake credentials, fake host keys and distinct fake ZeroTier identities.
They execute real libuci against isolated copies, including both bridge layouts,
DNS changes, protocol narrowing, Trojan/service-state retention, idempotence,
native tar output, CLI confirmation and hostile archive/config cases.

Synthetic tests do not prove an actual production backup is complete. Do not
export production keys until authorized. Production archives must remain private
and must never be uploaded as build artifacts, release assets or test fixtures.

The old `00_seed_migration` has been removed from the candidate firmware source:
it could override restored DNS and FullCone settings without a seed. Check that
the built image also omits it. This tool does not delete source or router files.

Build the candidate with both NIC drivers, PPPoE, DNS/firewall, management,
ZeroTier, Trojan and Nikki/Mihomo present. Verify BIOS/squashfs, partition layout
and root filesystem capacity. Exercise real native sysupgrade in isolated VMware
with fake identities; never bring a production ZT identity clone online.

The final production operation uses the old firmware's native `sysupgrade -f`
with the prepared archive, after image/backup checks and deployment authorization.
Do not restore the new archive onto the running old router first. Do not use
`-n`, broaden backup scope with `-c`/`-o`, or force compatibility with `-F`.
`sysupgrade -T` is a limited format/image check, not a network or migration test.

Prepare and verify everything while the old router still serves the network.
The outage should contain only flashing, reboot and base-network recovery.
Confirm WAN/LAN/SSH/DHCP/DNS and bidirectional ZeroTier TCP/UDP/ICMP before
separately enabling Nikki. Verify Trojan SOCKS, subscription bootstrap and
cgroup bypass. With the current managed profile, the service guard handles
native restarts, refreshes cgroup rules and withdraws unready listeners. Confirm
that its runtime state admits the intended listener after a restart; an older
or custom profile needs the managed providers and DNS policies integrated first.
Measure recovery times in the VM and keep a tested old-image/disk recovery path.
