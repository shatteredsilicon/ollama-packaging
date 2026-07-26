# ollama-noavx
Ollama Without mandatory AVX CPU Requirement and other enhancements

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
    │   └── ...
    └── SPECS/
        ├── cuda-virtual-provides.spec
        └── ollama.spec
~~~~

The non-secret RPM public key is stored in this repository for package signing
verification and publication. The private signing key and passphrase remain
protected by Jenkins credentials.

# Additional features
- Can be built on/for CPUs with limited or no AVX support.

AVX2 only (no AVX512):
~~~~ {.bash}
$ rpmbuild --rebuild --with avx ollama-<version>.src.rpm
~~~~

No AVX/AVX2 at all:
~~~~ {.bash}
$ rpmbuild --rebuild --without avx ollama-<version>.src.rpm
~~~~
  
- Support for manual explicit layer splitting override across GPUs, via ~/.ollama.ini. For example:
```
[llama3.3:70b]
tensor-split=18,21,21,21
```
fits the entire llama3.3:70b (q4_k_m) with 128K of context entirely into 4x22GB GPUs without anything spilling over to system memory.

# Install

If you see an install error like:

~~~~ {.bash}
Error: 
 Problem: conflicting requests
  - nothing provides cuda-cudart needed by ollama-0.12.10-1.el9.x86_64 from @commandline
  - nothing provides libcublas needed by ollama-0.12.10-1.el9.x86_64 from @commandline
~~~~

Build and install a small `virtual provides` shim RPM that maps these generic names to the
actual CUDA SONAMEs present on your system (`libcudart.so.12` and `libcublas.so.12`).
Then install the Ollama RPM.

**1) Build the shim RPM**

~~~~ {.bash}
$ rpmbuild -bb cuda-virtual-provides.spec
~~~~

**2) Install the shim and then Ollama**

~~~~ {.bash}
sudo dnf install -y ./cuda-virtual-provides-1-1.noarch.rpm
sudo dnf install -y ./ollama-<version>-1.el9.x86_64.rpm
~~~~

**Tip:** You should already have CUDA installed and `ldconfig` should see the libs:

~~~~ {.bash}
ldconfig -p | grep -E 'libcudart\.so\.12|libcublas\.so\.12'
~~~~
