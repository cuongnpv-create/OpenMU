# Dựng server MU Online (OpenMU) chạy thử

Toàn bộ các bước dưới đây đã được chạy thật và verify end-to-end
(Docker 29.3.1, Linux x64, 28/09/2026 — image `munique/openmu:latest`).

---

## 1. Yêu cầu

| | |
|---|---|
| Docker | có `docker compose` plugin (Docker Desktop trên Win/Mac đã kèm sẵn) |
| git | để clone repo |
| RAM | ~2 GB cho stack (container thực tế dùng ~500 MB) |
| Đĩa | ~1.2 GB cho 3 image + DB |

Trên Windows: chạy trong **WSL2** hoặc PowerShell với Docker Desktop.

---

## 2. Chạy nhanh (1 lệnh)

```bash
./openmu-up.sh ~/OpenMU
```

Script tự làm: clone repo → ghi override → pull image → up → chờ admin panel
→ chờ 6 listener → bắt tay giao thức MU để xác nhận server sống.

Muốn chơi trong LAN hoặc trên VPS:

```bash
RESOLVE_IP=local        ./openmu-up.sh ~/OpenMU   # LAN
RESOLVE_IP=203.0.113.10 ./openmu-up.sh ~/OpenMU   # VPS, IP công cộng cố định
```

---

## 3. Chạy tay (nếu muốn hiểu từng bước)

```bash
git clone --depth 1 https://github.com/MUnique/OpenMU.git
cd OpenMU/deploy/all-in-one

# QUAN TRỌNG: đọc mục 4 trước khi chạy lệnh dưới
cat > docker-compose.local.yml <<'EOF'
services:
  openmu-startup:
    environment:
      RESOLVE_IP: loopback
  database:
    ports:
      - "5433:5432"
EOF

docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
```

Khoảng **50–60 giây** sau, admin panel lên ở <http://localhost/>.

---

## 4. Hai cái bẫy khiến server "chạy mà không vào được"

### 4.1. `PublicIpResolver` làm game server chết im lặng

Mặc định OpenMU gọi API ngoài (ipify.org) để lấy IP công cộng. Nếu máy
không ra được internet, đứng sau proxy, hoặc chặn TLS → game server
**không start**, nhưng:

- admin panel vẫn HTTP 200 → tưởng là ổn
- `docker ps` vẫn thấy port 55901–55906 mở → **đây là docker-proxy bind port host, không phải process listen**

Log sẽ có:

```
[Error] [MUnique.OpenMU.GameServer.GameServer] Could not start the server listeners:
        The SSL connection could not be established, see inner exception.
[Information] ... Stopping listener on port 55901.
```

**Fix**: đặt `RESOLVE_IP` như mục 3. Giá trị hợp lệ:

| Giá trị | Dùng khi |
|---|---|
| `loopback` | chơi trên cùng máy — server báo IP `127.127.127.127` |
| `local` | chơi trong LAN — tự dò IP nội bộ |
| `public` | mặc định, cần internet thông |
| `<IP>` hoặc hostname | VPS có IP cố định |

Xác nhận đã fix — phải thấy đủ **6 dòng**:

```bash
docker compose ... logs openmu-startup | grep "Server listener started"
```

### 4.2. `docker-compose.override.yml` mặc định ép build từ source

File `deploy/all-in-one/docker-compose.override.yml` có sẵn trong repo chứa
`build:` → `docker compose up` trần sẽ **biên dịch cả solution .NET**, rất lâu.

