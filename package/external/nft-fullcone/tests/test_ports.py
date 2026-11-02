#!/usr/bin/env python3
"""Compile and exercise the prepared module's real IPv4/IPv6 port selectors.

Usage: test_ports.py path/to/prepared/src/nf_nat_fullcone.c
"""
from pathlib import Path
import subprocess
import sys
import tempfile

source = Path(sys.argv[1]).read_text()


def body(name):
    start = source.index("{", source.rindex("static uint16_t " + name + "("))
    depth = 0
    for end in range(start, len(source)):
        depth += (source[end] == "{") - (source[end] == "}")
        if not depth:
            return source[start:end + 1]
    raise AssertionError("Incomplete function: " + name)


prelude = r"""
#include <assert.h>
#include <arpa/inet.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint32_t u32;
typedef uint16_t u16;
typedef uint32_t __be32;
#define KERNEL_VERSION(a,b,c) (((a)<<16)|((b)<<8)|(c))
#define LINUX_VERSION_CODE KERNEL_VERSION(6,18,60)
#define NF_NAT_RANGE_PROTO_SPECIFIED 2
#define NF_NAT_RANGE_PROTO_RANDOM 4
#define NF_NAT_RANGE_PROTO_RANDOM_FULLY 16
#define be16_to_cpu ntohs
#define swap(a,b) do { u32 temporary = (a); (a) = (b); (b) = temporary; } while (0)
struct net { int unused; };
struct nf_conntrack_zone { int unused; };
union nf_inet_addr { u32 all[4]; };
union proto { struct { uint16_t port; } udp; };
struct nf_nat_range2 {
    u32 flags;
    union proto min_proto, max_proto, base_proto;
};
struct nat_mapping { int unused; };
struct nat_mapping6 { int unused; };
static bool occupied;
static unsigned probes, killed;
static struct nat_mapping mapping;
static struct nat_mapping6 mapping6;
static u32 get_random_u32(void) { return UINT32_MAX; }
static struct nat_mapping *get_mapping_by_ext_port(
    uint16_t port, __be32 ip, struct net *net, const struct nf_conntrack_zone *zone)
{ probes++; return occupied ? &mapping : NULL; }
static struct nat_mapping6 *get_mapping6_by_ext_port(
    uint16_t port, const union nf_inet_addr *ip, struct net *net,
    const struct nf_conntrack_zone *zone)
{ probes++; return occupied ? &mapping6 : NULL; }
static void kill_mapping(struct nat_mapping *entry) { assert(entry); killed++; }
static void kill_mapping6(struct nat_mapping6 *entry) { assert(entry); killed++; }
"""
program = prelude + """
static uint16_t find_appropriate_port(struct net *net,
    const struct nf_conntrack_zone *zone, uint16_t original_port,
    __be32 ext_ip, struct nf_nat_range2 *range)
""" + body("find_appropriate_port") + """
static uint16_t find_appropriate_port6(struct net *net,
    const struct nf_conntrack_zone *zone, uint16_t original_port,
    const union nf_inet_addr *ext_ip, struct nf_nat_range2 *range)
""" + body("find_appropriate_port6") + r"""
static uint16_t select_port(bool ipv6, uint16_t first, uint16_t last,
                           uint16_t original, u32 flags)
{
    union nf_inet_addr ip = {};
    struct nf_nat_range2 range = {
        .flags = flags, .min_proto.udp.port = htons(first),
        .max_proto.udp.port = htons(last)
    };
    return ipv6 ? find_appropriate_port6(NULL, NULL, original, &ip, &range)
                : find_appropriate_port(NULL, NULL, original, 0, &range);
}
int main(void)
{
    for (int ipv6 = 0; ipv6 < 2; ipv6++) {
        occupied = false;
        assert(select_port(ipv6, 0, 0, 53, 0) == 53);
        assert(select_port(ipv6, 10000, 10000, 999, 2) == 10000);
        assert(select_port(ipv6, 1024, 2047, 1500, 2) == 1500);
        assert(select_port(ipv6, 2047, 1024, 1500, 2) == 1500);
        assert(select_port(ipv6, 0, 65535, 1234, 2 | 4) == 65535);
        assert(select_port(ipv6, 0, 65535, 1234, 2 | 16) == 65535);
        occupied = true;
        probes = killed = 0;
        assert(select_port(ipv6, 0, 65535, 1234, 2) == 0);
        assert(probes >= 65536 && killed == 1);
        probes = killed = 0;
        assert(select_port(ipv6, 40000, 39990, 999, 2) == 39990);
        assert(probes == 12 && killed == 1);
    }
    puts("16 IPv4/IPv6 port selection cases passed.");
}
"""
with tempfile.TemporaryDirectory(prefix="fullcone-port-test-") as directory:
    path = Path(directory)
    (path / "test.c").write_text(program)
    subprocess.run(
        ["cc", "-std=gnu11", "-fsanitize=undefined", "-fno-sanitize-recover=all",
         "-o", str(path / "test"), str(path / "test.c")],
        check=True,
    )
    subprocess.run([str(path / "test")], check=True, timeout=10)
