#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Select the modem carrier configuration (MCFG) for the inserted SIM.

The cupid modem (SM8450) loads the 305 carrier configurations listed in
modem_pr/mcfg/configs/mcfg_sw/oem_sw.txt at every boot but keeps only the
last 25 (all South-East Asian), and on Linux nothing selects one, so no
carrier configuration is active and the modem's IMS stack never starts. On
LTE-only networks that means no voice: outgoing calls hang in "dialing" and
incoming calls go to voicemail. SMS works regardless.

This picks the configuration for the inserted SIM the way the modem's own
automatic selection does: from the network codes (MCC/MNC) and SIM card
number prefixes (IIN) each configuration lists in its trailer. It loads it
into the modem if it is missing, then selects and activates it (the modem
restarts once). It does nothing when the right configuration is already
active.

"stop" (run at shutdown) deactivates it again: with a VoLTE configuration
already active at power-on, the modem's start-up stalls ("DOG detects
stalled initialization") until its watchdog has reset it three times, after
which it comes up without any configuration. Activated after the modem is
up, it works. A boot after an unclean shutdown goes through those resets
and then gets the configuration activated here as usual.

/etc/cupid-modem-config can override the choice: a path relative to
modem_pr/mcfg/configs/mcfg_sw/generic (e.g. EU/Vodafone/VoLTE/Germany),
or "none" to leave the modem alone.
"""
import hashlib, os, select, socket, struct, subprocess, sys, time

BASE = "/lib/firmware/qcom/sm8450/cupid/modem_pr/mcfg/configs/mcfg_sw/generic"
# Configurations for test networks or without IMS, never picked
# automatically.
SKIP = ("/Lab", "/Test", "Non_VoLTE", "IMSless", "CDMAless")
# The modem keeps configurations under their SHA-1 from its own loading
# pass and refuses a second load under that ID, so ours get a suffix.
ID_SUFFIX = b"-cupid"

AF_QIPCRTR = 42
QRTR_PORT_CTRL = 0xFFFFFFFE
PDC = 0x24
SOFTWARE = 1


def log(msg):
    print(msg, flush=True)


def sim_codes(timeout=480):
    """(operator code, ICCID) of the SIM, once ModemManager knows them."""
    end = time.time() + timeout
    while time.time() < end:
        out = subprocess.run(["mmcli", "-i", "any", "-K"], capture_output=True, text=True).stdout
        props = {}
        for line in out.splitlines():
            key, _, value = line.partition(":")
            props[key.strip()] = value.strip()
        code = props.get("sim.properties.operator-code", "--")
        if code and code != "--":
            iccid = props.get("sim.properties.iccid", "--")
            return code, iccid if iccid != "--" else ""
        time.sleep(5)
    return None, None


def trailer(path):
    """MCFG trailer of a configuration: ([(mcc, mnc)], [iin])."""
    with open(path, "rb") as f:
        d = f.read()
    i = d.rfind(b"MCFG_TRL")
    if i < 0:
        return [], []
    p, tlv = i + 13, {}
    while p + 3 <= len(d):
        t, n = struct.unpack_from("<BH", d, p)
        tlv[t] = d[p + 3:p + 3 + n]
        p += 3 + n
    def entries(v, fmt):
        if len(v) < 2:
            return []
        size = struct.calcsize(fmt)
        return [struct.unpack_from(fmt, v, 2 + size * k) for k in range(v[1])
                if 2 + size * (k + 1) <= len(v)]
    return entries(tlv.get(6, b""), "<HH"), [x[0] for x in entries(tlv.get(4, b""), "<I")]


def pick(code, iccid):
    """The configuration for a SIM, relative to BASE, or None."""
    mcc, mnc = int(code[:3]), int(code[3:])
    found = []
    for root, _dirs, files in os.walk(BASE):
        rel = os.path.relpath(root, BASE)
        if "mcfg_sw.mbn" not in files or any(s in "/" + rel for s in SKIP):
            continue
        codes, iins = trailer(os.path.join(root, "mcfg_sw.mbn"))
        if (mcc, mnc) in codes:
            iin_match = any(iccid.startswith(str(x)) for x in iins)
            found.append((not iin_match, "VoLTE" not in rel, "Commercial" not in rel, rel))
    return min(found)[3] if found else None


class Pdc:
    def __init__(self):
        self.s = socket.socket(AF_QIPCRTR, socket.SOCK_DGRAM)
        node = self.s.getsockname()[0]
        self.s.sendto(struct.pack("<6I", 10, PDC, 0, 0, 0, 0), (node, QRTR_PORT_CTRL))
        self.svc = None
        end = time.time() + 5
        while time.time() < end and not self.svc:
            if not select.select([self.s], [], [], 1)[0]:
                continue
            d, _ = self.s.recvfrom(4096)
            cmd, svc, _inst, n, p = struct.unpack_from("<5I", d)
            if cmd == 4 and svc == PDC:
                self.svc = (n, p)
        if not self.svc:
            raise RuntimeError("PDC service not found")
        self.txn = 1

    @staticmethod
    def tlvs(b):
        i, out = 0, {}
        while i + 3 <= len(b):
            t, l = struct.unpack_from("<BH", b, i)
            out[t] = b[i + 3:i + 3 + l]
            i += 3 + l
        return out

    def call(self, msg, tlvs, timeout=15):
        """Send a request; return (response error, indication TLVs or None)."""
        tlvs = list(tlvs) + [(0x10, struct.pack("<I", 0xC0FE))]
        body = b"".join(struct.pack("<BH", t, len(v)) + v for t, v in tlvs)
        self.txn = self.txn % 0xFFFF + 1
        self.s.sendto(struct.pack("<BHHH", 0, self.txn, msg, len(body)) + body, self.svc)
        err, end = None, time.time() + timeout
        while time.time() < end:
            if not select.select([self.s], [], [], 1)[0]:
                continue
            d, _ = self.s.recvfrom(65536)
            kind, txn, mid, _ = struct.unpack_from("<BHHH", d)
            if mid != msg:
                continue
            t = self.tlvs(d[7:])
            if kind == 2 and txn == self.txn:
                err = struct.unpack_from("<HH", t.get(2, b"\0\0\0\0"))[1]
                if err:
                    return err, None
            elif kind == 4 and err == 0:
                return 0, t
        return err if err is not None else -1, None

    @staticmethod
    def ind_error(ind):
        return struct.unpack_from("<H", ind[1])[0] if ind and 1 in ind else -1

    def active_id(self):
        err, ind = self.call(0x22, [(0x01, struct.pack("<I", SOFTWARE))])
        if err or not ind or self.ind_error(ind) or 0x11 not in ind:
            return None
        return ind[0x11][1:]

    def select(self, cid):
        err, ind = self.call(0x23, [(0x01, struct.pack("<IB", SOFTWARE, len(cid)) + cid)])
        return err == 0 and self.ind_error(ind) == 0

    def load(self, data, cid):
        off = 0
        while off < len(data):
            chunk = data[off:off + 0x400]
            v = (struct.pack("<IB", SOFTWARE, len(cid)) + cid +
                 struct.pack("<IH", len(data), len(chunk)) + chunk)
            err, ind = self.call(0x26, [(0x01, v)])
            if err or self.ind_error(ind):
                raise RuntimeError("load failed at %d: %s/%s" % (off, err, self.ind_error(ind)))
            off += len(chunk)
            if 0x12 in ind and struct.unpack("<I", ind[0x12])[0] == 0:
                break

    def deactivate(self):
        err, ind = self.call(0x2B, [(0x01, struct.pack("<I", SOFTWARE))], timeout=30)
        return err == 0 and self.ind_error(ind) == 0

    def activate(self):
        err, ind = self.call(0x27, [(0x01, struct.pack("<I", SOFTWARE))], timeout=30)
        return err == 0 and self.ind_error(ind) == 0


def stop():
    pdc = Pdc()
    cid = pdc.active_id()
    if not cid or not cid.endswith(ID_SUFFIX):
        log("no configuration of ours active")
        return 0
    log("deactivated" if pdc.deactivate() else "could not deactivate")
    return 0


def main():
    if sys.argv[1:] == ["stop"]:
        return stop()
    choice = None
    try:
        with open("/etc/cupid-modem-config") as f:
            choice = f.read().strip() or None
    except FileNotFoundError:
        pass
    if choice == "none":
        log("disabled in /etc/cupid-modem-config")
        return 0
    if not choice:
        code, iccid = sim_codes()
        if not code:
            log("no SIM operator code, nothing to do")
            return 0
        choice = pick(code, iccid)
        if not choice:
            log("no carrier configuration lists network %s" % code)
            return 0
    path = os.path.join(BASE, choice, "mcfg_sw.mbn")
    data = open(path, "rb").read()
    cid = hashlib.sha1(data).digest() + ID_SUFFIX

    pdc = Pdc()
    if pdc.active_id() == cid:
        log("%s already active" % choice)
        return 0
    if not pdc.select(cid):
        log("loading %s (%d bytes)" % (choice, len(data)))
        pdc.load(data, cid)
        if not pdc.select(cid):
            log("could not select %s" % choice)
            return 1
    if not pdc.activate():
        log("could not activate %s" % choice)
        return 1
    log("activated %s; the modem restarts" % choice)
    return 0


if __name__ == "__main__":
    sys.exit(main())
