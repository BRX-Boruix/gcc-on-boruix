# gcc-on-boruix

**简体中文** | [English](#english)

把 **GCC** 带到 BORUIX 上——让这个系统能够用 GCC 编译代码。

> **仓库状态：已开工（2026-10，阶段 6 / 3P6-3）。** 已有第一项上游补丁与构建脚本骨架；
> **GCC 尚未能在 BORUIX 内运行**——真正的工程量是**宿主端口**（见下）。

---

## 当前进展（如实，S09）

| 事项 | 状态 |
| --- | --- |
| GCC 14.2.0 源码 + 前置库（gmp/mpfr/mpc） | **已取全**（可续传下载；本地 SHA512 记于 `docs/TODO/3p.md`） |
| 构建树 | 已解压（选择性解压，跳过 `gcc/testsuite` 等不需要的子树） |
| 让工具链认识 `boruix` OS | **已做**：`config.sub` 追加 `| boruix*`（见 `UPSTREAM-PATCHES`）。实测 `config.sub x86_64-boruix` → `x86_64-pc-boruix` |
| 构建方式 | **Canadian cross**：`--build=x86_64-pc-msys`（MSYS2 gcc 编构建期工具）、`--host=x86_64-boruix`（用 clang 18 + Boruix sysroot 编**在 Boruix 内运行**的 gcc/cc1）、`--target=x86_64-elf`（裸机 x86-64，与 BORUIX 的 ABI 同形；用 Boruix sysroot 提供 libc） |
| 宿主编译器 shim | `boruix/boruix-cc`：把 `-c/-E/-S` 透传给 clang，链接时追加 Boruix 的 `user_main.o` + `libc.a` + `linker.ld`（configure 需要支持 `-c` 的驱动，而 sysroot 自带的 `boruix-clang` 是一次性驱动）。**注意**：链接直接调 `ld.lld`——让 clang 驱动链接会退化成用 gcc 当链接器驱动，实测失败 |
| 工具链二进制（`AR`/`RANLIB`/…） | **显式传 LLVM 工具**（Boruix 没有 binutils；归档只是容器、与目标无关）。见 `boruix/configure-boruix.sh` |
| 路径风格（**实测踩过的坑**） | configure 必须用 **Windows 风格绝对路径**调用（`F:/...` 而非 `/f/...`）：否则生成文件里带 MSYS2 路径，**原生 clang 解析不了**，表现为 GMP 的 `mp_limb_t doesn't seem to work` |
| GCC configure（Canadian cross） | **已通过**（`host system type... x86_64-pc-boruix`、`whether the C compiler works... yes`、`config.status: creating Makefile`） |
| 前置库交叉构建 | **GMP configure 已通过**（`Host type: x86_64-pc-boruix`、`ABI: 64`），`make` 正在编译真实 C；MPFR/MPC 待做 |
| **GCC 在 Boruix 内运行** | **未达成**——这是本仓的主体工作 |

---

## 目标

BORUIX 目前的编译器情况是：

| 用途 | 现状 |
| --- | --- |
| 系统自身（内核、用户态程序） | Rust 工具链 |
| 少量自由式 C 程序 | clang / LLD 交叉编译 |

这两条路都成立，但都**不是自举的**：它们的编译器不在 BORUIX 上运行，也不为 BORUIX 生成
本地代码。这个仓库要做的是补上这一环——**让 GCC 能在 BORUIX 内部使用**。

## 为什么是 GCC

GCC 支持的目标平台数量是现有编译器里最多的，且经过数十年的实际检验。一个能用的 GCC 后端
意味着两件事：

1. **可以用 C 和 C++ 写 BORUIX 程序**，不必为了写系统程序而先学 Rust；
2. **为移植现成的第三方软件打开了门**——大量自由软件假定存在一个 C 编译器，其中很多还假定
   存在 GCC 或与 GCC 兼容的扩展。

第二条对这个项目尤其重要：操作系统的价值很大程度上取决于它能跑什么。

## 这需要什么

把 GCC 移植到一个新系统不是"编译一下就完了"，它包含几层工作：

- **目标平台支持**——让 GCC 知道如何为 BORUIX 生成代码（目标描述、调用约定、汇编输出）
- **运行时库**——GCC 生成的代码依赖底层运行时支持（整数运算辅助、栈展开等），这些需要为新
  系统实现
- **C/C++ 标准库**——程序真正可用还需要一个 C 库；BORUIX 已有面向 C ABI 的库实现，需要与
  GCC 生成的目标代码对接
- **构建系统集成**——让 GCC 能在 BORUIX 本身上构建，或者至少能作为交叉编译器产出 BORUIX 程序

具体采用哪条路线（直接在 BORUIX 上自举，还是先做交叉编译器）属于尚未确定的设计问题。

## 仓库里会有什么

将来这里会**克隆 GCC 的源码树**，再加上 BORUIX 相关的移植部分——目标定义、运行时适配、构建
脚本。

## 许可证

**本仓库不附带许可证文件**，这是有意的：

- GCC 本身由自由软件基金会发布，采用 **GNU 通用公共许可证（GPL）**，并附带运行时库例外条款。
  许可证的权威文本与说明随 GCC 源码一同提供。
- 因此本仓库**不能**统一声明为 MIT 之类的宽松许可证——一旦 GCC 源码进入这里，整个仓库的授权
  就必须服从 GCC 的条款。
- 克隆进来的源码与将来为本项目编写的移植代码，其授权方式需要在引入时逐项明确。

在仓库里还没有代码的时候先放一份许可证，只会造成误导。正确的做法是等源码进来时一并处理。

## 相关项目

- [`csrc`](https://github.com/BRX-Boruix/csrc) —— BORUIX 的自由式 C 运行环境
- [`libc`](https://github.com/BRX-Boruix/libc) —— 面向 C ABI 的 C 库实现

## 上游

- [GCC](https://gcc.gnu.org/)

---

# English

[简体中文](#gcc-on-boruix) | **English**

Bringing **GCC** to BORUIX — so the system can compile code with GCC.

> **Repository status: planning.** This is an empty repository and contains no code yet.

---

## Goal

BORUIX's compiler situation today is:

| Use | Current state |
| --- | --- |
| The system itself (kernel, user-space programs) | the Rust toolchain |
| A few freestanding C programs | cross-compiled with clang / LLD |

Both paths work, but neither is **self-hosting**: their compilers do not run on BORUIX, and they do
not produce native code for it. This repository exists to close that gap — to make **GCC usable from
within BORUIX**.

## Why GCC

GCC supports more target platforms than any other existing compiler, and has been proven in practice
over decades. A working GCC backend means two things:

1. **BORUIX programs can be written in C and C++**, without having to learn Rust first just to write
   system software;
2. **It opens the door to porting existing third-party software** — a great deal of free software
   assumes a C compiler is available, and much of it additionally assumes GCC or GCC-compatible
   extensions.

The second point matters especially for this project: an operating system's value depends heavily on
what it can run.

## What this takes

Porting GCC to a new system is not a matter of "compile it and done". It involves several layers:

- **Target support** — teaching GCC how to generate code for BORUIX (target description, calling
  convention, assembly output)
- **Runtime support library** — code GCC emits depends on low-level runtime support (integer
  arithmetic helpers, stack unwinding, and so on), which must be implemented for the new system
- **C/C++ standard library** — programs are only truly usable with a C library; BORUIX already has a
  C-ABI-facing implementation that needs to interoperate with GCC-generated code
- **Build system integration** — making GCC buildable on BORUIX itself, or at least able to produce
  BORUIX programs as a cross-compiler

Which route to take — bootstrapping directly on BORUIX, or starting with a cross-compiler — is an
open design question.

## What the repository will hold

GCC's **source tree will be cloned here** in the future, together with the BORUIX-specific porting
work: target definitions, runtime adaptations, and build scripts.

## License

**This repository ships no license file**, deliberately:

- GCC itself is published by the Free Software Foundation under the **GNU General Public License
  (GPL)**, with a runtime library exception. The authoritative license text and its explanation come
  with the GCC sources.
- This repository therefore **cannot** be declared under a permissive license such as MIT — once GCC
  sources are present, the repository's licensing is governed by GCC's terms.
- The licensing of both the cloned sources and any porting code written for this project needs to be
  established item by item as that code is introduced.

Placing a license file here while the repository holds no code would only be misleading. The right
time to settle it is when the sources arrive.

## Related projects

- [`csrc`](https://github.com/BRX-Boruix/csrc) — BORUIX's freestanding C runtime
- [`libc`](https://github.com/BRX-Boruix/libc) — the C-ABI-facing C library implementation

## Upstream

- [GCC](https://gcc.gnu.org/)
