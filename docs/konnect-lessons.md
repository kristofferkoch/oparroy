# Konnect — lessons for oparroy

[Konnect](https://github.com/mixelpixx/Konnect) is an AI-assisted KiCad
10 plugin: a single static Rust binary that serves ~230 MCP tools
(schematic capture, layout, routing, checks, manufacturing export) and
drives a live KiCad through the official IPC API. Mined at v0.13.0
(commit `9488e5f`, beta). License is AGPL-3.0 + commercial — so this is
idea-mining: mechanisms and idioms to reimplement, never code to lift.

Sections follow the repo's crate layout; file paths are given so claims
can be re-verified against the source.

## 1. KiCad IPC API instead of SWIG/pcbnew

Konnect's whole board backend is KiCad 10's IPC API — protobuf over NNG
— with zero pcbnew/SWIG (`crates/konnect-ipc/`). The mechanisms worth
stealing are the failure disciplines, not the transport:

- **Vendored protos, probe-don't-sniff capabilities.** The ~15 `.proto`
  files are copied verbatim from KiCad's source. There is no version
  handshake in the protocol, so capability is established by *runtime
  probing*: a command KiCad doesn't implement answers
  `AS_UNHANDLED`/`AS_UNIMPLEMENTED`, which is captured as typed,
  authoritative evidence — "never inferred from a version string"
  (`client.rs`, `pcb_components.rs`). `GetVersion` is decoration on the
  error, never the gate.
- **Typed failure classification drives recovery.** Every IPC failure
  lands in `Unreachable` (never reached KiCad — file fallback may be
  safe), `Rejected` (KiCad answered — fail closed), or `Uncertain`
  (delivered, no authoritative reply — *never retry, never
  file-fallback*). NNG req/rep retransmission is not exactly-once, so a
  timed-out request may still have executed; Konnect treats
  unknown-outcome as a first-class state instead of blind-retrying.
- **Fresh socket per request, bounded timeouts.** No persistent
  connection — a wedged KiCad can't hang the client past 30 s. And
  socket *discovery never connects*: a raw connect that doesn't
  complete NNG's handshake wedges KiCad's REP server for all clients
  until restart (their issue #498, pinned by a regression test).
- **Envelope success is not success.** `CreateItems`/`FlipItems` can
  return `IRS_OK` with zero items affected; only per-item status +
  returned KIID match + a fresh post-commit readback count as evidence.
- **Undo grouping is the transaction unit.** `BeginCommit` → ops →
  `EndCommit`; large syncs chunk creates (≤32 footprints) inside one
  commit so one Ctrl+Z reverts the whole batch. Rollback on
  unknown-outcome is itself unsafe (it can race an unfinished mutation),
  so recovery re-snapshots and requires byte-identical state before
  dropping — and still reports an error.
- **File fallback is gated, not assumed.** Editing the `.kicad_pcb`
  underneath KiCad is allowed only when transport was *unreachable*,
  no sibling `~<file>.lck` lock exists (never parsed — staleness is
  unprovable), and the server never saw the board live; any answer from
  KiCad at all fails closed, because its next save silently discards
  the file edit. Closed-board edits are revision-checked
  compare-and-swap with a geometry whitelist and named refusals.

**Lesson:** the IPC API is our escape hatch from the
Python-3.14-pinned-to-nixpkgs-pcbnew dance — the wire protocol is small
and has Python bindings (`pynng` + protobuf), so an oparroy IPC client
wouldn't carry the SWIG version lock at all. But note the asymmetry:
most of oparroy's KiCad coupling is *file*-level (netlist emission,
back-annotation, layout checks on saved boards), where Konnect's
guarded-file-edit machinery matters more than IPC. For the parked
layout-replication generator: closed-board file replication with
compare-and-swap + lock veto is the safer path, and oparroy is better
positioned for it than Konnect — the DSL knows tile congruence
statically. One IPC gotcha to design around either way: footprint
children serialize in *absolute* board coordinates despite the proto
comment claiming relative — an anchor-only move silently strands copper
(`transform.rs`).

## 2. Defensive round-trips against external tools

The Specctra/Freerouting autorouting path (`crates/konnect-core/src/ specctra.rs`, `specctra_ses.rs`, `freerouting_mcp.rs`) is the most
transferable engineering in the repo — a template for handing a design
to an external tool and taking the result back safely:

- **Hash-bound manifest.** DSN export works only from an IPC snapshot,
  re-snapshots after capture and bails if the board moved, and writes a
  JSON manifest with the SHA-256 of the exact source bytes plus full
  bidirectional name maps (layers, components, pads, nets, padstacks).
  SES import re-verifies the *live* board's hash against the manifest
  before planning anything — the revision binding on the return leg.
- **Fail-closed profile, rejection before mutation.** Anything the
  importer can't represent exactly (unlocked tracks, arcs, zones,
  unknown SES tags, placement drift beyond 1e-9) is a refusal, not an
  approximation. The generated DSN is even re-parsed with an
  independent parser as a self-check.
