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
URIs: https://archive.ubuntu.com/ubuntu
Suites: noble noble-updates
Components: main universe
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
Snapshot: $snapshot

Types: deb
URIs: https://security.ubuntu.com/ubuntu
Suites: noble-security
Components: main universe
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
Snapshot: $snapshot
EOF
apt-get update --error-on=any --snapshot "$snapshot"
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends --snapshot "$snapshot" "$@"
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
find /tmp /var/tmp -mindepth 1 -delete
rm -f /root/.bash_history /home/ci/.bash_history
# The reviewed official base has an empty root/.ssh directory. Remove only
# that empty directory: any unexpected credential content stops the build.
if [ -d /root/.ssh ]; then rmdir /root/.ssh; fi
