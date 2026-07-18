#!/usr/bin/env bash
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_ROOT="${FINANCE_BACKUP_ROOT:-$BACKEND_DIR/backups/finance}"
STAMP="$(date +%Y%m%d-%H%M%S)"
TARGET="$BACKUP_ROOT/$STAMP"
SQLITE_SOURCE="${FINANCE_SQLITE_SOURCE:-$BACKEND_DIR/data/finance.db}"

mkdir -p "$TARGET"
if [ -f "$SQLITE_SOURCE" ]; then
  sqlite3 "$SQLITE_SOURCE" ".backup '$TARGET/finance.db'"
  sqlite3 "$TARGET/finance.db" "PRAGMA integrity_check" > "$TARGET/sqlite-integrity.txt"
fi

if [ -n "${DATABASE_URL:-}" ] && [[ "$DATABASE_URL" == postgresql* ]]; then
  pg_dump --format=custom --no-owner --file="$TARGET/postgresql.dump" "$DATABASE_URL"
fi

if [ -n "${FINANCE_OBSIDIAN_DIR:-}" ] && [ -d "$FINANCE_OBSIDIAN_DIR" ]; then
  tar -czf "$TARGET/obsidian-finance.tgz" -C "$FINANCE_OBSIDIAN_DIR" .
fi

find "$TARGET" -type f -maxdepth 1 -exec shasum -a 256 {} \; > "$TARGET/SHA256SUMS"
chmod -R go-rwx "$TARGET"
printf '%s\n' "$TARGET"