- **One transaction, provable rollback.** The import applies in a
  single named commit; on any post-commit failure a compensating commit
  deletes exactly the created KIIDs and proves the board re-serializes
  byte-identical to the pre-import snapshot. Source files are never
  overwritten — outputs are create-new-only atomic writes, and exactly
  the files a failed call created are cleaned up.
- **Owned child processes.** Freerouting runs as a spawned Java child,
  HTTP pinned to loopback (a test asserts no `0.0.0.0`), timeouts at
  three levels, kill-on-drop, and tests that prove reaping on timeout
  and cancellation. External-tool schemas are validated against a
  contract before use, not trusted.

**Lesson:** this maps directly onto oparroy's DSL↔KiCad flows —
hash-bind any export to the exact source snapshot, validate the return
completely *before* mutating, mutate in one transaction, prove the
post-state, roll back byte-exactly. Also the *locked-routing trick*:
pre-routed geometry marked locked survives the round-trip and is
inventoried on return — exactly the mechanism for "route one CI-board
tile, stamp it out as locked, autoroute the rest" if we ever want a
router in the loop.

## 3. KiCad file editing discipline

Konnect edits `.kicad_sch` without KiCad via its own S-expression
engine (`crates/konnect-sexp/`, `crates/konnect-schematic-editor/`).
The design decisions are hard-won (each cites a corruption incident):

- **Targeted text edits, never re-serialization.** The parsed tree is
  read-only; writes are byte-range `SexpEdit`s applied in reverse
  offset order, with string/escape-aware balanced-block finders that
  are indentation-agnostic. A parse→dump round-trip caused "single-line
  collapse" corruption in their Python predecessor.
- **Deny-list preservation.** Within a typed element, every
  *unmodelled* child is kept verbatim and re-emitted; an earlier
  allow-list silently dropped `(lib_name …)` and "rewired the netlist
  without any error" (#143).
- **Atomic write recipe.** Sibling scratch file (never a shared temp
  dir — rename must stay on one filesystem) with a unique
  name-per-(file, pid, counter), `create_new`, destination's
  permission bits copied, fsync the file *and* the parent directory,
  then rename. Plus compare-and-swap: re-read under an advisory lock,
  require byte-equality with what the edit was computed from, verify
  after rename.
- **Conformance-oracle testing.** Their round-trip tests run against
  *every schematic KiCad ships* (demo corpus, skipped silently when
  absent), comparing per-UUID blocks; plus property tests (never panic
  on garbage, "every item parsed or counted"). Fixture rule: "a
  hand-authored fixture shares the assumption the code got wrong."

**Lesson:** direct upgrades for `src/oparroy/dsl/kicad_pcb.py` and
`pcb_merge.py`: text-surgery edits to preserve user formatting in
back-annotation merges, deny-list child preservation, the
compare-and-swap conflict model, and the KiCad-demo-corpus conformance
suite (hypothesis for the parser properties). The UUID-targeted command
model — each change carries its exact source block as precondition and
yields an exact inverse — is the blueprint if pcb_merge ever wants
per-footprint conflict granularity.

