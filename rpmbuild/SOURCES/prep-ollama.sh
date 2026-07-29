#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
spec_file="$script_dir/../SPECS/ollama.spec"

VERSION="${1:-${VERSION:-$(awk '
  /^%global[[:space:]]+upstream_version[[:space:]]+/ { print $3; found=1; exit }
  /^Version:[[:space:]]+/ && !found { print $2; exit }
' "$spec_file")}}"

test -n "$VERSION"

export GOAMD64="${GOAMD64:-v2}"

cd "$script_dir"

rm -f "ollama-${VERSION}-vendor.tar.gz"
rm -f "ollama-${VERSION}-llama.cpp.tar.gz"
rm -f "ollama-${VERSION}.tar.gz"
rm -f "v${VERSION}.tar.gz"
rm -f llama.cpp-source.tar.gz
rm -rf "ollama-${VERSION}" llama.cpp

wget -O "v${VERSION}.tar.gz" "https://github.com/ollama/ollama/archive/refs/tags/v${VERSION}.tar.gz"
tar -zxf "v${VERSION}.tar.gz"
tar -zcf "ollama-${VERSION}.tar.gz" "ollama-${VERSION}"

llama_cpp_version="$(tr -d '[:space:]' < "ollama-${VERSION}/LLAMA_CPP_VERSION")"
if [[ ! "$llama_cpp_version" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "Invalid LLAMA_CPP_VERSION: $llama_cpp_version" >&2
  exit 1
fi

wget -O llama.cpp-source.tar.gz \
  "https://github.com/ggml-org/llama.cpp/archive/${llama_cpp_version}.tar.gz"
mkdir llama.cpp
tar -zxf llama.cpp-source.tar.gz --strip-components=1 -C llama.cpp
test -f llama.cpp/CMakeLists.txt
tar -zcf "ollama-${VERSION}-llama.cpp.tar.gz" llama.cpp

pushd "ollama-${VERSION}" >/dev/null
go mod vendor
tar -zcf "../ollama-${VERSION}-vendor.tar.gz" vendor
popd >/dev/null

rm -rf "ollama-${VERSION}" llama.cpp
rm -f "v${VERSION}.tar.gz" llama.cpp-source.tar.gz
