# Single source for the freestanding flag set (code-std.md §2) — sourced by
# scripts/build-firmware-smoke and scripts/pre-commit/clang-tidy-changed.
# Keep word-splitting friendly: flags only, no quoting.
# shellcheck shell=sh
FREESTANDING_FLAGS="-std=c++23 -ffreestanding -fno-exceptions -fno-rtti \
-Wall -Wextra -Wpedantic -Werror \
-Wconversion -Wsign-conversion -Wdouble-promotion \
-Wshadow -Wundef -Wswitch-enum -Wold-style-cast -Wcast-qual \
-Wnull-dereference"
