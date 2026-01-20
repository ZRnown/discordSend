#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUTPUT_FILE="${1:-${ROOT_DIR}/business_code.txt}"

rg --files \
  -g 'src/**' \
  -g 'backend/**' \
  -g 'src-tauri/src/**' \
  -g '!**/node_modules/**' \
  -g '!**/target/**' \
  -g '!**/dist/**' \
  -g '!**/__pycache__/**' \
  -g '!backend/data/**' \
  "${ROOT_DIR}" \
  | sort \
  | while read -r file; do
      case "$file" in
        *.ts|*.tsx|*.js|*.jsx|*.py|*.rs)
          printf '\n===== %s =====\n' "${file#${ROOT_DIR}/}" >> "$OUTPUT_FILE"
          cat "$file" >> "$OUTPUT_FILE"
          ;;
        *)
          ;;
      esac
    done

echo "Wrote business code to: ${OUTPUT_FILE}"
