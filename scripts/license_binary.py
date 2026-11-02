"""Read direct native imports without loading or executing a release extension."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import StrEnum

MACHO_COMMAND_HEADER_SIZE = 8
ELF_PROGRAM_HEADER_SIZE = 56
ELF_DYNAMIC_SEGMENT = 2
ELF_STRING_TABLE = 5
PE_DELAY_DIRECTORY = 13
PE_64BIT_MAGIC = 0x20B


class BinaryFormat(StrEnum):
    ELF = "ELF"
    MACHO = "Mach-O"
    PE = "PE"


@dataclass(frozen=True, slots=True)
class NativeImports:
    format: BinaryFormat
    libraries: tuple[str, ...]


def integer(data: bytes, offset: int, size: int) -> int:
    if offset < 0 or offset + size > len(data):
        raise ValueError("Truncated native dependency table")
    return int.from_bytes(data[offset : offset + size], "little")


def string(data: bytes, offset: int) -> str:
    if offset < 0 or offset >= len(data):
        raise ValueError("Invalid native string offset")
    end = data.find(b"\0", offset)
    if end < 0:
        raise ValueError("Unterminated native library name")
    return data[offset:end].decode("ascii", errors="strict")


def macho(data: bytes) -> NativeImports:
    count = integer(data, 16, 4)
    offset = 32
    names: list[str] = []
    for _ in range(count):
        command = integer(data, offset, 4)
        size = integer(data, offset + 4, 4)
        if size < MACHO_COMMAND_HEADER_SIZE or offset + size > len(data):
            raise ValueError("Invalid Mach-O load command")
        if command in {0xC, 0x80000018, 0x8000001F, 0x80000023}:
            name_offset = integer(data, offset + 8, 4)
            if name_offset >= size:
                raise ValueError("Invalid Mach-O dylib name")
            names.append(string(data[: offset + size], offset + name_offset))
        offset += size
    return NativeImports(BinaryFormat.MACHO, tuple(sorted(set(names))))


@dataclass(frozen=True, slots=True)
class Segment:
    kind: int
    offset: int
    address: int
    size: int


def elf(data: bytes) -> NativeImports:
    if data[4:6] != b"\x02\x01":
        raise ValueError("Only release-target ELF64 little-endian is supported")
    start = integer(data, 32, 8)
    width = integer(data, 54, 2)
    count = integer(data, 56, 2)
    if width < ELF_PROGRAM_HEADER_SIZE:
        raise ValueError("Invalid ELF program-header width")
    segments = tuple(
        Segment(
            integer(data, start + i * width, 4),
            integer(data, start + i * width + 8, 8),
            integer(data, start + i * width + 16, 8),
            integer(data, start + i * width + 32, 8),
        )
        for i in range(count)
    )
    entries: list[tuple[int, int]] = []
    for segment in segments:
        if segment.kind == ELF_DYNAMIC_SEGMENT:
            for offset in range(segment.offset, segment.offset + segment.size, 16):
                key, value = struct.unpack_from("<QQ", data, offset)
                if key == 0:
                    break
                entries.append((key, value))
    addresses = [value for key, value in entries if key == ELF_STRING_TABLE]
    if len(addresses) != 1:
        raise ValueError("Missing/duplicate ELF dynamic string table")
    address = addresses[0]
    matching = [s for s in segments if s.kind == 1 and s.address <= address < s.address + s.size]
    if len(matching) != 1:
        raise ValueError("Unmapped ELF dynamic string table")
    table = matching[0].offset + address - matching[0].address
    names = tuple(sorted({string(data, table + value) for key, value in entries if key == 1}))
    return NativeImports(BinaryFormat.ELF, names)


@dataclass(frozen=True, slots=True)
class Section:
    address: int
    offset: int
    size: int


def pe_address(sections: tuple[Section, ...], address: int) -> int:
    for section in sections:
        if section.address <= address < section.address + section.size:
            return section.offset + address - section.address
    raise ValueError("Unmapped PE import address")


def pe_imports(data: bytes, optional: int, sections: tuple[Section, ...]) -> tuple[str, ...]:
    names: list[str] = []
    for directory, width, name_offset in ((1, 20, 12), (13, 32, 4)):
        address = integer(data, optional + 112 + directory * 8, 4)
        size = integer(data, optional + 116 + directory * 8, 4)
        if not address:
            continue
        start = pe_address(sections, address)
        for offset in range(start, start + size, width):
            if not any(data[offset : offset + width]):
                break
            if directory == PE_DELAY_DIRECTORY and integer(data, offset, 4) != 1:
                raise ValueError("Unsupported absolute PE delayed import")
            name = integer(data, offset + name_offset, 4)
            names.append(string(data, pe_address(sections, name)))
    return tuple(sorted(set(names)))


def pe(data: bytes) -> NativeImports:
    header = integer(data, 0x3C, 4)
    if data[header : header + 4] != b"PE\0\0":
        raise ValueError("Invalid PE signature")
    optional = header + 24
    if integer(data, optional, 2) != PE_64BIT_MAGIC:
        raise ValueError("Only release-target PE32+ is supported")
    count = integer(data, header + 6, 2)
    start = optional + integer(data, header + 20, 2)
    sections = tuple(
        Section(
            integer(data, start + i * 40 + 12, 4),
            integer(data, start + i * 40 + 20, 4),
            integer(data, start + i * 40 + 16, 4),
        )
        for i in range(count)
    )
    return NativeImports(BinaryFormat.PE, pe_imports(data, optional, sections))


def inspect_native(data: bytes) -> NativeImports:
    if data.startswith(b"\x7fELF"):
        return elf(data)
    if data.startswith(b"\xcf\xfa\xed\xfe"):
        return macho(data)
    if data.startswith(b"MZ"):
        return pe(data)
    raise ValueError("Unrecognized release extension format")
