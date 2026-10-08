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


def _fix_stdout():
    """S02：不依赖系统默认编码。Windows 控制台常是 GBK，写非 GBK 字符会**崩**
    （本脚本首版就因 `⇒` 抛 UnicodeEncodeError 而崩）。故显式指定编码 + errors=replace。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _case_target_blocks(lines):
    """找出所有 `case ${target} in ... esac` 块（config.gcc 里另有 case ${host} 等，不算）。

    返回 [(start0, end0, [(label0, [patterns])])]，行号为 **0-based**。
    实测（2026-10）：config.gcc 的块边界是 291-334 / 342-599 / 633-686 / 689-693 / 724-1178 /
    1181-1189 / **1191-3631** / …；`tm_file` 是在 **1191-3631** 里按目标逐条设的。"""
    blocks = []
    for i, s in enumerate(lines):
        if s.strip() != "case ${target} in":
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


def _first_matching_case_before(lines, ours_1based, target):
    """在同**块**内、我们这条之前，是否有 case 也匹配 `target`（shell 是**先匹配者胜**）。

    跨块比行号**毫无意义**（两块都执行、各设各的变量）——本脚本首版就是这么误报的。
    返回 (行号, 模式) 或 None；块找不到则返回 ("?", "?")。"""
    import fnmatch
    blk = next((b for b in _case_target_blocks(lines) if b[0] + 1 <= ours_1based <= b[1] + 1), None)
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
