# Bela platform — lessons for oparroy

Research date 2026-09-26, prompted by Bernt's tip ("done a lot of right
things"). Sources linked inline. Bela is a real-time audio/sensor
platform spun out of Queen Mary University of London after a
[2016 Kickstarter](http://andrewmcpherson.org/project/bela); now
Augmented Instruments Ltd.

## 1. Real-time I/O architecture: PRU as the I/O engine

Strict **split of responsibilities** on the BeagleBone's AM3358:

- **Linux (Xenomai Cobalt real-time thread)** runs the user's
  `render()` callback — DSP and control logic — with hard scheduling
  guarantees.
- **The PRU (200 MHz deterministic RISC core)** runs hand-written
  assembly (`pru_rtaudio.p` in the [Bela core repo](https://github.com/BelaPlatform/Bela))
  moving every sample between hardware and shared memory. Notably the
  PRU does **not** stream audio — the McASP peripheral does; the PRU is
  "a sort of sophisticated DMA controller" that also bit-bangs SPI to
  the analog ADC/DAC and samples GPIOs, **aligned sample-by-sample with
  the audio clock** ([forum: PRU vs McASP](https://forum.bela.io/d/20-pru-vs-mcasp)).

What it buys ([NIME-era paper](https://users.sussex.ac.uk/~thm21/ICLI_proceedings/2016/Practical/Workshops/129_Bela.pdf),
[Hackaday 2016](https://hackaday.com/2016/04/13/bela-real-time-beaglebone-audioanalog-cape/)):

- **Sensors at audio rate**: 8× 16-bit analog at 22.05–88.2 kHz, 16
  digital at 44.1 kHz — sensor reads synchronous with audio, so
  control-to-sound jitter is zero by construction, latency < 1 ms.
- A tiny, auditable blob of assembly owns *all* timing; Linux can be
  rebooted or crash without redesigning the real-time layer.

**Lesson:** validates the PIO argument in
[mcu-research](mcu-research-2026-09-26.md) §RP2040: *a small
deterministic engine owns the wire; a bigger non-deterministic host
owns policy*. Two specifics: (a) let a **dedicated peripheral do bulk
streaming** (McASP there; PIO+DMA here), use the programmable engine
only where programmability is needed (per-bit re-timing); (b) keep the
engine's code **small and frozen** — Bela's PRU blob barely changed
across a decade of Linux images. Bela Gem on PocketBeagle 2 (AM6254,
333 MHz PRUSS) reuses the same architecture
([BeagleBoard blog, 2025-07-10](https://www.beagleboard.org/blog/2025-07-10-bela-gem-brings-ultra-low-latency-audio-to-pocketbeagle-2)).

## 2. Sensor/IO ecosystem: Trill

[Trill](https://learn.bela.io/products/trill/about-trill/) is Bela's
capacitive-touch family (Bar, Square, Craft, Hex, Ring, Flex),
Kickstarter 2019. What they standardized:

- **One electrical interface**: 4-wire I2C + power, physically
  **JST-SH QWIIC connectors** ([Gliss update](https://www.crowdsupply.com/augmented-instruments/gliss/updates/the-next-generation-of-trill-sensors)),
  plus a Trill Hub breakout with on-board pull-ups for chaining.
- **One firmware, many shapes**: shared register protocol
  ([Trill datasheet](https://www.mouser.com/catalog/specsheets/Bela_TRILL_sensors_datasheet.pdf));
  host library auto-detects sensor type. Libraries for Bela (LGPL),
  Arduino (BSD-3), Linux ([GitHub: BelaPlatform/Trill](https://github.com/BelaPlatform/Trill)).
- **Deliberate address plan**: distinct default address per type
  (Bar 0x20 … Flex 0x48) plus 8 alternates via **tri-state solder
  bridges** (2×3 pads = 9 values), with docs covering even the
  "bridging both sides shorts VCC to GND" failure mode
  ([All about I2C](https://learn.bela.io/using-trill/all-about-i2c/)).
- **Smart-node partitioning**: touch processing (position + size,
  sensitivity tuning) happens **on the sensor's own MCU**; the host
  gets cooked data. Original Trill: Cypress PSoC 1; next-gen Gliss:
  STM32G491 ([gliss-firmware](https://github.com/BelaPlatform/gliss-firmware)).

**Lesson:** precedent for *oparroy nodes as smart peripherals with a
standardized cooked-data interface*, and for solving multi-instance
addressing **in hardware instead of a provisioning step**. Their
docs-driven treatment of I2C pull-up/address-collision pitfalls is
worth imitating for oparroy's accelerometer/captouch guide.

## 3. Developer experience

Adoption engine, in evidenced order of importance:

1. **Zero-install IDE in the browser**: board appears as `bela.local`;
   the IDE edits, cross-compiles *on the board*, runs projects;
   in-browser oscilloscope, console, interactive pin diagram
   ([IDE wiki](https://github.com/BelaPlatform/bela/wiki/Bela-IDE)).
1. **Examples as curriculum**: hundreds of categorized examples; docs
   say load one, save a copy, mutate it.
1. **A knowledge base, not a wiki**: [learn.bela.io](https://learn.bela.io)
   is tutorial-shaped; free YouTube C++ course; active
   [forum](https://forum.bela.io).
1. **Meet users in their language**: C/C++, Pure Data, SuperCollider,
   Csound, FAUST, Max RNBO, Arduino-style — same core engine behind
   all.
1. IDE is GPLv3, ships with every board.

**Lesson:** oparroy's DSL is the "single source of truth" advantage;
spend the savings on (a) a **golden live demo** (RP2040 supervisor +
ring visualizer) that works in minutes, and (b) **task-shaped docs**
("add a button node", "debug a dead ring segment"), not API-shaped
ones.

## 4. Open hardware / business model

Per their [licensing page](https://learn.bela.io/products/products-overview/open-source-licenses/)
and [Bela Gem Crowd Supply](https://www.crowdsupply.com/bela/bela-gem-stereo-and-multi):

- **Layered licenses**: hardware CC-BY-SA, core software **LGPL 3.0**
  (commercial products can link dynamically), IDE **GPL 3.0**, host
  libraries permissive (BSD-3).
- **Dual licensing as revenue**: closed use → commercial license,
  priced transparently for Trill (from £500 / 500 pieces).
- **Trademark is the moat**: "Bela" trademarked; community products use
  "X for Bela" naming and a community logo. Protocol/files free; the
  *brand* is not.
- **Crowdfunding every launch**: Kickstarter 2016 (Bela), 2019 (Trill),
  ~2022 (Gliss), Crowd Supply 2025 (Bela Gem). Retail via own shop +
  Mouser. Bela Gem released *unrouted* PCB files under CC BY-NC — a
  partial-closure experiment.
- University spin-out gave credibility and community before revenue.

**Lesson:** copyable core = **permissive protocol + copyleft reference
implementation + trademarked name**, permissive node-side libraries for
adoption. A sub-3-NOK node protocol has nothing to dual-license — the
asset is the standard and the supervisor tooling. (Note: oparroy is
currently settled on plain MIT, 2026-09-26 — revisit only if the
standard/tooling framing above resonates.)

## 5. Testing / manufacturing

Thinnest documented area; one very relevant recent data point — the
[Bela Gem production update (2025-12-22)](https://www.crowdsupply.com/bela/bela-gem-stereo-and-multi/updates/end-of-year-status-report-on-production-software-testing-and-the-new-bela-ide):

- **"Every Bela product is tested in operation before it goes out the
  door."**
- In-house **test jig**: clamped fixture with **spring-loaded pogo
  pins**, run **after SMT but before through-hole soldering** —
  catching failures at the cheapest rework point. The jig caused a
  multi-week slip ("teething problems"), reported publicly; paid off
  with "a very high yield rate."
- Software validated by **beta testers on real hardware** under stress
  workloads.

**Not found:** any public hardware-in-the-loop CI — the Bela core repo
has no GitHub Actions; if CI exists it isn't public. Bernt's claim
likely refers to architecture/UX, not CI.

**Lesson:** jig timing (post-SMT, pre-through-hole) and
test-every-unit-in-operation apply directly to oparroy's test board;
the jig-delay story warns to budget the test rig as a first-class
deliverable — aligning with hands-off-HIL from day one (DESIGN.md §6,
§8).

## Transferable to oparroy — decision map

| Bela decision                                                                     | oparroy design area                                                                                                                                   |
| --------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| Tiny frozen PRU assembly blob owns all wire timing; host does policy              | **PHY engine**: keep the PIO re-timing RX/TX program minimal, versioned separately from supervisor firmware                                           |
| Dedicated peripheral (McASP) streams bulk; programmable engine only where needed  | **PHY engine**: PIO + DMA chaining; CPU out of the bit path                                                                                           |
| Sensors sampled synchronously in the engine's timebase                            | **Protocol**: timestamp/slot node telemetry in the ring frame, not polled ad hoc                                                                      |
| Smart sensor nodes; cooked data over a standard 4-wire connector                  | **Node I/O**: nodes pre-process (debounce, captouch thresholding, accel FIFO), answer with digested values                                            |
| Hardware address selection via tri-state solder bridges, documented failure modes | **Node I/O / protocol**: hardware node-ID strategy instead of provisioning; docs teaching the short-circuit-class mistakes                            |
| Per-type default addresses + one shared register map, auto-detect in host lib     | **Protocol**: fixed node-type IDs in enumeration; supervisor auto-detects type                                                                        |
| One firmware across a sensor family                                               | **Node firmware**: single MCU image, personality by type ID — one HIL target (card T11)                                                               |
| Zero-install browser IDE, examples-as-curriculum, scope built in                  | **Tooling**: ship a runnable ring demo + live visualizer (RP2040 golden reference) before breadth of features                                         |
| Layered licensing: permissive libs, copyleft core, trademarked name               | **Repo/legal**: permissive node library, copyleft supervisor/tooling, trademark "oparroy" early — only if plain MIT (settled 2026-09-26) is revisited |
| In-house pogo-pin jig, test post-SMT/pre-through-hole, every unit in operation    | **Test board**: jig as its own deliverable; test at the cheapest rework stage (card T10)                                                              |

**Could not verify:** (a) any Bela hardware-in-the-loop CI — appears
not public; (b) whether Bela Gem reuses the original PRU assembly
unchanged; (c) current Trill production firmware (public repo reflects
the PSoC generation).
