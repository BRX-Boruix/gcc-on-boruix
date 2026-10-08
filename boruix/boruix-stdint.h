/* Boruix 的 <stdint.h> 类型宏（x86-64 LP64 / SysV ABI）。

   为什么需要：`__UINTPTR_TYPE__` / `__INT8_TYPE__` 等是 GCC 的**内建宏**，由本文件里的
   `UINTPTR_TYPE` / `INT8_TYPE` 等宏推导。此前插入点 1 去掉了 `newlib-stdint.h`（避免与
   sysroot 的 <stdint.h> 打架，S15）**但没有提供等价物** ⇒ 内建宏未定义，libgcc 的
   `unwind-dw2-fde.c:45` 报 `unknown type name '__UINTPTR_TYPE__'`。
   本文件补上那一步：**只提供类型宏给编译器**，不安装任何 <stdint.h>（故 use_gcc_stdint=none 不变）。

   内容与 `gcc/config/newlib-stdint.h` 同构（同为 x86-64 LP64 下的正确推导），
   故沿用其 GPLv3 + GCC Runtime Library Exception 头（本仓已有 LICENSE / LICENSE.RUNTIME）。

   Copyright (C) 2008-2024 Free Software Foundation, Inc.

   This file is part of GCC.

   GCC is free software; you can redistribute it and/or modify it under
   the terms of the GNU General Public License as published by the Free
   Software Foundation; either version 3, or (at your option) any later
   version.

   GCC is distributed in the hope that it will be useful, but WITHOUT ANY
   WARRANTY; without even the implied warranty of MERCHANTABILITY or
   FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
   for more details.

   Under Section 7 of GPL version 3, you are granted additional
   permissions described in the GCC Runtime Library Exception, version
   3.1, as published by the Free Software Foundation.

   You should have received a copy of the GNU General Public License and
   a copy of the GCC Runtime Library Exception along with this program;
   see the files COPYING3 and COPYING.RUNTIME respectively.  If not, see
   <http://www.gnu.org/licenses/>.  */

/* x86-64 LP64：long 是 64 位，故 STDINT_LONG32 为 0。 */
#ifndef STDINT_LONG32
#define STDINT_LONG32 (LONG_TYPE_SIZE == 32)
#endif

#define SIG_ATOMIC_TYPE "int"

#define INT8_TYPE (CHAR_TYPE_SIZE == 8 ? "signed char" : 0)
#define INT16_TYPE (SHORT_TYPE_SIZE == 16 ? "short int" : INT_TYPE_SIZE == 16 ? "int" : CHAR_TYPE_SIZE == 16 ? "signed char" : 0)
#define INT32_TYPE (STDINT_LONG32 ? "long int" : INT_TYPE_SIZE == 32 ? "int" : SHORT_TYPE_SIZE == 32 ? "short int" : CHAR_TYPE_SIZE == 32 ? "signed char" : 0)
#define INT64_TYPE (LONG_TYPE_SIZE == 64 ? "long int" : LONG_LONG_TYPE_SIZE == 64 ? "long long int" : INT_TYPE_SIZE == 64 ? "int" : 0)
#define UINT8_TYPE (CHAR_TYPE_SIZE == 8 ? "unsigned char" : 0)
#define UINT16_TYPE (SHORT_TYPE_SIZE == 16 ? "short unsigned int" : INT_TYPE_SIZE == 16 ? "unsigned int" : CHAR_TYPE_SIZE == 16 ? "unsigned char" : 0)
#define UINT32_TYPE (STDINT_LONG32 ? "long unsigned int" : INT_TYPE_SIZE == 32 ? "unsigned int" : SHORT_TYPE_SIZE == 32 ? "short unsigned int" : CHAR_TYPE_SIZE == 32 ? "unsigned char" : 0)
#define UINT64_TYPE (LONG_TYPE_SIZE == 64 ? "long unsigned int" : LONG_LONG_TYPE_SIZE == 64 ? "long long unsigned int" : INT_TYPE_SIZE == 64 ? "unsigned int" : 0)

#define INT_LEAST8_TYPE (INT8_TYPE ? INT8_TYPE : INT16_TYPE ? INT16_TYPE : INT32_TYPE ? INT32_TYPE : INT64_TYPE ? INT64_TYPE : 0)
#define INT_LEAST16_TYPE (INT16_TYPE ? INT16_TYPE : INT32_TYPE ? INT32_TYPE : INT64_TYPE ? INT64_TYPE : 0)
#define INT_LEAST32_TYPE (INT32_TYPE ? INT32_TYPE : INT64_TYPE ? INT64_TYPE : 0)
#define INT_LEAST64_TYPE INT64_TYPE
#define UINT_LEAST8_TYPE (UINT8_TYPE ? UINT8_TYPE : UINT16_TYPE ? UINT16_TYPE : UINT32_TYPE ? UINT32_TYPE : UINT64_TYPE ? UINT64_TYPE : 0)
#define UINT_LEAST16_TYPE (UINT16_TYPE ? UINT16_TYPE : UINT32_TYPE ? UINT32_TYPE : UINT64_TYPE ? UINT64_TYPE : 0)
#define UINT_LEAST32_TYPE (UINT32_TYPE ? UINT32_TYPE : UINT64_TYPE ? UINT64_TYPE : 0)
#define UINT_LEAST64_TYPE UINT64_TYPE

#define INT_FAST8_TYPE (INT_TYPE_SIZE >= 8 ? "int" : INT_LEAST8_TYPE)
#define INT_FAST16_TYPE (INT_TYPE_SIZE >= 16 ? "int" : INT_LEAST16_TYPE)
#define INT_FAST32_TYPE (INT_TYPE_SIZE >= 32 ? "int" : INT_LEAST32_TYPE)
#define INT_FAST64_TYPE (INT_TYPE_SIZE >= 64 ? "int" : INT_LEAST64_TYPE)
#define UINT_FAST8_TYPE (INT_TYPE_SIZE >= 8 ? "unsigned int" : UINT_LEAST8_TYPE)
#define UINT_FAST16_TYPE (INT_TYPE_SIZE >= 16 ? "unsigned int" : UINT_LEAST16_TYPE)
#define UINT_FAST32_TYPE (INT_TYPE_SIZE >= 32 ? "unsigned int" : UINT_LEAST32_TYPE)
#define UINT_FAST64_TYPE (INT_TYPE_SIZE >= 64 ? "unsigned int" : UINT_LEAST64_TYPE)

#define INTPTR_TYPE PTRDIFF_TYPE
#ifndef UINTPTR_TYPE
#define UINTPTR_TYPE SIZE_TYPE
#endif
