#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# BABEL DUPLICATION WORKER
# Hosted at: https://cdn.bkev.in/babel/worker.sh
# Zero credentials, fully stateless compute runner controlled by Babel.
# ==============================================================================

WORKER_ID="worker-$(head -c 2 /dev/urandom | xxd -p 2>/dev/null || echo $RANDOM)"
ENDPOINT="http://babel.ts.bkev.in:8080"
TOKEN=""
TS_KEY=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --id) WORKER_ID="$2"; shift 2 ;;
    --endpoint) ENDPOINT="$2"; shift 2 ;;
    --token) TOKEN="$2"; shift 2 ;;
    --tailscale-key) TS_KEY="$2"; shift 2 ;;
    *) shift ;;
  esac
done

# Ensure rclone, curl, and jq are available
if ! command -v curl >/dev/null 2>&1; then
  echo "[!] curl missing. Installing curl..."
  sudo apt-get update -qq && sudo apt-get install -y -qq curl
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "[!] jq missing. Installing jq..."
  sudo apt-get update -qq && sudo apt-get install -y -qq jq
fi

if ! command -v rclone >/dev/null 2>&1; then
  echo "[!] rclone missing. Installing official rclone binary..."
  curl -fsSL https://rclone.org/install.sh | sudo bash
fi

# Store config strictly in volatile kernel RAM disk (/dev/shm)
RAM_DIR="/dev/shm/.babel-worker-${WORKER_ID}"
mkdir -p -m 700 "$RAM_DIR"
RCLONE_CONF="${RAM_DIR}/rclone.conf"
RCLONE_PID=""
ACTIVE_TX=""
ACTIVE_LEASE=0
RC_PORT=$((20000 + RANDOM % 10000))
CURL_PROXY_ARGS=()

cleanup() {
  echo -e "\n[🛑] Shutting down worker ${WORKER_ID} and wiping RAM secrets..."
  if [[ -n "$RCLONE_PID" ]]; then
    kill -TERM "$RCLONE_PID" 2>/dev/null || true
  fi
  rm -rf "$RAM_DIR"
}
trap cleanup EXIT INT TERM

# Optional userspace Tailscale bootstrap for Google Cloud Shell / containers
if [[ -n "$TS_KEY" ]]; then
  if ! command -v tailscaled >/dev/null 2>&1; then
    echo "[🔒] Installing Tailscale..."
    curl -fsSL https://tailscale.com/install.sh | sudo bash
  fi
  echo "[🔒] Bootstrapping userspace Tailscale SOCKS5 proxy..."
  tailscaled --state="mem:" --tun=userspace-networking --socks5-server=127.0.0.1:1055 >/dev/null 2>&1 &
  sleep 2
  tailscale up --authkey="$TS_KEY" --hostname="babel-${WORKER_ID}" --accept-dns=false >/dev/null 2>&1 || true
  CURL_PROXY_ARGS=(--proxy "socks5h://127.0.0.1:1055")
fi

api_post() {
  curl -sS --max-time 5 "${CURL_PROXY_ARGS[@]}" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${TOKEN}" \
    -X POST "${ENDPOINT}$1" -d "$2"
}

api_get() {
  curl -sS --max-time 5 "${CURL_PROXY_ARGS[@]}" \
    -H "Authorization: Bearer ${TOKEN}" \
    "${ENDPOINT}$1"
}

# Register with Babel
HOSTNAME_STR="$(hostname 2>/dev/null || echo 'gcp-instance')"
echo "============================================================"
echo " BABEL DUPLICATION RUNNER"
echo "============================================================"
echo " Worker ID : ${WORKER_ID} (${HOSTNAME_STR})"
echo " Endpoint  : ${ENDPOINT}"
echo " Status    : Connecting to Babel..."
echo "============================================================"

if ! api_post "/api/worker/register" "{\"worker_id\":\"${WORKER_ID}\",\"hostname\":\"${HOSTNAME_STR}\"}" >/dev/null; then
  echo "[❌] Failed to connect to ${ENDPOINT}. Check network or Tailscale."
  exit 1
