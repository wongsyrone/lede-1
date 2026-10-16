# OpenWrt Configuration Management Guide

## 1. Architectural Overview & Configuration Hierarchy

OpenWrt separates configuration management into two distinct, decoupled layers:

```
+-----------------------------------------------------------------------------------+
| Layer 1: Device-Level Configuration (Root Buildroot: .config & cfg/*)             |
|   - Scope: Target architecture, subtarget, target profile (device model)          |
|   - Packages: LuCI UI, ZeroTier, Nikki/Mihomo, proxy clients, network daemons     |
|   - Images: RootFS formats (squashfs, ext4, initramfs, gzip compression)          |
|   - Toolchain: Compiler versions, ccache, user-facing kernel options (CONFIG_KERNEL_*)|
+-----------------------------------------------------------------------------------+
                                          │
                                          ▼ (drives target architecture & packages)
+-----------------------------------------------------------------------------------+
| Layer 2: Kernel-Level Configuration (target/linux/)                               |
|   ├── generic/config-$(KERNEL_PATCHVER)                                           |
|   │     └── Global baseline: Kernel configuration applied across ALL targets      |
|   └── <target>/config-$(KERNEL_PATCHVER) (e.g. x86, mvebu, ath79, ramips)         |
|         └── Platform layer: SoC architecture, board buses, peripheral drivers     |
|         └── Subtarget layer (optional): <subtarget>/config-default                |
+-----------------------------------------------------------------------------------+
```

---

## 2. Layer 1: Device-Level Configuration (`cfg/`)

### 2.1 Why Use Minimal Defconfigs Instead of Full `.config` Files?

* **Legacy full `.config` files (~300 KB)**: Hardcode thousands of transitive dependencies, default booleans, and obsolete symbol names from historical builds. When upstream updates packages or bumps the kernel version, full `.config` files introduce merge conflicts, broken builds, and stale symbols.
* **Minimal defconfigs (~2-5 KB)**: Store **only** non-default choices explicitly requested by the maintainer. OpenWrt's Kconfig resolver (`make defconfig`) automatically calculates and resolves all prerequisites, shared libraries, and dependencies dynamically against the active toolchain and kernel.

The two Linksys profiles use the same default `mvebu/cortexa9` toolchain.
Their `gcc-13` filename suffixes are historical; GCC and binutils versions follow
the source tree's Kconfig defaults. Do not copy resolved version symbols from a
full `.config` into these profiles. `DEVEL` and `TOOLCHAINOPTS` remain enabled so
that their explicit choice to disable GDB is preserved.

### 2.2 Native Workflow for Device Configurations

All target configurations under `cfg/` should be maintained as minimal defconfigs using **100% native OpenWrt upstream tools** (no third-party or custom-maintained scripts required).

#### Step 1: Load a Configuration
```bash
cp cfg/x86_64 .config
make defconfig
```
`make defconfig` checks `Config.in` and feed definitions, strips deprecated/stale symbols, and computes the complete dependency tree.

#### Step 2: Make Changes

You can modify options using native OpenWrt mechanisms:

* **Config Fragment / Direct Append (No External `merge_config` Needed)**:
  Append desired symbols or feature deltas directly to `.config`:
  ```bash
  cat << 'EOF' >> .config
  CONFIG_PACKAGE_nikki=y
  CONFIG_PACKAGE_nikki-profile-default=y
  CONFIG_PACKAGE_luci-app-nikki=y
  CONFIG_PACKAGE_zerotier=y
  # CONFIG_PACKAGE_ipt2socks is not set
  CONFIG_PACKAGE_trojan=y
  EOF
  ```
* **Interactive TUI**:
  ```bash
  make menuconfig
  ```
* **Native Set Algebra (`scripts/kconfig.pl`)**:
  OpenWrt provides `scripts/kconfig.pl` upstream since 2006 for config merging and diffing:
  ```bash
  # Merge a fragment over a base config:
  ./scripts/kconfig.pl + base_defconfig fragment.config > .config
  ```

#### Step 3: Resolve & Normalize
Whenever changes are made, run:
```bash
make defconfig
```
OpenWrt's Kconfig resolver reads the appended delta, evaluates all dependency graphs, discards invalid or superseded entries, and writes out a fully resolved, valid `.config`.

#### Step 4: Export to Minimal Defconfig
Export the normalized minimal delta back into `cfg/`:
```bash
./scripts/diffconfig.sh > cfg/x86_64
```

For `x86_64`, library packages are selected through application dependencies
instead of being pinned in the profile. `diffconfig.sh` may write these selections
back, so review its output after removing an application. Check package metadata
and install rules, including libraries outside the Libraries category, remove
only redundant library selections, and use `make defconfig` to verify the
resulting package list and unchanged target, kernel, and toolchain settings.

The same review applies to automatically selected applications, modules and
package suboptions, not just libraries. Compare every symbol in the complete
normalized configuration before and after pruning against the same source and
feed revisions; an unchanged package count alone is not sufficient. Keep
functional removals separate from this behavior-preserving cleanup.

---

## 3. Layer 2: Kernel-Level Configuration (`target/linux/`)

### 3.1 Kernel Version Resolution (`KERNEL_PATCHVER`)

Kernel versions are **never hardcoded**. Instead, OpenWrt dynamically resolves the active kernel version per target:

