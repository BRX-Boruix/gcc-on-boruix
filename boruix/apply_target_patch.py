#!/usr/bin/env python3
"""把 `x86_64-*-boruix*` 这个 GCC target 支持施加到 GCC 源码树（**幂等 + 锚点校验**）。

## 交付形态（为什么是「脚本 + patch」双份）

仓策略：**GCC 源码树不入版本控制**（在 `.tmp-gcc/`）。故本移植以**可重放**的形式交付：
- 本脚本：幂等，带**锚点校验**；锚点找不到就**报错退出**，绝不静默跳过（S09 宁可报错）。
- 同目录 `patches/*.patch`：`diff -u` 产物，供上游提交/评审（由本脚本 `--emit-patch` 生成，**不手写**）。

## 本次范围（S24 单组件专注）

**只做插入点 1**：让 GCC **认识** `x86_64-*-boruix*` 这个 target。
插入点 2（`libgcc/config.host`）与 3（`libstdc++-v3`）在后续步骤——**本脚本不假装做了它们**。

用法:
    python apply_target_patch.py --tree <gcc-14.2.0> [--check|--revert|--emit-patch <dir>]
退出码: 0 = 成功；1 = 锚点/前置不满足（含具体原因）；2 = 用法错误。
"""
import argparse
import os
import subprocess
import sys

# 锚点：`x86_64-*-elf*` 那个 case 块。**精确到字节**——它变了就说明源码树不是预期版本。
ANCHOR = ('x86_64-*-elf*)\n'
          '\ttm_file="${tm_file} i386/unix.h i386/att.h elfos.h newlib-stdint.h i386/i386elf.h i386/x86-64.h"\n'
          '\t;;\n')

# Boruix 的 case 块。
# - 保留 i386/unix.h i386/att.h elfos.h i386/i386elf.h i386/x86-64.h：**ABI 事实**（x86-64 ELF/SysV）。
# - 用 **boruix-stdint.h**（提供类型宏）+ **use_gcc_stdint=provide**（GCC 装自己的 <stdint.h>）：
#   两份并存会打架（S15 单点定义）。故 use_gcc_stdint=none：GCC 不提供 stdint。
# - tmake_file 参照 x86_64-*-rdos*（同为小型 OS）。
INSERT = ('x86_64-*-boruix*)\n'
          '\ttm_file="${tm_file} i386/unix.h i386/att.h elfos.h boruix-stdint.h i386/i386elf.h i386/x86-64.h boruix.h"\n'
          '\ttmake_file="i386/t-i386elf t-svr4"\n'
          '\tuse_gcc_stdint=provide\n'
          '\t;;\n')

# ---- 插入点 2：libgcc/config.host ----
#
# 让 libgcc 能为 boruix 构建。模板是 `x86_64-*-elf* | x86_64-*-rtems*)`（同族 ABI/链接器）。
#
# **诚实说明（S39）**：本条与 elf 那条目前**只有注释上的差别**——`tmake_file` 相同。
# 之所以单列而不并入 elf 的模式行：① 给 boruix 留一个**明确的落点**，后续差异（如
# `crtbegin/crtend`）有地方写；② 不把 boruix 绑在 elf 那行的未来改动上。
#
# **尚未决定的差异点（不预先写进去）**：`crtbegin.o`/`crtend.o`。
#  - `libgcc/config.host:71` 的 `extra_parts=` 默认**为空**，`i386/t-crtstuff` 只设
#    `CRTSTUFF_T_CFLAGS` ⇒ **`x86_64-*-elf*` 不装 crtbegin/crtend**（裸机不需要）。
#  - 它们对 C++ 的作用是：`.init_array`/`.fini_array` 边界、`__dso_handle`、EH frame 注册。
#  - **但本系统的 `.init_array` 边界由 `csrc/linker.ld` 提供、遍历由 `csrc/boruix_crt.h` 完成**
#    （已在系统内实测跑通）；而 `.eh_frame` 目前被 `linker.ld` **丢弃**（见 3p.md 的独立发现）。
#  - ⇒ 现阶段加它们**可能冗余甚至与自有符号冲突**。故**先不加**，等 libgcc 真能构建、
#    并出现明确的缺失证据（如 `__dso_handle` 未定义）再按证据加。
ANCHOR2 = 'x86_64-*-elf* | x86_64-*-rtems*)\n'
INSERT2 = ('x86_64-*-boruix*)\n'
          '\t# Boruix：与 elf 同族（x86-64 ELF / SysV ABI）的小型托管 OS。\n'
          '\t# 见 gcc-on-boruix/boruix/PORTING-TARGET.md；crtbegin/crtend 的取舍见该文件。\n'
          '\ttmake_file="$tmake_file i386/t-crtstuff t-crtstuff-pic t-libgcc-pic"\n'
          '\t;;\n')

