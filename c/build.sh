#!/bin/sh
# 编译 C 版本。优先用 gcc/clang，没有则回退 MSVC。
set -e
cd "$(dirname "$0")"
if command -v cc >/dev/null 2>&1; then
  cc -O2 -march=native -o lcs_c lcs_c.c && echo "built with cc"
elif command -v gcc >/dev/null 2>&1; then
  gcc -O2 -march=native -o lcs_c lcs_c.c && echo "built with gcc"
else
  MSVC="C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/VC/Tools/MSVC/14.44.35207"
  SDK="C:/Program Files (x86)/Windows Kits/10"
  export INCLUDE="C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Tools\MSVC\14.44.35207\include;C:\Program Files (x86)\Windows Kits\10\Include\10.0.26100.0\ucrt;C:\Program Files (x86)\Windows Kits\10\Include\10.0.26100.0\um;C:\Program Files (x86)\Windows Kits\10\Include\10.0.26100.0\shared"
  export LIB="C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Tools\MSVC\14.44.35207\lib\x64;C:\Program Files (x86)\Windows Kits\10\Lib\10.0.26100.0\ucrt\x64;C:\Program Files (x86)\Windows Kits\10\Lib\10.0.26100.0\um\x64"
  "$MSVC/bin/Hostx64/x64/cl.exe" -nologo -O2 -utf-8 -Fe:lcs_c.exe lcs_c.c >/dev/null && echo "built with MSVC"
fi