## 4. JLCPCB catalog without the API

Konnect's parts search sidesteps the JLCPCB/LCSC API entirely
(`crates/konnect-core/src/tools/integration.rs`):

- **Source is a third-party feed**: the kicad-jlcpcb-tools project's
  SQLite FTS5 snapshot, served from GitHub Pages — free, no auth, no
  rate limits, one bulk download. The `parts` table carries
  `LCSC Part`, `MFR.Part`, `Library Type` (Basic / Preferred /
  Extended verbatim), `Stock`, `Price` (a `qty:price` string; absent
  means *unknown*, never zero).
- **Local re-import, atomic install**: validated schema, re-indexed
  SQLite, `PRAGMA quick_check`, atomic rename with backup rollback.
  No auto-update — refresh is user-initiated; search results are
  cached with a 5-minute TTL so a fresh download shows through.
- **Staleness as policy**: their agent skill doc instructs treating the
  catalog as "discovery evidence, not a live stock or price guarantee,"
  recording the catalog date; their pick-and-place correction exporter
  always returns `PREVIEW_REQUIRED` — the human verifies in JLCPCB's
  placement view. Tests pin verbatim feed rows as a TSV fixture with a
  README recording download date and part count.
- **Basic-first ranking solved**: tier order Basic > Preferred >
  Extended, then known-price before unknown, price ascending, stock
  descending — a ready-made ranking for "suggest a Basic substitute."
  They deliberately do *not* bundle the GPL JLCKicadTools correction DB
  — license hygiene even for data.

**Lesson:** this settles the parked parts-DB stock-refresh idea's open
questions. (a) *Rate limits/auth*: skip the API; mirror the feed.
(b) *Edit in place vs overlay*: overlay — keep `design/parts_db.py`
hand-authored, build a local SQLite/JSON cache keyed by LCSC code that
`check_stock` reads, and have the refresh script emit *proposed edits*
(a diff) for PR review rather than rewriting data-as-code. (c) Record
the feed snapshot date per refresh — the existing as-of-date discipline
in `Stock`, now machine-sourced.

## 5. Serving tools to LLM agents

Konnect's context economy and reliability machinery
(`crates/konnect-core/src/router/`, `observability.rs`, `mcp/error.rs`,
`docs/RELIABILITY_CONTRACT.md`):

- **Starter kit + on-demand toolsets**: 2 tools pre-loaded (~2K tokens)
  instead of ~230 (~23K); `load_toolset` pulls in a domain on demand,
  and an unloaded-tool error names its owning toolset so recovery is
  one hop. Call logs (ring buffer + JSONL) record args/result byte
  counts — poor-man's token accounting — and the model self-diagnoses
  via `get_recent_calls`/`server_stats`.
- **Structured error taxonomy**: ~20 stable `kind` tags
  (`invalid_argument{field}`, `stale_target`,
  `mutation_outcome_uncertain`, `conflict{paths}`), each carrying the
  fields recovery needs, with a drift-pinning test so log vocabulary
  and served vocabulary can't diverge.
- **Reliability contract with a ratchet**: outcome envelope
  (`complete/partial/failed/uncertain` + counts that must sum + typed
  retry hint), evidence rules ("a response field must be derived from
  the result, never echoed from the request"; "not checked ≠ none
  found"), a **negative-control rule** (neuter each new guard, watch
  its test fail), and a machine-checked legacy-debt inventory with a CI
  ceiling that only ratchets down.
- **Guidance drift detection**: bundled agent skills are embedded in
  the binary, byte-compared on `status`, and drift is *reported*, never
  auto-overwritten.

**Lesson:** oparroy's agent-facing surface is CLIs + docs today; if it
ever grows an MCP/skill server, the starter-kit/on-demand split and the
kind-tagged error taxonomy are the mechanisms to copy. Two rules are
worth adopting into our engineering culture *now*, verbatim: response
fields derived from evidence, never echoed; and a negative-control test
for every guard.

