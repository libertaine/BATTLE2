# Reproducible console-only pMARS build

This tooling builds, but does not download, install, package, or redistribute,
pMARS. It is release engineering support, not part of normal BATTLE2 installation.

## Verified source

The tested source is the authoritative Corewar project release
[`pmars-0.9.5.zip`](https://sourceforge.net/projects/corewar/files/pMARS/0.9.5/pmars-0.9.5.zip/download),
published on 2026-01-11.

```text
SHA-256: 6c7c72dbd2a6670d36ba7a96b113d2b54557508afdd99573dfa1da6557700d37
```

That digest was recorded by the BATTLE2 audit from the HTTPS SourceForge
download; SourceForge does not publish a detached upstream signature alongside
the file. Treat changing bytes at the same URL as a provenance failure.

Download the archive separately, verify that exact checksum, and extract it.
The build script also checks release-specific hashes for `COPYING`, `ChangeLog`,
`src/pmars.c`, and `src/Makefile` before compiling.

## Build

Required tools are Bash, GCC, GNU Make, binutils (`strip`), coreutils, `file`,
and `ldd` from glibc. No X11, SDL, Qt, or other graphical development package
is needed.

```bash
sha256sum pmars-0.9.5.zip
unzip pmars-0.9.5.zip -d pmars-0.9.5
tools/build_pmars_linux.sh pmars-0.9.5 build/pmars-linux
```

The script copies the verified source to a temporary directory and overrides
the upstream Makefile with:

```text
CFLAGS=-O2 -DEXT94 -DPERMUTATE -DRWLIMIT
LIB=
LDFLAGS=-Wl,--build-id=sha1
```

In particular, it omits `XWINGRAPHX`, `GRAPHX`, and `CURSESGRAPHX`. No source
patch is required. The executable is written to `build/pmars-linux/pmars`; it
is never copied into package resources or the Python wheel.

Two builds from clean temporary copies were byte-identical with the same GCC
toolchain. This does not promise identical bytes across compiler or distribution
versions. The current Ubuntu 26.04 audit binary requires symbols through
`GLIBC_2.38` and is not a portable release binary; the script must still be run
and validated on the oldest intended release runner, currently Ubuntu 22.04.

The manual GitHub Actions workflow `.github/workflows/linux-pmars-build.yml`
performs that Ubuntu 22.04 validation. It verifies the source archive checksum,
extracts two clean copies, compares two same-toolchain builds byte-for-byte,
checks the highest referenced GLIBC symbol version against the runner's glibc,
and exercises successful and failing BATTLE2 matches. It uploads and retains no
pMARS source or executable artifact. A successful run establishes reproducibility
for that runner toolchain only, not universal cross-toolchain reproducibility.

Select it explicitly when testing BATTLE2:

```bash
PMARS_CMD="$PWD/build/pmars-linux/pmars" battle2 run \
  --mode redcode94 --red-a warrior-a.red --red-b warrior-b.red
```

`PMARS_CMD` denotes exactly one executable path. Fixed arguments in the
environment variable are intentionally unsupported; BATTLE2 supplies and
owns the pMARS argument list.

`--quota` remains a native BATTLE engine setting. It is accepted in pMARS mode
but does not replace pMARS's `--max-processes`/`-p` process limit.

## Licensing and possible redistribution

pMARS source headers license the program under GPL-2.0-or-later. The verified
upstream `COPYING` is the complete GPL version 2 text. BATTLE2 does not
currently distribute a Linux pMARS executable or source.

The future third-party notice should identify “pMARS — a portable Memory Array
Redcode Simulator,” link the authoritative Corewar SourceForge release, retain
the source-file copyright notices (including Albert Ma, Na'ndor Sieben, Stefan
Strack, Mintardjo Wangsawidjaja, and later contributors), state
`GPL-2.0-or-later`, and point to
`third_party_licenses/pmars-GPL-2.0-or-later.txt`.

If a later artifact distributes the executable, its accompanying source bundle
should contain at least the exact pMARS source used, `COPYING`, copyright
notices, this build script, all local patches (currently none), and complete
build instructions. Shipping corresponding source beside the binary is simpler
than relying on a written source offer, whose GPL version 2 duration is at least
three years.

The full upstream archive also contains documentation under GFDL 1.3 and CC BY
3.0. A release that republishes the entire archive must handle those works and
their notices separately. This repository does not yet define that broader
source-bundle layout, so no pMARS binary should be distributed in v0.2.
