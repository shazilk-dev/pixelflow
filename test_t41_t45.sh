#!/usr/bin/env bash
# T4.1 + T4.5 verification script
# Run from repo root with: bash test_t41_t45.sh
# Prereq: docker compose up --build is already running

set -euo pipefail
API="http://localhost:8000"
IMGS="./test_imgs"

# ── helpers ────────────────────────────────────────────────────────────────────
log() { echo "[$(date +%T)] $*"; }

submit_batch() {
    local transforms=$1
    local fd_args=""
    for f in "$IMGS"/test_*.jpg; do
        fd_args="$fd_args -F images=@$f"
    done
    curl -s -X POST "$API/api/process-batch" \
        $fd_args \
        -F "transformations=$transforms" \
        -F "num_workers=3" | python3 -m json.tool
}

wait_for_batch() {
    local batch_id=$1
    log "Streaming SSE for batch $batch_id…"
    curl -s -N "$API/api/stream/$batch_id" | while IFS= read -r line; do
        echo "$line"
        if echo "$line" | grep -q '"event": "batch_complete"'; then
            echo "--- batch_complete received ---"
            break
        fi
    done
}

# ═══════════════════════════════════════════════════════════════════════════════
# T4.1 — scale test
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "══════════════════════════════════════"
echo " T4.1  Scale worker=5"
echo "══════════════════════════════════════"

log "Scaling generic worker to 5 replicas…"
docker compose up --scale worker=5 -d

log "Waiting 5s for workers to register heartbeats…"
sleep 5

log "GET /api/workers/status"
WORKER_RESP=$(curl -s "$API/api/workers/status")
echo "$WORKER_RESP" | python3 -m json.tool
WORKER_COUNT=$(echo "$WORKER_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['workers']))")
echo ""
echo "  API worker count : $WORKER_COUNT"
echo "  Expected (named) : 3  (generic workers process tasks but have no WORKER_ID — not in heartbeat registry)"
echo "  UI card cap      : 3  (MAX_VISIBLE_WORKERS constant in dashboard/[batchId]/page.tsx)"

# ═══════════════════════════════════════════════════════════════════════════════
# T4.5 — Amdahl's Law
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "══════════════════════════════════════"
echo " T4.5  Amdahl's Law — 1 worker vs 3"
echo "══════════════════════════════════════"
TRANSFORMS='["resize","grayscale","blur","sharpen","watermark"]'

# --- 1-worker run ---
log "Stopping worker_2 and worker_3 for 1-worker run…"
docker compose stop worker_2 worker_3
sleep 3

log "Submitting 12-image batch (1 worker)…"
RESP_1=$(curl -s -X POST "$API/api/process-batch" \
    $(for f in "$IMGS"/test_*.jpg; do echo "-F images=@$f"; done) \
    -F "transformations=$TRANSFORMS" \
    -F "num_workers=1")
BATCH_1=$(echo "$RESP_1" | python3 -c "import sys,json; print(json.load(sys.stdin)['batch_id'])")
log "batch_id = $BATCH_1"

log "Waiting for batch_complete…"
COMPLETE_1=$(curl -s -N "$API/api/stream/$BATCH_1" | while IFS= read -r line; do
    if echo "$line" | grep -q "batch_complete"; then
        echo "$line"
        break
    fi
done)
ACTUAL_MS_1=$(echo "$COMPLETE_1" | sed 's/.*"actual_ms": *\([0-9]*\).*/\1/')
log "1-worker actual_ms = $ACTUAL_MS_1"

# --- 3-worker run ---
log "Restarting worker_2 and worker_3 for 3-worker run…"
docker compose start worker_2 worker_3
sleep 5

log "Submitting 12-image batch (3 workers)…"
RESP_3=$(curl -s -X POST "$API/api/process-batch" \
    $(for f in "$IMGS"/test_*.jpg; do echo "-F images=@$f"; done) \
    -F "transformations=$TRANSFORMS" \
    -F "num_workers=3")
BATCH_3=$(echo "$RESP_3" | python3 -c "import sys,json; print(json.load(sys.stdin)['batch_id'])")
log "batch_id = $BATCH_3"

log "Waiting for batch_complete…"
COMPLETE_3=$(curl -s -N "$API/api/stream/$BATCH_3" | while IFS= read -r line; do
    if echo "$line" | grep -q "batch_complete"; then
        echo "$line"
        break
    fi
done)
ACTUAL_MS_3=$(echo "$COMPLETE_3" | sed 's/.*"actual_ms": *\([0-9]*\).*/\1/')
log "3-worker actual_ms = $ACTUAL_MS_3"

echo ""
echo "══════════════════════════════════════"
echo " T4.5  Results"
echo "══════════════════════════════════════"
python3 - <<PYEOF
ms1 = $ACTUAL_MS_1
ms3 = $ACTUAL_MS_3
speedup = ms1 / ms3
print(f"  1-worker time  : {ms1:,} ms  ({ms1/1000:.1f}s)")
print(f"  3-worker time  : {ms3:,} ms  ({ms3/1000:.1f}s)")
print(f"  Speedup factor : {speedup:.2f}×")
if 2.0 <= speedup <= 3.5:
    print("  ✅ Amdahl's Law: speedup is in expected 2–3× range")
elif speedup < 2.0:
    print("  ⚠️  Speedup below 2× — possible CPU bottleneck (fewer cores than workers?)")
else:
    print("  ⚠️  Speedup above 3.5× — check if actual_ms captured correctly")
PYEOF

log "Checking results page benchmark for batch $BATCH_3…"
curl -s "$API/api/batch/$BATCH_3/results" | python3 -c "
import sys, json
d = json.load(sys.stdin)
b = d['benchmark']
print(f\"  sequential_estimate_ms : {b['sequential_estimate_ms']:,}\")
print(f\"  actual_ms              : {b['actual_ms']:,}\")
print(f\"  speedup_factor         : {b['speedup_factor']}×\")
"
