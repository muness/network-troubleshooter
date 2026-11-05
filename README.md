# Network Troubleshooter

Check one Wi-Fi or Ethernet adapter at a time. The checklist shows link, IP address, route, ping, DNS, captive sign-in, and HTTPS. Open it from the application launcher even when the internet is down.

## Install

Network Troubleshooter uses Python 3, NetworkManager, iproute2, iputils, curl, systemd, YAD, and xdg-utils. On Arch, install any missing packages before an outage. Per-adapter DNS checks use systemd-resolved when it is running.

```sh
git clone https://github.com/muness/network-troubleshooter.git
cd network-troubleshooter
python3 install.py
```

Open **Network Troubleshooter** and choose the adapter to check. **Reconnect** activates an existing NetworkManager profile after you confirm. **Open sign-in** uses Omarchy's captive-portal helper when available, or opens NetworkManager's HTTP probe in the default browser. If the browser uses another connection, try sign-in with the captive network as your active route.

You can also run a read-only check from a terminal.

```sh
~/.local/bin/network-troubleshooter
~/.local/bin/network-troubleshooter --device enp2s0
```

The route check looks for a path to `1.1.1.1` and `2606:4700:4700::1111` without sending packets. Ping tests those same targets through the selected adapter. Choose **Ping target** to test a different IP, such as your router, for the current session. **Use defaults** restores the public targets. The HTTPS result can still show internet access if ping gets no reply.

DNS and HTTPS use `archlinux.org` as a test site. HTTPS binds to the selected adapter. If per-adapter DNS cannot be verified, HTTPS may use the system resolver. An unverified probe identifies the failed check, and the app leaves the cause open.

The desktop entry ID is `io.github.muness.NetworkTroubleshooter.desktop`. The app runs as your user and calls NetworkManager for explicit reconnects. The checks and controls are local and do not require an AI account.

To uninstall, remove `~/.local/bin/network-troubleshooter` and `io.github.muness.NetworkTroubleshooter.desktop` from your user applications directory (`~/.local/share/applications` by default).
