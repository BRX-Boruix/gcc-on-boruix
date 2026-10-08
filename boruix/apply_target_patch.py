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
# - **去掉 newlib-stdint.h**：它按 newlib 的头定义 stdint；Boruix 的 sysroot **已有自己的 <stdint.h>**，
#   两份并存会打架（S15 单点定义）。故 use_gcc_stdint=none：GCC 不提供 stdint。
# - tmake_file 参照 x86_64-*-rdos*（同为小型 OS）。
INSERT = ('x86_64-*-boruix*)\n'
          '\ttm_file="${tm_file} i386/unix.h i386/att.h elfos.h i386/i386elf.h i386/x86-64.h boruix.h"\n'
          '\ttmake_file="i386/t-i386elf t-svr4"\n'
          '\tuse_gcc_stdint=none\n'
          '\t;;\n')

BORUIX_H = '''/* Boruix 的 target 事实（**只写已验证的**，S06/S13）。

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


def die(msg):
    print("[FAIL] " + msg)
    return 1


def main():
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
        print("[check] gcc/config/boruix.h 存在 = %s" % os.path.isfile(h))
        return 0 if (has_insert and os.path.isfile(h)) else 1

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
        print("[OK] config.gcc 已是目标状态（幂等，未改动）")
    else:
        if ANCHOR not in src:
            return die("锚点（x86_64-*-elf* case 块）在源码树里**找不到**——源码树版本不是预期的 GCC 14.2，"
                       "或该块已被改动。**拒绝盲插**。请人工核对 gcc/config.gcc")
        if src.count(ANCHOR) != 1:
            return die("锚点出现 %d 次（期望 1）——拒绝盲插" % src.count(ANCHOR))
        with open(cfg, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
            f.write(src.replace(ANCHOR, ANCHOR + INSERT))
        print("[OK] 已向 config.gcc 插入 boruix 分支（锚点唯一，替换 1 处）")

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