1. Each hardware target defines its kernel branch in `target/linux/<target>/Makefile`:
   ```makefile
   KERNEL_PATCHVER:=6.6
   ```
2. The build system expands `$(KERNEL_PATCHVER)` to locate:
   * **Global Baseline**: `target/linux/generic/config-$(KERNEL_PATCHVER)`
     * Baseline kernel configuration shared across all targets.
     * Contains generic Linux subsystems (netfilter core, cgroups, cryptographic algorithms, standard filesystems).
   * **Platform Specific**: `target/linux/<target>/config-$(KERNEL_PATCHVER)`
     * SoC-specific CPU extensions, on-chip buses (PCIe, MDIO), ethernet MACs, and wireless drivers.
   * **Subtarget Specific (optional)**: `target/linux/<target>/<subtarget>/config-default`
     * Finer-grained overrides for specific hardware revisions or sub-families.

During `make target/linux/compile`, OpenWrt's `scripts/kconfig.pl` merges `generic/config-$(KERNEL_PATCHVER)` and `<target>/config-$(KERNEL_PATCHVER)` to synthesize the final kernel `.config`.

### 3.2 Modifying Platform-Specific Kernel Options

Do **NOT** manually edit generated `build_dir/.../linux-*/.config`. Use the standard OpenWrt lifecycle:

#### Step 1: Configure the Buildroot for the Target
```bash
cp cfg/<target> .config
make defconfig
```

#### Step 2: Launch Kernel Menuconfig
```bash
make kernel_menuconfig
```
This prepares the combined kernel config, opens the Linux kernel kconfig dialog, and saves the modified state.

#### Step 3: Refresh and Split Kernel Configurations
```bash
make target/linux/refresh
```
OpenWrt's build system executes `scripts/kconfig.pl` to automatically diff the changes:
* Any platform-specific kernel symbols are automatically saved to `target/linux/<target>/config-$(KERNEL_PATCHVER)`.
* The generic base remains untouched unless explicitly instructed.

### 3.3 Modifying Global Kernel Options (All Targets)

If a kernel configuration must take effect globally across **all** hardware platforms (e.g., enabling an eBPF feature or wireguard crypto):

1. Identify the target's kernel version:
   ```bash
   KERNEL_VER=$(grep -m1 '^KERNEL_PATCHVER:=' target/linux/<target>/Makefile | cut -d= -f2)
   ```
2. Append the required kernel symbol to `target/linux/generic/config-${KERNEL_VER}`:
   ```bash
   echo "CONFIG_BPF_JIT=y" >> target/linux/generic/config-${KERNEL_VER}
   ```
3. Run `make target/linux/refresh` on any target to re-sort and validate the symbol hierarchy across all targets.

---

## 4. Native Tooling Summary (Zero External Tools to Maintain)

All tools required for this workflow are **native to upstream OpenWrt**:

| Tool | Upstream Location | Primary Purpose | Standard Usage |
| :--- | :--- | :--- | :--- |
| **diffconfig** | `scripts/diffconfig.sh` | Dumps minimal defconfig against default | `./scripts/diffconfig.sh > cfg/<target>` |
| **defconfig** | `make defconfig` | Merges fragments, resolves dependencies, cleans stale symbols | `cat delta >> .config && make defconfig` |
| **kconfig.pl** | `scripts/kconfig.pl` | Native Perl set operations (merge `+`, diff `>`, subtract `-`) | `./scripts/kconfig.pl + base delta > .config` |
| **kernel_menuconfig** | `make kernel_menuconfig` | Interactive Linux kernel Kconfig TUI | `make kernel_menuconfig` |
| **linux/refresh** | `make target/linux/refresh` | Splits & writes back kernel configs to target/generic | `make target/linux/refresh` |

---

## 5. Migration Guide: Upgrading Legacy `cfg/*` Files

When migrating historical ~300 KB configs to modern minimal defconfigs:

1. **Load Existing Target Config**:
   ```bash
   cp cfg/<target> .config
   ```
2. **Apply Delta Fragment (Retire Legacy Redirection; Keep Standalone Trojan)**:
   ```bash
   cat << 'EOF' >> .config
   # CONFIG_PACKAGE_ipt2socks is not set
   # CONFIG_PACKAGE_transocks-wong is not set
   CONFIG_PACKAGE_trojan=y
   # CONFIG_PACKAGE_v2ray is not set
   # CONFIG_PACKAGE_pdnsd is not set
   CONFIG_PACKAGE_nikki=y
   CONFIG_PACKAGE_nikki-profile-default=y
   CONFIG_PACKAGE_luci-app-nikki=y
   CONFIG_PACKAGE_zerotier=y
   EOF
   ```
   Standalone Trojan remains a SOCKS upstream for Mihomo. Keep its configuration and
   enabled state; the default profile package extends Nikki's existing scoped bypass
   with `services/trojan`. Do not bypass the entire root UID or restore an old Trojan
   binary/init script over the version shipped in the new firmware. The profile package
   enables cgroups and socket cgroup support required by Nikki's process bypasses.
3. **Re-expand against Active Kernel & Toolchain**:
   ```bash
   make defconfig
   ```
4. **Generate Minimal Target Defconfig**:
   ```bash
   ./scripts/diffconfig.sh > cfg/<target>
   ```
