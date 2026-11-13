#!/bin/sh
# Copy this phone's sensor registry (factory calibration of the accelerometer,
# gyroscope, magnetometer and light sensors) from the stock persist partition
# to /var/lib/cupid-sensors, where hexagonrpcd serves it to the SLPI
# (firmware-xiaomi-cupid-hexagonfs links sensors/registry there).
# Read-only on persist (debugfs, no mount); runs once, skips when present.
set -e

dest=/var/lib/cupid-sensors
persist=/dev/disk/by-partlabel/persist

if [ -n "$(ls -A "$dest/registry" 2>/dev/null)" ]; then
	exit 0
fi
if [ ! -e "$persist" ]; then
	echo "cupid-sensor-registry: no persist partition, sensors stay off" >&2
	exit 0
fi

mkdir -p "$dest"
debugfs -R "rdump /sensors/registry/registry $dest" "$persist"
debugfs -R "dump /sensors/registry/sns_reg_version $dest/sns_reg_version" "$persist"
chmod -R a+rX "$dest"
echo "cupid-sensor-registry: $(ls "$dest/registry" | wc -l) registry files copied"
