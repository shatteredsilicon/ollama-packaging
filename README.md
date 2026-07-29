# ollama-noavx

Ollama RPM packaging with bounded x86-64 CPU variants and additional runtime enhancements.

## Repository layout

~~~~ {.text}
ollama-noavx/
├── README.md
├── LICENSE
├── Jenkinsfile.watcher
├── Jenkinsfile.build
├── keys/
│   └── RPM-GPG-KEY-ollama.pub
├── scripts/
│   └── ollama_check_patches.py
└── rpmbuild/
    ├── SOURCES/
    │   ├── prep-ollama.sh
    │   ├── restrict-llama-cpu-variants.patch
    │   ├── support-overriding-tensor-split.patch
    │   └── ...
    └── SPECS/
        ├── cuda-virtual-provides.spec
        └── ollama.spec
~~~~

The non-secret RPM public key is stored in this repository for package signing
verification and publication. The private signing key and passphrase remain
protected by Jenkins credentials.

## CPU target variants

Ollama builds a separate `llama-server` payload from the version of
`llama.cpp` recorded in Ollama's `LLAMA_CPP_VERSION` file. The RPM preserves
upstream's dynamically loaded GGML CPU-runner architecture, but restricts the
set of runners packaged in the RPM.

This provides two supported build modes:

- **No AVX:** package only the `x64` and `sse42` GGML CPU runners. No runner
  requiring AVX, AVX2, AVX-VNNI, AVX-512, or AMX is built.
- **AVX + AVX2 only:** package the baseline runners and the upstream
  `sandybridge`, `ivybridge`, `piledriver`, and `haswell` runners. The highest
  supported ISA is AVX2. AVX-VNNI, AVX-512, and AMX runners are not built.

At runtime, `llama-server` selects the best packaged runner supported by the
host CPU. Keeping the baseline runners in both modes allows the same RPM to run
on CPUs below the maximum ISA selected for that package.

The rationale for these variants is to:

- support older x86-64 systems that cannot execute AVX instructions;
- provide a predictable AVX2 upper bound for heterogeneous deployments;
- prevent AVX-512, AVX-VNNI, or AMX code from being compiled into the packaged
  CPU-runner set; and
- stay close to upstream by filtering the runner list instead of replacing
  Ollama's runtime CPU detection.

### Nested `llama.cpp` patch

`restrict-llama-cpu-variants.patch` is applied first to the Ollama source tree.
It adds the following nested compatibility patch:

~~~~ {.text}
llama/compat/900-shatteredsilicon-cpu-variants.patch
~~~~

`prep-ollama.sh` reads `LLAMA_CPP_VERSION` from the selected Ollama release and
packages that exact `llama.cpp` source version. During `%prep`, the source is
extracted as `llama.cpp/`, and Ollama's `llama/compat/apply-patch.cmake` is run
with `llama.cpp/` as its working directory. The nested patch therefore applies
to:

~~~~ {.text}
llama.cpp/ggml/src/CMakeLists.txt
~~~~

The RPM build then sets `OLLAMA_LLAMA_CPP_SOURCE` to this patched tree, ensuring
that Ollama's superbuild uses it for the separate `llama-server` payload. For
Ollama v0.32.5, the pinned `llama.cpp` version is `b10091`; the nested patch must
be revalidated whenever a future Ollama release changes `LLAMA_CPP_VERSION`.

### Build without AVX

~~~~ {.bash}
$ rpmbuild --rebuild --without avx ollama-<version>.src.rpm
~~~~

This build sets:

~~~~ {.text}
GOAMD64=v2
GGML_CPU_VARIANTS=x64;sse42
~~~~

`GOAMD64=v2` permits SSE4.2 but does not enable AVX. Consequently, this mode is
"no AVX," not a generic x86-64-v1 build: the target CPU must support SSE4.2.

### Build with AVX and AVX2 only

~~~~ {.bash}
$ rpmbuild --rebuild --with avx ollama-<version>.src.rpm
~~~~

This is the default build mode and selects:

