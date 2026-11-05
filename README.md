# Network Troubleshooter for Linux

Diagnose and repair one Wi-Fi or Ethernet connection at a time on **Linux with NetworkManager**. Test a broken Ethernet port while Wi-Fi stays online, or open the app during a total outage to check the local connection. The desktop app and CLI run the same checks.

## Install

Install Python 3, NetworkManager, iproute2, iputils, curl, and systemd journal tools. Add YAD for the desktop UI, `iw` for Wi-Fi link details, and `wl-clipboard` to copy reports on Wayland. Browser sign-in uses Omarchy's portal helper or `xdg-open` from xdg-utils.

Run as your desktop user.

```sh
git clone https://github.com/muness/network-troubleshooter.git
cd network-troubleshooter
python3 install.py
```

Open **Network Troubleshooter** from your app launcher. The installer puts the CLI in `~/.local/bin`.

## Open it from OmaDoctor on Omarchy

Install the version of OmaDoctor in PR #9, then click **Network** next to **Ask AI**. OmaDoctor opens the app locally, before or after a scan, without passing scan data. [OmaDoctor](https://github.com/Davedes83/OmaDoctor) · [Launcher PR #9](https://github.com/Davedes83/OmaDoctor/pull/9)

For a fresh OmaDoctor install, use the PR branch.

```sh
git clone --branch codex/network-troubleshooter-launcher https://github.com/muness/OmaDoctor.git omadoctor-preview
omarchy plugin add "$PWD/omadoctor-preview" --enable
```

The **Network troubleshooter app** setting defaults to `auto` and shows **Network** when this app is installed. Enter another desktop app ID to launch it instead, or clear the setting to hide the button. This app's ID is `io.github.muness.NetworkTroubleshooter.desktop`.

## Diagnose, repair, and share

- **Link and IP address** show whether Ethernet has a link or Wi-Fi joined and whether the adapter has an address beyond link-local. Wi-Fi details show radio state, signal, and cached visibility for the saved network.
- **Route, Gateway, and Ping** check for a route, a reply from the router, and a reply from a public IP. Ping defaults to `1.1.1.1` and `2606:4700:4700::1111`. Change it with **Ping target** or `--ping-target IP`.
- **DNS and Internet** check `archlinux.org`. The app uses systemd-resolved to check DNS on the selected adapter. HTTPS binds to that adapter and falls back to system DNS when per-adapter DNS yields no verified answer. HTTPS can pass even if ping gets no reply.
- **Open sign-in** starts sign-in when NetworkManager detects a captive portal. **Try sign-in** opens the probe page when the check cannot confirm a portal or internet access. Configure a sign-in helper below to bind the browser to the selected adapter.

**Repair connection** retries the saved profile after confirmation. If it fails and that profile is still active, the app disconnects the adapter and retries. It locks the adapter during repair and reruns the checks afterward.

**View report** shows adapter logs and before-and-after repair results. The app saves private reports in `${XDG_STATE_HOME:-$HOME/.local/state}/network-troubleshooter/`. Share **Copy redacted** output, which contains check statuses and repair outcomes.

## CLI

```sh
network-troubleshooter --list-adapters
network-troubleshooter --device enp2s0
network-troubleshooter --device enp2s0 --ping-target 192.168.1.1 --redacted-report
network-troubleshooter --device enp2s0 --repair --report
network-troubleshooter --device wlan0 --sign-in
```

Use the interface name from `--list-adapters`. Repair prompts in a terminal. Add `--yes` for scripts. `--report` prints private evidence. Share the stdout of `--redacted-report`. The private report path goes to stderr.

## Configure a driver recovery service

**Repair connection** retries the saved profile first. If that fails, it can start a systemd recovery service through polkit. The adapter must be disconnected, allow autoconnect, and still use the configured driver. Wi-Fi also requires `iw`, an enabled radio, and exactly one Wi-Fi adapter visible to NetworkManager.

### Broadcom Wi-Fi on Apple Silicon

