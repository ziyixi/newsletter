"""Freeze optional public discovery guides into instructions, never load on replay."""

from pathlib import Path

from newsletter.collection.instructions import (
    MAX_INSTRUCTION_BYTES,
    Instruction,
    InstructionError,
    load_instructions,
)
from newsletter.contracts import content_hash

MAX_GUIDE_BYTES = 16_000
_GUIDES = {"01-ai-ml": "ai-ml.md"}


def load_discovery_instructions(directory: Path) -> list[Instruction]:
    """An optional _sources file augments its direction, not the worker count.

    Old custom instruction directories need no migration. Source-guide edits
    affect the next frozen run only; ordinary execution consumes that snapshot.
    """
    instructions = load_instructions(directory)
    result = []
    for instruction in instructions:
        name = _GUIDES.get(instruction.id)
        if name is None:
            result.append(instruction)
            continue
        folder = directory / "_sources"
        path = folder / name
        try:
            if folder.is_symlink() or path.is_symlink():
                raise InstructionError()
            if not folder.exists():
                result.append(instruction)
                continue
            if not folder.is_dir():
                raise InstructionError()
            if not path.exists():
                result.append(instruction)
                continue
            if not path.is_file():
                raise InstructionError()
            with path.open("rb") as source:
                raw = source.read(MAX_GUIDE_BYTES + 1)
            guide = raw.decode("utf-8")
            if (
                len(raw) > MAX_GUIDE_BYTES
                or not guide.strip()
                or "\x00" in guide
            ):
                raise InstructionError()
            text = (
                instruction.text
                + "\n\n## Frozen public source guide\n\n"
                + guide
            )
            if len(text.encode("utf-8")) > MAX_INSTRUCTION_BYTES:
                raise InstructionError()
            result.append(Instruction(instruction.id, text, content_hash(text)))
        except (OSError, UnicodeError):
            raise InstructionError() from None
    return result
