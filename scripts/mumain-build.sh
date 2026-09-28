#!/usr/bin/env bash
# Build client MuMain (Linux x64) va noi vao OpenMU.
# Da chay that: Ubuntu 24.04, gcc 13, cmake 3.28.3, .NET SDK 10.0.112, 4 core.
# Ket qua: 997/997 target, 321/321 test pass, login duoc vao Lorencia.
#
# Dung: ./mumain-build.sh [thu-muc]   (mac dinh: ./MuMain)
set -euo pipefail

TARGET="${1:-$PWD/MuMain}"
PRESET="${PRESET:-linux-x64}"              # linux-x64 | linux-x64-mueditor
CONTROL_SOCKET="${CONTROL_SOCKET:-OFF}"    # ON de script dieu khien client
JOBS="${JOBS:-$(nproc)}"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mLOI: %s\033[0m\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- 1. He thong
say "Cai dependency he thong"
sudo apt-get update -qq
# Danh sach chuan cua docs...
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  build-essential cmake ninja-build pkg-config clang zlib1g-dev \
  libgl1-mesa-dev libglu1-mesa-dev libglew-dev libegl1-mesa-dev libturbojpeg0-dev \
  libx11-dev libxext-dev libxrandr-dev libxi-dev libxcursor-dev \
  libxfixes-dev libxrender-dev libxss-dev libxtst-dev libxkbcommon-dev \
  libdrm-dev libgbm-dev libwayland-dev libdecor-0-dev wayland-protocols \
  libasound2-dev libpulse-dev libdbus-1-dev libudev-dev
# ...cong 3 goi docs QUEN liet ke, thieu la CMake configure fail:
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  libcurl4-openssl-dev libssl-dev libvulkan-dev

# ------------------------------------------------------------------ 2. .NET 10
if ! command -v dotnet >/dev/null || ! dotnet --list-sdks 2>/dev/null | grep -q '^10\.'; then
  say "Cai .NET SDK 10 (+ NativeAOT components)"
  # Ubuntu 24.04 co san trong archive; khong can dotnet-install.sh
  if apt-cache policy dotnet-sdk-10.0 2>/dev/null | grep -q Candidate:' *[0-9]'; then
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq dotnet-sdk-10.0 dotnet-sdk-aot-10.0
  else
    curl -sSL https://dot.net/v1/dotnet-install.sh | bash -s -- --channel 10.0 --install-dir "$HOME/.dotnet"
    export PATH="$HOME/.dotnet:$PATH" DOTNET_ROOT="$HOME/.dotnet"
  fi
fi
dotnet --list-sdks | grep '^10\.' >/dev/null || die ".NET SDK 10 chua san sang"

# -------------------------------------------------------------------- 3. Clone
if [ ! -d "$TARGET/.git" ]; then
  say "Clone MuMain (~800 MB: engine + 722 MB game data)"
  git clone --depth 1 https://github.com/sven-n/MuMain.git "$TARGET"
else
  say "Da co repo tai $TARGET"
fi
cd "$TARGET"

say "Init submodule (SDL, imgui)"
git submodule update --init --depth 1

# --------------------------------------- 4. miniaudio (workaround mang bi chan)
# CMake keo miniaudio bang URL tarball qua codeload.github.com. Neu mang/proxy
# chan codeload (403), clone bang git roi tro FetchContent vao thu muc do.
MINIAUDIO_COMMIT=$(grep -oP 'miniaudio/archive/\K[0-9a-f]{40}' CMakeLists.txt | head -1)
EXTRA_CMAKE=()
if [ -n "$MINIAUDIO_COMMIT" ]; then
  if ! curl -sSf -o /dev/null --max-time 15 \
        "https://github.com/mackron/miniaudio/archive/${MINIAUDIO_COMMIT}.tar.gz" 2>/dev/null; then
    say "codeload bi chan -> clone miniaudio @ ${MINIAUDIO_COMMIT:0:12} bang git"
    D="$PWD/.deps/miniaudio"
    rm -rf "$D" && mkdir -p "$D" && git -C "$D" init -q
    git -C "$D" remote add origin https://github.com/mackron/miniaudio.git
    git -C "$D" fetch -q --depth 1 origin "$MINIAUDIO_COMMIT"
    git -C "$D" checkout -q FETCH_HEAD
    EXTRA_CMAKE+=("-DFETCHCONTENT_SOURCE_DIR_MINIAUDIO=$D")
  fi
fi

# ----------------------------------------------------------- 5. Configure/build
say "Configure (preset=$PRESET, control socket=$CONTROL_SOCKET)"
cmake --preset "$PRESET" -DENABLE_CONTROL_SOCKET="$CONTROL_SOCKET" "${EXTRA_CMAKE[@]}"

say "Build voi $JOBS job (lan dau ~20 phut tren 4 core)"
cmake --build --preset "${PRESET}-release" -j"$JOBS"

say "Chay test"
ctest --test-dir "out/build/$PRESET" -C Release --output-on-failure | tail -5

OUT="$PWD/out/build/$PRESET/src/Release"
cat <<DONE

============================================================
  MuMain da build xong
============================================================
  Binary   : $OUT/Main
  Net lib  : $OUT/MUnique.Client.Library.so   (.NET NativeAOT)
  Data     : $(du -sh "$OUT/Data" 2>/dev/null | cut -f1) (da copy san)
  config   : $OUT/config.ini

  Chay (server mac dinh trong config.ini la localhost:44405):
    cd $OUT && ./Main

  Hoac chi dinh server tren dong lenh:
    ./Main /u127.0.0.1 /p44405

  Neu build trong WSL, ep dung GPU passthrough cho nhanh:
    MESA_LOADER_DRIVER_OVERRIDE=d3d12 ./Main
============================================================
DONE
