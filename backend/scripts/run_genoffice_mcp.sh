#!/bin/zsh
# Phase G1 GenOffice Sidecar launcher. It intentionally has a smaller
# environment than 3021 and only exposes the local, read-only MCP surface.

set -euo pipefail
umask 077

runtime_env="${GENOFFICE_RUNTIME_ENV_FILE:-./data/genoffice-runtime.env}"
if [[ ! -r "$runtime_env" || -L "$runtime_env" ]]; then
  print -u2 -- "GenOffice Sidecar: dedicated runtime configuration is missing or unsafe"
  exit 0
fi

# Do not source 3021's general .env here: it contains credentials unrelated to
# the Sidecar. This small parser accepts only the non-secret G1 settings and
# leaves the token itself in its protected file.
while IFS= read -r line || [[ -n "$line" ]]; do
  line="${line%$'\r'}"
  [[ -z "$line" || "$line" == \#* ]] && continue
  if [[ "$line" != *=* ]]; then
    print -u2 -- "GenOffice Sidecar: invalid dedicated runtime configuration"
    exit 0
  fi
  key="${line%%=*}"
  value="${line#*=}"
  case "$key" in
    GENOFFICE_INTEGRATION_ENABLED|GENOFFICE_MCP_URL|GENOFFICE_MCP_TOKEN_FILE|GENOFFICE_BINARY_PATH|GENOFFICE_REQUIRED_CHANNEL|GENOFFICE_MIN_SUPPORTED_VERSION|GENOFFICE_MAX_TESTED_VERSION|GENOFFICE_MIN_SUPPORTED_MCP_VERSION|GENOFFICE_MAX_TESTED_MCP_VERSION|GENOFFICE_CONNECT_TIMEOUT_SECONDS|GENOFFICE_TOOL_TIMEOUT_SECONDS|GENOFFICE_MAX_INPUT_BYTES|GENOFFICE_MAX_RENDER_BYTES|GENOFFICE_SIDECAR_HOME|GENOFFICE_SIDECAR_TMPDIR|GENOFFICE_G1_PILOT_GATE)
      export "${key}=${value}"
      ;;
    *)
      print -u2 -- "GenOffice Sidecar: unsupported dedicated runtime setting"
      exit 0
      ;;
  esac
done < "$runtime_env"

case "${GENOFFICE_INTEGRATION_ENABLED:-false}" in
  1|true|TRUE|yes|YES|on|ON) ;;
  *)
    print -u2 -- "GenOffice Sidecar: disabled by GENOFFICE_INTEGRATION_ENABLED"
    exit 0
    ;;
esac

if [[ -n "${GENOFFICE_ALLOWED_ROOTS:-}" ]]; then
  print -u2 -- "GenOffice Sidecar: GENOFFICE_ALLOWED_ROOTS must be unset in Phase G1"
  exit 0
fi

ensure_private_dir() {
  local directory="$1"
  if [[ -L "$directory" ]]; then
    print -u2 -- "GenOffice Sidecar: private runtime directory is unsafe"
    exit 0
  fi
  /bin/mkdir -p "$directory"
  /bin/chmod 700 "$directory"
  local mode owner
  mode="$(/usr/bin/stat -f '%Lp' "$directory")"
  owner="$(/usr/bin/stat -f '%u' "$directory")"
  if [[ ! -d "$directory" || "$mode" != "700" || "$owner" != "$EUID" ]]; then
    print -u2 -- "GenOffice Sidecar: private runtime directory permissions are unsafe"
    exit 0
  fi
}

sidecar_home="${GENOFFICE_SIDECAR_HOME:-./data/genoffice-sidecar-home}"
sidecar_tmp="${GENOFFICE_SIDECAR_TMPDIR:-./data/genoffice-sidecar-tmp}"
ensure_private_dir "$sidecar_home"
ensure_private_dir "$sidecar_tmp"
ensure_private_dir "$sidecar_home/electron-user-data"

# launchd opens the configured stdout/stderr file before this script starts.
# Its parent is the private TMP directory; make the file itself private too so
# random FileStore URLs and converter diagnostics do not land in a world-readable
# workspace log.
sidecar_log="$sidecar_tmp/genoffice-mcp.log"
if [[ -L "$sidecar_log" || ( -e "$sidecar_log" && ! -f "$sidecar_log" ) ]]; then
  print -u2 -- "GenOffice Sidecar: private log file is unsafe"
  exit 0