After suspend on Linux, Broadcom Wi-Fi can get stuck. NetworkManager keeps trying to join, and the journal can show repeated `ASSOC-REJECT status_code=16` or scan errors. A `brcmfmac` reload can restore the connection. The issue has been reported on M1 and M2 models. [BCM4378/BCM4387 resume fix](https://github.com/omacom/omarchy-mac/pull/255) · [M2 Pro report](https://github.com/omacom/omarchy/issues/10857) · [M2 Air report](https://github.com/AsahiLinux/linux/issues/439)

Run `lspci -nnk -d 14e4:` to find the PCI ID and check for `Kernel driver in use: brcmfmac`. The helper supports BCM4378 (`14e4:4425`, found in M1 Macs), BCM4387 (`14e4:4433`, found in M1 Pro and Max Macs), and BCM4388 (`14e4:4434`, found in some M2 and M3 Macs). Use the PCI ID to select the helper. It requires ARM64, NetworkManager, wpa_supplicant, and the loadable `brcmfmac` and `brcmfmac_wcc` kernel modules. [Broadcom chip IDs](https://github.com/omacom/omarchy/issues/7439) · [Asahi Linux driver notes](https://asahilinux.org/2024/01/fedora-asahi-new/)

If joins also fail right after a fresh boot, check whether an older Omarchy installation set `feature_disable=0x82000` in `/etc/modprobe.d/brcmfmac.conf`. That setting caused association failures on BCM4387. Follow the Omarchy cleanup instructions for that case. [Omarchy Apple Silicon troubleshooting](https://omarchylinux.org/hardware/apple-silicon-asahi/) · [BCM4387 report](https://github.com/omacom/omarchy/issues/7439)

If you already have a guarded recovery service for your chip, use its unit name in the next section. The Broadcom helper below detaches NetworkManager and wpa_supplicant before unloading the driver, then restores NetworkManager management. These commands install it and disable its automatic wake hook so it runs on demand from **Repair connection**. [Helper source](https://github.com/muness/dotfiles/tree/53aacf6c6606a88b7d0acaca6a9d5dbf58e2e60e/scripts/linux/wifi-resume)

```sh
git clone https://github.com/muness/dotfiles.git broadcom-recovery &&
  git -C broadcom-recovery checkout 53aacf6c6606a88b7d0acaca6a9d5dbf58e2e60e &&
  pkexec /usr/bin/python3 "$PWD/broadcom-recovery/scripts/linux/wifi-resume/install.py" &&
  pkexec /usr/bin/systemctl disable dotfiles-wifi-resume.service
```

Use `dotfiles-wifi-resume.service` in the next step. The reload briefly removes the Wi-Fi adapter. Check the service log with `journalctl -b -u dotfiles-wifi-resume.service`.

### Connect the service to Network Troubleshooter

Run the setup as your desktop user. Find the interface and saved profile UUID, then substitute those values and your unit name.

```sh
network-troubleshooter --list-adapters
nmcli -f NAME,UUID,TYPE connection show
network-troubleshooter --configure-recovery dotfiles-wifi-resume.service \
  --device wlan0 --profile YOUR_PROFILE_UUID
```

This writes or replaces `recovery.json` under `${XDG_CONFIG_HOME:-$HOME/.config}/network-troubleshooter/` and records the detected driver. Run setup again if you recreate the profile. Delete that file to remove the service from Network Troubleshooter.

Use **Repair connection** in the desktop app or `network-troubleshooter --device wlan0 --repair`. For Ethernet or another Wi-Fi driver, use the same setup command with a system service that checks its own hardware support and restores the adapter after recovery.

## Configure a sign-in helper

Save `portal.json` under `${XDG_CONFIG_HOME:-$HOME/.config}/network-troubleshooter/`. Set a helper for `wifi`, `ethernet`, or both. Start each argument list with an absolute executable path. The app appends the adapter name and HTTP probe URL. Return after opening the window, or exit nonzero if launch fails.

```json
{
  "wifi": ["/absolute/path/to/portal-helper", "--open-device"]
}
```

With no helper for the selected adapter type, the app uses Omarchy's portal helper or opens the probe in the default browser.

## Uninstall

Delete `~/.local/bin/network-troubleshooter`. Delete `io.github.muness.NetworkTroubleshooter.desktop` from your user applications directory, which defaults to `~/.local/share/applications`.

[MIT license](LICENSE)