# ---- 插入点 3：libstdc++-v3/crossconfig.m4 ----
#
# **红态是硬的**：crossconfig.m4 的默认分支是 `AC_MSG_ERROR([No support for this host/target
# combination.])` ⇒ boruix 会让 libstdc++ 的 configure **直接失败**。
#
# 两条设计决定（都写进分支注释，S39）：
#  1) **线程**：本系统没有 pthread 面。这里**机械拒绝**「假装有线程」的配置（必须 --disable-threads），
#     而不是只在文档里建议。`enable_threads` 由 configure.ac:170 的 GLIBCXX_ENABLE_THREADS 设置，
#     早于 406 行的 GLIBCXX_CROSSCONFIG ⇒ 本处已就位（已核实）。
#  2) **故意不 AC_DEFINE 任何 `HAVE_*F`**：那些是「目标 libc 有该函数」的断言，而交叉构建跑不了
#     运行时探测。**未验证的能力不写进去**（S09）——等 libgcc/libstdc++ 真构建时按实际缺失证据再补。
ANCHOR3 = '  *)\n    AC_MSG_ERROR([No support for this host/target combination.])\n   ;;\n'
INSERT3 = ('  x86_64-*-boruix*)\n'
           '    dnl Boruix（见 gcc-on-boruix/boruix/PORTING-TARGET.md）。\n'
           '    dnl\n'
           '    dnl 1) **线程**：本系统没有 pthread 面（libsys/libc 均未提供）。故这里**机械拒绝**\n'
           '    dnl    「假装有线程」的配置——必须以 --disable-threads 配置。这是门，不是建议。\n'
           '    if test "$enable_threads" != "no"; then\n'
           '      AC_MSG_ERROR([Boruix has no pthread support; configure libstdc++ with --disable-threads.])\n'
           '    fi\n'
           '    dnl\n'
           '    dnl 2) **故意不 AC_DEFINE 任何 HAVE_*F**：那些是「目标 libc 有该函数」的断言，而交叉\n'
           '    dnl    构建跑不了运行时探测。**未验证的能力不写进去**（S09）——等真构建时按实际缺失\n'
           '    dnl    证据再补（证据驱动，不是猜）。\n'
           '    ;;\n')

