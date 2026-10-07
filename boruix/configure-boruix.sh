#!/bin/sh
# configure-boruix.sh —— 把 GCC 14.2.0 配置成 **hosted-on-Boruix** 的 Canadian cross。
#
#   build  = x86_64-pc-msys   （MSYS2 gcc 编"构建期工具"，如 gen*）
#   host   = x86_64-boruix    （用 clang 18 + Boruix sysroot 编**在 Boruix 内运行**的 gcc/cc1）
#   target = x86_64-elf       （裸机 x86-64，与 BORUIX 的 ABI 同形；libc 由 Boruix sysroot 提供）
#
# **硬性要求（实测踩过）**：configure 必须用 **Windows 风格绝对路径**调用（F:/... 而不是 /f/...）。
# 否则 configure 生成的 conftest.c / Makefile 里会带 MSYS2 风格路径，而 shim 调的是**原生 Windows**
# clang，解析不了 /f/... —— 表现为 GMP 的 `checking size of mp_limb_t... 0` ->
# `configure: error: Oops, mp_limb_t doesn't seem to work`（根因见 config.log 里的 gmp-h.in 路径）。
#
# 前置：
#   - GCC 源码树已解压，gmp/mpfr/mpc 已放进树内（GCC 会内联构建它们）；
#   - config.sub / configfsf.sub 已打补丁（见 ../UPSTREAM-PATCHES）；
#   - BORUIX_SYSROOT 指向 `python tools/main.py install --prefix <dir>` 的产物；
#   - boruix/boruix-cc 可用（宿主编译器 shim）。
#
# **为什么显式传 AR/RANLIB/NM/OBJDUMP/STRIP**：跨构建下 GCC 默认去找 `${host}-ar`
# （即 x86_64-boruix-ar），而 Boruix 没有 binutils。**归档只是容器，与目标无关**，故用 LLVM
# 的对应工具即可。实测（未传时）：`make` 报 `[Makefile:529：libz.a] 错误 127`
# （No such file or directory）。
set -e
: "${BORUIX_SYSROOT:?需要 BORUIX_SYSROOT（install --prefix 的产物）}"
BIN=${BORUIX_LLVM_BIN:-/f/clang/18.1.8x86_64/bin}
HERE=$(cd "$(dirname "$0")" && pwd)
BUILD_DIR=${1:-/f/boruix-project/.tmp-gcc/build}
SRC_DIR=${2:-/f/boruix-project/.tmp-gcc/gcc-14.2.0}
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

CC_FOR_BUILD=/usr/bin/gcc \
AR="$BIN/llvm-ar.exe" RANLIB="$BIN/llvm-ranlib.exe" NM="$BIN/llvm-nm.exe" \
OBJDUMP="$BIN/llvm-objdump.exe" STRIP="$BIN/llvm-strip.exe" \
CC="sh $HERE/boruix-cc" \
"$SRC_DIR/configure" \
  --build=x86_64-pc-msys \
  --host=x86_64-boruix \
  --target=x86_64-elf \
  --enable-languages=c \
  --disable-nls --disable-bootstrap --disable-shared --disable-multilib \
  --without-headers --disable-libssp --disable-libquadmath --disable-threads \
  --disable-libatomic --disable-libgomp --disable-libitm --disable-libsanitizer \
  --without-isl
echo "CONFIGURE_DONE"
