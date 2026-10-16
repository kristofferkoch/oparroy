# AMS1117 — quirks

- **Tantalum output capacitor demanded, ceramics fitted.** The
  datasheet makes 22 µF *solid tantalum* the stability condition
  (Application Hints §Stability) and specifies no ESR window — the
  classic 1117-family story: the compensation expects the tantalum's
  ESR zero, and sub-100 mΩ MLCCs can push the loop unstable (LM1117
  datasheets from TI/National state the ESR window explicitly,
  0.3–22 Ω; AMS1117's own doc stays silent on the number). The CI
  board capture (`design/ci_power.py`) fits 0603 ceramics anyway —
  C0603 22 µF out, 10 µF in — because tantalums would add an Extended
  BOM line and the load is digital and modest. **Bench-verify
  obligation:** check regulator stability (output ringing on a load
  step) on the first CI boards; the fix if it oscillates is an
  RC-damped output cap or a part swap to a ceramic-stable LDO, not a
  respin. (DS Application Hints §Stability; TI LM1117 SNOS412 for the
  ESR-window framing.)
- **The rail's total ESR keeps falling after the power module ships.**
  The 1117 compensation cares about the ESR of the whole output node,
  and everything downstream of `Cout` is more ceramic: the supervisor
  capture adds the RP2040's decoupling swarm (100 nF per power pin,
  1 µF on each VREG pin — `datasheets/RP2040/notes/power-design.md`,
  AN §2.1.2/§2.1.3), and each tile adds its own. Parallel MLCCs push
  the node's effective ESR even further below the tantalum zero the
  loop expects. Consequence for the bench-verify obligation above: run
  the load-step ringing check on a **fully populated** board
  (supervisor + tiles), not on a bare power subassembly.
- **Quiescent current is real money at idle:** 5–11 mA to GND before
  any load (DS Electrical Characteristics) — the single largest
  always-on draw of the 3V3 rail if the tiles sleep.
- **Clones abound.** "AMS1117" is an industry-standard footprint and
  dozens of vendors ship compatible die with looser specs; the C6186
  listing is the genuine Advanced Monolithic Systems part. The numbers
  in `facts.md` are AMS's; a future cheaper clone listing does not
  inherit them without re-extraction.
