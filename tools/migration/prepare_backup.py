#!/usr/bin/env python3
"""Prepare a reviewed native sysupgrade backup offline; never contacts a router."""

import argparse
import copy
import gzip
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath


DEVICES = {"10.0.0.1": (5, "192.168.1.140"), "10.0.1.1": (3, "192.168.100.140")}
RETIRED = ("pdnsd", "transocks", "transocks-wong", "ipt2socks", "v2ray")
RULE_FILES = {
    "accelerated-domains.china.conf", "bogus-nxdomain.china.conf",
    "china-cdn-domain-whitelist.conf", "china-top-website-whitelist.conf",
    "gfw-nftset.conf", "gfw-ipset.conf.ipset", "local-self-ipset.conf.ipset",
    "local-self-nftset.conf",
}
NFT_FILES = {
    "10-custom-filter-chains.nft", "20-setmefree.nft",
    "99-zerotier-auto-nat-auto-generated-do-not-touch.nft", "README",
}
ZT_RULES = ("zt_rule_allowInbound", "zt_rule_allowSecondPort", "zt_rule_allowThirdPort")
REQUIRED = {
    "etc/config/" + name for name in ("network", "dhcp", "firewall", "dropbear", "zerotier", "trojan")
} | {
    "etc/passwd", "etc/group", "etc/shadow", "etc/rc.local", "etc/sysupgrade.conf",
    "etc/trojan.json", "etc/zerotier/identity.secret", "etc/zerotier/identity.public",
    "etc/zerotier/planet", "etc/uci-defaults/10_disable_services", "etc/dnsmasq.conf",
}
MAX_BYTES = 256 * 1024 * 1024


