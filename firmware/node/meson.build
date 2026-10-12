# Node target support: the DSL-generated CH32V003 pin map —
# design/node_pins.py regenerates pins.hpp, and tests/golden/
# node-pins.hpp pins it byte-exact. pins.cpp is the compile proof that
# the header builds under the freestanding rule set on every toolchain
# in the matrix. runtime.cpp is the soft integer runtime the rv32ec
# link needs (no M extension, no libgcc multilib — see its header
# comment); its unit tests run on the host.
static_library('node-pins', 'pins.cpp')

if not meson.is_cross_build()
  test('node-runtime', executable('node-runtime-test',
    ['runtime.cpp', 'test_runtime.cpp', '../lib/test_main.cpp'],
  ), suite: 'firmware')
endif
