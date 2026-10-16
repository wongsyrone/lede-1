#!/bin/sh

service="$1"
shift
case "$service" in ''|*[!a-zA-Z0-9_-]*) exit 78 ;; esac
[ "$#" -gt 0 ] || exit 78

# procd has already placed this process in the service cgroup; exec keeps that identity.
attempt=0
while [ "$attempt" -lt 30 ]; do
	if /usr/libexec/nikki-service-guard gate "$service" >/dev/null 2>&1; then
		exec "$@"
	fi
	attempt=$((attempt + 1))
	sleep 1
done
logger -t nikki-service-guard "$service: startup gate timed out"
exit 78
