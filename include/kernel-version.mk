# Use the default kernel version if the Makefile doesn't override it

LINUX_RELEASE?=1

LINUX_VERSION-3.18 = .43
LINUX_VERSION-4.4 = .76
LINUX_VERSION-4.9 = .39

LINUX_KERNEL_HASH-3.18.43 = 1236e8123a6ce537d5029232560966feed054ae31776fe8481dd7d18cdd5492c
LINUX_KERNEL_HASH-4.4.76 = 71e6fca6c4fcbd4f9d8b43a2ea599f20f2ed2e76af7eada2127e9eacfcb315a0
LINUX_KERNEL_HASH-4.9.39 = 6e8cf7bb936fa8ce720d08ddb4d05a5d37093e1f8d6fe0bf73789c9eef1cfa31

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
