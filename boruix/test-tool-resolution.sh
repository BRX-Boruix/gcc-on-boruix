#!/bin/sh
# 行为测试：boruix-cc 的工具解析（S01：零硬编码环境）。
set -u
CC=/f/boruix-project/gcc-on-boruix/boruix/boruix-cc
FAKE=/f/boruix-project/.tmp-fakebin
SYS=/f/boruix-project/.tmp-fakesys
fails=0

echo '--- 1) 假工具在 PATH 上：应调用 FAKE_CLANG ---'
out=$(PATH=$FAKE:/usr/bin BORUIX_SYSROOT=$SYS sh $CC -c /dev/null -o /tmp/x.o 2>&1)
echo "$out"
case "$out" in *FAKE_CLANG*) echo '[ok] 用的是 PATH 上的工具' ;; *) echo '[FAIL] 没有调用 PATH 上的工具'; fails=$((fails+1)) ;; esac

echo '--- 2) PATH 上没有这两个工具：应明确报错且 rc!=0 ---'
out=$(PATH=/usr/bin BORUIX_SYSROOT=$SYS sh $CC -c /dev/null -o /tmp/x.o 2>&1; echo "rc=$?")
echo "$out"
case "$out" in *找不到*clang*) echo '[ok] 给出可操作报错' ;; *) echo '[FAIL] 报错不可操作'; fails=$((fails+1)) ;; esac

echo '--- 3) 显式覆盖优先于 PATH ---'
out=$(PATH=/usr/bin BORUIX_CC_CLANG=$FAKE/clang BORUIX_CC_LLD=$FAKE/ld.lld BORUIX_SYSROOT=$SYS sh $CC -c /dev/null -o /tmp/x.o 2>&1)
echo "$out"
case "$out" in *FAKE_CLANG*) echo '[ok] 覆盖生效' ;; *) echo '[FAIL] 覆盖没生效'; fails=$((fails+1)) ;; esac

echo "FAILS=$fails"
exit $fails