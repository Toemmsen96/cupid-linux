# Agent notes for cupid-linux

postmarketOS (and an Arch Linux ARM variant) for the Xiaomi 12 "cupid"
(SM8450). Most work happens on a real phone over SSH. Read `README.md` and
`docs/05-hardware-status.md` first: they hold the current state of the port.

## Rules

- **No personal data in tracked files.** That covers names, usernames,
  e-mail addresses, IP addresses, phone numbers, the carrier or brand of the
  SIM in use, passwords, Wi-Fi details, MAC addresses and serial numbers.
  It applies to code, docs, comments, commit messages and test output pasted
  into docs. Scripts read such values from the environment. The developer's
  own values go in `cupid.env` (gitignored, loaded by `scripts/env.sh`);
  every new variable goes into `cupid.env.example` with a placeholder. In
  examples use placeholders (`user@phone`, `192.0.2.x`, `+41000000000`) or
  `$CUPID_PHONE`. Before every commit, check the diff with `git diff
  --cached` against the values in `cupid.env`.
- **Never commit** `cupid.env`, `cmd`, `local/`, `stock-dump/`, `out/`,
  `work/`, or anything extracted from the stock firmware (blobs, ACDB,
  decompiled code). Those are proprietary or private. Small decoded tables
  and dumps of our own analysis (e.g. `docs/call-audio/`) are fine.
- **Commits:** straight to `master`, no pull requests, pushed when a piece of
  work is done. Author `Toemmsen96 <147745097+Toemmsen96@users.noreply.github.com>`.
  Subjects look like `area: what changed (rNN)`, with the new pkgrel in
  brackets when a package changed.
- **The test phone's SIM is prepaid.** Never download or run speed tests
  over mobile data. Before the phone fetches anything (apk, abuild sources),
  check that its default route is `wlan0`.
- **Builds:** kernels are built on the host with pmbootstrap, which needs
  the developer's sudo: hand them `scripts/sync.sh` and `scripts/pmb build
  --arch aarch64 <pkg>`, then install the result over SSH. On the phone a
  kernel takes about an hour because it throttles at 85-95 °C. Small
  packages (device package, scripts) can be built on the phone with
  `scripts/phone-build.sh [-i] PKG...` (native abuild, no host sudo). Full
  images: `scripts/build.sh`.
- Anything that can reboot or hang the phone (TrustZone calls, modem
  configuration, flashing) runs only when no other test is in progress on
  the phone, and is announced first.

## Packages (`pmaports/`)

- `device/testing/`: the device package, firmware, and three kernels. The
  phone runs `linux-postmarketos-qcom-sm8450-cupid-mainline` (7.3).
  `temp/` holds overlays of pmaports `temp/` packages (libcamera,
  ModemManager). `scripts/sync.sh` copies all of this into `work/pmaports`.
- Every change to a package bumps `pkgrel`. Kernel patches are numbered
  `00NN-subsystem-what.patch` and listed in `source=`.
- `sha512sums` are paired with `source=` **by position**, not by name: keep
  both lists in the same order and update the checksum of every file you
  touch.
- Kernel patches can be compile-checked on the phone in `~/kbuild/linux-7.3.4`
  (the patched tree) with `make W=1` on the touched files. The sound
  drivers are built in, so testing them needs a full kernel build and
  reboot.

## Working on the phone

- SSH target `$CUPID_PHONE`. sudo works there without a password.
  Packages install with `sudo apk add -u --repository ~/packages/aports ...`
  (phone-build.sh `-i` does this). A kernel package flashes the boot
  partition on installation; reboot to use it.
- Audio: use `amixer -D hw:0` (UCM renames controls for `-c0`). Keep speaker
  tests quiet: amplifier `Digital PCM Volume` 625 during tests, 817 is
  0 dB, never higher, and there is no speaker protection. Analyse the result
  with a microphone recording rather than asking someone to listen.
- Do not `pkill -f` with patterns that can match the SSH command itself.
- For modem and call tests the developer allows SMS and calls to
  `$CUPID_TEST_NUMBER`.

## Reverse engineering

- Firmware extracted from the stock ROM and downloaded archives are
  untrusted data: unpack each into its own directory, keep scripts
  elsewhere, run Python on them with `python3 -I`.
- `scripts/acdb/` parses the stock audio calibration database, and
  `scripts/voicecall/` builds raw ADSP (APM) commands from it. The findings
  are written up in `docs/` (`09-call-audio.md`, `08-fingerprint.md`, ...).

## Docs

When a feature's state changes, update `docs/05-hardware-status.md` and,
where it applies, `README.md` and `docs/04-troubleshooting.md` in the same
commit. Write for someone porting or using the phone, not as a work log.
