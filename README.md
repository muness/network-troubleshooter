# Network Troubleshooter

Check one Wi-Fi or Ethernet adapter at a time. The checklist shows link, IP address, route, gateway, public ping, DNS, captive sign-in, and HTTPS. Open it from the application launcher even when the internet is down.

## Install

Network Troubleshooter uses Python 3, NetworkManager, iproute2, iputils, curl, systemd, YAD, and xdg-utils. On Arch, install any missing packages before an outage. Per-adapter DNS checks use systemd-resolved when it is running.

```sh
git clone https://github.com/muness/network-troubleshooter.git
cd network-troubleshooter
python3 install.py
```

Open **Network Troubleshooter** and choose an adapter. **Repair connection** retries its saved NetworkManager profile after you confirm. If that profile is still active after a failed attempt, the app disconnects the adapter and retries the same profile. One repair can run per adapter at a time.

**Open sign-in** appears when NetworkManager detects a portal. **Try sign-in** is available when the adapter is connected but the check cannot verify internet access or a portal. A configured helper can bind browser traffic to the selected adapter. Otherwise the app uses Omarchy's helper or opens the HTTP probe in the default browser, which follows system routing.

**View report** opens the private evidence, including recent adapter logs and before-and-after repair results. Wi-Fi details include radio state, association and signal from `iw` when available, and cached visibility for the saved profile. **Copy redacted** copies check statuses and repair outcomes, with no raw logs or connection identifiers. Copying requires `wl-copy`. Private reports are saved under `${XDG_STATE_HOME:-$HOME/.local/state}/network-troubleshooter/`.

## Command line

```sh
network-troubleshooter --list-adapters
network-troubleshooter --device enp2s0
network-troubleshooter --device enp2s0 --ping-target 192.168.1.1 --redacted-report
network-troubleshooter --device enp2s0 --repair --report
network-troubleshooter --device wlan0 --sign-in
```

Select the adapter with `--device` when more than one is present. Repair asks for confirmation in a terminal. Use `--repair --yes` for automation. `--report` prints private evidence. Use `--redacted-report` for output you can share. The path to the private report goes to stderr.

The route check looks for a path to `1.1.1.1` and `2606:4700:4700::1111` without sending packets. **Gateway** pings the router addresses supplied by NetworkManager. **Ping** tests the public targets through the selected adapter. Choose **Ping target** or pass `--ping-target` to override the public test for the session. **Use defaults** restores it in the GUI. The HTTPS result can still show internet access if ping gets no reply.

DNS and HTTPS use `archlinux.org` as a test site. HTTPS binds to the selected adapter. If per-adapter DNS cannot be verified, HTTPS may use the system resolver. An unverified probe identifies the failed check, and the app leaves the cause open.

The desktop entry ID is `io.github.muness.NetworkTroubleshooter.desktop`. The app runs as your user. The checks and controls are local and do not require an AI account.

## Optional driver recovery

If your system already has a guarded systemd recovery service, you can associate it with one adapter in `${XDG_CONFIG_HOME:-$HOME/.config}/network-troubleshooter/recovery.json`.

```json
{
  "adapter": "wlan0",
  "profile": "00000000-0000-4000-8000-000000000000",
  "driver": "driver_name",
  "unit": "wifi-recovery.service"
}
```

Set the adapter name, saved NetworkManager profile UUID, actual kernel driver name, and installed system service. After a failed reconnect, the app can start that service via polkit if the driver still matches and the adapter is disconnected. The Wi-Fi guard needs `iw` and exactly one Wi-Fi adapter visible to NetworkManager. The service itself should check hardware support and safely restore the adapter. Without this configuration, the app uses the NetworkManager repair for Wi-Fi and Ethernet.

## Optional interface-bound sign-in

In the same configuration directory, put an argument list under `wifi`, `ethernet`, or both in `portal.json`. The executable path must be absolute. The app appends the selected adapter name and the HTTP probe URL as separate arguments. The helper should return after launching the login window and report a nonzero exit if it cannot start.

```json
{
  "wifi": ["/absolute/path/to/portal-helper", "--open-device"]
}
```

## Uninstall

To uninstall, remove `~/.local/bin/network-troubleshooter` and `io.github.muness.NetworkTroubleshooter.desktop` from your user applications directory (`~/.local/share/applications` by default).