BORUIX_H = '''/* Boruix 的 target 事实与**链接规格**（只写已验证的，S06/S13）。

   ## 链接规格（LINK_SPEC 等）—— 来路是真实报错，不是预猜

   libgcc 的 configure 报：
       configure: error: cannot compute suffix of object files: cannot compile
   真因：xgcc 默认去找 crt1.o/crti.o/crtbegin.o 与系统 ld，而本系统都没有，
   它会退到 Cygwin 的 PE 链接器。

   本规格与 `gcc-on-boruix/boruix/boruix-cc`（sysroot 的 C 驱动）**同一配方**：
   `ld.lld -e _start -nostdlib --no-dynamic-linker -z noexecstack -z norelro -T linker.ld`。
   链接器本身由 configure 的 `--with-ld=<ld.lld>` 指定，故此处只写**参数**。
   `%R` = sysroot 前缀（由 configure 的 --with-sysroot 提供）。 */

/* 汇编器：GCC 走 cc1 -> .s -> 汇编器 -> .o，而本工具链此前只有 clang 的 C->.o 一步到位
   （boruix-cc shim 里没有独立汇编阶段）⇒ 这是我漏掉的一等前置（第 16 轮实测：
   `build-boruix/gcc/as: line 114: exec: -o: invalid option`，因为没配 --with-as）。
   做法：**旗标放 ASM_SPEC、程序名放 --with-as**（而不是写 .sh/.bat 包装——
   Windows 下 GCC 直接 exec 包装脚本会失败，与 --with-ld 同一考虑）。
   故 configure 需 `--with-as=F:/clang/18.1.8x86_64/bin/clang.exe`。 */
/* cc1 的固定旗标（第 26 轮实测驱动）。
   来路：汇编器前置修好后，`xgcc -c` 报
     `error: changed section flags for .eh_frame, expected: 0x2`
   （clang 的集成汇编器不接受 GCC 发的 `.section .eh_frame,"aw",@progbits`）。
   **与本系统的现状一致**：`csrc/linker.ld` 本来就把 `*(.eh_frame*)` 丢进 /DISCARD/，
   且 Boruix **没有异常展开运行时**（`.eh_frame` 无消费者）。故这里让 cc1 干脆不生成它——
   **不是绕过，是让编译产物与链接脚本的既有事实一致**（S15：一处事实，两处不打架）。
   **诚实边界**：将来若要支持 C++ 异常，必须同时改三处（本旗标、linker.ld 的 DISCARD、
   以及提供 __register_frame_info 一侧），**不能只去掉这一行**。 */
#undef CC1_SPEC
#define CC1_SPEC "-fno-asynchronous-unwind-tables -g0"
/* `-g0` 的来路（第 28 轮实测）：libgcc 的 config.log 里除 `.eh_frame` 外还有
     error: changed section flags for .debug_str, expected: 0x30
     error: changed section entsize for .debug_str, expected: 1
   —— `-g` 产生的调试段同样与 clang 集成汇编器的期望冲突。**诚实边界**：`-g0` 意味着
   本 target 目前**产不出调试信息**（bootstrap 期的取舍）；将来要调试支持，须换用与 GCC
   段旗标兼容的汇编器，或让 clang 接受这些旗标——**不能只删这一行**。 */

#undef ASM_SPEC
/* **空**：汇编器已从 clang 换成 **GNU as**（binutils 2.43.1, x86_64-elf，见第 40 轮）。
   clang 需要 `--target=... -c`；而 **GNU as 支持长选项缩写**，会把 `--target=x86_64-unknown-none`
   误匹配成 `--target-help` 并因多出参数而报错：
     as: option `--target-help' doesn't allow an argument
   GNU as 本就是 x86_64-elf 目标、且默认「只汇编」，故两者都不需要。 */
#define ASM_SPEC ""

#undef STARTFILE_SPEC
#define STARTFILE_SPEC "%{!nostdlib:%{!r:%R/lib/user_main.o%s}}"
#undef ENDFILE_SPEC
#define ENDFILE_SPEC ""
#undef LIB_SPEC
#define LIB_SPEC "%{!nostdlib:-L%R/lib -lc}"
#undef LINK_SPEC
#define LINK_SPEC "%{!r:-m elf_x86_64 -e _start --no-dynamic-linker -z noexecstack -z norelro -T %R/lib/linker.ld}"

/* Boruix 的 target 事实（**只写已验证的**，S06/S13）。

   本文件由 gcc-on-boruix/boruix/apply_target_patch.py 施加，**不是上游文件**；
   上游提交时随 patches/ 一起走。

   诚实边界：本文件**只声明已被本仓验证过的事实**。不定义 __linux__ 等其它 OS 的宏——
   那会让程序走错分支（比不定义更坏）。 */

/* 本 OS 的预定义宏。__ELF__ 由 elfos.h 提供，此处不重复定义。 */
#undef TARGET_OS_CPP_BUILTINS
#define TARGET_OS_CPP_BUILTINS() \\
  do {                                   \\
    builtin_define ("__boruix__");        \\
  } while (0)
'''


