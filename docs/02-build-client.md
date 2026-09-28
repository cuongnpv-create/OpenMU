# Build client MuMain và nối vào OpenMU

Mọi bước dưới đây đã chạy thật và verify end-to-end trong môi trường:
Ubuntu 24.04 · gcc 13.3 · CMake 3.28.3 · .NET SDK 10.0.112 · 4 core · 28/09/2026.

Kết quả: **997/997 target build OK · 321/321 test pass · login được vào Lorencia**.

---

## 1. Tổng quan kiến trúc

MuMain không phải một khối C++ thuần. Nó gồm hai nửa:

| Phần | Ngôn ngữ | Vai trò |
|---|---|---|
| Engine | C++ (SDL3 + SDL_gpu + SDL_ttf + imgui) | render, input, game logic, UI |
| `MUnique.Client.Library` | C# .NET 10, **Native AOT** | toàn bộ network stack, dùng chung `MUnique.OpenMU.Network` với server |

Vì network layer là code C# dùng chung với OpenMU, client và server luôn khớp
protocol — đây là lý do cặp này chạy được với nhau còn client Webzen gốc thì không.

Render backend là **SDL GPU**: D3D12 trên Windows, Vulkan trên Linux, Metal trên macOS.
(Bản OpenGL cũ đã bị gỡ.)

---

## 2. Linux — build nhanh

```bash
./mumain-build.sh ~/MuMain
```

Biến môi trường tùy chọn:

```bash
PRESET=linux-x64-mueditor ./mumain-build.sh ~/MuMain   # kèm in-game editor (F12)
CONTROL_SOCKET=ON         ./mumain-build.sh ~/MuMain   # cho script điều khiển client
JOBS=8                    ./mumain-build.sh ~/MuMain
```

Thời gian build lần đầu: **~20 phút trên 4 core** (997 target, gồm cả SDL và freetype vendored).

---

## 3. Ba thứ docs không nói mà thiếu là fail

### 3.1. Thiếu 3 gói dev — CMake configure chết giữa chừng

Danh sách prerequisite trong `docs/build/linux/console.md` **không có**
`libcurl`, `libssl`, `libvulkan`. Mà `src/CMakeLists.txt` lại có:

```cmake
find_package(OpenSSL REQUIRED COMPONENTS Crypto)   # dòng 222
find_package(Vulkan REQUIRED)                      # dòng 226
find_package(CURL REQUIRED)                        # dòng 234
```

Triệu chứng:

```
CMake Error at FindPackageHandleStandardArgs.cmake:230 (message):
  Could NOT find CURL (missing: CURL_LIBRARY CURL_INCLUDE_DIR)
```

Fix:

```bash
sudo apt-get install -y libcurl4-openssl-dev libssl-dev libvulkan-dev
```

### 3.2. `miniaudio` tải bằng URL tarball — hay bị chặn

Các dependency khác (`glm`, `spdlog`, `SDL_ttf`) dùng `GIT_REPOSITORY` nên đi
qua git bình thường. Riêng `miniaudio` dùng `URL` trỏ vào
`github.com/mackron/miniaudio/archive/<sha>.tar.gz`, tức **codeload.github.com** —
proxy công ty / firewall hay chặn host này (trả 403), và configure chết:

```
CMake Error at FetchContent.cmake:1679 (message):
  Build step for miniaudio failed: 1
```

Fix — clone bằng git rồi trỏ FetchContent vào thư mục local:

```bash
SHA=$(grep -oP 'miniaudio/archive/\K[0-9a-f]{40}' CMakeLists.txt | head -1)
mkdir -p .deps/miniaudio && git -C .deps/miniaudio init -q
git -C .deps/miniaudio remote add origin https://github.com/mackron/miniaudio.git
git -C .deps/miniaudio fetch -q --depth 1 origin "$SHA"
git -C .deps/miniaudio checkout -q FETCH_HEAD

cmake --preset linux-x64 -DFETCHCONTENT_SOURCE_DIR_MINIAUDIO="$PWD/.deps/miniaudio"
```

Biến `FETCHCONTENT_SOURCE_DIR_<TÊN VIẾT HOA>` là cơ chế chuẩn của CMake để
bỏ qua hẳn bước download — dùng được cho bất kỳ dependency nào bị chặn.

### 3.3. `dotnet-install.sh` có thể không tải được

