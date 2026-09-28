# Node target support: the DSL-generated CH32V003 pin map (T9) —
# design/node_pins.py regenerates pins.hpp, and tests/golden/
# node-pins.hpp pins it byte-exact. pins.cpp is the compile proof that
# the header builds under the freestanding rule set on every toolchain
# in the matrix; T11's node firmware adds the real translation units
# here.
static_library('node-pins', 'pins.cpp')
