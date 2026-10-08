# 把 GCC 移植到 Boruix 作为目标 OS（组件设计）

## 为什么要做（S06 真实链路，不是为移植而移植）

`3P6-3` 要让 **cc1 在 Boruix 内运行**。cc1 是 C++，需要 **target=boruix 的 C++ 运行时**。
而现有构建（`3p.md` 已记真值）是 `host=x86_64-pc-boruix`、**`target=x86_64-pc-elf`**——
它产出的库是给 elf 的，**不是** cc1 运行所需的宿主库。

owner 已裁定：C++ 标准库走 **libstdc++**（不是 libc++、不是自建最小库），
且 target 支持走 **(A) 改 GCC 源码**（不是复用已有 target）。

## 三处必须同时改（缺一不可——只改一处会在后面以「no support for this host/target」之类的形态炸出来）

### 1. `gcc/config.gcc` —— 让 GCC 认识这个 target

**模板（已核实，`gcc-14.2.0/gcc/config.gcc`）**：
```sh
x86_64-*-elf*)
	tm_file="${tm_file} i386/unix.h i386/att.h elfos.h newlib-stdint.h i386/i386elf.h i386/x86-64.h"
	;;
```
**Boruix 分支要点**：
- 保留 `i386/unix.h i386/att.h elfos.h i386/i386elf.h i386/x86-64.h`（ABI 事实：我们是 x86-64 ELF）。
- **去掉 `newlib-stdint.h`**：它按 newlib 的头定义 stdint 类型；Boruix 有**自己的 `<stdint.h>`**
  （在 sysroot 里）。应改为让 GCC 不装自己的 stdint（`use_gcc_stdint=none`），
  否则会出现**两份 stdint 打架**——这正是 S15「单点定义」要防的。
- 新增 `boruix.h`（`gcc/config/boruix.h`）：放本 OS 的宏事实（如 `TARGET_OS_CPP_BUILTINS`）。
  **不臆造**：只写**已验证**的事实（ELF、SysV ABI、无 `__linux__` 等）。
- `tmake_file` 参照 `x86_64-*-rdos*` 的 `i386/t-i386elf t-svr4`（同为小型 OS）。

### 2. `libgcc/config.host` —— 让 libgcc 能为 boruix 构建

**模板（已核实，`gcc-14.2.0/libgcc/config.host:744`）**：
```sh
x86_64-*-elf* | x86_64-*-rtems*)
	tmake_file="$tmake_file i386/t-crtstuff t-crtstuff-pic t-libgcc-pic"
	case ${host} in
	  x86_64-*-rtems*)
	    extra_parts="$extra_parts crti.o crtn.o"
```
**Boruix 要点**：
- 加 `x86_64-*-boruix*` 分支。
- **`crtbegin.o`/`crtend.o` 是 C++ 的硬需求**（跑 `.init_array`/`.fini_array`、注册 EH frame）。
  当前 Boruix 的链接配方（`linker.ld` + `user_main.o`）**没有**这两个，故这是**集成项**，
  不是「照抄一行」——必须和 `linker.ld`/`user_main.c` 一起设计并实测。
- `libgcc` 的异常/展开（`_Unwind_*`）是 libstdc++ 的前置（`3p.md` 前置链第 2 步）。

### 3. `libstdc++-v3/configure.host` + `crossconfig.m4` —— 让 libstdc++ 认这个 host

- `configure.host`：按 `host` 映射 `host_cpu`/`host_os`/ABI。
- `crossconfig.m4`：按 `${host}` 设 `GLIBCXX_CHECK_*`（线程、locale、wchar 等）。**未知 OS 会落到
  默认分支并报错**——这就是第三处必改点的证据形态。
- **诚实边界**：Boruix **现在没有线程**（`pthread` 面未实现）。故这里要**显式**选择
  单线程配置（`gthreads` 的 single 变体），并在文档写明——**不假装有线程**（S09）。

## 验收（S23 TDD 先行 / S29 真实实战可用）

**先写必然失败的检查**（本组件的最小验收）：
1. `gcc -dumpmachine` 对 `--target=x86_64-boruix` 应输出 `x86_64-boruix`（**现在必然失败**：
   configure 会因 target 未知而报错）。
2. `x86_64-boruix-gcc -print-libgcc-file-name` 应指向**存在**的 `libgcc.a`。
3. 一个 C++ 程序（`std::string` + `std::vector`）能被该 target 编译**并链接**出 ELF。
4. 该 ELF 能在 **Boruix 内运行**（QEMU 串口为证）——这一条才是真正的验收。

**每一步都留真实证据**（命令 + 原始输出），不接受「编译通过」当验收（S29）。

## 已知待办（与本组件独立，但同属 S01 红线）

- `boruix/boruix-cc` 里 `CLANG="F:/clang/…"`、`LLD="F:/clang/…"` 是**硬编码本机路径**，
  违反 S01「零硬编码环境」。`stage_assets.py` 已用 `BORUIX_CLANG`/PATH 整改过同类问题，
  **shim 本身尚未改**。


## ⚠ 更正（2026-10，实测推翻了本文件初稿的一处前提）

**初稿写的是**：「GCC 必须认识 `x86_64-boruix` 这个 target —— 已核实 `gcc/config.gcc` 没有 boruix 分支」
并据此把验收定成「`--target=x86_64-boruix` 下 configure 能成功」。

**实测推翻**：
- `gcc/config.gcc:414` 有**兜底分支** `i[34567]86-*-* | x86_64-*-*)`（另见 `:663` 的 `x86_64-*-*)`）。
- 故 **`x86_64-boruix` 本来就配得下去**：撤掉补丁后 configure 依然报
  `checking target system type... x86_64-pc-boruix` 并继续走到 GMP/MPFR/MPC 那一步。
- **TDD 红态没红**（撤掉补丁后验收仍然通过）——**这本身就是「前提错了」的证据**，不是测试写错了。

**因此（S39 如实更正）**：
1. 补丁的**真实价值**不是「让 GCC 认识 target」（它本来就认），而是「**给它正确的 `tm_file` 集合**」——
   我的分支排在兜底之前，故**抢到** `x86_64-*-boruix*` 的匹配，从而拿到去掉 `newlib-stdint.h`、
   加上 `boruix.h` 的那一份。**价值仍在，但理由必须改对。**
2. **验收标准必须改**：不能拿「configure 是否成功」当验收（它本来就成功）。要验的是
   「**到底落到哪一份 `tm_file` / 哪套内置宏**」——可验方式：构建后 `gcc -dM -E - </dev/null`
   看 `__boruix__` 是否出现（兜底分支不会定义它），或直接检查生成的 `tm.h`。
3. **仍然成立的部分**：去 `newlib-stdint.h`（避免与 sysroot 的 `<stdint.h>` 两份打架，S15）——
   这条与「GCC 是否认识 target」无关，独立成立。

**教训（写在这里供后来者）**：「源码里没有 X」**推不出**「工具会因此失败」——中间还隔着一个兜底分支。
**验收标准必须先被证明是红的**（S23），红不了就说明测的不是你以为的那个东西。

## 状态

- **已完成**：侦察（三处插入点与模板已核实到文件行号）、裁定（libstdc++ + 改源码）；
  插入点 1 的幂等脚本 `apply_target_patch.py` 已落地并实测（施加/校验/撤销/幂等四种路径）。
- **未开始**：实际改这三处。**未改一行**——本文件是设计，不是实现记录。
