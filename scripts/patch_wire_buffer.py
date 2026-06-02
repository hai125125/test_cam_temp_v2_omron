from pathlib import Path


def patch_wire_header():
    wire_h = (
        Path.home()
        / ".platformio"
        / "packages"
        / "framework-arduino-avr"
        / "libraries"
        / "Wire"
        / "src"
        / "Wire.h"
    )
    if not wire_h.exists():
        print(f"[patch_wire_buffer] Wire.h not found: {wire_h}")
        return

    text = wire_h.read_text(encoding="utf-8")
    old = "#define BUFFER_LENGTH 32"
    new = "#ifndef BUFFER_LENGTH\n#define BUFFER_LENGTH 32\n#endif"
    if old in text:
        wire_h.write_text(text.replace(old, new), encoding="utf-8")
        print("[patch_wire_buffer] Patched Wire.h BUFFER_LENGTH override support")
    elif new in text:
        print("[patch_wire_buffer] Wire.h already patchable")
    else:
        print("[patch_wire_buffer] Wire.h BUFFER_LENGTH pattern not recognized")


patch_wire_header()


def patch_softwarewire_header():
    candidates = list(Path.cwd().glob(".pio/libdeps/*/SoftwareWire/SoftwareWire.h"))
    if not candidates:
        print("[patch_wire_buffer] SoftwareWire.h not found under .pio/libdeps")
        return

    old = "#define SOFTWAREWIRE_BUFSIZE 32"
    new = "#ifndef SOFTWAREWIRE_BUFSIZE\n#define SOFTWAREWIRE_BUFSIZE 32\n#endif"
    for header in candidates:
        text = header.read_text(encoding="utf-8")
        if old in text:
            header.write_text(text.replace(old, new), encoding="utf-8")
            print(f"[patch_wire_buffer] Patched {header} SOFTWAREWIRE_BUFSIZE override support")
        elif new in text:
            print(f"[patch_wire_buffer] {header} already patchable")
        else:
            print(f"[patch_wire_buffer] {header} SOFTWAREWIRE_BUFSIZE pattern not recognized")


patch_softwarewire_header()
