# Subcircuit simulation unit tests (DESIGN.md §7): each
# circuits/<name>/tb_*.cir is a standalone ngspice testbench asserting
# its subcircuit's contract (engage timing, missed-pulse tolerance,
# glitch behavior). scripts/sim-run runs one bench and propagates the
# pass/fail exit status from its control block.
if not meson.is_cross_build()
  ngspice = find_program('ngspice')

  sim_runs = []
  foreach cand : ['watchdog-chargepump', 'watchdog-supervisor']
    foreach tb : ['tb_engage', 'tb_missed_pulse', 'tb_glitch']
      sim_runs += run_target('sim-' + cand + '-' + tb,
        command: [
          files('..' / 'scripts' / 'sim-run'),
          meson.current_build_dir() / ('sim-out-' + cand + '-' + tb),
          meson.current_source_dir() / cand / (tb + '.cir'),
        ],
      )
    endforeach
  endforeach

  foreach tb : ['tb_decode', 'tb_noise', 'tb_fault']
    sim_runs += run_target('sim-phy-segment-' + tb,
      command: [
        files('..' / 'scripts' / 'sim-run'),
        meson.current_build_dir() / ('sim-out-phy-segment-' + tb),
        meson.current_source_dir() / 'phy-segment' / (tb + '.cir'),
      ],
    )
  endforeach

  # ninja sim: run every subcircuit simulation unit test.
  alias_target('sim', sim_runs)
endif