Cách tránh: chỉ định file tường minh, bỏ qua override mặc định:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
```

(hoặc dùng `docker compose up -d --no-build` như doc gốc)

---

## 5. Kiểm tra server sống thật

Đừng tin vào `docker ps`. Bắt tay giao thức MU trực tiếp:

```bash
python3 - <<'EOF'
import socket
s = socket.create_connection(("127.0.0.1", 44405), timeout=8); s.settimeout(6)
print("hello:", s.recv(64).hex(" ").upper())
s.sendall(bytes([0xC1, 0x04, 0xF4, 0x06]))   # yeu cau danh sach server
r = s.recv(512); print("list :", r.hex(" ").upper())
print(f"=> {r[6]} game server online")
EOF
```

Kết quả đúng:

```
hello: C1 04 00 01
list : C2 00 13 F4 06 00 03 00 00 00 00 01 00 00 00 02 00 00 00
=> 3 game server online
```

Giải mã `C2 00 13 F4 06 00 03 …`: header `C2`, dài `0x0013` = 19 byte,
opcode `F4 06` = server list, `03` = 3 server, rồi 3 cụm
`{id: 0/1/2, load: 0}`.

---

## 6. Cổng và thông tin đăng nhập

| Thành phần | Địa chỉ |
|---|---|
| Admin panel | <http://localhost/> |
| **Connect server** (client trỏ vào đây) | `127.0.0.1:44405` |
| Connect server #2 | `44406` |
| Game server 0 / 1 / 2 | `55901-55902` / `55903-55904` / `55905-55906` |
| Chat server | `55980` |
| PostgreSQL | `localhost:5433` — `postgres` / `admin` |

**Admin panel không có user khi cài mới** → nó cho vào thẳng và báo rõ điều đó.
Tạo user đầu tiên ngay, hoặc set trước `OPENMU_ADMIN_USER` / `OPENMU_ADMIN_PASSWORD`
trong `.env` (có hỗ trợ TOTP qua `OPENMU_ADMIN_TOTP_SECRET`).

### Tài khoản test (mật khẩu trùng tên đăng nhập)

DB mới init có sẵn **20 account**:

| Account | Nội dung |
|---|---|
| `test0` … `test9` | level 1 → 90, cách 10 level |
| `test300` | level 300 |
| `test400` | level 400, có master character |
| `testgm`, `testgm2` | game master (`testgm2` có Summoner + Rage Fighter) |
| `testunlock` | chưa có nhân vật, đã mở khóa hết class |
| `quest1/2/3` | test quest level 150 / 220 / 400 |
| `ancient` | bộ đồ cổ, level 330 |
| `socket` | bộ đồ socket, level 380 |

> Nếu mở server cho người khác vào: **xóa hoặc ban hết đống này trước**, hoặc
> init DB với tùy chọn test accounts tắt ở trang Setup.

### Dữ liệu Season 6 đã init sẵn

Kiểm chứng bằng query thật trên DB vừa dựng:

```
73 maps · 468 monster definitions · 676 item definitions · 76 characters
```

---

## 7. Lệnh vận hành

Chạy trong `deploy/all-in-one`. Đặt alias cho gọn:

```bash
alias omu='docker compose -f docker-compose.yml -f docker-compose.local.yml'

omu logs -f openmu-startup     # xem log
omu restart openmu-startup     # restart server (giữ DB)
omu ps                         # trạng thái
omu down                       # tắt, giữ DB
omu down -v                    # tắt + XÓA SẠCH DB (init lại từ đầu)
```

Truy vấn DB:

```bash
docker exec -e PGPASSWORD=admin database \
  psql -U postgres -d openmu -c 'select "LoginName" from data."Account";'
```

---

## 8. Bước tiếp theo

1. **Đổi cấu hình gameplay** — Admin panel → Configuration. Exp rate, drop rate,
   monster spawn, item option… sửa trực tiếp, không cần rebuild.
2. **Bot server-side** — OpenMU có sẵn AI bot để test tải,
   xem `docs-website/docs/server-features/bots.md`.
3. **Nối client** — build `sven-n/MuMain`, trỏ vào `127.0.0.1:44405`.
   Xem `docs-website/docs/getting-started/game-client.md`.
4. **Chạy từ source thay vì image** — cần .NET SDK; bỏ `-f docker-compose.local.yml`
   để dùng override build sẵn trong repo, hoặc mở solution bằng Rider/VS.
5. **Deploy thật** — `deploy/all-in-one-traefik` (HTTPS tự động) hoặc
   `deploy/distributed` (tách connect/login/game server ra nhiều container).

---

## 9. Ghi chú pháp lý

**OpenMU** phát hành theo giấy phép **MIT**, và README nói rõ đây là bản
viết lại hoàn toàn từ đầu — không dựa trên source server decompile hay các
bản phái sinh. Fork, sửa, dùng thoải mái.

Phần **client** (`sven-n/MuMain`) thì khác: repo không có file LICENSE, và gốc
của nó là source client Season 5.2 rò rỉ từ Webzen. Vọc học hành thì bình
thường, nhưng đừng thương mại hóa.
