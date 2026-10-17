# Subcircuit simulation unit tests (DESIGN.md §7): each
# circuits/<name>/tb_*.cir is a standalone ngspice testbench asserting
# its subcircuit's contract (engage timing, missed-pulse tolerance,
# glitch behavior). scripts/sim-run runs one bench and propagates the
# pass/fail exit status from its control block.
# CI runs each sim-* target as its own matrix leg
# (.github/workflows/ci.yml) — add new benches to that matrix too.
#
# DSL-captured DUTs (phy-segment, watchdog-chargepump — the hand-written
# .cir files retired with the phy-segment port) are regenerated at build
# time by the DSL emitter; sim-run's mirror mode drops the emission next
# to the unmodified bench decks, so the benches drive it exactly as they
# drove the hand-written file.
if not meson.is_cross_build()
  ngspice = find_program('ngspice')

  dut_phy_segment = custom_target('dut-phy-segment',
    output: 'phy-segment.cir',
    command: [files('..' / 'scripts' / 'spice-emit'), 'design.phy_segment'],
    capture: true,
  )
  dut_watchdog_chargepump = custom_target('dut-watchdog-chargepump',
    output: 'watchdog-chargepump.cir',
    command: [files('..' / 'scripts' / 'spice-emit'), 'design.watchdog_chargepump'],
    capture: true,
  )

  sim_runs = []
  foreach cand : ['watchdog-chargepump', 'watchdog-supervisor']
    foreach tb : ['tb_engage', 'tb_missed_pulse', 'tb_glitch']
      cmd = [
        files('..' / 'scripts' / 'sim-run'),
        meson.current_build_dir() / ('sim-out-' + cand + '-' + tb),
        meson.current_source_dir() / cand / (tb + '.cir'),
      ]
      if cand == 'watchdog-chargepump'
        cmd += dut_watchdog_chargepump
      endif
      sim_runs += run_target('sim-' + cand + '-' + tb,
        command: cmd,
      )
    endforeach
  endforeach

  foreach tb : ['tb_decode', 'tb_noise', 'tb_fault']
    sim_runs += run_target('sim-phy-segment-' + tb,
      command: [
        files('..' / 'scripts' / 'sim-run'),
        meson.current_build_dir() / ('sim-out-phy-segment-' + tb),
        meson.current_source_dir() / 'phy-segment' / (tb + '.cir'),
        dut_phy_segment,
      ],
    )
  endforeach

  foreach tb : ['tb_reach', 'tb_redriver', 'tb_reach_noise']
    sim_runs += run_target('sim-cable-reach-' + tb,
      command: [
        files('..' / 'scripts' / 'sim-run'),
        meson.current_build_dir() / ('sim-out-cable-reach-' + tb),
        meson.current_source_dir() / 'cable-reach' / (tb + '.cir'),
      ],
    )
  endforeach

  # ninja sim: run every subcircuit simulation unit test.
  alias_target('sim', sim_runs)
endif
