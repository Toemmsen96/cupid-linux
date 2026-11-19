#!/usr/bin/env python3
"""Bring up the main camera's ROHM BU24618 OIS controller from userspace, to
test whether an initialised OIS fixes the streaks of the IMX766 image.

The BU24618 runs from RAM: until the host loads its program, coefficients and
memory image and signals the end of the download, its servo is off and the lens
floats. Sequence after Xiaomi's BU24618 driver (MediaTek tree) and ROHM's BU24
register header: download start (0xF010), the three images, checksum (0xF008),
calibration from the module EEPROM to 0x1DC0, download complete (0xF006),
status (0x6024 == 1), then servo on (0x6020 = 1, lens held centred) or OIS on.

Run as root while the main camera streams (it powers the controller):
  sudo python3 ois-bu24618.py FWDIR [--mode centre|ois|off] [--bus 5]
FWDIR holds cupid_imx766_bu24618_ois.{prog,coeff,mem} from the stock vendor
firmware. Registers have 16-bit addresses; the Qualcomm CCI takes at most 11
bytes per write message and 12 per read.
"""
import argparse
import ctypes
import fcntl
import os
import time

I2C_RDWR = 0x0707
I2C_M_RD = 0x0001
OIS = 0x3e
EEPROM = 0x50
# Download addresses: the stock module's cam_ois_opcode {prog, coeff, peripheral,
# memory} = {0x0000, 0x1B40, 0x1DC0, 0x4000}; the calibration goes to "peripheral".
# The checksum (0xF008) must read 0x6AE02, the byte sum of the three files.
PROG_ADDR, COEFF_ADDR, MEM_ADDR = 0x0000, 0x1B40, 0x4000
CAL_EEPROM, CAL_OIS, CAL_LEN = 0x20F2, 0x1DC0, 38
WRITE_MAX = 11 - 2   # data bytes per write after the 16-bit address


class Msg(ctypes.Structure):
    _fields_ = [("addr", ctypes.c_uint16), ("flags", ctypes.c_uint16),
                ("len", ctypes.c_uint16), ("buf", ctypes.POINTER(ctypes.c_uint8))]


class RdwrData(ctypes.Structure):
    _fields_ = [("msgs", ctypes.POINTER(Msg)), ("nmsgs", ctypes.c_uint32)]


class Bus:
    def __init__(self, n):
        self.f = open("/dev/i2c-%d" % n, "rb+", buffering=0)

    def xfer(self, *msgs):
        arr = (Msg * len(msgs))(*msgs)
        fcntl.ioctl(self.f.fileno(), I2C_RDWR, RdwrData(arr, len(msgs)))

    def write(self, dev, reg, data):
        for off in range(0, len(data), WRITE_MAX):
            part = data[off:off + WRITE_MAX]
            a = reg + off
            buf = (ctypes.c_uint8 * (2 + len(part)))(a >> 8, a & 0xff, *part)
            self.xfer(Msg(dev, 0, len(buf), buf))

    def read(self, dev, reg, n):
        out = b""
        while len(out) < n:
            k = min(8, n - len(out))
            a = reg + len(out)
            w = (ctypes.c_uint8 * 2)(a >> 8, a & 0xff)
            r = (ctypes.c_uint8 * k)()
            self.xfer(Msg(dev, 0, 2, w), Msg(dev, I2C_M_RD, k, r))
            out += bytes(r)
        return out


