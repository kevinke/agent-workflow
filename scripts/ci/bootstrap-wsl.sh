#!/bin/bash
# Used only inside a freshly imported, disposable CI distro, as root.
set -euo pipefail
snapshot="$1"
definition="$2"
shift 2
test "$(id -u)" = 0
test ! -e /etc/agent-workflow-ci.json
# Replace all inherited sources; signed package resolution uses one fixed date.
rm -f /etc/apt/sources.list /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources
cat > /etc/apt/sources.list.d/ubuntu.sources <<EOF
Types: deb
URIs: https://snapshot.ubuntu.com/ubuntu/$snapshot/
Suites: noble noble-updates noble-security
Components: main universe
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
EOF
apt-get update --error-on=any
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "$@"
useradd --create-home --uid 2000 --shell /bin/bash ci
cat > /etc/wsl.conf <<'EOF'
[user]
default=ci
[boot]
systemd=false
EOF
printf '{"definition":"%s","snapshot":"%s"}\n' "$definition" "$snapshot" > /etc/agent-workflow-ci.json
dpkg-query -W -f='${Package}\t${Version}\n' > /etc/agent-workflow-ci-packages.txt
apt-get clean
# These are owned by this new CI distro; no workspace has been mounted by us.
# WSLg mounts a read-only X11 socket tree here. Never traverse/delete mounted
# filesystems. Its empty mount directory is allowed in the exported tar;
# socket contents are still refused by the cache guard.
find /tmp -xdev -mindepth 1 ! -path /tmp/.X11-unix ! -path '/tmp/.X11-unix/*' -delete
find /var/tmp -xdev -mindepth 1 -delete
rm -f /root/.bash_history /home/ci/.bash_history
# The reviewed official base has an empty root/.ssh directory. Remove only
# that empty directory: any unexpected credential content stops the build.
if [ -d /root/.ssh ]; then rmdir /root/.ssh; fi
