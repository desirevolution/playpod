#!/bin/sh
# Build the same pinned QuickJS-NG release against the builder's own libc/CPU.
set -eu
work=${1:?Usage: build-quickjs.sh WORK_DIRECTORY OUTPUT_DIRECTORY}
out=${2:?Usage: build-quickjs.sh WORK_DIRECTORY OUTPUT_DIRECTORY}
version=0.17.0
checksum=559bc4c420475e55c7ab4510adbc562f55d7524d75e8e89d79ce4bb02f5687d9
mkdir -p "$work" "$out"
curl --fail --location --retry 3 --connect-timeout 20 --max-time 180 \
  "https://github.com/quickjs-ng/quickjs/archive/refs/tags/v${version}.tar.gz" \
  --output "$work/source.tar.gz"
printf '%s  %s\n' "$checksum" "$work/source.tar.gz" | sha256sum -c -
mkdir -p "$work/source"
tar -xzf "$work/source.tar.gz" --strip-components=1 -C "$work/source"
cmake -S "$work/source" -B "$work/build" \
  -DCMAKE_BUILD_TYPE=MinSizeRel -DBUILD_SHARED_LIBS=OFF -DQJS_BUILD_EXAMPLES=OFF
cmake --build "$work/build" --target qjs_exe --parallel 2
cp "$work/build/qjs" "$out/qjs"
strip "$out/qjs"
cp "$work/source/LICENSE" "$out/LICENSE.quickjs-ng"
"$out/qjs" -e 'if (JSON.stringify([1n.toString(),new Uint8Array([42])[0]]) !== "[\"1\",42]") throw Error("QuickJS smoke failed");'
