"""Firmware pin maps: function requests, late pad binding, one table.

A capture requests pins by *function* (``gpio.request("keepalive")``);
pad numbers bind late, as refinement data (``gpio.bind(keepalive="PD3")``).
The one authoritative table then feeds both consumers:

- ``emit_pin_header`` — the freestanding-C++ header the firmware
  includes (``constexpr`` pads and peripheral-channel constants,
  code-std-cpp.md#6-constants-and-configuration style);
- ``check_pin_map`` — the GPIO-budget check of DESIGN.md §5/§3 ("lands
  at ~16-17 of 18"): every request bound to a fitting pad, no pad
  serving two functions, reservations (SWIO) and the total count
  honored.

Chip data (``Chip``/``Pad``) is datasheet-derived: the CH32V003F4P6
table below cites datasheets/CH32V003/notes/ — pad functions from
gpio-pinout.md (DS0 §2.1), OPA routing from opa.md, port bases from the
facts.md memory map (RM §1.2). Only the *default* alternate functions
are tabulated; AFIO remaps (gpio-pinout.md's remap column) are
refinement room, added when a binding needs one.

Structural misuse (duplicate requests, unknown pads, rebinding) raises
``DefinitionError`` at capture; pad-fit and budget violations are the
check's batch of ``Issue``s, mirroring the capture → check → emit split
of DESIGN.md §7.
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from oparroy.dsl.check import Issue, Severity, raise_on_errors
from oparroy.dsl.ir import DefinitionError, natural_key

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

_IDENT = re.compile(r"[a-z][a-z0-9_]*")

#: clang-format's column limit (.clang-format): emitted comments wrap
#: here so the header is clang-format-stable (LLVM reflows comments).
_COMMENT_WIDTH = 100


def _comment(text: str, *, prefix: str = "// ") -> list[str]:
    """Wrap one comment to the column limit, each line ``// ``-prefixed."""
    wrapper = textwrap.TextWrapper(
        width=_COMMENT_WIDTH,
        initial_indent=prefix,
        subsequent_indent=prefix,
        break_long_words=False,
        break_on_hyphens=False,
    )
    return wrapper.wrap(text)


@dataclass(frozen=True)
class Pad:
    """One package pad: a GPIO bit, or a power pin (``port`` None).

    ``channels`` maps a peripheral signal name to its channel value —
    ``adc`` → the ADC input number, ``opa_p`` → the OPA_PSEL bit value —
    or to None when the signal is presence-only (``usart_tx``, ``swio``).
    ``tags`` holds markers with no signal shape (``ft`` = 5 V-tolerant).
    """

    name: str
    pin: int
    port: str | None
    bit: int | None
    channels: Mapping[str, int | None] = field(default_factory=dict)
    tags: frozenset[str] = frozenset()

    @property
    def is_gpio(self) -> bool:
        """True for GPIO pads; False for power pads (VSS/VDD)."""
        return self.port is not None


class Chip:
    """One MCU in one package: the pad table and GPIO port bases."""

    def __init__(
        self,
        part: str,
        pads: Iterable[Pad],
        port_bases: Mapping[str, int],
    ) -> None:
        self._part = part
        self._pads = tuple(pads)
        self._by_name = {pad.name: pad for pad in self._pads}
        if len(self._by_name) != len(self._pads):
            msg = f"chip {part} has duplicate pad names"
            raise DefinitionError(msg)
        self._port_bases = dict(port_bases)

    @property
    def part(self) -> str:
        """The full part number ("CH32V003F4P6")."""
        return self._part

    @property
    def gpio_pads(self) -> tuple[Pad, ...]:
        """The requestable pads, in package-pin order."""
        return tuple(pad for pad in self._pads if pad.is_gpio)

    @property
    def gpio_count(self) -> int:
        """The GPIO budget: how many pads firmware may spend.

        >>> CH32V003F4P6.gpio_count
        18
        """
        return len(self.gpio_pads)

    @property
    def port_bases(self) -> dict[str, int]:
        """GPIO port register-block base addresses by port letter."""
        return dict(self._port_bases)

    def pad(self, name: str) -> Pad:
        """Look up a pad by name ("PD3"); raises DefinitionError if absent.

        >>> CH32V003F4P6.pad("PA2").channels["opa_p"]
        0
        """
        try:
            return self._by_name[name]
        except KeyError:
            msg = f"{self._part} has no pad {name!r}"
            raise DefinitionError(msg) from None


