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

## Optional recovery and sign-in helpers

Store these files under `${XDG_CONFIG_HOME:-$HOME/.config}/network-troubleshooter/`.

### `recovery.json`

Point to a guarded systemd service you already have. After a failed reconnect, the app starts the configured unit through polkit if the adapter is disconnected and the driver matches. The service must check hardware support and restore the adapter. The Wi-Fi guard requires `iw` and exactly one Wi-Fi adapter visible to NetworkManager.

```json
{
  "adapter": "wlan0",
  "profile": "00000000-0000-4000-8000-000000000000",
  "driver": "driver_name",
  "unit": "wifi-recovery.service"
}
```

### `portal.json`

Set a helper for `wifi`, `ethernet`, or both. Start each argument list with an absolute executable path. The app appends the adapter name and HTTP probe URL. Return after opening the window, or exit nonzero if launch fails.

```json
{
  "wifi": ["/absolute/path/to/portal-helper", "--open-device"]
}
```

With no helper for the selected adapter type, the app uses Omarchy's portal helper or opens the probe in the default browser.

## Uninstall

Delete `~/.local/bin/network-troubleshooter`. Delete `io.github.muness.NetworkTroubleshooter.desktop` from your user applications directory, which defaults to `~/.local/share/applications`.

[MIT license](LICENSE)
