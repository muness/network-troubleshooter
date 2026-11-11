#!/usr/bin/bash
# Connect the local 217 recovery service to the generic Network Troubleshooter.
set -euo pipefail

if (( EUID == 0 )); then
    echo 'Run as the desktop user.' >&2
    exit 1
fi

test -x "$HOME/.local/bin/network-troubleshooter" || {
    echo 'Install Network Troubleshooter first.' >&2
    exit 1
}
unit=dotfiles-wifi-resume.service
test "$(systemctl show -p LoadState --value "$unit")" = loaded || {
    echo "Install $unit first." >&2
    exit 1
}

mapfile -t adapters < <(LC_ALL=C nmcli -t -f DEVICE,TYPE device status | awk -F: '$2 == "wifi" {print $1}')
if (( ${#adapters[@]} != 1 )); then
    echo 'Expected exactly one Wi-Fi adapter for the guarded recovery service.' >&2
    exit 1
fi
adapter=${adapters[0]}
driver=$(basename "$(readlink -e "/sys/class/net/$adapter/device/driver")")
test "$driver" = brcmfmac || {
    echo "Expected the brcmfmac driver, found $driver." >&2
    exit 1
}
profile=$(nmcli -g connection.uuid connection show id 217)
if [[ ! $profile =~ ^[0-9a-fA-F-]{36}$ ]]; then
    echo 'Expected exactly one saved 217 profile.' >&2
    exit 1
fi
config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/network-troubleshooter"
mkdir -p "$config_dir"
staged=$(mktemp "$config_dir/.recovery.XXXXXX")
jq -n --arg adapter "$adapter" --arg profile "$profile" --arg driver "$driver" --arg unit "$unit" \
    '{adapter:$adapter, profile:$profile, driver:$driver, unit:$unit}' > "$staged"
mv -- "$staged" "$config_dir/recovery.json"

helper="$HOME/.local/libexec/omarchy-captive-portal"
if [[ -x $helper ]]; then
    portal_config="$config_dir/portal.json"
    staged=$(mktemp "$config_dir/.portal.XXXXXX")
    {
        if [[ -f $portal_config ]]; then
            cat "$portal_config"
        else
            printf '{}\n'
        fi
    } | jq -e --arg helper "$helper" '.wifi = [$helper, "--open-device"]' > "$staged"
    mv -- "$staged" "$portal_config"
fi
echo 'Configured 217 recovery and the available Wi-Fi sign-in helper in Network Troubleshooter.'
