#!/usr/bin/env bash
set -Eeuo pipefail

CANONICAL_REPOSITORY="https://github.com/CipherCuttle/frontier.git"
CANONICAL_COMMIT="db206cda7eed92b62c706a10089c2571b4381d66"
CANONICAL_TREE="5134857849b03c0dcff4595c8c9fe1059ffe47a6"
CANONICAL_PARENT_1="b1a5f198420614da6ba7eb4d34838be0e0efd1a5"
CANONICAL_PARENT_2="0b383638853853c12ceded0c0691435870620556"
EXPECTED_FREEZE_RECEIPT_ID="freezereceipt_d8ea34d4f5ae84d7eb1de30272395876823c55287b8900af7ba8abadfc5c2346"
EXPECTED_PUBLICATION_COMMIT="$CANONICAL_COMMIT"
OPS_REF="8573cff245614a7410c4ad916b6241c4f9c8bd49"
UV_VERSION="0.12.10"

APP_DIR="/opt/frontier/app"
OPERATOR_DIR="/opt/frontier/operator"
SECRET_DIR="/etc/frontier"
SECRET_FILE="$SECRET_DIR/frontier_database_url"
SERVICE_FILE="/etc/systemd/system/frontier-pef-v0-confirmatory.service"
SERVICE_NAME="frontier-pef-v0-confirmatory.service"
RUN_USER="frontier"
RAW_ROOT="https://raw.githubusercontent.com/CipherCuttle/frontier/$OPS_REF/ops/pef_v0_confirmatory_vm"

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "ERROR: run this bootstrap as root (sudo)." >&2
  exit 2
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl git openssl xz-utils

if ! id "$RUN_USER" >/dev/null 2>&1; then
  useradd --system --create-home --home-dir /var/lib/frontier --shell /usr/sbin/nologin "$RUN_USER"
fi
install -d -o root -g root -m 0755 /opt/frontier "$OPERATOR_DIR"
install -d -o "$RUN_USER" -g "$RUN_USER" -m 0750 /var/lib/frontier
install -d -o root -g root -m 0700 "$SECRET_DIR"

if ! command -v uv >/dev/null 2>&1; then
  tmp_uv="$(mktemp -d)"
  trap 'rm -rf "$tmp_uv"' EXIT
  curl -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh" -o "$tmp_uv/install-uv.sh"
  UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh "$tmp_uv/install-uv.sh"
  rm -rf "$tmp_uv"
  trap - EXIT
fi
uv --version

if [[ ! -d "$APP_DIR/.git" ]]; then
  rm -rf "$APP_DIR"
  git clone --no-checkout "$CANONICAL_REPOSITORY" "$APP_DIR"
elif [[ -n "$(git -C "$APP_DIR" status --porcelain)" ]]; then
  echo "ERROR: $APP_DIR is dirty; refusing to overwrite it." >&2
  exit 3
fi

git -C "$APP_DIR" fetch --quiet origin main
git -C "$APP_DIR" cat-file -e "${CANONICAL_COMMIT}^{commit}"
git -C "$APP_DIR" checkout --detach --quiet "$CANONICAL_COMMIT"
test "$(git -C "$APP_DIR" rev-parse HEAD)" = "$CANONICAL_COMMIT"
test "$(git -C "$APP_DIR" rev-parse 'HEAD^{tree}')" = "$CANONICAL_TREE"
test "$(git -C "$APP_DIR" rev-parse HEAD^1)" = "$CANONICAL_PARENT_1"
test "$(git -C "$APP_DIR" rev-parse HEAD^2)" = "$CANONICAL_PARENT_2"
test -z "$(git -C "$APP_DIR" status --porcelain)"

cd "$APP_DIR"
export UV_PYTHON_INSTALL_DIR="/opt/frontier/python"
install -d -o root -g root -m 0755 "$UV_PYTHON_INSTALL_DIR"
uv python install 3.14
uv lock --check
uv sync --all-extras --frozen
chmod -R a+rX "$UV_PYTHON_INSTALL_DIR" "$APP_DIR/.venv"

curl -LsSf "$RAW_ROOT/confirmatory_service.py" -o "$OPERATOR_DIR/confirmatory_service.py"
curl -LsSf "$RAW_ROOT/frontier-pef-v0-confirmatory.service" -o "$SERVICE_FILE"
chmod 0755 "$OPERATOR_DIR/confirmatory_service.py"
chmod 0644 "$SERVICE_FILE"
chown root:root "$OPERATOR_DIR/confirmatory_service.py" "$SERVICE_FILE"

if [[ ! -s "$SECRET_FILE" ]]; then
  echo "Paste the canonical FRONTIER Neon PostgreSQL URL. It is stored only in $SECRET_FILE." >/dev/tty
  IFS= read -r -s DATABASE_URL </dev/tty
  echo >/dev/tty
  if [[ -z "$DATABASE_URL" ]]; then
    echo "ERROR: empty database URL." >&2
    exit 4
  fi
  umask 077
  printf '%s' "$DATABASE_URL" > "$SECRET_FILE"
  unset DATABASE_URL
fi
chmod 0600 "$SECRET_FILE"
chown root:root "$SECRET_FILE"

cat > /usr/local/sbin/frontier-pef-v0-status <<EOF_STATUS
#!/usr/bin/env bash
set -euo pipefail
DB_URL="\$(cat "$SECRET_FILE")"
cd "$APP_DIR"
FRONTIER_DATABASE_URL="\$DB_URL" exec "$APP_DIR/.venv/bin/frontier" ops status
EOF_STATUS
chmod 0700 /usr/local/sbin/frontier-pef-v0-status
chown root:root /usr/local/sbin/frontier-pef-v0-status

systemctl daemon-reload
DB_URL="$(cat "$SECRET_FILE")"
FRONTIER_DATABASE_URL="$DB_URL" "$APP_DIR/.venv/bin/frontier" doctor
FRONTIER_DATABASE_URL="$DB_URL" \
  CANONICAL_PUBLICATION_COMMIT="$CANONICAL_COMMIT" \
  CANONICAL_PUBLICATION_TREE="$CANONICAL_TREE" \
  CANONICAL_PARENT_1="$CANONICAL_PARENT_1" \
  CANONICAL_PARENT_2="$CANONICAL_PARENT_2" \
  EXPECTED_FREEZE_RECEIPT_ID="$EXPECTED_FREEZE_RECEIPT_ID" \
  EXPECTED_PUBLICATION_COMMIT="$EXPECTED_PUBLICATION_COMMIT" \
  "$APP_DIR/.venv/bin/python" "$OPERATOR_DIR/confirmatory_service.py" --preflight
unset DB_URL

systemctl enable --now "$SERVICE_NAME"
sleep 2
systemctl --no-pager --full status "$SERVICE_NAME" || true

echo
echo "FRONTIER PEF_V0 confirmatory VM operator installed."
echo "Canonical commit: $CANONICAL_COMMIT"
echo "Canonical tree:   $CANONICAL_TREE"
echo "Operator ref:     $OPS_REF"
echo "Logs:             journalctl -u $SERVICE_NAME -f"
echo "Read-only status: sudo frontier-pef-v0-status"