fi

echo "[✓] Connected to ${ENDPOINT}"
echo "[⏳] Standby: Waiting for Babel Transaction Assignment from Dashboard..."

MISSED_POLLS=0

while true; do
  POLL_RESP="$(api_get "/api/worker/poll?id=${WORKER_ID}" 2>/dev/null || echo '')"
  
  if [[ -z "$POLL_RESP" ]]; then
    MISSED_POLLS=$((MISSED_POLLS + 1))
    echo -ne "\r[⚠️] Lost contact with Babel (${MISSED_POLLS}/3)... "
    if [[ $MISSED_POLLS -ge 3 && -n "$RCLONE_PID" ]]; then
      echo -e "\n[🚨] Lease timeout (15s lost contact)! Stopping local rclone to prevent split-brain..."
      kill -TERM "$RCLONE_PID" 2>/dev/null || true
      RCLONE_PID=""
      ACTIVE_TX=""
    fi
    sleep 2
    continue
  fi

  MISSED_POLLS=0
  ACTION="$(echo "$POLL_RESP" | jq -r '.action // "STANDBY"')"

  case "$ACTION" in
    RUN_TRANSACTION)
      TX_ID="$(echo "$POLL_RESP" | jq -r '.tx.tx_id')"
      LEASE_ID="$(echo "$POLL_RESP" | jq -r '.tx.lease_id')"
      SRC="$(echo "$POLL_RESP" | jq -r '.tx.source')"
      DST="$(echo "$POLL_RESP" | jq -r '.tx.dest')"
      MODE="$(echo "$POLL_RESP" | jq -r '.tx.mode // "copy"')"

      # Start rclone if not already running this exact TX + Lease
      if [[ "$ACTIVE_TX" != "$TX_ID" || "$ACTIVE_LEASE" != "$LEASE_ID" || -z "$RCLONE_PID" ]]; then
        if [[ -n "$RCLONE_PID" ]]; then
          kill -TERM "$RCLONE_PID" 2>/dev/null || true
        fi
        echo -e "\n[🚀] Assigned Transaction: ${TX_ID} [Lease #${LEASE_ID}]"
        echo "[i] Mode: ${MODE} | ${SRC} ➔ ${DST}"

        # Fetch fresh rclone.conf directly into /dev/shm
        api_get "/api/worker/config?id=${WORKER_ID}&token=${TOKEN}" > "$RCLONE_CONF"
        chmod 600 "$RCLONE_CONF"

        # Read dynamic flags from Babel (or defaults)
        mapfile -t CUSTOM_FLAGS < <(echo "$POLL_RESP" | jq -r '.tx.rclone_flags[]?' 2>/dev/null || true)
        if [[ ${#CUSTOM_FLAGS[@]} -eq 0 ]]; then
          CUSTOM_FLAGS=("--size-only" "--transfers=4" "--checkers=8" "--tpslimit=4")
        fi

        # Launch rclone with dynamic mode and flags
        rclone "$MODE" "$SRC" "$DST" \
          --config="$RCLONE_CONF" \
          "${CUSTOM_FLAGS[@]}" \
          --rc --rc-addr="127.0.0.1:${RC_PORT}" --rc-no-auth \
          --quiet &
        RCLONE_PID=$!
        ACTIVE_TX="$TX_ID"
        ACTIVE_LEASE="$LEASE_ID"
        sleep 1
      fi

      # Poll local rclone RC for live metrics
      if kill -0 "$RCLONE_PID" 2>/dev/null; then
        STATS="$(curl -sS --max-time 2 -X POST "http://127.0.0.1:${RC_PORT}/core/stats" -d '{}' 2>/dev/null || echo '{}')"
        BYTES="$(echo "$STATS" | jq '.bytes // 0')"
        TOTAL_BYTES="$(echo "$STATS" | jq '.totalBytes // 0')"
        SPEED="$(echo "$STATS" | jq '[.transferring[]?.speed] | add // 0')"
        ETA="$(echo "$STATS" | jq '.eta // 0')"
        CUR_FILE="$(echo "$STATS" | jq -r '.transferring[0].name // "Checking existing files..."')"
        CHECKS="$(echo "$STATS" | jq '.checks // 0')"
        TRANSFERS="$(echo "$STATS" | jq '.transfers // 0')"

        SPEED_MB="$(awk "BEGIN {printf \"%.1f\", $SPEED/1048576}")"
        BYTES_GB="$(awk "BEGIN {printf \"%.2f\", $BYTES/1073741824}")"
        TOTAL_GB="$(awk "BEGIN {printf \"%.2f\", $TOTAL_BYTES/1073741824}")"

        printf "\r[%s] %s @ %s MB/s | Copied: %s GB / %s GB | Checked: %d   " \
          "$TX_ID" "${CUR_FILE##*/}" "$SPEED_MB" "$BYTES_GB" "$TOTAL_GB" "$CHECKS"

        REPORT_RES="$(api_post "/api/worker/report" "$(jq -nc \
          --arg wid "$WORKER_ID" \
          --arg txid "$TX_ID" \
          --argjson lease "$ACTIVE_LEASE" \
          --arg state "RUNNING" \
          --argjson bytes "$BYTES" \
          --argjson total "$TOTAL_BYTES" \
          --argjson speed "$SPEED" \
          --argjson eta "$ETA" \
          --argjson checks "$CHECKS" \
          --argjson transfers "$TRANSFERS" \
          --arg file "$CUR_FILE" \
          '{worker_id:$wid, tx_id:$txid, lease_id:$lease, status:$state, bytes:$bytes, total_bytes:$total, speed_bps:$speed, eta_sec:$eta, checks:$checks, transfers:$transfers, current_file:$file}')" 2>/dev/null || echo '{}')"

        # Check for fence conflict
        if echo "$REPORT_RES" | grep -q "LEASE_SUPERSEDED"; then
          echo -e "\n[🚨] Lease superseded by Babel! Stopping local rclone..."
          kill -TERM "$RCLONE_PID" 2>/dev/null || true
          RCLONE_PID=""
          ACTIVE_TX=""
        fi
      else
        wait "$RCLONE_PID" 2>/dev/null && EXIT_CODE=0 || EXIT_CODE=$?
        RCLONE_PID=""
        ACTIVE_TX=""
        if [[ $EXIT_CODE -eq 0 ]]; then
          echo -e "\n[✅] Transaction ${TX_ID} COMPLETED successfully!"
          api_post "/api/worker/report" "{\"worker_id\":\"${WORKER_ID}\",\"tx_id\":\"${TX_ID}\",\"lease_id\":${ACTIVE_LEASE},\"status\":\"COMPLETED\"}" >/dev/null || true
        else
          echo -e "\n[❌] Rclone exited with code ${EXIT_CODE}"
          api_post "/api/worker/report" "{\"worker_id\":\"${WORKER_ID}\",\"tx_id\":\"${TX_ID}\",\"lease_id\":${ACTIVE_LEASE},\"status\":\"INTERRUPTED\"}" >/dev/null || true
        fi
      fi
      ;;

    PAUSE|STOP|STANDBY)
      if [[ -n "$RCLONE_PID" ]]; then
        echo -e "\n[⏸] Received ${ACTION} from Babel Dashboard. Stopping rclone..."
        kill -TERM "$RCLONE_PID" 2>/dev/null || true
        wait "$RCLONE_PID" 2>/dev/null || true
        RCLONE_PID=""
        ACTIVE_TX=""
      fi
      if echo "$POLL_RESP" | jq -e '.terminate // false' >/dev/null 2>&1; then
        echo "[🛑] Received termination signal from Babel. Exiting."
        exit 0
      fi
      ;;
  esac

  sleep 1
done