fi
/usr/bin/touch "$sidecar_log"
/bin/chmod 600 "$sidecar_log"
if [[ ! -f "$sidecar_log" || "$(/usr/bin/stat -f '%Lp' "$sidecar_log")" != "600" || "$(/usr/bin/stat -f '%u' "$sidecar_log")" != "$EUID" ]]; then
  print -u2 -- "GenOffice Sidecar: private log file permissions are unsafe"
  exit 0
fi

token_file="${GENOFFICE_MCP_TOKEN_FILE:-}"
if [[ -z "$token_file" || ! -f "$token_file" || -L "$token_file" ]]; then
  print -u2 -- "GenOffice Sidecar: protected token file is unavailable"
  exit 0
fi
token_mode="$(/usr/bin/stat -f '%Lp' "$token_file")"
token_owner="$(/usr/bin/stat -f '%u' "$token_file")"
case "$token_mode" in
  400|600) ;;
  *)
    print -u2 -- "GenOffice Sidecar: protected token file permissions are unsafe"
    exit 0
    ;;
esac
if [[ "$token_owner" != "$EUID" ]]; then
  print -u2 -- "GenOffice Sidecar: protected token file ownership is unsafe"
  exit 0
fi
token="$(<"$token_file")"
if (( ${#token} < 32 )); then
  print -u2 -- "GenOffice Sidecar: protected token is invalid"
  exit 0
fi

binary="${GENOFFICE_BINARY_PATH:-/Applications/GenOffice.app/Contents/Resources/cli/genoffice}"
bundle="${binary%/Contents/Resources/cli/genoffice}"
if [[ "$bundle" == "$binary" || ! -x "$binary" || ! -d "$bundle" ]]; then
  print -u2 -- "GenOffice Sidecar: configured GenOffice bundle is unavailable"
  exit 0
fi
headless_wrapper="${0:A:h}/run_genoffice_headless.sh"
if [[ ! -x "$headless_wrapper" || ! -x "$bundle/Contents/MacOS/GenOffice" ]]; then
  print -u2 -- "GenOffice Sidecar: isolated headless export wrapper is unavailable"
  exit 0
fi

# These checks run in the host launchd environment. Never replace them with a
# sandbox-only diagnostic, remove quarantine, disable Gatekeeper, or re-sign
# the bundle to force a start.
if ! /usr/bin/codesign --verify --deep --strict --verbose=2 "$bundle" >&2; then
  print -u2 -- "GenOffice Sidecar: bundle signature verification failed; not starting"
  exit 0
fi
# A generic valid/notarized bundle is not sufficient: bind the launcher to the
# official G1 publisher as well.  Keep these values in code review alongside
# the pinned release version, rather than accepting an environment override.
if ! signing_info="$(/usr/bin/codesign -dv --verbose=4 "$bundle" 2>&1)"; then
  print -u2 -- "GenOffice Sidecar: bundle signing identity is unreadable; not starting"
  exit 0
fi
if [[ "$signing_info" != *"Identifier=com.genoffice.app"* || "$signing_info" != *"TeamIdentifier=TC7CATC2Z2"* ]]; then
  print -u2 -- "GenOffice Sidecar: bundle signing identity is not the approved GenOffice publisher; not starting"
  exit 0
fi
if ! /usr/sbin/spctl --assess --type execute --verbose=4 "$bundle" >&2; then
  print -u2 -- "GenOffice Sidecar: Gatekeeper assessment failed; not starting"
  exit 0
fi
if ! /usr/bin/xcrun stapler validate "$bundle" >&2; then
  print -u2 -- "GenOffice Sidecar: stapled notarization validation failed; not starting"
  exit 0
fi

# env -i prevents DB URLs, JWT secrets, cloud keys, proxy variables, and the
# general 3021 .env from reaching an Electron/Node child process.
exec /usr/bin/env -i \
  HOME="$sidecar_home" \
  TMPDIR="$sidecar_tmp" \
  XDG_CONFIG_HOME="$sidecar_home/.config" \
  XDG_CACHE_HOME="$sidecar_home/.cache" \
  XDG_DATA_HOME="$sidecar_home/.local/share" \
  PATH="/usr/bin:/bin:/usr/sbin:/sbin" \
  LANG="${LANG:-en_US.UTF-8}" \
  GENOFFICE_APP_BIN="$headless_wrapper" \
  GENOFFICE_APP_BINARY="$bundle/Contents/MacOS/GenOffice" \
  GENOFFICE_SIDECAR_HOME="$sidecar_home" \
  GENOFFICE_MCP_TOKEN="$token" \
  "$binary" mcp --http 3094 --host 127.0.0.1
