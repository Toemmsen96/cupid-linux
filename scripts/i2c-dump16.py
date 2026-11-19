#!/usr/bin/env python3
"""Dump a device with 16-bit register addresses (camera module EEPROMs) over
I2C_RDWR in short reads, as the Qualcomm CCI allows at most 12 bytes per read.

  sudo python3 i2c-dump16.py BUS ADDR SIZE OUT [CHUNK]
  e.g. sudo python3 i2c-dump16.py 5 0x50 16384 /tmp/eeprom.bin

The main camera's devices only answer while the camera is powered (streaming).
"""
import ctypes
import fcntl
import sys

I2C_RDWR = 0x0707
I2C_M_RD = 0x0001


class Msg(ctypes.Structure):
    _fields_ = [("addr", ctypes.c_uint16), ("flags", ctypes.c_uint16),
                ("len", ctypes.c_uint16), ("buf", ctypes.POINTER(ctypes.c_uint8))]


class RdwrData(ctypes.Structure):
    _fields_ = [("msgs", ctypes.POINTER(Msg)), ("nmsgs", ctypes.c_uint32)]


def read16(fd, addr, reg, n):
    wbuf = (ctypes.c_uint8 * 2)(reg >> 8, reg & 0xff)
    rbuf = (ctypes.c_uint8 * n)()
    msgs = (Msg * 2)(Msg(addr, 0, 2, wbuf), Msg(addr, I2C_M_RD, n, rbuf))
    fcntl.ioctl(fd, I2C_RDWR, RdwrData(msgs, 2))
    return bytes(rbuf)


def main():
    bus, addr, size, out = int(sys.argv[1]), int(sys.argv[2], 0), int(sys.argv[3], 0), sys.argv[4]
    chunk = int(sys.argv[5]) if len(sys.argv) > 5 else 8
    data = bytearray()
    with open("/dev/i2c-%d" % bus, "rb+", buffering=0) as f:
        for reg in range(0, size, chunk):
            data += read16(f.fileno(), addr, reg, min(chunk, size - reg))
    open(out, "wb").write(data)
    print("%s: %d bytes from %d-%04x" % (out, len(data), bus, addr))


if __name__ == "__main__":
    main()
