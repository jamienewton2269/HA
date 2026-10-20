#!/bin/sh
# JNS HA-General VM905 fan audit v1 - READ ONLY
# Only writes /config/jns_fan_diagnostics.txt; never alters HA configuration or equipment.
set -u
BASE=/config
OUT="$BASE/jns_fan_diagnostics.txt"
[ -d "$BASE" ] || { echo "ERROR: /config not found; run inside HA-General Terminal & SSH."; exit 1; }
umask 077
: > "$OUT" || { echo "Cannot write $OUT"; exit 1; }
exec > "$OUT" 2>&1
echo "JNS FAN DIAGNOSTIC v1 | $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "READ ONLY | Target: HA-General VM905 | Sensitive data should be reviewed before sharing."
echo "================================================================"
echo
echo "=== HA CONFIGURATION STRUCTURE ==="
for f in configuration.yaml automations.yaml scripts.yaml scenes.yaml; do
  if [ -f "$BASE/$f" ]; then
    ls -l "$BASE/$f" | sed 's/  */ /g'
  else echo "$f: absent"; fi
done
find "$BASE" -maxdepth 3 -type f \( -iname '*fan*.yaml' -o -iname '*fan*.yml' -o -iname '*wc*.yaml' -o -iname '*bath*.yaml' -o -iname '*testing*.yaml' \) 2>/dev/null | head -60
echo
echo "=== PACKAGE / DASHBOARD INCLUDES ==="
if [ -f "$BASE/configuration.yaml" ]; then
  grep -Ein '(^|[[:space:]])(packages|automation|lovelace|dashboard|timer|history|logbook|recorder):|include' "$BASE/configuration.yaml" | head -60
fi
echo
echo "=== MATCHING ENTITY REGISTRY RECORDS ==="
if command -v jq >/dev/null 2>&1 && [ -r "$BASE/.storage/core.entity_registry" ]; then
  jq -r '.data.entities[] | select(((.entity_id // "")+" "+(.name // "")+" "+(.original_name // "")+" "+(.platform // "")+" "+(.unique_id // "")) | test("fan|extract|bath|humid|pir|motion|downstairs_wc|wc_";"i")) | [.entity_id, (.name // ""), (.original_name // ""), (.platform // ""), (.disabled_by // "")] | @tsv' "$BASE/.storage/core.entity_registry" | head -130
else
  echo "jq or readable entity registry unavailable. No raw registry dumped."
fi
echo
echo "=== MATCHING DEVICE REGISTRY RECORDS ==="
if command -v jq >/dev/null 2>&1 && [ -r "$BASE/.storage/core.device_registry" ]; then
  jq -r '.data.devices[] | select(((.name // "")+" "+(.name_by_user // "")+" "+(.model // "")) | test("fan|extract|bath|humid|pir|motion|wc";"i")) | [.id, (.name_by_user // ""), (.name // ""), (.model // "")] | @tsv' "$BASE/.storage/core.device_registry" | head -70
fi
echo
echo "=== AUTOMATIONS MATCHING FAN / PIR / HUMIDITY (context) ==="
if [ -f "$BASE/automations.yaml" ]; then
  grep -Ein -B 14 -A 26 'fan|extract|bathroom|humidity|humid|wc|pir|motion' "$BASE/automations.yaml" | head -550
else echo "automations.yaml absent"; fi
echo
echo "=== MATCHING PACKAGE / DASHBOARD FILE EXCERPTS ==="
find "$BASE/packages" "$BASE/dashboards" -maxdepth 2 -type f \( -name '*.yaml' -o -name '*.yml' \) 2>/dev/null | while IFS= read -r file; do
  if grep -Eiq 'fan|extract|bathroom|humidity|humid|downstairs_wc|pir' "$file"; then
    echo "--- $file ---"
    grep -Ein -B 8 -A 22 'fan|extract|bathroom|humidity|humid|downstairs_wc|pir' "$file" | head -220
  fi
done
echo
echo "=== RELEVANT STORAGE DASHBOARDS (names only) ==="
find "$BASE/.storage" -maxdepth 1 -type f \( -name 'lovelace*' -o -name 'core.config_entries' \) 2>/dev/null | sed 's#^/config/##' | head -40
echo
echo "=== RLM / NATIVE TIMER / COUNTER REFERENCES ==="
grep -RinE -B 3 -A 6 'rlm\.|timer\.|input_number\.|input_datetime\.|counter\.|history_stats|logbook' "$BASE/automations.yaml" "$BASE/packages" "$BASE/dashboards" 2>/dev/null | grep -Ei 'fan|wc|bath|humid|timer|rlm|counter|input_|history_stats|logbook|^--$' | head -180
echo
echo "=== HA SYSTEM COMMAND AVAILABILITY ==="
command -v ha || true
command -v jq || true
echo
echo "END OF REPORT"
