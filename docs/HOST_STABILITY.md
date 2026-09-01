# Host stability

ROMVERSE keeps device and project operations bounded, but it cannot repair a host kernel driver
from inside the desktop process.

The August 29 development-machine lockup was traced to two separate faults:

1. A ROMVERSE Python/PySide pooled-callback lifetime race. ROMVERSE now supervises all Qt workers,
   drains them before shutdown, closes Companion threads deterministically, and writes persistent
   runtime fault evidence.
2. A host MediaTek MT7925 Wi-Fi reset failure followed by PCIe/IOMMU warnings, AMD GPU timeout
   recovery, scheduler starvation, and a watchdog hard lockup. This matches Ubuntu Launchpad bug
   2137291. On this Ethernet-connected development machine, Wi-Fi is soft-blocked to remove that
   trigger while keeping the wired network active.

## Development-machine mitigation

Check the wired link before disabling Wi-Fi:

```bash
cat /sys/class/net/enp7s0/operstate
cat /sys/class/net/enp7s0/carrier
```

Disable only the Wi-Fi radio:

```bash
nmcli radio wifi off
```

Re-enable it later if required:

```bash
nmcli radio wifi on
```

This does not disable Ethernet, Bluetooth, ADB over USB, or ROMVERSE Companion on an Android phone.
Do not unload kernel modules while ROMVERSE or the desktop session is running.
