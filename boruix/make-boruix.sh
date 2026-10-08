#!/bin/sh
# make-boruix.sh —— 构建 **host=boruix** 的 GCC（Canadian cross），配 configure-boruix.sh 使用。
#
#   build  = x86_64-pc-msys   （MSYS2 gcc 编构建期工具）
#   host   = x86_64-boruix    （用 boruix-cc shim 编**在 Boruix 内运行**的 gcc/cc1）
#   target = x86_64-elf
#
# 用法: BORUIX_SYSROOT=<sysroot> sh make-boruix.sh [build-dir] [src-dir] [make-target]
set -e
if [ -z "$BORUIX_SYSROOT" ]; then
  echo "需要 BORUIX_SYSROOT（install --prefix 的产物）" >&2
  exit 1
fi
BUILD_DIR=$1
[ -n "$BUILD_DIR" ] || BUILD_DIR=/f/boruix-project/.tmp-gcc/build-native
SRC_DIR=$2
[ -n "$SRC_DIR" ] || SRC_DIR=/f/boruix-project/.tmp-gcc/gcc-14.2.0
MAKE_TARGET=$3
[ -n "$MAKE_TARGET" ] || MAKE_TARGET=all-gcc
J=$BORUIX_JOBS
[ -n "$J" ] || J=8

# **autoconf 的缓存变量必须覆盖整个构建，而不只是顶层 configure**（2026-10 实测）：
# 子 configure 是 `make` 在稍后拉起的，从**环境**继承。而
#   checking whether byte ordering is bigendian…
# 靠**运行**编译出的程序来判断，而 boruix 的 ELF 在宿主上跑不了 ⇒ 不给缓存就是
#   configure: error: unknown endianness        （gcc/configure:9811 实测）
# x86-64 与构建机（msys/x86-64）都是小端，故 no 对两侧都成立。
export ac_cv_c_bigendian=no

cd "$BUILD_DIR"
make -k -j"$J" MAKEINFO=true "$MAKE_TARGET"
