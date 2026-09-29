#!/usr/bin/env bash
# Dumps the production Postgres database to a timestamped, gzip-compressed
# file. Free by design: no backup service, just pg_dump + gzip. Intended to
# run from .github/workflows/backup.yml (daily, GitHub Actions artifact
# storage) or any cron with DATABASE_URL exported.
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL must be set (postgresql://user:pass@host:port/dbname)}"

OUT_DIR="${BACKUP_OUT_DIR:-./backups}"
mkdir -p "$OUT_DIR"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
out_file="${OUT_DIR}/pappu_crm_${timestamp}.sql.gz"

pg_dump --no-owner --no-privileges "$DATABASE_URL" | gzip > "$out_file"

echo "Backup written to $out_file ($(du -h "$out_file" | cut -f1))"