Docs khuyên `curl -sSL https://dot.net/v1/dotnet-install.sh | bash`. Host
`dot.net` và `builds.dotnet.microsoft.com` hay bị chặn. Trên Ubuntu 24.04 thì
không cần — .NET 10 có sẵn trong archive:

```bash
sudo apt-get install -y dotnet-sdk-10.0 dotnet-sdk-aot-10.0
```

`dotnet-sdk-aot-10.0` là **bắt buộc** — thiếu nó thì Native AOT publish của
`MUnique.Client.Library` sẽ fail.

---

## 4. Game data: có sẵn, không phải tải riêng

Đây là chỗ dễ hiểu nhầm.

| Cách lấy client | Data |
|---|---|
| **Build từ source** | `src/bin/Data` đã nằm trong repo — **722 MB, 13.183 file** (5.730 `.ozj` texture, 5.290 `.bmd` model, 1.751 `.ozt`, 90 `.map`). CMake tự copy sang cạnh binary. Không phải tải gì thêm. |
| **Tải release binary** | Artifact là bản *no-data*. Phải tải thêm data release tag `data-<id>` mà release đó trỏ tới, **đúng cặp version** — lệch là crash/thiếu model. |

Tổng dung lượng repo sau clone `--depth 1`: ~772 MB (+354 MB thư mục `.git`).

---

## 5. Windows

```
1. Cài Visual Studio kèm workload "Desktop development with C++" (có sẵn CMake + Ninja)
2. Cài .NET 10 SDK
3. File > Open > Folder  →  chọn thư mục repo (VS tự đọc CMakePresets.json)
4. Chọn configure preset trên toolbar:
      windows-x64            64-bit, không editor
      windows-x64-mueditor   64-bit, có editor (F12)
      windows-x86 / -mueditor  32-bit
5. Build > Build All
6. Debug target = Main.exe, working directory = out/build/<preset>/src/Debug/
```

> Visual Studio **không mở được** project nằm trên đường dẫn WSL
> (`\\wsl.localhost\...`). Phải checkout repo trên ổ Windows.

Presets Windows dùng vcpkg (`vcpkg.json` + `toolchain-x64.cmake`), khác Linux
dùng apt — nên hai nền tảng không chung cách lấy dependency.

---

## 6. Nối vào server

`config.ini` được sinh tự động từ template lúc build, và **mặc định đã đúng**:

```ini
[CONNECTION SETTINGS]
ServerIP=localhost
ServerPort=44405
```

Đúng bằng connect server của OpenMU all-in-one. Hoặc truyền trên dòng lệnh:

```bash
cd out/build/linux-x64/src/Release
./Main /u127.0.0.1 /p44405
```

Log thành công (`MuError.log`):

```
[core]   > Login Scene init success.
[dotnet] NET: First packet received -- handle=1 size=4 (callback path working)
[core]   Send Request Server List.
[core]   Success Receive Server List.
```

Đăng nhập bằng test account của OpenMU, ví dụ `test400` / `test400`.

---

## 7. Điều khiển client bằng script (control socket)

Tính năng rất mạnh để vọc: login, chọn nhân vật, đi, đánh, chat, chụp màn hình —
tất cả từ shell, không cần ai ngồi bàn phím.

Build với `-DENABLE_CONTROL_SOCKET=ON` (preset `-mueditor` đã bật sẵn), rồi:

```bash
MU_CONTROL_SOCKET=/tmp/mu.sock ./Main /u127.0.0.1 /p44405
```

Giao thức: JSON phân cách bằng newline trên Unix socket, 1 request = 1 response.

```bash
printf '{"cmd":"ping"}\n' | socat - UNIX-CONNECT:/tmp/mu.sock
{"ok":true,"result":{"build":"Sep 28 2026 14:44:23","scene":"login"}}
```

Kèm sẵn `mu-drive.py`:

```bash
MU_CONTROL_SOCKET=/tmp/mu.sock ./mu-drive.py           # demo: login -> vào world -> screenshot
MU_CONTROL_SOCKET=/tmp/mu.sock ./mu-drive.py state
MU_CONTROL_SOCKET=/tmp/mu.sock ./mu-drive.py raw '{"cmd":"say","text":"hello"}'
```

Output thật của lần chạy demo:

