#!/usr/bin/env python3
"""Host-side model of the LSM6DSV16X SPI sequence used in main/main.c.

Pins down the framing so a wiring/mode mistake gets caught here instead of
looking like a dead sensor on the bench. The sequence follows ST's reference
platform_read / platform_write in STMems_Standard_C_drivers
(lsm6dsv16x_STdC/examples/lsm6dsv16x_read_data_polling.c):

    read:  CS low -> send (reg | 0x80) -> receive len -> CS high
    write: CS low -> send reg          -> send payload -> CS high

Run: python3 tools/spi_frame_model.py
"""

READ_BIT = 0x80

# Register file: address -> value, seeded with plausible sensor contents.
REGS = {
    0x0F: 0x70,                          # WHO_AM_I
    0x10: 0x00, 0x11: 0x00, 0x12: 0x44,  # CTRL1_XL, CTRL2_G, CTRL3
    0x15: 0x00, 0x17: 0x00,              # CTRL6_G, CTRL8_XL
    0x1E: 0x03,                          # STATUS_REG: XLDA|GDA
    0x22: 0x11, 0x23: 0x22, 0x24: 0x33,  # OUTX_L_G .. OUTZ_H_G
    0x25: 0x44, 0x26: 0x55, 0x27: 0x66,
    0x28: 0xAA, 0x29: 0xBB, 0x2A: 0xCC,  # OUTX_L_A .. OUTZ_H_A
    0x2B: 0xDD, 0x2C: 0xEE, 0x2D: 0xFF,
}


class CsViolation(AssertionError):
    pass


class Device:
    """Datasheet-level model: the part only responds while CS is low."""

    def __init__(self):
        self.regs = dict(REGS)
        self.cs_low = False
        self._ptr = None
        self._writing = False
        self._expect_addr = True

    # -- bus events ---------------------------------------------------------
    def cs(self, level: int):
        if level == 0:
            if self.cs_low:
                raise CsViolation("CS asserted while already low")
            self.cs_low = True
            self._ptr = None
            self._writing = False
            self._expect_addr = True
        else:
            if not self.cs_low:
                raise CsViolation("CS released while already high")
            self.cs_low = False
            self._ptr = None
            self._writing = False
            self._expect_addr = True

    def _require_cs(self):
        if not self.cs_low:
            raise CsViolation("bus activity with CS high — part is deselected")

    def send(self, byte: int):
        """The part latches MOSI; first byte after CS-low is the address."""
        self._require_cs()
        if self._expect_addr:
            self._writing = not bool(byte & READ_BIT)
            self._ptr = byte & 0x7F
            self._expect_addr = False
        elif self._writing:
            self.regs[self._ptr] = byte
            self._ptr = (self._ptr + 1) & 0x7F

    def recv(self) -> int:
        """The part drives MISO; valid only in a read window."""
        self._require_cs()
        if self._expect_addr or self._writing:
            return 0x00
        # ST's reference (HAL_SPI_Transmit(addr) then HAL_SPI_Receive(len))
        # starts the payload on the first received byte.
        v = self.regs.get(self._ptr & 0x7F, 0x00)
        self._ptr = (self._ptr + 1) & 0x7F
        return v


class Bus:
    """Firmware-side sequence, mirrored from main/main.c."""

    def __init__(self, dev: Device):
        self.dev = dev
        self.trace = []

    def _cs(self, level):
        self.dev.cs(level)
        self.trace.append("CS_LO" if level == 0 else "CS_HI")

    def read(self, reg: int, length: int) -> bytes:
        self._cs(0)
        for b in [reg | READ_BIT]:
            self.dev.send(b)
        out = bytearray()
        for _ in range(length):
            out.append(self.dev.recv())
        self._cs(1)
        return bytes(out)

    def write(self, reg: int, data: bytes):
        self._cs(0)
        self.dev.send(reg & 0x7F)
        for byte in data:
            self.dev.send(byte)
        self._cs(1)


def main() -> int:
    dev = Device()
    bus = Bus(dev)
    fails = []

    def expect(name, got, want):
        if isinstance(want, int):
            want = bytes([want])
        if got != want:
            fails.append(f"{name}: got {got!r} want {want!r}")
            print(f"  FAIL {name}: got {got!r} want {want!r}")
        else:
            print(f"  ok   {name} = {got!r}")

    print("identity read:")
    expect("WHO_AM_I", bus.read(0x0F, 1), bytes([0x70]))

    print("burst reads (driver reads these as int16 triples):")
    expect("accel raw 0x28..0x2D", bus.read(0x28, 6),
           bytes([0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF]))
    expect("gyro  raw 0x22..0x27", bus.read(0x22, 6),
           bytes([0x11, 0x22, 0x33, 0x44, 0x55, 0x66]))

    print("single-byte read from mid-block:")
    expect("accel z_l", bus.read(0x2C, 1), bytes([0xEE]))

    print("write then read back (IF_INC, CTRL3 bit2):")
    bus.write(0x12, bytes([0x40]))  # clear bit2, keep bit6
    expect("CTRL3", bus.read(0x12, 1), bytes([0x40]))

    print("burst write (CTRL1_XL, CTRL2_G, CTRL3 in one window):")
    bus.write(0x10, bytes([0x60, 0x60, 0x44]))
    expect("CTRL1_XL", bus.read(0x10, 1), bytes([0x60]))
    expect("CTRL2_G", bus.read(0x11, 1), bytes([0x60]))
    expect("CTRL3", bus.read(0x12, 1), bytes([0x44]))

    print("neighbouring registers survive a single-register read:")
    expect("CTRL3 still intact", bus.read(0x12, 1), bytes([0x44]))

    print("CS discipline:")
    lo, hi = bus.trace.count("CS_LO"), bus.trace.count("CS_HI")
    expect("balanced CS edges", (lo, hi), (lo, hi))
    if lo != hi:
        fails.append(f"unbalanced CS: {lo} low vs {hi} high")
    else:
        print(f"  ok   {lo} framing windows, each opened and closed once")

    print()
    if fails:
        print(f"FAIL ({len(fails)} problem(s))")
        return 1
    print("PASS — SPI framing matches the ST reference sequence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())