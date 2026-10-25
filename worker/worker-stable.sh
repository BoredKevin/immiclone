#!/usr/bin/env bash
set -euo pipefail

# Ensure standard system binary paths are available for non-root users
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"

# Determine sudo availability
SUDO=""
if [[ $EUID -ne 0 ]]; then
  if command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
  fi
fi

# ==============================================================================
# IMMICLONE DUPLICATION WORKER
# Zero credentials stored on disk; fully stateless compute runner.
# ==============================================================================

WORKER_ID="worker-$(head -c 2 /dev/urandom | xxd -p 2>/dev/null || echo $RANDOM)"
ENDPOINT="http://localhost:8080"
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
  $SUDO apt-get update -qq && $SUDO apt-get install -y -qq curl
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "[!] jq missing. Installing jq..."
  $SUDO apt-get update -qq && $SUDO apt-get install -y -qq jq
fi

if ! command -v rclone >/dev/null 2>&1; then
  echo "[!] rclone missing. Installing official rclone binary..."
  curl -fsSL https://rclone.org/install.sh | $SUDO bash
fi

# Store config strictly in volatile kernel RAM disk (/dev/shm)
RAM_DIR="/dev/shm/.immiclone-worker-${WORKER_ID}"
mkdir -p -m 700 "$RAM_DIR"
RCLONE_CONF="${RAM_DIR}/rclone.conf"
RCLONE_LOG="${RAM_DIR}/rclone.log"
TAILSCALE_SOCK="${RAM_DIR}/tailscaled.sock"
TAILSCALE_LOG="${RAM_DIR}/tailscaled.log"
TAILSCALE_PID=""
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
  if [[ -n "$TAILSCALE_PID" ]]; then
    $SUDO kill -TERM "$TAILSCALE_PID" 2>/dev/null || true
  fi
  if [[ -n "$TS_KEY" ]] && command -v tailscale >/dev/null 2>&1; then
    tailscale --socket="$TAILSCALE_SOCK" logout 2>/dev/null || true
  fi
  rm -rf "$RAM_DIR"
}
trap cleanup EXIT INT TERM

# Optional userspace Tailscale bootstrap for Google Cloud Shell / containers
if [[ -n "$TS_KEY" ]]; then
  if ! command -v tailscaled >/dev/null 2>&1; then
    echo "[🔒] Installing Tailscale..."
    curl -fsSL https://tailscale.com/install.sh | $SUDO bash
  fi

  echo "[🔒] Bootstrapping userspace Tailscale SOCKS5 proxy..."
  $SUDO tailscaled \
    --state="mem:" \
    --tun=userspace-networking \
    --socks5-server=127.0.0.1:1055 \
    --socket="$TAILSCALE_SOCK" \
    >"$TAILSCALE_LOG" 2>&1 &
  TAILSCALE_PID=$!

  # Wait for the userspace control socket to appear
  for i in {1..10}; do
    if [[ -S "$TAILSCALE_SOCK" ]]; then
      break
    fi
    sleep 0.5
  done

  # Ensure user can communicate with socket
  if [[ -n "$SUDO" && -S "$TAILSCALE_SOCK" ]]; then
    $SUDO chmod 666 "$TAILSCALE_SOCK" 2>/dev/null || true
  fi

  echo "[🔒] Authenticating with Tailscale network..."
  if ! tailscale --socket="$TAILSCALE_SOCK" up \
    --authkey="$TS_KEY" \
    --hostname="worker-${WORKER_ID}" \
    --accept-dns=false >>"$TAILSCALE_LOG" 2>&1; then
    echo "[❌] Tailscale authentication failed! Daemon log:"
    tail -n 15 "$TAILSCALE_LOG" 2>/dev/null || true
    exit 1
  fi

  echo "[🔒] Waiting for Tailscale tunnel to become active..."
  CONNECTED=0
  for i in {1..15}; do
    if tailscale --socket="$TAILSCALE_SOCK" status 2>/dev/null | grep -q "100\."; then
      CONNECTED=1
      break
    fi
    sleep 1
  done

  if [[ $CONNECTED -eq 0 ]]; then
    echo "[⚠️] Warning: Tailscale route discovery exceeded 15s. Proceeding..."
  else
    echo "[✓] Tailscale connected successfully!"
  fi

  CURL_PROXY_ARGS=(--proxy "socks5://127.0.0.1:1055")
fi

WORKER_VERSION="1.1.0"