```
[OK ] ping           {"build": "Sep 28 2026 14:44:23", "commit": "bbc077af...", "scene": "login"}
[OK ] login          {"account": "test400", "characters": [{"level": 400, "name": "test400Dk", "slot": 1}, ...]}
[OK ] select-char    {"character": "test400Dk", "map": 0, "position": [147, 118], "scene": "world"}
  -> test400Dk | class=12 lv400 | Lorencia [147, 118] | HP 132/1110 | zen 10000000
     nearby: npc      Leo the Helper
     nearby: npc      Shadow Phantom Soldier
     nearby: npc      Safety Guardian
[OK ] screenshot     {"height": 768, "path": "/tmp/mu-screenshot.jpg", "width": 1024}
```

### Bẫy trong `login`

Tham số `server` là **tên server group**, không phải index. Truyền `server=0` thì:

```json
{"ok":false,"error":"bad_request",
 "message":"`server` is the name of a server group; omit it for the first one"}
```

Bỏ hẳn tham số đó đi là lấy group đầu tiên.

### Các lệnh có sẵn

`ping` · `scene` · `state` · `nearby` · `events` · `wait-for` · `screenshot` ·
`login` · `select-char` · `logout` · `quit` · `move` · `warp` · `teleport` ·
`attack` · `skill` · `pickup` · `use` · `equip` · `say` · `whisper` · `party` ·
`trade` · `halt` · `click-ui`

Lệnh điều khiển nhân vật chạy tuần tự (lệnh sau ngắt lệnh trước và báo lại tiến
độ); lệnh đọc (`state`, `screenshot`, `events`) chạy song song. Tất cả được phục
vụ trên main thread, mỗi frame một lần, sau khi packet của frame đó đã xử lý —
nên không bao giờ race với game logic.

> Control socket **chỉ có** trong build bật `ENABLE_CONTROL_SOCKET`. Build cho
> người chơi không compile một dòng nào của nó, và test `control_socket_leak`
> trong test suite chứng minh điều đó.

Repo còn có `InGameTests` (bật kèm `ENABLE_IN_GAME_TESTS` ở preset `-mueditor`):
một GUI tự dựng OpenMU bằng docker ở chế độ `-demo` (in-memory, reset mỗi lần
chạy), lái nhiều client cùng lúc theo kịch bản rồi xuất report kèm screenshot.

---

## 8. Chạy headless (CI / server không màn hình)

Client cần display + Vulkan. Dùng Xvfb + lavapipe (Vulkan phần mềm của Mesa):

```bash
sudo apt-get install -y xvfb mesa-vulkan-drivers
Xvfb :99 -screen 0 1024x768x24 &

DISPLAY=:99 \
VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json \
SDL_VIDEODRIVER=x11 SDL_AUDIODRIVER=dummy \
XDG_RUNTIME_DIR=/tmp/xdg \
MU_CONTROL_SOCKET=/tmp/mu.sock \
./Main /u127.0.0.1 /p44405
```

`SDL_AUDIODRIVER=dummy` quan trọng: không có sound card thì miniaudio spam
`failed to init stream 'data\music\login_theme.mp3' (-7)` mỗi ~200ms, ngập log.
Lỗi này vô hại, không chặn game.

Nếu client dừng với `SDL video init failed`, build lại với
`-DMU_LINK_SDL_PLATFORM_BACKENDS=ON` để SDL link thẳng backend lúc build.

---

## 9. Ghi chú

- `--depth 1` khi clone: repo đầy đủ nặng vì có game data trong lịch sử.
- Lần build đầu compile cả SDL và freetype vendored nên lâu; build lại chỉ
  vài phút (Ninja Multi-Config, mỗi preset một build tree riêng).
- Bật/tắt editor là lựa chọn **lúc configure**, Debug/Release là **lúc build** —
  hai trục độc lập.
- Muốn clangd index được cả code editor: configure một lần preset
  `linux-x64-mueditor` rồi trỏ `--compile-commands-dir=out/build/linux-x64-mueditor`.
  Chỉ cần configure, không cần build.
- Client này chạy với OpenMU nhờ protocol Season 6 Ep3 **đã được mở rộng**
  (damage/exp vượt 16 bit, item và appearance serialize lại, thanh máu quái).
  Nó **không** tương thích với server MU gốc hay các MuServer emulator khác.

---

## 10. Pháp lý

**OpenMU** (server): MIT, viết lại từ đầu, sạch.

**MuMain** (client): repo **không có file LICENSE**, gốc là source client
Season 5.2 rò rỉ từ Webzen (`LouisEmulator/Main5.2`). Học hành, vọc vạch thì
bình thường — nó public nhiều năm, cộng đồng lớn, tác giả OpenMU duy trì.
Nhưng đừng thương mại hóa.
