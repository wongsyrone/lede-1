#!/bin/sh

umask 077
mkdir -p /var/run/nikki-service-guard /var/lock || exit 1
# The native Nikki init uses this lock too. Never invoke its reload while holding it.
exec 1000>/var/lock/procd_nikki.lock
flock -n 1000 || exit 75
exec /usr/bin/ucode -S /usr/share/nikki-service-guard/worker.uc "$@"
