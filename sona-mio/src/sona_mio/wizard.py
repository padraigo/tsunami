"""Interactive prompts for the multi-step intake wizards (Epics 1 & 2).

Kept tiny and IO-injectable so tests can drive the CLI by passing canned
``input``/``output`` callables.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Callable, Iterable

Reader = Callable[[str], str]
Writer = Callable[[str], None]


def _default_writer(line: str) -> None:
    print(line)


def prompt_decimal(
    label: str,
    *,
    default: Decimal | None = None,
    minimum: Decimal | None = None,
    allow_blank: bool = False,
    read: Reader = input,
    write: Writer = _default_writer,
) -> Decimal | None:
    suffix = f" [{default}]" if default is not None else (" [blank to skip]" if allow_blank else "")
    while True:
        raw = read(f"{label}{suffix}: ").strip()
        if not raw:
            if default is not None:
                return default
            if allow_blank:
                return None
            write("  value required.")
            continue
        try:
            value = Decimal(raw.replace(",", "").replace("$", ""))
        except InvalidOperation:
            write(f"  '{raw}' is not a number; try again.")
            continue
        if minimum is not None and value < minimum:
            write(f"  must be ≥ {minimum}.")
            continue
        return value


def prompt_choice(
    label: str,
    choices: Iterable[str],
    *,
    default: str | None = None,
    read: Reader = input,
    write: Writer = _default_writer,
) -> str:
    choices = list(choices)
    suffix = f" ({'/'.join(choices)})"
    if default is not None:
        suffix += f" [{default}]"
    while True:
        raw = read(f"{label}{suffix}: ").strip().lower()
        if not raw and default is not None:
            return default
        if raw in choices:
            return raw
        write(f"  pick one of: {', '.join(choices)}.")


def prompt_text(
    label: str,
    *,
    default: str | None = None,
    read: Reader = input,
) -> str:
    suffix = f" [{default}]" if default else ""
    raw = read(f"{label}{suffix}: ").strip()
    if not raw and default is not None:
        return default
    return raw


def confirm(label: str, *, default: bool = False, read: Reader = input) -> bool:
    suffix = " [Y/n]" if default else " [y/N]"
    raw = read(f"{label}{suffix} ").strip().lower()
    if not raw:
        return default
    return raw in ("y", "yes")
