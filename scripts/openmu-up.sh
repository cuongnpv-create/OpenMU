#!/usr/bin/env bash
# OpenMU all-in-one quickstart — da test tren Docker 29.3.1 / Linux x64
# Dung: ./openmu-up.sh [thu-muc-cai-dat]   (mac dinh: ./OpenMU)
set -euo pipefail

TARGET="${1:-$PWD/OpenMU}"
RESOLVE_IP="${RESOLVE_IP:-loopback}"   # loopback = choi tren cung may
                                       # local    = choi trong LAN
                                       # <ip>     = IP/hostname co dinh (VPS)

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mLOI: %s\033[0m\n' "$*" >&2; exit 1; }

command -v docker >/dev/null || die "Chua cai Docker. Xem https://docs.docker.com/get-started/get-docker/"
docker compose version >/dev/null 2>&1 || die "Thieu docker compose plugin."
docker info >/dev/null 2>&1 || die "Docker daemon chua chay."

if [ ! -d "$TARGET/.git" ]; then
  say "Clone OpenMU vao $TARGET"
  git clone --depth 1 https://github.com/MUnique/OpenMU.git "$TARGET"
else
  say "Da co repo tai $TARGET, bo qua clone"
fi

cd "$TARGET/deploy/all-in-one"

# Override rieng: khong dung docker-compose.override.yml mac dinh
# (file do ep BUILD tu source, rat lau). File nay chi them RESOLVE_IP.
say "Ghi docker-compose.local.yml (RESOLVE_IP=$RESOLVE_IP)"
cat > docker-compose.local.yml <<EOF
services:
  openmu-startup:
    environment:
      RESOLVE_IP: $RESOLVE_IP
  database:
    ports:
      - "5433:5432"
EOF

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.local.yml)

say "Keo image (munique/openmu, postgres, nginx)"
"${COMPOSE[@]}" pull

say "Khoi dong stack"
"${COMPOSE[@]}" up -d

say "Cho admin panel san sang (toi da 3 phut)"
for i in $(seq 1 36); do
  code=$(curl -s -o /dev/null -w '%{http_code}' --noproxy localhost http://localhost/ 2>/dev/null || echo 000)
  printf '  [%02d/36] HTTP %s\n' "$i" "$code"
  [ "$code" = "200" ] && break
  sleep 5
done
[ "${code:-000}" = "200" ] || die "Admin panel khong len. Xem log: ${COMPOSE[*]} logs -f openmu-startup"

say "Cho game server dang ky vao connect server"
for i in $(seq 1 24); do
  n=$("${COMPOSE[@]}" logs openmu-startup 2>&1 | grep -c 'Server listener started' || true)
  printf '  [%02d/24] listener da start: %s/6\n' "$i" "$n"
  [ "$n" -ge 6 ] && break
  sleep 5
done

say "Kiem tra giao thuc MU tren connect server (44405)"
python3 - <<'PY' || echo "  (bo qua: khong co python3)"
import socket
try:
    s = socket.create_connection(("127.0.0.1", 44405), timeout=8); s.settimeout(6)
    print("  hello tu server :", s.recv(64).hex(" ").upper())
    s.sendall(bytes([0xC1, 0x04, 0xF4, 0x06]))
    r = s.recv(512)
    print("  danh sach server:", r.hex(" ").upper())
    if len(r) > 6:
        print(f"  => {r[6]} game server dang online")
    s.close()
except Exception as e:
    print("  loi ket noi:", e)
PY

cat <<'DONE'

============================================================
  OpenMU da chay
============================================================
  Admin panel   : http://localhost/
  Connect server: 127.0.0.1:44405   <-- client tro vao day
  Game servers  : 55901-55906
  PostgreSQL    : localhost:5433  (postgres / admin)

  Tai khoan test (mat khau = ten dang nhap):
    test0..test9   level 1..90
    test300        level 300
    test400        level 400 + master
    testgm         game master
    ancient/socket bo do co/socket

  Lenh thuong dung (chay trong deploy/all-in-one):
    docker compose -f docker-compose.yml -f docker-compose.local.yml logs -f openmu-startup
    docker compose -f docker-compose.yml -f docker-compose.local.yml restart openmu-startup
    docker compose -f docker-compose.yml -f docker-compose.local.yml down
    docker compose -f docker-compose.yml -f docker-compose.local.yml down -v   # xoa ca DB
============================================================
DONE
