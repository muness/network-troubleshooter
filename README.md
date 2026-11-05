# Network Troubleshooter for Linux

Find out why a Wi-Fi or Ethernet connection stopped working. Pick an adapter and check its link, IP address, route, gateway, DNS, captive portal, and internet access. A working Wi-Fi connection can stay up while you test an Ethernet port that stopped working.

Use the desktop app or run the same checks in a terminal. You can diagnose a connection, retry a saved profile, and open a sign-in page during an outage. Local checks and repairs run on your machine and need no AI account.

## Install

You need **Linux with NetworkManager**. The checks use Python 3, `ip` from iproute2, `ping` from iputils, curl, and systemd's journal tools. Install YAD for the desktop UI and xdg-utils for browser sign-in on desktops without Omarchy's portal helper. The app uses systemd-resolved for per-adapter DNS checks when available, `iw` for Wi-Fi link details, and `wl-copy` to copy reports on Wayland.

Run as your desktop user.

```sh
git clone https://github.com/muness/network-troubleshooter.git
cd network-troubleshooter
python3 install.py
```

Search for **Network Troubleshooter** in your app launcher. The installer puts the command in `~/.local/bin`. Use that path in the examples below if the directory is outside your `PATH`.

## Use it from OmaDoctor on Omarchy

OmaDoctor is a diagnostics widget for Omarchy. The **Network** button is available to try in its draft launcher PR. [OmaDoctor project](https://github.com/Davedes83/OmaDoctor) · [Draft PR #9](https://github.com/Davedes83/OmaDoctor/pull/9)

With that version of OmaDoctor and this app installed, click **Network** next to **Ask AI**. The button opens Network Troubleshooter locally, even before an OmaDoctor scan finishes. OmaDoctor sends no report to the app.

In OmaDoctor's widget settings, **Network troubleshooter app** defaults to `auto`, which shows the button when this app is installed. Its desktop ID is `io.github.muness.NetworkTroubleshooter.desktop`. Enter a different desktop app ID to use another tool, or clear the field to hide the button.

For a fresh OmaDoctor install, try the draft branch with Omarchy's plugin manager.

```sh
git clone --branch codex/network-troubleshooter-launcher https://github.com/muness/OmaDoctor.git omadoctor-preview
omarchy plugin add "$PWD/omadoctor-preview" --enable
```

## Read the checklist

- **Link and IP address** show whether the Ethernet cable has a link or Wi-Fi joined, and whether the adapter got an IPv4 or IPv6 address beyond link-local. Wi-Fi details include the radio state, association, signal, and cached visibility of the saved network when available.
- **Route, Gateway, and Ping** separate a missing route from a router or public IP that gives no reply. The public targets are `1.1.1.1` and `2606:4700:4700::1111`. Use **Ping target** to try a different IP for this session.
- **DNS and Internet** check `archlinux.org`. The HTTPS request uses the selected adapter. It may use system DNS if the app cannot verify per-adapter DNS. A successful HTTPS request still verifies internet access if ping gets no reply.
- **Sign-in** offers **Open sign-in** for a detected captive portal and **Try sign-in** when the result is inconclusive. The system browser uses normal routing. An optional helper can bind sign-in to the selected adapter.

**Repair connection** retries the saved NetworkManager profile after you confirm. If the retry fails and that profile is still active, the app disconnects the selected adapter and retries the same profile. It runs one repair at a time per adapter and checks the connection again afterward.

**View report** shows recent adapter logs and before-and-after repair results. The full report can contain IP addresses, network names, and log messages. Private reports are saved under `${XDG_STATE_HOME:-$HOME/.local/state}/network-troubleshooter/`. Use **Copy redacted** to share check statuses and repair outcomes without the raw evidence.

## Use it from a terminal

```sh
network-troubleshooter --list-adapters
network-troubleshooter --device enp2s0
network-troubleshooter --device enp2s0 --ping-target 192.168.1.1 --redacted-report
network-troubleshooter --device enp2s0 --repair --report
network-troubleshooter --device wlan0 --sign-in
```

Use the adapter name from `--list-adapters`. Repair prompts for confirmation in a terminal. Add `--yes` to confirm it in a script. `--report` prints the private report and `--redacted-report` prints the shareable one. The saved private report path goes to stderr.

## Configure a driver recovery service

If your system already has a guarded systemd recovery service, put its adapter, saved NetworkManager profile UUID, driver name, and unit in `${XDG_CONFIG_HOME:-$HOME/.config}/network-troubleshooter/recovery.json`.

```json
{
  "adapter": "wlan0",
  "profile": "00000000-0000-4000-8000-000000000000",
  "driver": "driver_name",
  "unit": "wifi-recovery.service"
}
```

After a failed reconnect, the app can ask for polkit authentication and start that unit if the adapter is disconnected and its driver still matches. Wi-Fi recovery requires `iw` and exactly one Wi-Fi adapter visible to NetworkManager. The service is responsible for verifying hardware support and restoring the adapter safely.

## Configure an interface-bound sign-in helper

Put an argument list under `wifi`, `ethernet`, or both in `portal.json` in the same configuration directory.

```json
{
  "wifi": ["/absolute/path/to/portal-helper", "--open-device"]
}
```

The executable path must be absolute. The app passes the selected adapter name and HTTP probe URL as two additional arguments. The helper should return after opening the login window, or exit nonzero if launch fails. With no helper configured for that adapter type, the app uses Omarchy's captive-portal helper if available or opens the probe URL in the default browser.

## Uninstall

Remove the command at `~/.local/bin/network-troubleshooter` and the entry named `io.github.muness.NetworkTroubleshooter.desktop` in your user applications directory, usually `~/.local/share/applications`.

[MIT license](LICENSE)