def _gpio(
    pin: int,
    name: str,
    channels: dict[str, int | None],
    *,
    ft: bool = False,
) -> Pad:
    """Build a GPIO pad; the name carries port and bit ("PD3" → D/3)."""
    return Pad(
        name=name,
        pin=pin,
        port=name[1],
        bit=int(name[2:]),
        channels=channels,
        tags=frozenset({"ft"} if ft else ()),
    )


# CH32V003F4P6 (TSSOP-20), the §5 node MCU. Default alternate functions
# only, per DS0 §2.1 (gpio-pinout.md); OPA signal names per opa.md
# (OPP0/OPP1 → opa_p 0/1, OPN0/OPN1 → opa_n 0/1, OPO → opa_out).
# TIM2_CH1 needs no pad: the OPA output routes to it internally (§2).
# PD7 is GPIO out of reset — NRST only via option byte (quirks.md §GPIO).
CH32V003F4P6 = Chip(
    "CH32V003F4P6",
    (
        _gpio(1, "PD4", {"adc": 7, "usart_ck": None, "tim2_ch": 1, "opa_out": None}),
        _gpio(2, "PD5", {"adc": 5, "usart_tx": None}),
        _gpio(3, "PD6", {"adc": 6, "usart_rx": None}),
        _gpio(4, "PD7", {"nrst": None, "tim2_ch": 4, "opa_p": 1}),
        _gpio(5, "PA1", {"osc_in": None, "adc": 1, "tim1_ch": 2, "opa_n": 0}),
        _gpio(6, "PA2", {"osc_out": None, "adc": 0, "tim1_chn": 2, "opa_p": 0}),
        Pad("VSS", 7, None, None),
        _gpio(8, "PD0", {"tim1_chn": 1, "opa_n": 1}),
        Pad("VDD", 9, None, None),
        _gpio(10, "PC0", {"tim2_ch": 3}),
        _gpio(11, "PC1", {"i2c_sda": None, "spi_nss": None}, ft=True),
        _gpio(
            12, "PC2", {"i2c_scl": None, "usart_rts": None, "tim1_bkin": None}, ft=True
        ),
        _gpio(13, "PC3", {"tim1_ch": 3}),
        _gpio(14, "PC4", {"adc": 2, "tim1_ch": 4, "mco": None}),
        _gpio(15, "PC5", {"spi_sck": None, "tim1_etr": None}, ft=True),
        _gpio(16, "PC6", {"spi_mosi": None}, ft=True),
        _gpio(17, "PC7", {"spi_miso": None}),
        _gpio(18, "PD1", {"swio": None, "tim1_chn": 3, "adc_etr2": None}),
        _gpio(19, "PD2", {"tim1_ch": 1, "adc": 3}),
        _gpio(20, "PD3", {"adc": 4, "tim2_ch": 2, "adc_etr": None, "usart_cts": None}),
    ),
    # RM §1.2 (facts.md memory map); the F4P6 bonds ports A, C, D — no B.
    {"A": 0x40010800, "C": 0x40011000, "D": 0x40011400},
)


@dataclass(frozen=True)
class PinRequest:
    """One function's claim on a pad: constraint and emitted constants.

    ``uses`` names the peripheral signals the function needs from its
    pad — the check requires the bound pad to carry each, and the
    emitter turns channel-valued ones into ``<name>_<signal>``
    constants. ``const`` adds capture-supplied constants verbatim
    (``<name>_<key>``) for routing facts that live off the pad — DMA
    channel assignments (dma.md Table 8-2). ``doc`` becomes the
    constant's comment in the header.
    """

    name: str
    uses: tuple[str, ...]
    const: Mapping[str, int]
    doc: str