def _fix_stdout():
    """S02：不依赖系统默认编码。Windows 控制台常是 GBK，写非 GBK 字符会**崩**
    （本脚本首版就因 `⇒` 抛 UnicodeEncodeError 而崩）。故显式指定编码 + errors=replace。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _case_target_blocks(lines, var="${target}"):
    """找出所有 `case <var> in ... esac` 块。

    **`var` 必须按文件给对**（2026-10 实测教训）：`gcc/config.gcc` 用的是 `case ${target} in`，
    而 **`libgcc/config.host` 用的是 `case ${host} in`**（那里的 `host` 指 libgcc 的宿主即目标）。
    首版写死 `${target}`，于是对 config.host 找不到块、误报 FAIL。

    返回 [(start0, end0, [(label0, [patterns])])]，行号为 **0-based**。
    实测（2026-10）：config.gcc 的块边界是 291-334 / 342-599 / 633-686 / 689-693 / 724-1178 /
    1181-1189 / **1191-3631** / …；`tm_file` 是在 **1191-3631** 里按目标逐条设的。"""
    blocks = []
    for i, s in enumerate(lines):
        if s.strip() != ("case " + var + " in"):
            continue
        j = i + 1
        while j < len(lines) and lines[j].rstrip() != "esac":
            j += 1
        labels = []
        for k in range(i + 1, j):
            t = lines[k]
            # 顶层 case 标签：行首无缩进且以 `)` 结尾（如 `x86_64-*-elf*)`）。
            if t and not t[0].isspace() and t.rstrip().endswith(")"):
                pats = [p.strip() for p in t.rstrip()[:-1].split("|")]
                labels.append((k, pats))
        blocks.append((i, j, labels))
    return blocks


def _first_matching_case_before(lines, ours_1based, target, var="${target}"):
    """在同**块**内、我们这条之前，是否有 case 也匹配 `target`（shell 是**先匹配者胜**）。

    跨块比行号**毫无意义**（两块都执行、各设各的变量）——本脚本首版就是这么误报的。
    返回 (行号, 模式) 或 None；块找不到则返回 ("?", "?")。"""
    import fnmatch
    blk = next((b for b in _case_target_blocks(lines, var) if b[0] + 1 <= ours_1based <= b[1] + 1), None)
    if blk is None:
        return ("?", "?")
    for (k, pats) in blk[2]:
        if k + 1 >= ours_1based:
            break
        for p in pats:
            if fnmatch.fnmatchcase(target, p):
                return (k + 1, p)
    return None


def die(msg):
    print("[FAIL] " + msg)
    return 1


def main():
    _fix_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", required=True)
    ap.add_argument("--check", action="store_true", help="只校验是否已是目标状态")
    ap.add_argument("--revert", action="store_true", help="撤销（移除本脚本加的块）")
    ap.add_argument("--emit-patch", metavar="DIR", help="把 diff -u 产物写到该目录")
    a = ap.parse_args()

    cfg = os.path.join(a.tree, "gcc", "config.gcc")
    if not os.path.isfile(cfg):
        return die("找不到 " + cfg + "（--tree 应指向 GCC 源码树根）")
    with open(cfg, encoding="utf-8", errors="surrogateescape") as f:
        src = f.read()
    has_insert = "x86_64-*-boruix*)" in src

    if a.check:
        print("[check] config.gcc 已含 boruix 分支 = %s" % has_insert)
        h = os.path.join(a.tree, "gcc", "config", "boruix.h")
        h_ok = os.path.isfile(h)
        print("[check] gcc/config/boruix.h 存在 = %s" % h_ok)
        ok = has_insert and h_ok
        # **顺序检查——这才是本补丁的真实语义**（2026-10 更正）：
        # `config.gcc` 是 shell `case`，**先匹配者胜**；兜底分支 `i[34567]86-*-* | x86_64-*-*)`
        # **也能**匹配 `x86_64-boruix`，故我们的分支**必须排在它之前**才抢得到。
        # 此前我把验收错定成「configure 能否成功」——而它本来就成功（兜底接住了），
        # **红态没红**才发现前提有误。故这条顺序检查才是对的验收。
        if has_insert:
            lines = src.splitlines()
            ours = next((i + 1 for i, l in enumerate(lines) if l.startswith("x86_64-*-boruix*)")), None)
            print("[check] boruix 分支在第 %s 行" % ours)
            # **同块内**的先匹配者胜。跨块比行号无意义（config.gcc 有多个 case ${target} in 块，
            # 各设各的变量；`tm_file` 的块是 1191-3631）。
            early = _first_matching_case_before(lines, ours, "x86_64-pc-boruix")
            if early == ("?", "?"):
                print("[FAIL] 找不到包含该分支的 `case ${target} in` 块 => 无法判定匹配顺序，**拒绝通过**")
                ok = False
            elif early is not None:
                print("[FAIL] 同块内第 %s 行的模式 `%s` **也匹配** x86_64-pc-boruix 且排在我们之前"
                      % (early[0], early[1]))
                print("       => shell case 先匹配者胜，本分支**永远轮不到**（补丁等于无效）")
                ok = False
            else:
                print("[OK] 同块内没有更早的模式匹配 x86_64-pc-boruix => 本分支抢到匹配（补丁有效）")
        # ---- 插入点 2：libgcc/config.host ----
        h2 = os.path.join(a.tree, "libgcc", "config.host")
        if not os.path.isfile(h2):
            print("[FAIL] 找不到 " + h2)
            return 1
        with open(h2, encoding="utf-8", errors="surrogateescape") as f:
            src2 = f.read()
        has2 = "x86_64-*-boruix*)" in src2
        print("[check] libgcc/config.host 已含 boruix 分支 = %s" % has2)
        ok = ok and has2
        if has2:
            l2 = src2.splitlines()
            ours2 = next((i + 1 for i, l in enumerate(l2) if l.startswith("x86_64-*-boruix*)")), None)
            early2 = _first_matching_case_before(l2, ours2, "x86_64-pc-boruix", "${host}")
            if early2 == ("?", "?"):
                print("[FAIL] 找不到包含该分支的 case 块 => 拒绝通过")
                ok = False
            elif early2 is not None:
                print("[FAIL] 同块内第 %s 行的 `%s` 更早匹配 => 本分支无效" % (early2[0], early2[1]))
                ok = False
            else:
                print("[OK] libgcc：同块内无更早匹配 => 本分支有效")
        # ---- 插入点 3：libstdc++-v3/crossconfig.m4 ----
        h3 = os.path.join(a.tree, "libstdc++-v3", "crossconfig.m4")
        if not os.path.isfile(h3):
            print("[FAIL] 找不到 " + h3)
            return 1
        with open(h3, encoding="utf-8", errors="surrogateescape") as f:
            src3 = f.read()
        has3 = "x86_64-*-boruix*)" in src3
        print("[check] libstdc++-v3/crossconfig.m4 已含 boruix 分支 = %s" % has3)
        ok = ok and has3
        if has3:
            # 默认分支是**硬错误**——boruix 分支必须排在它之前才轮得到。
            l3 = src3.splitlines()
            # **注意缩进**：`crossconfig.m4` 的 case 标签**有 2 空格缩进**，与 `config.gcc` 的列 0 标签
            # 不同。首版用 `startswith`（隐含要求列 0）⇒ 找不到行号、误报 FAIL。
            # 这是本检查器**第 6 次**被实测打回——每次都记在这里，供后来者对照。
            ours3 = next((i + 1 for i, l in enumerate(l3) if l.strip().startswith("x86_64-*-boruix*)")), None)
            dflt = next((i + 1 for i, l in enumerate(l3)
                         if l.strip() == "*)" and "AC_MSG_ERROR" in "\n".join(l3[i + 1:i + 3])), None)
            print("[check] boruix 分支第 %s 行；默认（AC_MSG_ERROR）分支第 %s 行" % (ours3, dflt))
            if ours3 is None or dflt is None:
                print("[FAIL] 找不到分支行号 => 拒绝通过")
                ok = False
            elif ours3 > dflt:
                print("[FAIL] boruix 分支排在默认分支**之后** => 永远轮不到，configure 仍会硬失败")
                ok = False
            else:
                print("[OK] boruix 分支排在默认硬错误之前 => 生效")
        return 0 if ok else 1

    if a.revert:
        if not has_insert:
            print("[OK] 本就没有 boruix 分支，无需撤销")
            return 0
        if INSERT not in src:
            return die("有 boruix 分支但**与脚本写入的不一致**——拒绝自动撤销（怕删错东西）。请人工处理")
        with open(cfg, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
            f.write(src.replace(INSERT, ""))
        print("[OK] 已从 config.gcc 移除 boruix 分支（boruix.h 保留，请人工确认是否删除）")
        return 0

    if has_insert:
        if INSERT in src:
            print("[OK] config.gcc 已是目标状态且内容一致（幂等，未改动）")
        else:
            # **内容不一致时必须替换**（第 42 轮实测踩到）：此前只要「分支已存在」就跳过，
            # 于是我改了 tm_file（加 boruix-stdint.h）后，脚本报「已是目标状态」，
            # **新 tm_file 从未写入 config.gcc** ⇒ 构建仍报 __UINTPTR_TYPE__ 未定义。
            # **幂等 ≠ 只判存在，还要判内容一致。**
            import re as _re
            pat = _re.compile(r"x86_64-\*-boruix\*\)\n(?:\t.*\n)*?\t;;\n")
            new_src, n = pat.subn(INSERT, src, count=1)
            if n != 1:
                return die("boruix 分支存在但与当前 INSERT 不一致，且无法安全定位其范围 => 拒绝自动替换")
            with open(cfg, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
                f.write(new_src)
            print("[OK] config.gcc 的 boruix 分支内容已更新为新版（含 boruix-stdint.h）")
    else:
        if ANCHOR not in src:
            return die("锚点（x86_64-*-elf* case 块）在源码树里**找不到**——源码树版本不是预期的 GCC 14.2，"
                       "或该块已被改动。**拒绝盲插**。请人工核对 gcc/config.gcc")
        if src.count(ANCHOR) != 1:
            return die("锚点出现 %d 次（期望 1）——拒绝盲插" % src.count(ANCHOR))
        with open(cfg, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
            f.write(src.replace(ANCHOR, ANCHOR + INSERT))
        print("[OK] 已向 config.gcc 插入 boruix 分支（锚点唯一，替换 1 处）")

    # ---- 插入点 2：libgcc/config.host ----
    h2 = os.path.join(a.tree, "libgcc", "config.host")
    if not os.path.isfile(h2):
        return die("找不到 " + h2)
    with open(h2, encoding="utf-8", errors="surrogateescape") as f:
        src2 = f.read()
    if "x86_64-*-boruix*)" in src2:
        print("[OK] libgcc/config.host 已是目标状态（幂等，未改动）")
    else:
        if src2.count(ANCHOR2) != 1:
            return die("libgcc 锚点出现 %d 次（期望 1）——拒绝盲插" % src2.count(ANCHOR2))
        with open(h2, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
            f.write(src2.replace(ANCHOR2, INSERT2 + ANCHOR2))
        print("[OK] 已向 libgcc/config.host 插入 boruix 分支（锚点唯一）")

    # ---- 插入点 3：libstdc++-v3/crossconfig.m4 ----
    h3 = os.path.join(a.tree, "libstdc++-v3", "crossconfig.m4")
    if not os.path.isfile(h3):
        return die("找不到 " + h3)
    with open(h3, encoding="utf-8", errors="surrogateescape") as f:
        src3 = f.read()
    if "x86_64-*-boruix*)" in src3:
        print("[OK] crossconfig.m4 已是目标状态（幂等，未改动）")
    else:
        if src3.count(ANCHOR3) != 1:
            return die("crossconfig.m4 锚点出现 %d 次（期望 1）——拒绝盲插" % src3.count(ANCHOR3))
        with open(h3, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
            f.write(src3.replace(ANCHOR3, INSERT3 + ANCHOR3))
        print("[OK] 已向 crossconfig.m4 插入 boruix 分支（锚点唯一）")

    # boruix-stdint.h：与 boruix.h 同源同目录，从本脚本旁拷入（**单一数据源**，不在脚本里内联）。
    sd = os.path.join(a.tree, "gcc", "config", "boruix-stdint.h")
    src_sd = os.path.join(os.path.dirname(os.path.abspath(__file__)), "boruix-stdint.h")
    if not os.path.isfile(src_sd):
        return die("找不到同目录的 boruix-stdint.h（应与本脚本同放）")
    if os.path.isfile(sd):
        print("[OK] gcc/config/boruix-stdint.h 已存在（幂等，未改动）")
    else:
        import shutil as _sh
        _sh.copyfile(src_sd, sd)
        print("[OK] 已拷入 gcc/config/boruix-stdint.h")

    h = os.path.join(a.tree, "gcc", "config", "boruix.h")
    if os.path.isfile(h):
        print("[OK] gcc/config/boruix.h 已存在（幂等，未改动）")
    else:
        with open(h, "w", encoding="utf-8", newline="\n") as f:
            f.write(BORUIX_H)
        print("[OK] 已写出 gcc/config/boruix.h")

    if a.emit_patch:
        os.makedirs(a.emit_patch, exist_ok=True)
        print("[INFO] --emit-patch 需要一份 pristine 副本作 diff 基准；见 PORTING-TARGET.md 的交付流程")
    return 0


if __name__ == "__main__":
    sys.exit(main())
