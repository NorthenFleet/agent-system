#!/bin/zsh
# Private wrapper for GenOffice's renderer-backed exports. The packaged CLI
# honors GENOFFICE_APP_BIN, so this keeps Electron's user-data profile inside
# the Sidecar's 0700 runtime home instead of the interactive desktop profile.

set -euo pipefail
umask 077

app_binary="${GENOFFICE_APP_BINARY:-/Applications/GenOffice.app/Contents/MacOS/GenOffice}"
sidecar_home="${GENOFFICE_SIDECAR_HOME:-}"
if [[ -z "$sidecar_home" || ! -d "$sidecar_home" || -L "$sidecar_home" || ! -x "$app_binary" ]]; then
  print -u2 -- "GenOffice Sidecar: isolated headless export configuration is unavailable"
  exit 78
fi

user_data_dir="$sidecar_home/electron-user-data"
if [[ -L "$user_data_dir" ]]; then
  print -u2 -- "GenOffice Sidecar: isolated Electron profile is unsafe"
  exit 78
fi
/bin/mkdir -p "$user_data_dir"
/bin/chmod 700 "$user_data_dir"
if [[ ! -d "$user_data_dir" || "$(/usr/bin/stat -f '%Lp' "$user_data_dir")" != "700" ]]; then
  print -u2 -- "GenOffice Sidecar: isolated Electron profile permissions are unsafe"
  exit 78
fi

exec "$app_binary" "--user-data-dir=$user_data_dir" "$@"