class PinMap:
    """The authoritative pin table for one design on one chip.

    Requests are by function, pads bind late as refinement data; both
    the firmware header and the GPIO-budget check read this one table.
    """

    def __init__(self, chip: Chip) -> None:
        self._chip = chip
        self._requests: dict[str, PinRequest] = {}
        self._reservations: dict[str, str] = {}
        self._assignments: dict[str, Pad] = {}

    @property
    def chip(self) -> Chip:
        """The chip this map assigns pads on."""
        return self._chip

    @property
    def requests(self) -> dict[str, PinRequest]:
        """All pin requests by function name (insertion order)."""
        return dict(self._requests)

    @property
    def reservations(self) -> dict[str, str]:
        """Reserved pads: pad name → reason (insertion order)."""
        return dict(self._reservations)

    @property
    def assignments(self) -> dict[str, Pad]:
        """The refinement data: function name → bound pad."""
        return dict(self._assignments)

    def request(
        self,
        name: str,
        *,
        uses: Iterable[str] = (),
        const: Mapping[str, int] | None = None,
        doc: str = "",
    ) -> None:
        """Claim a pad for a function; the pad itself binds later.

        ``uses`` constrains the binding to pads carrying those signals
        (``uses=("adc",)`` — an ADC-capable pad; the check enforces it
        and the emitter emits the channel value). Function names and
        signal/const keys become C identifiers in the header, so they
        must be ``snake_case`` identifiers.
        """
        if not _IDENT.fullmatch(name):
            msg = f"pin function {name!r} is not a snake_case C identifier"
            raise DefinitionError(msg)
        if name in self._requests:
            msg = f"duplicate pin request {name!r}"
            raise DefinitionError(msg)
        const = dict(const or {})
        for key in (*uses, *const):
            if not _IDENT.fullmatch(key):
                msg = f"pin signal {key!r} is not a snake_case C identifier"
                raise DefinitionError(msg)
        overlap = sorted(set(uses) & set(const), key=natural_key)
        if overlap:
            msg = f"{name}: const keys {overlap} collide with used signals"
            raise DefinitionError(msg)
        self._requests[name] = PinRequest(name, tuple(uses), const, doc)

    def reserve(self, pad: str, *, reason: str) -> None:
        """Take a pad off the table without a firmware function (SWIO).

        Reservations count in the GPIO budget and are documented in the
        header, but no constant is emitted — firmware never touches
        the pad.
        """
        resolved = self._chip.pad(pad)
        if not resolved.is_gpio:
            msg = f"{resolved.name} is a power pad, not reservable GPIO"
            raise DefinitionError(msg)
        if resolved.name in self._reservations:
            msg = f"pad {resolved.name} is already reserved"
            raise DefinitionError(msg)
        self._reservations[resolved.name] = reason

    def bind(self, **pads: str) -> None:
        """Bind functions to pads — the refinement data.

        Each key must be a requested function, each value a pad of the
        chip; both raise at capture on a typo. A function binds once:
        changing a pin means editing the refinement data, not layering
        a second binding.
        """
        for name, pad in pads.items():
            if name not in self._requests:
                msg = f"bind: no pin request named {name!r}"
                raise DefinitionError(msg)
            if name in self._assignments:
                msg = f"pin function {name!r} is already bound"
                raise DefinitionError(msg)
            self._assignments[name] = self._chip.pad(pad)


def check_pin_map(pin_map: PinMap) -> list[Issue]:
    """Validate a pin map; returns the issue list.

    The §5/§3 GPIO budget: pad fit (the bound pad carries every used
    signal), one function per pad, reservations respected, and the
    total — requests plus reservations — inside the chip's GPIO count.
    Unbound requests are warnings, not errors: refinement may still be
    in flight (the header emitter refuses them, since it needs the pad).
    """
    issues: list[Issue] = []
    for name, req in pin_map.requests.items():
        pad = pin_map.assignments.get(name)
        if pad is None:
            issues.append(
                Issue(Severity.WARNING, f"pin function {name!r} is not bound to a pad")
            )
            continue
        if not pad.is_gpio:
            issues.append(
                Issue(
                    Severity.ERROR,
                    f"{name} is bound to {pad.name} (pin {pad.pin}), a power pad",
                )
            )
            continue
        if pad.name in pin_map.reservations:
            issues.append(
                Issue(
                    Severity.ERROR,
                    f"{name} is bound to {pad.name}, reserved: "
                    f"{pin_map.reservations[pad.name]}",
                )
            )
        issues.extend(
            Issue(
                Severity.ERROR,
                f"{pad.name} (pin {pad.pin}) has no {signal} function, "
                f"requested by {name}",
            )
            for signal in req.uses
            if signal not in pad.channels
        )
    occupants: dict[str, str] = {}
    for name, pad in pin_map.assignments.items():
        other = occupants.get(pad.name)
        if other is not None:
            issues.append(
                Issue(
                    Severity.ERROR,
                    f"{other} and {name} are both bound to {pad.name}",
                )
            )
        else:
            occupants[pad.name] = name
    used = len(pin_map.requests) + len(pin_map.reservations)
    budget = pin_map.chip.gpio_count
    if used > budget:
        issues.append(
            Issue(
                Severity.ERROR,
                f"GPIO budget exceeded: {used} of {budget} pads used "
                f"({pin_map.chip.part})",
            )
        )
    return issues