def wait_ready(bus, what, timeout=0.5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if bus.read(OIS, 0x6024, 1)[0] == 1:
            return True
        time.sleep(0.005)
    print("  %s: not ready (0x6024 = 0x%02x)" % (what, bus.read(OIS, 0x6024, 1)[0]))
    return False


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("fwdir")
    p.add_argument("--mode", choices=("centre", "ois", "off"), default="centre")
    p.add_argument("--bus", type=int, default=5)
    p.add_argument("--no-cal", action="store_true", help="skip the EEPROM calibration")
    p.add_argument("--skip-download", action="store_true",
                   help="the controller already runs its firmware: only switch the mode")
    args = p.parse_args()
    bus = Bus(args.bus)

    if args.mode == "off":
        bus.write(OIS, 0x6020, b"\x00")
        status(bus, "servo off")
        return
    if args.skip_download:
        apply_mode(bus, args.mode)
        return
    if download(bus, args):
        return 1
    apply_mode(bus, args.mode)


def download(bus, args):
    """Firmware, calibration and the stock post-init; non-zero on failure."""
    name = os.path.join(args.fwdir, "cupid_imx766_bu24618_ois")
    images = [(PROG_ADDR, open(name + ".prog", "rb").read()),
              (COEFF_ADDR, open(name + ".coeff", "rb").read()),
              (MEM_ADDR, open(name + ".mem", "rb").read())]
    print("status before: 0x6024 = 0x%02x, 0x6020 = 0x%02x"
          % (bus.read(OIS, 0x6024, 1)[0], bus.read(OIS, 0x6020, 1)[0]))

    t = time.monotonic()
    bus.write(OIS, 0xF010, b"\x00")          # download start
    time.sleep(0.001)
    total = 0
    for addr, data in images:
        bus.write(OIS, addr, data)
        total += sum(data)
        print("  wrote %d bytes at 0x%04x" % (len(data), addr))
    chk = int.from_bytes(bus.read(OIS, 0xF008, 4), "big")
    print("checksum 0x%08x, expected 0x%08x: %s (%.2f s)"
          % (chk, total & 0xffffffff, "ok" if chk == total & 0xffffffff else "MISMATCH",
             time.monotonic() - t))
    if chk != total & 0xffffffff:
        return 1

    if not args.no_cal:
        cal = bus.read(EEPROM, CAL_EEPROM, CAL_LEN)
        print("calibration from EEPROM 0x%04x: %s" % (CAL_EEPROM, cal.hex()))
        bus.write(OIS, CAL_OIS, cal)

    bus.write(OIS, 0xF006, b"\x00")          # download complete
    time.sleep(0.02)
    if not wait_ready(bus, "after download"):
        return 1
    print("revision 0x6010 = %s" % bus.read(OIS, 0x6010, 4).hex())
    run(bus, POST_INIT)
    status(bus, "after post-init")


# The stock CamX module's oisPostInitSettings
# (com.qti.sensormodule.cupid_semco_imx766_wide.bin): first table after the
# download (servo and gyro set-up), then OIS on, or centring
POST_INIT = ((0x614F, 0x01), (0x617C, 0x00), (0x6020, 0x01), (0x617D, 0x0C), (0x617E, 0x48),
             (0x6023, 0x02), (0x602C, 0x70), (0x602D, 0x21), (0x602C, 0x71), (0x602D, 0x00),
             (0x602C, 0x72), (0x602D, 0x00), (0x602A, 0x00), (0x6023, 0x00))
OIS_ON = ((0x6021, 0x61), (0x618E, 0x38), (0x6025, 0x90), (0x6020, 0x02), (0x6157, 0x09))
CENTRE = ((0x6020, 0x01),)


def run(bus, table):
    for reg, val in table:
        bus.write(OIS, reg, bytes([val]))
        # stock polls 0x6024 after each step except inside the gyro pairs
        if reg not in (0x602C,):
            wait_ready(bus, "0x%04x" % reg)


def status(bus, what):
    regs = (0x6020, 0x6021, 0x6023, 0x6024, 0x6025, 0x614F, 0x617C, 0x617D, 0x617E)
    print("%s: %s" % (what, " ".join("%04x=%02x" % (r, bus.read(OIS, r, 1)[0]) for r in regs)))


def apply_mode(bus, mode):
    run(bus, OIS_ON if mode == "ois" else CENTRE)
    status(bus, "mode %s" % mode)


if __name__ == "__main__":
    raise SystemExit(main())
