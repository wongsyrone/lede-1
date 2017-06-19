# Use the default kernel version if the Makefile doesn't override it

LINUX_RELEASE?=1

LINUX_VERSION-3.18 = .43
LINUX_VERSION-4.4 = .73
LINUX_VERSION-4.9 = .33

LINUX_KERNEL_HASH-3.18.43 = 1236e8123a6ce537d5029232560966feed054ae31776fe8481dd7d18cdd5492c
LINUX_KERNEL_HASH-4.4.73 = 008562b5f14ba383efca38dae637d4ca50d0e19491a30a63e424ea00f67d44b6
LINUX_KERNEL_HASH-4.9.33 = f5ca2ba3d6ab5130bcca9c693aecafbd9813db11d450bd74ac7305bc46544c34

ifdef KERNEL_PATCHVER
  LINUX_VERSION:=$(KERNEL_PATCHVER)$(strip $(LINUX_VERSION-$(KERNEL_PATCHVER)))
endif

split_version=$(subst ., ,$(1))
merge_version=$(subst $(space),.,$(1))
KERNEL_BASE=$(firstword $(subst -, ,$(LINUX_VERSION)))
KERNEL=$(call merge_version,$(wordlist 1,2,$(call split_version,$(KERNEL_BASE))))
KERNEL_PATCHVER ?= $(KERNEL)

# disable the md5sum check for unknown kernel versions
LINUX_KERNEL_HASH:=$(LINUX_KERNEL_HASH-$(strip $(LINUX_VERSION)))
LINUX_KERNEL_HASH?=x
