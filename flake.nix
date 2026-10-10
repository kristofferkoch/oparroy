{
  description = "oparroy dev shell — every non-Python tool, pinned (DESIGN.md §8)";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { nixpkgs, ... }:
    let
      systems = [
        # klee is x86_64-linux only in nixpkgs; single-platform until a
        # second dev machine forces the question.
        "x86_64-linux"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in
    {
      devShells = forAllSystems (
        system:
        let
          pkgs = import nixpkgs {
            inherit system;
            config = {
              # klee 3.2 is marked broken: upstream has only partial
              # LLVM >= 16 support, so nixpkgs builds it against LLVM 19
              # with ~23% of its own test suite xfailed (POSIX-runtime,
              # UBSan features — the core symbolic engine is intact).
              # Accept that; oparroy's harnesses exercise the core.
              problems.handlers.klee.broken = "ignore";
            };
          };
          # Must match the LLVM that nixpkgs' klee is built against, or
          # klee rejects our bitcode (verified: klee 3.2 → LLVM 19).
          llvmPkgs = pkgs.llvmPackages_19;
          # mdformat + GFM plugin as one tool env. A packaged tool, not a
          # project Python dependency — uv's lane (project packages) is
          # untouched (DESIGN.md §8).
          mdformatGfm = pkgs.python3.withPackages (ps: [
            ps.mdformat
            ps.mdformat-gfm
          ]);
        in
        {
          default = pkgs.mkShell {
            packages = [
              # Node toolchain (CH32V003, RV32EC) — smoke-tested with
              # -march=rv32ec -mabi=ilp32e.
              pkgs.pkgsCross.riscv64-embedded.buildPackages.gcc
              # Supervisor toolchain (RP2040).
              pkgs.pkgsCross.arm-embedded.buildPackages.gcc
              # Host bitcode build (KLEE input) + static analysis +
              # libFuzzer (-fsanitize=fuzzer).
              llvmPkgs.clang
              llvmPkgs.clang-tools
              # llvm-ar: pinned archiver for the host build
              # (meson/native/clang.ini) — host /usr/bin/ar would leak
              # tool provenance into artifacts (reproducibility, §8).
              llvmPkgs.bintools
              # Firmware build system (DESIGN.md §8).
              pkgs.meson
              pkgs.ninja
              pkgs.klee
              pkgs.aflplusplus
              # Subcircuit simulation unit tests (DESIGN.md §7).
              pkgs.ngspice
              # KiCad: symbol/footprint libraries — the DSL validates
              # part references against these (DESIGN.md §7 DSL shape) —
              # plus the application itself for layout (DESIGN.md §7).
              # One pkgs.kicad, so pcbnew's
              # version always matches the libraries.
              pkgs.kicad
              pkgs.kicad.libraries.symbols
              pkgs.kicad.libraries.footprints
              # Python side is uv's alone; nix only supplies uv itself.
              pkgs.uv
              # Pre-commit hooks — the framework plus every tool the
              # hooks call, all nix-pinned so `.pre-commit-config.yaml` can
              # use `language: system` instead of downloading its own.
              pkgs.pre-commit
              mdformatGfm
              pkgs.markdownlint-cli2
              pkgs.lychee
            ];
            shellHook = ''
              # clang-tidy (unwrapped) needs libc++'s freestanding headers
              # pointed out; see scripts/pre-commit/clang-tidy-changed.
              export OPARROY_LIBCXX_INCLUDE=${llvmPkgs.libcxx.dev}/include/c++/v1
              # Where the DSL finds KiCad's libraries (DESIGN.md §7).
              export OPARROY_KICAD_SYMBOL_DIR=${pkgs.kicad.libraries.symbols}/share/kicad/symbols
              export OPARROY_KICAD_FOOTPRINT_DIR=${pkgs.kicad.libraries.footprints}/share/kicad/footprints
              # Project-owned footprints (boards/lib/) resolve alongside
              # KiCad's; searched after the nix-store roots.
              export OPARROY_PROJECT_FOOTPRINT_DIR="$PWD/boards/lib"
              # pcbnew's SWIG module (src/oparroy/dsl/pcb_merge.py): nixpkgs
              # builds it for Python 3.14, the same 3.14 the project pins —
              # uv finds nix's interpreter on PATH, so exporting pcbnew's
              # site-packages makes `import pcbnew` work in the project venv
              # (verified against KiCad 10.0.6). The
              # python314 pin must track kicad's build.
              export PYTHONPATH=${pkgs.kicad.base}/lib/python${pkgs.python314.pythonVersion}/site-packages''${PYTHONPATH:+:$PYTHONPATH}
              echo "== oparroy dev shell =="
              riscv64-none-elf-gcc --version | head -1
              arm-none-eabi-gcc --version | head -1
              clang --version | head -1
              clang-tidy --version | grep -E 'LLVM version' | head -1
              llvm-ar --version | grep -E 'LLVM version' | head -1
              meson --version
              ninja --version
              klee --version | head -2
              afl-cc --version | head -1
              ngspice --version | grep -i ngspice | head -1
              uv --version
              pre-commit --version
              lychee --version
            '';
          };
        }
      );
    };
}
