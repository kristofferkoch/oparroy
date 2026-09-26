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
              pkgs.klee
              pkgs.aflplusplus
              # Subcircuit simulation unit tests (DESIGN.md §7).
              pkgs.ngspice
              # Python side is uv's alone; nix only supplies uv itself.
              pkgs.uv
            ];
            shellHook = ''
              echo "== oparroy dev shell =="
              riscv64-none-elf-gcc --version | head -1
              arm-none-eabi-gcc --version | head -1
              clang --version | head -1
              clang-tidy --version | grep -E 'LLVM version' | head -1
              klee --version | head -2
              afl-cc --version | head -1
              ngspice --version | grep -i ngspice | head -1
              uv --version
            '';
          };
        }
      );
    };
}