def emit_pin_header(
    pin_map: PinMap,
    *,
    source: str,
    regenerate: str,
    title: str,
) -> str:
    """Emit the pin map as a freestanding-C++ header.

    ``constexpr`` throughout — the preprocessor is for includes
    (code-std-cpp.md#6-constants-and-configuration): one ``Pad``
    constant per function plus ``uint8_t`` channel constants for the
    used signals and the
    capture-supplied ``const`` entries. Emission is byte-identical
    across runs (no dates, no paths beyond the caller's ``source``)
    and requires a clean, fully bound map: the check's errors raise,
    and unbound requests are a ``DefinitionError`` here — the header
    is where the pads must exist.
    """
    raise_on_errors(check_pin_map(pin_map))
    unbound = [name for name in pin_map.requests if name not in pin_map.assignments]
    if unbound:
        msg = f"unbound pin functions: {', '.join(unbound)}"
        raise DefinitionError(msg)
    chip = pin_map.chip
    bound = {pad.name for pad in pin_map.assignments.values()}
    spare = [
        pad
        for pad in chip.gpio_pads
        if pad.name not in bound and pad.name not in pin_map.reservations
    ]
    used = len(pin_map.requests) + len(pin_map.reservations)
    if spare:
        pads = ", ".join(f"{pad.name} (pin {pad.pin})" for pad in spare)
        budget = f"{used} of {chip.gpio_count} GPIO assigned; spare: {pads}."
    else:
        budget = f"{used} of {chip.gpio_count} GPIO assigned; no spare pads."
    ports = sorted(
        {pad.port for pad in pin_map.assignments.values() if pad.port is not None}
    )
    lines = [
        "#pragma once",
        "",
        f"// Generated by oparroy-dsl from {source} — do not edit.",
        f"// Regenerate: {regenerate}",
        "//",
        *_comment(title),
        *_comment(budget),
        "",
        "#include <cstdint>",
        "",
        "namespace pins {",
        "",
        "// GPIO port register-block base addresses (RM §1.2).",
    ]
    lines.extend(
        f"inline constexpr uint32_t gpio_{port.lower()}_base = "
        f"0x{chip.port_bases[port]:08x};"
        for port in ports
    )
    lines += [
        "",
        "// One pad as firmware sees it: the port register block, the bit",
        "// inside it, and the package pin for schematic cross-reference.",
        "struct Pad {",
        "    uint32_t port_base;",
        "    uint8_t bit;",
        "    uint8_t package_pin;",
        "};",
    ]
    for name, req in pin_map.requests.items():
        pad = pin_map.assignments[name]
        assert pad.port is not None  # noqa: S101 — check passed: bound GPIO
        lines.append("")
        if req.doc:
            lines.extend(_comment(f"{name} — {req.doc}"))
        lines.append(
            f"inline constexpr Pad {name}{{.port_base = gpio_{pad.port.lower()}_base, "
            f".bit = {pad.bit}, .package_pin = {pad.pin}}};"
        )
        lines.extend(
            f"inline constexpr uint8_t {name}_{signal} = {pad.channels[signal]};"
            for signal in req.uses
            if pad.channels[signal] is not None
        )
        lines.extend(
            f"inline constexpr uint8_t {name}_{key} = {value};"
            for key, value in req.const.items()
        )
    if pin_map.reservations:
        lines.append("")
        lines.append("// Reserved — counted in the GPIO budget, never firmware GPIO:")
        for pad_name, reason in pin_map.reservations.items():
            lines.extend(
                _comment(f"  {pad_name} (pin {chip.pad(pad_name).pin}): {reason}")
            )
    lines.append("")
    lines.append("} // namespace pins")
    return "\n".join(lines) + "\n"
