#!/usr/bin/env bash
set -euo pipefail

install -m 0755 /tmp/update-analysis.sh /opt/martian-analysis/update-analysis.sh
install -m 0644 /tmp/martian-analysis-update.service /etc/systemd/system/martian-analysis-update.service
install -m 0644 /tmp/martian-analysis-update.timer /etc/systemd/system/martian-analysis-update.timer
systemctl daemon-reload
systemctl enable --now martian-analysis-update.timer
systemctl start martian-analysis-update.service
systemctl is-active martian-analysis-update.timer
