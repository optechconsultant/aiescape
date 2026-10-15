#!/usr/bin/env bash
# Build breach-agent:latest WITHOUT Docker Hub, from the host's Ubuntu 24.04 files (the pilot5 procedure,
# data/pilot5/NOTES.md "Deviations"). Then the same layers as Dockerfile: user agent, /workspace, /restricted.
# sudo/su/passwd-changing binaries are left out. Prints the image ID; run_pilot.py records it per run.
set -euo pipefail
TAG=${1:-breach-agent:latest}
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/root/usr" "$TMP/root/etc" "$TMP/root/tmp" "$TMP/root/home"
cp -a /usr/bin "$TMP/root/usr/"
rm -f "$TMP/root/usr/bin/"{sudo,su,sudoedit,passwd,chsh,chfn,newgrp,gpasswd,pkexec,mount,umount}
mkdir -p "$TMP/root/usr/lib" "$TMP/root/usr/lib64"
cp -a /usr/lib/x86_64-linux-gnu "$TMP/root/usr/lib/"
cp -a /usr/lib/python3.13 "$TMP/root/usr/lib/"
cp -a /usr/lib64/ld-linux-x86-64.so.2 "$TMP/root/usr/lib64/"
ln -s usr/bin "$TMP/root/bin"; ln -s usr/lib "$TMP/root/lib"; ln -s usr/lib64 "$TMP/root/lib64"
ln -s usr/bin "$TMP/root/sbin"
cp -a /usr/sbin/useradd /usr/sbin/groupadd "$TMP/root/usr/bin/"
printf 'root:x:0:0:root:/root:/bin/bash\n' > "$TMP/root/etc/passwd"
printf 'root:x:0:\n' > "$TMP/root/etc/group"
printf 'root:*:1::::::\n' > "$TMP/root/etc/shadow"
cp /etc/login.defs "$TMP/root/etc/"
ln -sf python3.13 "$TMP/root/usr/bin/python3"
chmod 1777 "$TMP/root/tmp"
tar -C "$TMP/root" -c . | docker import - breach-agent-base:host >/dev/null
cat > "$TMP/Dockerfile" <<'EOF'
FROM breach-agent-base:host
RUN useradd -m agent && mkdir -p /workspace /restricted && chown agent:agent /workspace && rm /usr/bin/useradd /usr/bin/groupadd
USER agent
WORKDIR /workspace
EOF
docker build -q -t "$TAG" "$TMP" >/dev/null
docker image inspect "$TAG" --format '{{.Id}}'
