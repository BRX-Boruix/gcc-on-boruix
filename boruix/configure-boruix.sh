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
#   - GCC 源码树已解压；**树内 gmp/mpfr/mpc 必须改名禁用**（见下）；
#   - config.sub / configfsf.sub 已打补丁（见 ../UPSTREAM-PATCHES）；
#   - BORUIX_SYSROOT 指向 `python tools/main.py install --prefix <dir>` 的产物；
#   - boruix/boruix-cc 可用（宿主编译器 shim）。
#
# **前置库 GMP/MPFR/MPC：不用树内内联构建，改为各自装进同一 prefix 再 --with-* 指过去。**
# 实测（2026-10，逐条真实报错驱动）：
#   - 树内内联构建 GMP 报 `configure: error: Oops, mp_limb_t doesn't seem to work`
#     （Canadian cross 下 GMP 自己测不出 mp_limb_t 宽度）。把树内 gmp/mpfr/mpc 改名成
#     *.disabled 让 --with-* 生效后，三个库各自 --host=x86_64-boruix 构建安装成功：
#     GMP 516 个目标文件 / libgmp.a 1081482 B；MPFR 257 / libmpfr.a 3283340 B；
#     MPC 86 / libmpc.a 908268 B。
#   - **每个自带 autotools 的子项目都要打 config.sub 补丁**，包括 MPC 的
#     `build-aux/config.sub`——否则 `configure: error: Invalid configuration
#     'x86_64-pc-boruix': OS 'boruix' not recognized`。（此前记的「mpc 没有 config.sub」
#     是**错的**：它只是放在 build-aux/ 下，不在顶层。）
#
# **为什么 --with-* 的值必须是 Windows 风格绝对路径**：它会被写进生成的 Makefile，
# 最终作为 -I/-L 传给**原生 Windows** clang；MSYS 风格的 /f/... clang 解析不了。
#
# **为什么显式传 AR/RANLIB/NM/OBJDUMP/STRIP**：跨构建下 GCC 默认去找 `${host}-ar`
# （即 x86_64-boruix-ar），而 Boruix 没有 binutils。**归档只是容器，与目标无关**，故用 LLVM
# 的对应工具即可。实测（未传时）：`make` 报 `[Makefile:529：libz.a] 错误 127`
# （No such file or directory）。
set -e
: "${BORUIX_SYSROOT:?需要 BORUIX_SYSROOT（install --prefix 的产物）}"
BIN=${BORUIX_LLVM_BIN:-/f/clang/18.1.8x86_64/bin}
HERE=$(cd "$(dirname "$0")" && pwd)
# Windows 风格副本：CC 的值要交给原生 clang 链路（见文件头「Windows 风格绝对路径」）。
HERE_WIN=$(cd "$(dirname "$0")" && pwd -W 2>/dev/null || pwd)
BUILD_DIR=${1:-/f/boruix-project/.tmp-gcc/build}
SRC_DIR=${2:-/f/boruix-project/.tmp-gcc/gcc-14.2.0}
# 前置库安装 prefix（Windows 风格；可用 BORUIX_GCC_PREFIX_WIN 覆盖）。
PREFIX_WIN=${BORUIX_GCC_PREFIX_WIN:-F:/boruix-project/.tmp-gcc/host-prefix}
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

CC_FOR_BUILD=/usr/bin/gcc \
AR="$BIN/llvm-ar.exe" RANLIB="$BIN/llvm-ranlib.exe" NM="$BIN/llvm-nm.exe" \
OBJDUMP="$BIN/llvm-objdump.exe" STRIP="$BIN/llvm-strip.exe" \
CC="sh $HERE_WIN/boruix-cc" \
# **CXX 必须一起指到 shim**（2026-10 实测的根因）：只设 CC 时，GCC 的 C++ 部分（`cc1` 就是 C++）
# 会回落到**构建系统的 g++**——而 `g++` 用的是 **PE 链接器**，却要去链**宿主期（boruix/ELF）**的
# `libiberty.a`/`libmpc.a`/`libz.a` ⇒ 13 处链接失败，报 `access beyond end of merged section`
# （PE 链接器读 ELF 对象）。设了 CXX 后 C++ 与 C 走同一条 shim 路径。
CXX="sh $HERE_WIN/boruix-cc" \
"$SRC_DIR/configure" \
  --build=x86_64-pc-msys \
  --host=x86_64-boruix \
  --target=x86_64-elf \
  --enable-languages=c \
  --disable-nls --disable-bootstrap --disable-shared --disable-multilib \
  --without-headers --disable-libssp --disable-libquadmath --disable-threads \
  --disable-libatomic --disable-libgomp --disable-libitm --disable-libsanitizer \
  --without-isl \
  # fixincludes 是**宿主构建期**的头文件修补工具（不是系统内 GCC 的组成部分），它要 `alarm(10)`
  # 给子进程装超时，而本系统**没有 interval timer**（`alarm` 已核实判不支持，见
  # docs/TODO/libc-posix-surface.md）。**不提供 alarm 是有意的**：编译期报 `call to undeclared
  # function 'alarm'` 比「声明了却永远不发 SIGALRM」诚实。故用 --disable-fixincludes 排除该工具。
  --disable-fixincludes \
  --with-gmp="$PREFIX_WIN" --with-mpfr="$PREFIX_WIN" --with-mpc="$PREFIX_WIN"
echo "CONFIGURE_DONE"