~~~~ {.text}
GGML_CPU_VARIANTS=x64;sse42;sandybridge;ivybridge;piledriver;haswell
~~~~

The `haswell` runner is the highest selected target and uses AVX2. The
`alderlake` runner is intentionally excluded because it enables AVX-VNNI. All
AVX-512 and AMX runners are also excluded.

## Overriding `tensor-split`

The `support-overriding-tensor-split.patch` adds a per-model INI configuration
that overrides Ollama's automatic multi-GPU placement when the model is loaded.
The override is forwarded to the separate `llama-server` process as:

~~~~ {.text}
-ngl <sum> --split-mode layer --tensor-split <values>
~~~~

The values are passed to upstream `llama-server` as relative GPU proportions,
and their sum is used as the maximum number of model layers to offload. The
number of values therefore also selects the number of GPUs used by the
override. Actual tensor placement and any rounding remain controlled by
`llama.cpp`.

By default, Ollama reads the configuration from `~/.ollama.ini`, where `~` is
the home directory of the process running `ollama serve`. With the packaged
systemd service, that is:

~~~~ {.text}
/var/lib/ollama/.ollama.ini
~~~~

A different file can be selected with the `OLLAMA_OVERRIDE_CONFIG` environment
variable.

Each section name must exactly match Ollama's short model name, including its
tag. Each `tensor-split` value must be a positive integer. The override is
ignored, with a warning in the service log, when the sum exceeds the model's
layer count or no compatible GPU group has enough devices.

### Example: split `llama3.3:70b` across four GPUs

Create the configuration used by the `ollama` service:

~~~~ {.bash}
$ sudo install -o ollama -g ollama -m 0600 /dev/null /var/lib/ollama/.ollama.ini
$ sudo tee /var/lib/ollama/.ollama.ini >/dev/null <<'EOF'
[llama3.3:70b]
tensor-split=18,21,21,21
EOF

$ sudo chown ollama:ollama /var/lib/ollama/.ollama.ini
$ sudo chmod 0600 /var/lib/ollama/.ollama.ini
~~~~

The four values request the ratio `18:21:21:21`. Their sum is `81`, so Ollama
starts `llama-server` with a maximum of 81 GPU-offloaded layers and passes the
same values to `--tensor-split`.

Restart the service so any already loaded model is unloaded, and then run the
matching model name:

~~~~ {.bash}
$ sudo systemctl restart ollama
$ ollama run llama3.3:70b
~~~~

Confirm that the override was applied:

~~~~ {.bash}
$ journalctl -u ollama -n 100 --no-pager \
    | grep 'applying model tensor-split override'
~~~~

If the service uses another configuration path, add a systemd override such as:

~~~~ {.ini}
[Service]
Environment="OLLAMA_OVERRIDE_CONFIG=/etc/ollama/overrides.ini"
~~~~

Then restart `ollama` after creating that file with ownership and permissions
that allow the `ollama` user to read it.

## Install

If you see an install error like:

~~~~ {.bash}
Error: 
 Problem: conflicting requests
  - nothing provides cuda-cudart needed by ollama-0.12.10-1.el9.x86_64 from @commandline
  - nothing provides libcublas needed by ollama-0.12.10-1.el9.x86_64 from @commandline
~~~~

Build and install a small `virtual provides` shim RPM that maps these generic
names to the actual CUDA SONAMEs present on your system (`libcudart.so.12` and
`libcublas.so.12`). Then install the Ollama RPM.

**1) Build the shim RPM**

~~~~ {.bash}
$ rpmbuild -bb cuda-virtual-provides.spec
~~~~

**2) Install the shim and then Ollama**

~~~~ {.bash}
$ sudo dnf install -y ./cuda-virtual-provides-1-1.noarch.rpm
$ sudo dnf install -y ./ollama-<version>-1.el9.x86_64.rpm
~~~~

**Tip:** You should already have CUDA installed and `ldconfig` should see the
libraries:

~~~~ {.bash}
$ ldconfig -p | grep -E 'libcudart\.so\.12|libcublas\.so\.12'
~~~~
