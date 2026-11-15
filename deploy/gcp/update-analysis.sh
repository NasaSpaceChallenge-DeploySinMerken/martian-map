#!/usr/bin/env bash
set -euo pipefail

root=/opt/martian-analysis
bucket=martian-map-javier-2026-releases
pending="$root/release.pending.zip"
installed="$root/installed.sha256"
previous="$root/release.previous.zip"
current="$root/release.zip"

exec 9>"$root/update.lock"
flock -n 9 || exit 0
trap 'rm -f "$pending"' EXIT

gcloud storage cp "gs://$bucket/analysis-release.zip" "$pending" --quiet
unzip -tqq "$pending"
new_hash=$(sha256sum "$pending" | cut -d ' ' -f 1)
if [ -f "$installed" ] && [ "$(cat "$installed")" = "$new_hash" ]; then
  exit 0
fi

if [ -f "$current" ]; then cp "$current" "$previous"; fi
unzip -q -o "$pending" -d "$root/app"
if ! "$root/venv/bin/python" -m pip install --disable-pip-version-check -q -r "$root/app/analysis/requirements.txt"; then
  if [ -f "$previous" ]; then unzip -q -o "$previous" -d "$root/app"; fi
  echo 'No se pudieron instalar las dependencias del análisis' >&2
  exit 1
fi
systemctl restart martian-analysis
if ! curl --fail --silent --show-error --retry 15 --retry-delay 1 --retry-connrefused http://127.0.0.1:8000/health >/dev/null; then
  if [ -f "$previous" ]; then
    unzip -q -o "$previous" -d "$root/app"
    systemctl restart martian-analysis
  fi
  echo 'El análisis nuevo no respondió; se restauró la versión anterior' >&2
  exit 1
fi
mv "$pending" "$current"
printf '%s\n' "$new_hash" > "$installed"
echo "Análisis actualizado: $new_hash"