## 6. Testing and releasing against real KiCad

- **Layered CI**: fast per-PR gates on mocks (a lifecycle-owned
  `inproc://` NNG double), plus an opt-in lane (`run:e2e-kicad` PR
  label, weekly cron) that installs a pinned KiCad 10.0.5 and runs the
  full loop — create→wire→ERC→Gerber→DRC — against real KiCad, plus
  demo-corpus conformance. Release runs the same gate pre-tag with a
  synthetic version before any tag build publishes.
- **Doc-drift guards**: doc claims (tool counts) are derived from the
  registry and CI-checked, with a `fix` task that regenerates — so the
  guard doesn't itself create merge conflicts.

**Lesson:** oparroy already has the golden-file discipline; the
transferable piece is the *opt-in pinned-KiCad lane* — feed emitted
netlists/boards back through real `kicad-cli`/KiCad in a weekly or
labeled CI job, keeping the per-PR gate cheap, and bump the pinned
KiCad version deliberately alongside the supported-version claim. The
derived-doc-count guard fits our single-source-of-truth culture.

## Transferable to oparroy — decision map

| Konnect mechanism                                                             | oparroy design area                                                                               |
| ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| KiCad IPC API (protobuf/NNG), vendored protos, no Python                      | **Tooling**: escape the pcbnew/SWIG Python pin; IPC client in any language for live-board tooling |
| Probe-don't-sniff capabilities (`AS_UNHANDLED` as evidence)                   | **Tooling**: any version-dependent KiCad integration; never gate on version strings               |
| Typed failure classification; uncertain-outcome = never blind-retry           | **DSL I/O**: back-annotation and any board-editing path in `kicad_pcb.py`/`pcb_merge.py`          |
| Guarded file fallback (lock-file veto, revision-checked CAS)                  | **DSL I/O**: policy for editing files KiCad might hold open                                       |
| Hash-bound manifest + rejection-before-mutation + byte-exact rollback         | **DSL I/O**: DSL↔KiCad round-trips; any external-tool handoff                                     |
| Locked-routing inventory survives autorouter round-trip                       | **CI board**: route-one-tile-stamp-rest, if a router ever enters the loop                         |
| Targeted text edits + deny-list preservation + atomic-write recipe            | **DSL I/O**: `pcb_merge.py` formatting fidelity and corruption safety                             |
| KiCad demo corpus as conformance oracle; "no hand-authored fixtures"          | **Tests**: round-trip oparroy's parser/emitter against shipped KiCad files                        |
| kicad-jlcpcb-tools feed (no auth, bulk) + overlay cache + proposed-edit diffs | **Parts DB**: settles the stock-refresh tooling's open questions                                  |
| Basic > Preferred > Extended ranking; snapshot-date provenance                | **Parts DB**: `check_stock` staleness + Basic-substitute suggestion                               |
| Starter-kit/on-demand toolsets; kind-tagged errors; observability             | **Agent surface**: only if oparroy grows an MCP/skill server                                      |
| Evidence-derived response fields; negative-control tests; debt ratchet        | **Engineering culture**: adopt as rules now (AGENTS.md/pre-commit)                                |
| Opt-in pinned-KiCad e2e lane; pre-tag release rehearsal                       | **CI**: weekly/labeled real-KiCad job for netlist emitter + DRC                                   |

**Not transferable:** schematic capture and AI-driven design (the DSL
is the source of truth — Konnect's capture path targets hand/LLM-drawn
KiCad schematics), PCM plugin packaging (oparroy isn't a KiCad plugin),
the two-maintainer governance machinery, and anything code-shaped —
AGPL-3.0 means reimplementation from these notes, not reuse.

**Could not verify:** real-world mileage of the IPC API under KiCad
11 (Konnect targets 10.0.x; the bridge is labeled "not the KiCad 11
integration path"); the kicad-jlcpcb-tools feed's update cadence and
long-term stability (third-party, unofficial); Linux QA of the plugin
(Windows is their tested platform).
