#!/usr/bin/python3
"""Install Network Troubleshooter for the current user."""
import os
from pathlib import Path
import shutil

APP_ID = 'io.github.muness.NetworkTroubleshooter'

if os.geteuid() == 0:
    raise SystemExit('Run this installer as your desktop user.')

source = Path(__file__).resolve().parent
target = Path.home() / '.local/bin/network-troubleshooter'
applications = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share') / 'applications'
target.parent.mkdir(parents=True, exist_ok=True)
applications.mkdir(parents=True, exist_ok=True)
shutil.copyfile(source / target.name, target)
target.chmod(0o755)

# The Desktop Entry string parser runs before Exec argument unquoting.
command = str(target).replace('%', '%%')
command = ''.join('\\' + char if char in '\\"$`' else char for char in command)
command = command.replace('\\', '\\\\')
(applications / f'{APP_ID}.desktop').write_text(f'''[Desktop Entry]
Type=Application
Name=Network Troubleshooter
Comment=Check and reconnect a Wi-Fi or Ethernet adapter
Exec="{command}" --gui
Icon=network-wireless
Terminal=false
Categories=Network;
Keywords=wifi;ethernet;diagnostics;sign-in;
''', encoding='utf-8')
print('Installed Network Troubleshooter in the application launcher.')
