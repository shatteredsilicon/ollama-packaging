%define debug_package %{nil}

%bcond_without avx

%{!?upstream_version:%{error:upstream_version must be defined, e.g. rpmbuild --define 'upstream_version 0.32.5'}}

Name:           ollama
Version:        %{upstream_version}
Release:        1%{?dist}
Summary:        Tool for running AI models on-premise
License:        MIT
URL:            https://ollama.com
Source0:        %{name}-%{upstream_version}.tar.gz
Source1:        %{name}-%{upstream_version}-vendor.tar.gz
Source2:        %{name}-%{upstream_version}-llama.cpp.tar.gz
Source3:        %{name}.service
Source4:        %{name}-user.conf
Patch0:         restrict-llama-cpu-variants.patch
Patch1:         support-overriding-tensor-split.patch
BuildRequires:  cmake >= 3.24
BuildRequires:  git-core
BuildRequires:  make
BuildRequires:  redhat-rpm-config
BuildRequires:  zstd
BuildRequires:  golang >= 1.26.0
BuildRequires:  gcc-c++
BuildRequires:  libstdc++
BuildRequires:  systemd-rpm-macros
%if 0%{?rhel} <= 9
BuildRequires:  cuda-toolkit-12-9
%else
BuildRequires:  cuda-toolkit-13-1
%endif
%{?sysusers_requires_compat}

Requires: nvidia-driver-cuda-libs libcublas cuda-cudart

%description
Ollama is a tool for running AI models on one's own hardware.
It offers a command-line interface and a RESTful API.
New models can be created or existing ones modified in the
Ollama library using the Modelfile syntax.
Source model weights found on Hugging Face and similar sites
can be imported.

%prep
%setup -q
%setup -q -D -a 1
%setup -q -D -a 2

%patch 0 -p1
%patch 1 -p1

# The Ollama superbuild treats OLLAMA_LLAMA_CPP_SOURCE as an already prepared
# tree. Apply the same compatibility patch set that Ollama's FetchContent build
# uses, including our local CPU-variant allowlist patch, before configuration.
(
  cd llama.cpp
  cmake \
    -DPATCH_DIR="$PWD/../llama/compat" \
    -DPATCH_LABEL="llama/compat" \
    -P "$PWD/../cmake/apply-git-patches.cmake"
)

%build
%set_build_flags
export CFLAGS="${CFLAGS} -ffunction-sections -fdata-sections"
export CXXFLAGS="${CXXFLAGS} -ffunction-sections -fdata-sections"
export LDFLAGS="${LDFLAGS} -Wl,--gc-sections"
export GIN_MODE=release
export GOFLAGS="-mod=vendor -buildvcs=false"
export CGO_ENABLED=1
export OLLAMA_LLAMA_CPP_SOURCE="$PWD/llama.cpp"

# RHEL-family RPM builds link executables as PIE through the hardened linker
# specs. CUDA 13's compiler probe otherwise compiles a non-PIC host object and
# fails while linking the test executable. Ollama forwards CMAKE_CUDA_FLAGS to
# each nested llama-server CUDA ExternalProject, so pass the host PIC flag
# through nvcc explicitly.
export CUDAFLAGS="${CUDAFLAGS:+$CUDAFLAGS }-Xcompiler=-fPIC"

%if %{with avx}
# Build baseline, SSE4.2, AVX and AVX2 CPU modules, but no AVX-VNNI/AVX-512/AMX modules.
export OLLAMA_CPU_VARIANTS='x64;sse42;sandybridge;ivybridge;piledriver;haswell'
%else
# GOAMD64=v2 requires SSE4.2 but does not enable AVX instructions.
export GOAMD64=v2
export OLLAMA_CPU_VARIANTS='x64;sse42'
%endif

%if 0%{?rhel} <= 9
export PATH=/usr/local/cuda-12/bin:$PATH
%else
export PATH=/usr/local/cuda-13/bin:$PATH
%endif

cmake -S . -B build \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=%{_prefix} \
  -DOLLAMA_VERSION=%{version} \
  -DGGML_CPU_VARIANTS="$OLLAMA_CPU_VARIANTS" \
  -DCMAKE_CUDA_FLAGS="$CUDAFLAGS" \
  -DGGML_LTO=ON \
%if 0%{?rhel} <= 9
  -DOLLAMA_LLAMA_BACKENDS=cuda_v12 \
  -DCUDAToolkit_ROOT=/usr/local/cuda-12
%else
  -DOLLAMA_LLAMA_BACKENDS=cuda_v13 \
  -DCUDAToolkit_ROOT=/usr/local/cuda-13 \
  -DCMAKE_CUDA_ARCHITECTURES='75;86;89;90'
%endif

cmake --build build --parallel %{?_smp_build_ncpus}

%install
cmake --install build \
  --prefix %{buildroot}%{_prefix} \
  --component ollama-local

%{__install} -p -D -m 0644 %{SOURCE4} %{buildroot}%{_sysusersdir}/%{name}.conf
%{__install} -d %{buildroot}%{_localstatedir}/lib/%{name}

%{__install} -d %{buildroot}%{_unitdir}
%{__install} -p -m 0644 %{SOURCE3} %{buildroot}%{_unitdir}/%{name}.service

mkdir -p "%{buildroot}/%{_docdir}/%{name}"
cp -Ra docs/* "%{buildroot}/%{_docdir}/%{name}"

%pre
%sysusers_create_compat %{SOURCE4}

%post
%systemd_post %{name}.service

%preun
%systemd_preun %{name}.service

%postun
%systemd_postun %{name}.service

%files
# %doc README.md
%license LICENSE
%{_docdir}/%{name}
%{_bindir}/%{name}
%{_prefix}/lib/ollama
%{_unitdir}/%{name}.service
%{_sysusersdir}/%{name}.conf
%attr(-, ollama, ollama) %{_localstatedir}/lib/%{name}

%changelog
