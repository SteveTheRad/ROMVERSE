#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
IMAGES="$ROOT/images"
WIPE=0
ASSUME_YES=0
NO_REBOOT=0

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

usage() {
    cat <<EOF
Usage: $0 [--wipe] [--yes] [--no-reboot]
  --wipe       Erase metadata and userdata for a clean installation (recommended).
  --yes        Skip the POPSICLE confirmation prompt.
  --no-reboot  Stay in bootloader fastboot after flashing.
EOF
}

for arg in "$@"; do
    case "$arg" in
        --wipe) WIPE=1 ;;
        --yes) ASSUME_YES=1 ;;
        --no-reboot) NO_REBOOT=1 ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; die "Unknown option: $arg" ;;
    esac
done

for tool in fastboot sha256sum awk grep; do
    command -v "$tool" >/dev/null 2>&1 || die "Required tool is missing: $tool"
done

cd "$ROOT"
echo "Verifying every package file before flashing..."
./verify.sh

wait_fastboot() {
    local tries=0
    while [ "$tries" -lt 120 ]; do
        if fastboot devices 2>/dev/null | awk 'NF >= 2 && $2 == "fastboot" {found=1} END {exit !found}'; then
            return 0
        fi
        tries=$((tries + 1))
        sleep 1
    done
    die "Timed out waiting for a fastboot device. Check the cable and USB port."
}

mapfile -t fastboot_serials < <(fastboot devices 2>/dev/null | awk 'NF >= 2 && $2 == "fastboot" {print $1}')
if [ "${#fastboot_serials[@]}" -eq 0 ]; then
    command -v adb >/dev/null 2>&1 || die "No fastboot device found, and adb is unavailable."
    mapfile -t adb_serials < <(adb devices 2>/dev/null | awk 'NR > 1 && $2 == "device" {print $1}')
    [ "${#adb_serials[@]}" -eq 1 ] || die "Connect exactly one authorised popsicle device in Android or bootloader fastboot."
    adb_serial="${adb_serials[0]}"
    device_name="$(adb -s "$adb_serial" shell getprop ro.product.device 2>/dev/null | tr -d '\r')"
    [ "$device_name" = "popsicle" ] || die "ADB reports '$device_name', not popsicle."
    echo "ADB confirmed Xiaomi popsicle; rebooting it to bootloader fastboot..."
    adb -s "$adb_serial" reboot bootloader
    wait_fastboot
    mapfile -t fastboot_serials < <(fastboot devices 2>/dev/null | awk 'NF >= 2 && $2 == "fastboot" {print $1}')
fi

[ "${#fastboot_serials[@]}" -eq 1 ] || die "Connect exactly one fastboot device."
SERIAL="${fastboot_serials[0]}"
FB=(fastboot -s "$SERIAL")

mode_info="$("${FB[@]}" getvar is-userspace 2>&1 || true)"
if grep -qi 'is-userspace:[[:space:]]*yes' <<<"$mode_info"; then
    echo "Leaving fastbootd for bootloader fastboot..."
    "${FB[@]}" reboot bootloader
    wait_fastboot
fi

unlock_info="$("${FB[@]}" oem device-info 2>&1 || true)"
grep -Fq 'Device unlocked: true' <<<"$unlock_info" || die "The bootloader is not reported unlocked."
grep -Fq 'Device critical unlocked: true' <<<"$unlock_info" || die "Critical partitions are not reported unlocked."

product_info="$("${FB[@]}" getvar product 2>&1 || true)"
if ! grep -qi 'popsicle' <<<"$product_info"; then
    super_info="$("${FB[@]}" getvar partition-size:super 2>&1 || true)"
    grep -qi '0x320000000' <<<"$super_info" || {
        printf '%s\n%s\n' "$product_info" "$super_info" >&2
        die "The phone did not identify as popsicle and its super size is unexpected."
    }
    echo "WARNING: this Xiaomi bootloader omits getvar:product; its expected popsicle super size was confirmed."
fi

cat <<EOF

Target: Xiaomi 17 Pro Max (popsicle), slot A
Build: OS4.0.0.23.XPBCNXM / Android 17
Includes: proven Android Auto role fix, Gboard, Theme Manager/Store, App Vault, Chrome
Removes: Child Mode, Mi Browser, CarWith, Sogou/Baidu/iFlytek keyboards
This installer never relocks the bootloader and never writes slot B.
EOF

if [ "$WIPE" -eq 1 ]; then
    echo "WARNING: --wipe will erase all apps, accounts, photos and other userdata."
else
    echo "Userdata will be retained. Use --wipe for the cleanest and most reliable first boot."
fi

if [ "$ASSUME_YES" -ne 1 ]; then
    read -r -p "Type POPSICLE to begin flashing: " answer
    [ "$answer" = "POPSICLE" ] || die "Cancelled."
fi

"${FB[@]}" set_active a

physical_partitions=(
    abl aop aop_config bluetooth boot cpucp cpucp_dtb dcp devcfg dsp dtbo
    featenabler hyp hyp_ac_config idmanager imagefv init_boot keymaster modem
    modemfirmware multiimgqti pdp pdp_cdb pvmfw qtvm_dtbo qupfw recovery
    secretkeeper shrm soccp soccp_dcd soccp_debug spuservice tme_config tme_fw
    tme_seq_patch tz tz_ac_config tz_qti_config uefi uefisecapp vendor_boot
    vm-bootsys xbl xbl_ac_config xbl_config xbl_ramdump
)

for partition in "${physical_partitions[@]}"; do
    echo "Flashing ${partition}_a..."
    "${FB[@]}" flash "${partition}_a" "$IMAGES/${partition}.img"
done

echo "Flashing complete OS4.0.0.23 dynamic-partition container..."
"${FB[@]}" -S 700M flash super "$IMAGES/super.img"

echo "Flashing matching descriptor-preserving AVB metadata..."
"${FB[@]}" flash vbmeta_system_a "$IMAGES/vbmeta_system.img"
"${FB[@]}" flash vbmeta_a "$IMAGES/vbmeta.img"

if [ "$WIPE" -eq 1 ]; then
    "${FB[@]}" erase metadata
    "${FB[@]}" erase userdata
fi

"${FB[@]}" set_active a
echo "Flash completed. The first boot can take 10-15 minutes."
if [ "$NO_REBOOT" -eq 1 ]; then
    echo "Remaining in bootloader fastboot because --no-reboot was supplied."
else
    "${FB[@]}" reboot
fi