api_post() {
  local req_path="$1"
  if [[ "$req_path" != /api/v1/* && "$req_path" == /api/* ]]; then
    req_path="/api/v1${req_path#/api}"
  elif [[ "$req_path" != /api/v1/* ]]; then
    req_path="/api/v1${req_path}"
  fi
  curl -sS --max-time 5 "${CURL_PROXY_ARGS[@]}" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "X-Worker-Version: ${WORKER_VERSION}" \
    -X POST "${ENDPOINT}${req_path}" -d "$2"
}

api_get() {
  local req_path="$1"
  if [[ "$req_path" != /api/v1/* && "$req_path" == /api/* ]]; then
    req_path="/api/v1${req_path#/api}"
  elif [[ "$req_path" != /api/v1/* ]]; then
    req_path="/api/v1${req_path}"
  fi
  curl -sS --max-time 5 "${CURL_PROXY_ARGS[@]}" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "X-Worker-Version: ${WORKER_VERSION}" \
    "${ENDPOINT}${req_path}"
}

# Register with Controller
HOSTNAME_STR="$(hostname 2>/dev/null || echo 'gcp-instance')"
echo "============================================================"
echo " IMMICLONE DUPLICATION RUNNER"
echo "============================================================"
echo " Worker ID : ${WORKER_ID} (${HOSTNAME_STR})"
echo " Endpoint  : ${ENDPOINT}"
echo " Status    : Connecting to control server..."
echo "============================================================"

REG_RES="$(api_post "/api/v1/worker/register" "{\"worker_id\":\"${WORKER_ID}\",\"token\":\"${TOKEN}\",\"hostname\":\"${HOSTNAME_STR}\",\"version\":\"${WORKER_VERSION}\"}" 2>&1 || true)"
if [[ "$REG_RES" != *"\"status\":\"ok\""* && "$REG_RES" != *"\"status\": \"ok\""* ]]; then
  echo "[❌] Failed to connect to ${ENDPOINT}."
  echo "     Response from server: ${REG_RES}"
  if [[ -n "$TS_KEY" && -f "$TAILSCALE_LOG" ]]; then
    echo "     Tailscale daemon logs:"
    tail -n 10 "$TAILSCALE_LOG" 2>/dev/null || true
  fi
  exit 1
fi

echo "[✓] Connected to ${ENDPOINT}"
echo "[⏳] Standby: Waiting for Transaction Assignment from Dashboard..."

MISSED_POLLS=0

while true; do
  POLL_RESP="$(api_get "/api/v1/worker/poll?id=${WORKER_ID}" 2>/dev/null || echo '')"
  
  if [[ -z "$POLL_RESP" ]]; then
    MISSED_POLLS=$((MISSED_POLLS + 1))
    echo -ne "\r[⚠️] Lost contact with control server (${MISSED_POLLS}/3)... "
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
        api_get "/api/v1/worker/config?id=${WORKER_ID}&token=${TOKEN}" > "$RCLONE_CONF"
        if grep -q "Forbidden" "$RCLONE_CONF" 2>/dev/null; then
          echo "[❌] Error fetching rclone configuration: Forbidden (Session token invalid or expired. Check token or launch a new session in dashboard)."
          rm -f "$RCLONE_CONF"
          sleep 3
          continue
        fi
        chmod 600 "$RCLONE_CONF"

        # Read dynamic flags from server (or defaults)
        mapfile -t CUSTOM_FLAGS < <(echo "$POLL_RESP" | jq -r '.tx.rclone_flags[]?' 2>/dev/null || true)
        if [[ ${#CUSTOM_FLAGS[@]} -eq 0 ]]; then
          CUSTOM_FLAGS=(
            "--size-only"
            "--drive-chunk-size=64M"
            "--drive-upload-cutoff=64M"
            "--buffer-size=32M"
            "--transfers=4"
            "--checkers=8"
            "--tpslimit=10"
            "--drive-pacer-min-sleep=10ms"
          )
        fi

        # Sanitize flags: Strip --fast-list on Google Drive to prevent recursive pacer backoff
        FILTERED_FLAGS=()
        for flag in "${CUSTOM_FLAGS[@]}"; do
          if [[ "$flag" == "--fast-list" || "$flag" == --fast-list=* ]]; then
            echo "[⚠️] Stripped flag '${flag}' (triggers Google Drive API rate-limiting pacer backoff)."
            continue
          fi
          FILTERED_FLAGS+=("$flag")
        done
        CUSTOM_FLAGS=("${FILTERED_FLAGS[@]}")

        # Launch rclone with dynamic mode and flags
        rclone "$MODE" "$SRC" "$DST" \
          --config="$RCLONE_CONF" \
          "${CUSTOM_FLAGS[@]}" \
          --rc --rc-addr="127.0.0.1:${RC_PORT}" --rc-no-auth \
          --log-file="$RCLONE_LOG" --log-level=NOTICE &
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
        
        ACTIVE_TRANSFER="$(echo "$STATS" | jq -r '.transferring[0].name // empty')"
        ACTIVE_CHECK="$(echo "$STATS" | jq -r '.checking[0].name // empty')"
        if [[ -n "$ACTIVE_TRANSFER" ]]; then
          CUR_FILE="${ACTIVE_TRANSFER}"
        elif [[ -n "$ACTIVE_CHECK" ]]; then
          CUR_FILE="Check: ${ACTIVE_CHECK}"
        else
          CUR_FILE="Scanning / comparing file trees..."
        fi

        CHECKS="$(echo "$STATS" | jq '.checks // 0')"
        TRANSFERS="$(echo "$STATS" | jq '.transfers // 0')"

        SPEED_MB="$(awk "BEGIN {printf \"%.1f\", $SPEED/1048576}")"
        BYTES_GB="$(awk "BEGIN {printf \"%.2f\", $BYTES/1073741824}")"
        TOTAL_GB="$(awk "BEGIN {printf \"%.2f\", $TOTAL_BYTES/1073741824}")"

        printf "\r[%s] %s @ %s MB/s | Copied: %s GB / %s GB | Checked: %d   " \
          "$TX_ID" "${CUR_FILE##*/}" "$SPEED_MB" "$BYTES_GB" "$TOTAL_GB" "$CHECKS"

        REPORT_RES="$(api_post "/api/v1/worker/report" "$(jq -nc \
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

        # Early detection of fatal Google Drive cross-account 404 error in log
        if grep -q -E "googleapi: Error 404|Error 404: File not found|notFound" "$RCLONE_LOG" 2>/dev/null; then
          echo -e "\n[❌] Fatal Google Drive 404 Not Found error detected in rclone log!"
          echo "     Destination account cannot access source remote (server-side copy permission required)."
          kill -TERM "$RCLONE_PID" 2>/dev/null || true
          wait "$RCLONE_PID" 2>/dev/null || true
          RCLONE_PID=""
          ACTIVE_TX=""
          api_post "/api/v1/worker/report" "$(jq -nc \
            --arg wid "$WORKER_ID" \
            --arg txid "$TX_ID" \
            --argjson lease "$ACTIVE_LEASE" \
            --arg state "FAILED" \
            --arg err "Google Drive 404 Not Found: destination account lacks read access on source remote" \
            '{worker_id:$wid, tx_id:$txid, lease_id:$lease, status:$state, error_message:$err}')" >/dev/null || true
          continue
        fi

        # Check for fence conflict
        if echo "$REPORT_RES" | grep -q "LEASE_SUPERSEDED"; then
          echo -e "\n[🚨] Lease superseded by control server! Stopping local rclone..."
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
          api_post "/api/v1/worker/report" "{\"worker_id\":\"${WORKER_ID}\",\"tx_id\":\"${TX_ID}\",\"lease_id\":${ACTIVE_LEASE},\"status\":\"COMPLETED\"}" >/dev/null || true
        else
          echo -e "\n[❌] Rclone exited with code ${EXIT_CODE}. Log output:"
          tail -n 12 "$RCLONE_LOG" 2>/dev/null || true
          if grep -q -E "googleapi: Error 404|Error 404: File not found|notFound" "$RCLONE_LOG" 2>/dev/null; then
            echo "[❌] Detected Google Drive 404 Not Found (Cross-drive permission missing). Reporting FAILED."
            api_post "/api/v1/worker/report" "$(jq -nc \
              --arg wid "$WORKER_ID" \
              --arg txid "$TX_ID" \
              --argjson lease "$ACTIVE_LEASE" \
              --arg state "FAILED" \
              --arg err "Google Drive 404 Not Found: destination account lacks read access on source remote" \
              '{worker_id:$wid, tx_id:$txid, lease_id:$lease, status:$state, error_message:$err}')" >/dev/null || true
          else
            api_post "/api/v1/worker/report" "$(jq -nc \
              --arg wid "$WORKER_ID" \
              --arg txid "$TX_ID" \
              --argjson lease "$ACTIVE_LEASE" \
              --arg state "INTERRUPTED" \
              --arg err "Rclone process exited with code ${EXIT_CODE}" \
              '{worker_id:$wid, tx_id:$txid, lease_id:$lease, status:$state, error_message:$err}')" >/dev/null || true
          fi
        fi
      fi
      ;;

    PAUSE|STOP|STANDBY)
      if [[ -n "$RCLONE_PID" ]]; then
        echo -e "\n[⏸] Received ${ACTION} from Dashboard. Stopping rclone..."
        kill -TERM "$RCLONE_PID" 2>/dev/null || true
        wait "$RCLONE_PID" 2>/dev/null || true
        RCLONE_PID=""
        ACTIVE_TX=""
      fi
      if echo "$POLL_RESP" | jq -e '.terminate // false' >/dev/null 2>&1; then
        echo "[🛑] Received termination signal from control server. Exiting."
        exit 0
      fi
      ;;
  esac

  sleep 1
done