class Rejected(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Rejected(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read_backup(source):
    require(source.is_file() and not source.is_symlink(), "Input must be a regular backup file")
    require(source.stat().st_size <= MAX_BYTES, "Backup exceeds the offline tool's size limit")
    raw = source.read_bytes()
    entries = {}
    total = 0
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as compressed:
            unpacked = compressed.read(MAX_BYTES + 1)
        require(len(unpacked) <= MAX_BYTES, "Uncompressed backup exceeds size limit")
        require(unpacked.endswith(b"\0" * 1024), "Missing native tar end markers")
        with tarfile.open(fileobj=io.BytesIO(unpacked), mode="r:") as archive:
            for item in archive:
                require(len(entries) < 10000, "Too many archive entries")
                name = item.name.removeprefix("./").rstrip("/")
                parts = name.split("/")
                require(name and not name.startswith("/") and all(p not in ("", ".", "..") for p in parts)
                        and not any(ord(c) < 32 or ord(c) == 127 for c in name)
                        and "\\" not in name, "Unsafe archive path")
                require(name not in entries, "Duplicate archive path: " + name)
                require(item.isfile() or item.isdir() or item.issym(), "Unsupported archive entry: " + name)
                require(item.sparse is None, "Sparse archive entries are not supported")
                require(not (item.mode & 0o7000), "Special permission bits: " + name)
                if item.issym():
                    match = re.fullmatch(r"etc/rc\.d/[SK][0-9]{2}([A-Za-z0-9_+-]+)", name)
                    require((match and item.linkname == "../init.d/" + match[1])
                            or (name == "etc/samba/smb.conf" and item.linkname == "/var/etc/smb.conf"),
                            "Unreviewed symbolic link: " + name)
                total += item.size
                require(0 <= item.size <= 64 * 1024 * 1024 and total <= MAX_BYTES, "Archive payload exceeds size limit")
                data = archive.extractfile(item).read() if item.isfile() else b""
                require(len(data) == item.size if item.isfile() else item.size == 0, "Incomplete archive member")
                item = copy.copy(item)
                item.name = name
                entries[name] = (item, data)
    except (tarfile.TarError, EOFError, OSError):
        raise Rejected("Invalid or truncated gzip/tar backup") from None
    for name in entries:
        for ancestor in PurePosixPath(name).parents:
            if str(ancestor) in entries:
                require(entries[str(ancestor)][0].isdir(), "Non-directory archive parent")
    missing = REQUIRED - entries.keys()
    require(not missing, "Missing essential files: " + ", ".join(sorted(missing)))
    require(all(entries[name][0].isfile() for name in REQUIRED), "Essential file is not regular")
    require(any(n.startswith("etc/dropbear/dropbear_") and n.endswith("_host_key") and item.isfile()
                for n, (item, _) in entries.items()), "Missing SSH host key")
    require(entries["etc/zerotier/identity.secret"][0].mode == 0o600, "ZeroTier private identity must have mode 0600")
    require(all(entries[n][1] for n in ("etc/zerotier/identity.secret", "etc/zerotier/identity.public",
                                      "etc/zerotier/planet", "etc/shadow")), "Empty identity or authentication file")
    return entries, sha256(raw)


class Uci:
    def __init__(self, directory, executable):
        self.directory = directory
        for name in ("config", "save", "override"):
            (directory / name).mkdir()
        self.command = [executable, "-c", str(directory / "config"),
                        "-t", str(directory / "save"), "-C", str(directory / "override")]

    def run(self, *args):
        result = subprocess.run(self.command + list(args), text=True, capture_output=True)
        require(result.returncode == 0, "UCI validation/edit failed: " + args[0])
        return result.stdout

    def export(self, package):
        tokens = iter(shlex.split(self.run("-n", "export", package)))
        sections = []
        for token in tokens:
            if token == "package":
                require(next(tokens) == package, "Unexpected UCI package")
            elif token == "config":
                sections.append({"type": next(tokens), "name": next(tokens), "options": {}})
            elif token in ("option", "list"):
                key, value = next(tokens), next(tokens)
                if token == "list":
                    sections[-1]["options"].setdefault(key, []).append(value)
                else:
                    sections[-1]["options"][key] = value
            else:
                raise Rejected("Unexpected UCI export token")
        return sections

    def set(self, package, section, key, value):
        path = f"{package}.{section['name']}.{key}"
        if isinstance(value, list):
            if key in section["options"]:
                self.run("delete", path)
            for item in value:
                self.run("add_list", path + "=" + item)
        elif value is None:
            if key in section["options"]:
                self.run("delete", path)
        else:
            self.run("set", path + "=" + value)
        if value is None:
            section["options"].pop(key, None)
        else:
            section["options"][key] = value


def only(sections, kind, name=None, option=None):
    matches = [s for s in sections if s["type"] == kind and (name is None or s["name"] == name)
               and (option is None or s["options"].get(option[0]) == option[1])]
    require(len(matches) == 1, "Expected one UCI section: " + (name or kind))
    return matches[0]


def normalized(sections):
    # Anonymous libuci section IDs change when earlier sections are removed.
    return [(s["type"], None if re.fullmatch(r"cfg[0-9a-f]+", s["name"]) else s["name"], s["options"])
            for s in sections]


def active_lines(data):
    try:
        return [line.strip() for line in data.decode("utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#")]
    except UnicodeDecodeError:
        raise Rejected("Expected UTF-8 configuration text") from None


def retired_path(name):
    for service in RETIRED:
        if name in (f"etc/config/{service}", f"etc/init.d/{service}", f"usr/sbin/{service}", f"usr/bin/{service}"):
            return True
        if re.fullmatch(r"etc/rc\.d/[SK][0-9]{2}" + re.escape(service), name):
            return True
    return (name in ("usr/sbin/v2ctl", "etc/transocks.toml", "etc/pdnsd.conf", "etc/v2ray*.json")
            or name == "etc/v2ray" or name.startswith("etc/v2ray/")
            or re.fullmatch(r"etc/v2ray[^/]*\.json", name) is not None)


def inspect_hooks(entries):
    for name, (item, data) in entries.items():
        if item.isdir():
            continue
        if name.startswith("etc/uci-defaults/"):
            require(name == "etc/uci-defaults/10_disable_services", "Unknown first-boot hook: " + name)
            lines = active_lines(data)
            require(lines and lines[-1] == "exit 0"
                    and all(re.fullmatch(r"/etc/init\.d/[A-Za-z0-9_+-]+ disable", x) for x in lines[:-1]),
                    "Unexpected native service-disable hook")
        if name == "etc/rc.local":
            require(active_lines(data) == ["echo 3 > /proc/sys/net/ipv4/tcp_fastopen", "exit 0"],
                    "Unreviewed rc.local commands")
        if name.startswith("etc/init.d/"):
            require(name.removeprefix("etc/init.d/") in RETIRED + ("trojan",),
                    "Unreviewed saved service script: " + name)
        if name.startswith(("etc/crontabs/", "etc/udhcpc.user.d/", "etc/odhcp6c.user.d/",
                            "etc/hotplug.d/", "etc/ppp/", "etc/profile.d/")):
            if name == "etc/profile.d/busybox-history-file.sh":
                require(active_lines(data) == ["export HISTFILE=/tmp/.busybox_ash_history"],
                        "Unexpected BusyBox history hook")
            else:
                require(not active_lines(data), "Unreviewed startup/network hook: " + name)
        if name.startswith("usr/"):
            require(retired_path(name) or name == "usr/sbin/trojan", "Unreviewed saved program: " + name)
        require(not name.startswith(("usr/lib/opkg/", "lib/apk/db/", "usr/lib/apk/db/", "var/")),
                "Do not restore old package databases or runtime state: " + name)


def clean_dns(entries, replace, exclude):
    known = RULE_FILES | {"server.conf", "option.conf", "migration-local.conf"}
    local_lines = []
    for name, (item, data) in list(entries.items()):
        if not name.startswith("etc/dnsmasq.d/") or item.isdir():
            continue
        base = name.removeprefix("etc/dnsmasq.d/")
        require(base in known and item.isfile(), "Unknown DNS fragment: " + name)
        if base == "option.conf":
            require(all(re.fullmatch(r"(no-resolv|no-poll|no-negcache|all-servers|min-cache-ttl=\d+|cache-size=\d+|srv-host=[^#]+)", line)
                        for line in active_lines(data)), "Unreviewed dnsmasq option.conf")
            continue
        if base == "migration-local.conf":
            local_lines.extend(active_lines(data))
            continue
        lines = active_lines(data)
        if base == "server.conf":
            require(lines == ["server=::1#8153"], "Unexpected legacy default DNS server")
        else:
            for line in lines:
                if re.fullmatch(r"(address|host-record|cname|srv-host)=[^#]+", line):
                    local_lines.append(line)
                else:
                    require(re.fullmatch(
                        r"server=/[^\s]+/(?:114\.114\.114\.114|119\.29\.29\.29|222\.222\.202\.202|222\.222\.222\.222)(?:#53)?"
                        r"|nftset=/[^\s]+/4#inet#fw4#setmefree,6#inet#fw4#setmefree6"
                        r"|ipset=/[^\s]+/setmefree(?:,setmefree6)?"
                        r"|bogus-nxdomain=[0-9a-fA-F:.]+", line),
                            "Unknown directive in legacy DNS fragment: " + name)
        exclude(name)
    if local_lines:
        require(all(re.fullmatch(r"(address|host-record|cname|srv-host)=[^#]+", line) for line in local_lines),
                "Unexpected preserved local DNS content")
        replace("etc/dnsmasq.d/migration-local.conf", ("\n".join(dict.fromkeys(local_lines)) + "\n").encode())
    if "etc/dnsmasq.conf" in entries:
        require(active_lines(entries["etc/dnsmasq.conf"][1]) in ([], ["conf-dir=/etc/dnsmasq.d/,*.conf"]),
                "Unknown dnsmasq include/options")
    for name, (item, data) in entries.items():
        if name.startswith("etc/nftables.d/") and not item.isdir():
            require(name.removeprefix("etc/nftables.d/") in NFT_FILES, "Unknown nft include: " + name)
            require(not any(re.match(r"include\s", line) for line in active_lines(data)),
                    "Unreviewed nested nft include: " + name)
    exclude("etc/nftables.d/20-setmefree.nft")


def prepare(source, device, identity_sha256, executable):
    require(device in DEVICES and re.fullmatch(r"[a-f0-9]{64}", identity_sha256), "Invalid device or identity digest")
    entries, source_sha = read_backup(source)
    require(sha256(entries["etc/zerotier/identity.secret"][1]) == identity_sha256, "Device identity digest mismatch")
    original = dict(entries)
    inspect_hooks(entries)

    def replace(name, data):
        if name in entries and entries[name][1] == data:
            return
        if name not in entries:
            info = tarfile.TarInfo(name)
            info.mode = 0o600
            info.size = len(data)
        else:
            info = copy.copy(entries[name][0])
            require(info.isfile(), "Cannot replace non-regular configuration")
            info.size = len(data)
        entries[name] = (info, data)

    def exclude(name):
        entries.pop(name, None)

    with tempfile.TemporaryDirectory(prefix="openwrt-backup-") as temp:
        uci = Uci(Path(temp), executable)
        packages = ("network", "dhcp", "firewall", "dropbear", "zerotier", "trojan")
        for package in packages:
            (uci.directory / "config" / package).write_bytes(entries["etc/config/" + package][1])
        records = {p: uci.export(p) for p in packages}
        expected = copy.deepcopy(records)
        network, dhcp, firewall = expected["network"], expected["dhcp"], expected["firewall"]
        lan = only(network, "interface", "lan")
        wan = only(network, "interface", "wan")
        modem = only(network, "interface", "modem")
        bridge = only(network, "device", option=("name", "br-lan"))
        ports, modem_ip = DEVICES[device]
        require(lan["options"].get("ipaddr") == device and lan["options"].get("device") == "br-lan"
                and wan["options"].get("proto") == "pppoe" and wan["options"].get("device") == "eth0"
                and wan["options"].get("peerdns") == "0"
                and isinstance(wan["options"].get("username"), str) and isinstance(wan["options"].get("password"), str)
                and bridge["options"].get("ports") == [f"eth{i}" for i in range(1, ports + 1)]
                and modem["options"].get("ipaddr") == modem_ip and modem["options"].get("defaultroute") == "0",
                "Backup network layout does not match the selected device")
        require(only(records["dropbear"], "dropbear")["options"].get("Port") == "444", "Unexpected SSH port")
        only(records["zerotier"], "zerotier", "openwrt_network")
        only(records["trojan"], "trojan")
        try:
            trojan = json.loads(entries["etc/trojan.json"][1])
        except (ValueError, UnicodeDecodeError):
            raise Rejected("Invalid Trojan JSON") from None
        require(isinstance(trojan, dict) and trojan.get("run_type") == "client" and trojan.get("local_addr") == device
                and trojan.get("local_port") == 1081, "Unexpected independent Trojan listener")
        dns = only(dhcp, "dnsmasq")
        require(dns["options"].get("confdir") in (None, "/etc/dnsmasq.d")
                and not any(k in dns["options"] for k in ("conf_file", "conf_file_path")),
                "Unknown dnsmasq UCI include")
        old_servers = dns["options"].get("server", [])
        require(isinstance(old_servers, list)
                and all(s in ("::1#8153", "119.29.29.29", "114.114.114.114") for s in old_servers),
                "Unknown dnsmasq UCI upstream")
        for section in firewall:
            if section["type"] == "include":
                require(section["options"].get("path") == "/usr/share/miniupnpd/firewall.include",
                        "Unreviewed firewall include")
            elif section["type"] != "ipset":
                require("setmefree" not in json.dumps(section["options"]), "Unknown reference to retired firewall set")
        for package in ("network", "dhcp", "firewall"):
            if package == "network" and "dns" in wan["options"]:
                value = wan["options"]["dns"]
                values = value if isinstance(value, list) else [value]
                uci.set("network", wan, "dns", [x for x in values if x not in ("::1", "127.0.0.1")] or None)
            if package == "dhcp":
                uci.set("dhcp", dns, "server", ["119.29.29.29", "114.114.114.114"])
                uci.set("dhcp", dns, "noresolv", "1")
                uci.set("dhcp", dns, "dns_redirect", "0")
            if package == "firewall":
                for rule_name in ZT_RULES:
                    rule = only(firewall, "rule", rule_name)
                    require(rule["options"].get("src") == "*" and rule["options"].get("target") == "ACCEPT"
                            and rule["options"].get("proto") in ("all", "udp", ["all"], ["udp"])
                            and re.fullmatch(r"[0-9]+", rule["options"].get("dest_port", ""))
                            and 1 <= int(rule["options"]["dest_port"]) <= 65535, "Unexpected ZeroTier dynamic input rule")
                    uci.set("firewall", rule, "proto", ["udp"])
                for section in reversed(firewall[:]):
                    if section["type"] == "ipset" and section["options"].get("name") in ("setmefree", "setmefree6"):
                        uci.run("delete", "firewall." + section["name"])
                        firewall.remove(section)
            uci.run("commit", package)
            require(normalized(uci.export(package)) == normalized(expected[package]), "Unexpected UCI semantic change")
            # Keep exact source bytes for an already migrated, semantically unchanged package.
            if normalized(records[package]) != normalized(expected[package]):
                replace("etc/config/" + package, (uci.directory / "config" / package).read_bytes())
        require("etc/config/nikki" not in entries, "Existing Nikki configuration needs separate review")
    clean_dns(entries, replace, exclude)
    for name in list(entries):
        if retired_path(name) or name in ("usr/sbin/trojan", "etc/init.d/trojan"):
            exclude(name)
    retention = entries["etc/sysupgrade.conf"][1].decode("utf-8")
    lines = [line for line in retention.splitlines()
             if not retired_path(line.split("#", 1)[0].strip().lstrip("/"))
             and line.split("#", 1)[0].strip() not in ("/usr/sbin/trojan", "/etc/init.d/trojan")]
    replace("etc/sysupgrade.conf", ("\n".join(lines) + "\n").encode())

    changed = sorted(name for name in original.keys() | entries.keys()
                     if name not in original or name not in entries or entries[name] != original[name])
    protected = sorted(name for name in original if name not in changed)
    for name in protected:
        require(entries[name] == original[name], "Protected entry changed")
    require(entries["etc/trojan.json"] == original["etc/trojan.json"]
            and entries["etc/config/trojan"] == original["etc/config/trojan"], "Trojan configuration changed")
    require(all(entries[name] == item for name, item in original.items() if name.startswith("etc/zerotier/")),
            "ZeroTier persistence changed")
    digest = hashlib.sha256()
    for name, (info, data) in sorted(entries.items()):
        digest.update(json.dumps([name, info.type.decode(), info.mode, info.uid, info.gid, info.mtime, info.linkname, sha256(data)]).encode())
    require(sha256(source.read_bytes()) == source_sha, "Input changed during preparation")
    plan = {
        "version": 1, "device": device, "identity_sha256": identity_sha256,
        "source_sha256": source_sha, "result_sha256": digest.hexdigest(),
        "changes": [{"path": "/" + n, "action": "exclude" if n not in entries else "add" if n not in original else "modify"}
                    for n in changed],
        "protected": protected,
        "behavior": [
            "Keep WAN/LAN/IPv6/modem/bridge/DHCP/authentication except the explicitly listed DNS fields.",
            "Remove only WAN DNS loopback entries; dnsmasq uses 119.29.29.29 and 114.114.114.114 with noresolv=1.",
            "Keep independent Trojan JSON/UCI and native disabled-service state unchanged.",
            "Replace only the three dynamic ZeroTier input-rule protocols with UDP; keep ports/forwarding/NAT and all identity data.",
            "Exclude reviewed retired proxy files; preserve local DNS records and SSH/ZeroTier nft fragments.",
            "Nikki stays disabled during base-network recovery; enable it only after VMware and device acceptance.",
        ],
    }
    return entries, plan


def verify_plan(actual, confirmed):
    require(actual == confirmed, "Confirmed plan does not match this input and transformation")


def write_backup(output, entries):
    require(output.parent.is_dir(), "Output directory must already exist")
    with tempfile.NamedTemporaryFile(dir=output.parent, prefix=".sysupgrade-", suffix=".tmp") as temp:
        with gzip.GzipFile(fileobj=temp, mode="wb", filename="", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT) as archive:
                for info, data in entries.values():
                    archive.addfile(info, io.BytesIO(data) if info.isfile() else None)
        temp.flush()
        os.fsync(temp.fileno())
        os.link(temp.name, output)  # Atomic publication; refuses any existing path, including symlinks.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup", type=Path)
    parser.add_argument("--device", choices=DEVICES, required=True)
    parser.add_argument("--identity-sha256", required=True, help="Independently verified device identity.secret digest")
    parser.add_argument("--uci", default="uci", help="Native libuci CLI")
    parser.add_argument("--apply-plan", type=Path, help="Previously reviewed preview JSON; explicit confirmation")
    parser.add_argument("--output", type=Path, help="New native tar.gz; never overwrites")
    args = parser.parse_args()
    require(bool(args.apply_plan) == bool(args.output), "--apply-plan and --output must be used together")
    executable = shutil.which(args.uci)
    require(executable, "Native libuci CLI unavailable; no regex-based UCI fallback")
    entries, plan = prepare(args.backup, args.device, args.identity_sha256, executable)
    if args.apply_plan:
        verify_plan(plan, json.loads(args.apply_plan.read_text()))
        write_backup(args.output, entries)
        print(json.dumps({"output": str(args.output), "sha256": sha256(args.output.read_bytes()), "device": args.device}))
    else:
        print(json.dumps(plan, indent=2))


if __name__ == "__main__":
    os.umask(0o077)
    try:
        main()
    except Rejected as error:
        print("Backup preparation refused: " + str(error), file=sys.stderr)
        sys.exit(1)
    except (OSError, ValueError, KeyError, StopIteration):
        # Never dump UCI exports, credentials, archive contents or private traceback locals.
        print("Backup preparation refused; check archive/layout, identity, hooks and the reviewed plan.", file=sys.stderr)
        sys.exit(1)
