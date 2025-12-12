# DD Interface (DDI)

**Professional Disk Imaging Tool with Clonezilla-Inspired Interface**

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.x](https://img.shields.io/badge/python-3.x-blue.svg)](https://www.python.org/)
[![Platform: Linux](https://img.shields.io/badge/platform-linux-lightgrey.svg)]()
![Version](https://img.shields.io/badge/version-1.0.0-green.svg)

A modern TUI wrapper for the classic Unix `dd` command, bringing safety, visualization, and advanced features to disk imaging operations.

---

## Features

**Core Operations:** Backup/restore disks, disk cloning, secure wipe (zero/random/DOD/Gutmann)  
**Network:** SSH/NFS backup and restore with remote file browser  
**Visualization:** SpinRite-style block map + traditional progress bar (toggle with `v`)  
**Safety:** SMART health checks, mount detection, multi-level confirmations, automatic checksums (MD5/SHA-256)  
**Performance:** Intelligent block size detection, multiple compression (gzip/pigz/zstd/xz)  
**Interface:** Clonezilla colors, full keyboard/mouse navigation, scrollable logs, built-in help (F1)

### Screenshots

```
╔════════════════════════════════════════════════════════════════╗
║ DD Interface v1.0.0 - Main Menu    [Professional Disk Imaging] ║
╠════════════════════════════════════════════════════════════════╣
║   [1] Backup Disk to Image File                                ║
║   [2] Restore Image File to Disk                               ║
║   [3] Clone Disk to Disk                                       ║
║   [4] Secure Wipe Disk                                         ║
║   [5] Network Operations (SSH/NFS)                             ║
╠════════════════════════════════════════════════════════════════╣
║ LOG [Tab to focus]                                             ║
║ 2024-01-15 10:30:45 - INFO - Application started               ║
╚════════════════════════════════════════════════════════════════╝
↑↓:Navigate | Enter:Select | Esc:Back | Tab:Log | F1:Help | q:Quit
```

**Block Map Progress:**
```
║ Block Map (each char = 64 MiB):                                ║
║ ████████████████████████████████████▒························· ║
║ Progress: 45.2% | 32.1 GiB / 71.0 GiB                          ║
║ Speed: 125.3 MiB/s | ETA: 00:05:12 | Errors: 0                 ║
Legend: · = Pending | ▒ = Writing | █ = Complete | X = Error
```

---

## Installation

### Quick Install
```bash
wget https://raw.githubusercontent.com/opensolutionsgroup/dd-interface/main/ddi.py
wget https://raw.githubusercontent.com/opensolutionsgroup/dd-interface/main/ddi.md
chmod +x ddi.py
sudo ./ddi.py
```

### System-Wide
```bash
sudo cp ddi.py /usr/local/bin/ddi
sudo cp ddi.md /usr/local/share/doc/ddi/
sudo chmod +x /usr/local/bin/ddi
sudo ddi
```

### Requirements
- **Python 3.6+** (all required packages in stdlib: curses, subprocess, os, sys, time, re, logging, textwrap)
- **Root access** (required for disk operations)
- **Optional utilities:** smartmontools, pigz, zstd, gzip, xz, openssh-client, nfs-common

**Install optional utilities:**
```bash
# Debian/Ubuntu
sudo apt-get install smartmontools pigz zstd openssh-client nfs-common

# RHEL/Fedora
sudo dnf install smartmontools pigz zstd openssh-clients nfs-utils

# Arch
sudo pacman -S smartmontools pigz zstd openssh nfs-utils
```

---

## Quick Start

### Backup a Disk
1. Run: `sudo ./ddi.py`
2. Select **"Backup Disk to Image File"**
3. Choose source device → SMART check performed → unmount if needed
4. Select compression (gzip recommended) and block size (or use auto-detected)
5. Enter output directory/filename → free space checked
6. Confirm with "YES" → monitor progress (press `v` to toggle views)
7. Choose checksum algorithm (MD5/SHA-256/both/skip)

### Restore a Disk
1. Select **"Restore Image File to Disk"**
2. Browse/select image → checksum auto-verified if available
3. Choose target device → SMART check → unmount if needed
4. Confirm with "YES" → monitor progress
5. Restore partition table if needed (`.geometry` file)

### Network Backup via SSH
1. Select **"Network Operations"** → **"SSH Backup"**
2. Enter credentials (user@host:port) → browse remote directory
3. Choose source device and compression → image created on remote server

**SSH Setup:**
```bash
ssh-keygen -t rsa -b 4096
ssh-copy-id user@remote-server
ssh user@remote-server echo "Connection works"
```

---

## Safety Features

### SMART Health Checks
Automatic pre-operation checks: Overall health, reallocated sectors, pending sectors, uncorrectable sectors, spin retry, temperature, power-on hours  
**Results:** PASSED (safe) | WARNING (caution) | FAILED (not recommended)

### Three-Level Confirmations
1. **Info dialogs** - Operation details (any key)
2. **Yes/No** - Red background, keyboard only (y/n)  
3. **Final warning** - Type "YES" exactly for destructive operations

### Auto Features
- Mount detection and unmounting
- Checksum creation (.md5/.sha256) and verification
- Partition table geometry preservation (.geometry)
- Free space checking
- Complete operation logging

---

## Keyboard Shortcuts

| Key | Action | Key | Action |
|-----|--------|-----|--------|
| **F1** | Help screen | **F12** | About/credits |
| **↑/↓** | Navigate menus | **1-9** | Quick select |
| **Enter** | Select | **Esc/q** | Cancel/Quit |
| **Tab** | Focus log | **v** | Toggle view (during ops) |
| **y/n** | Confirm/Cancel | **Mouse** | Scroll/select |

**Log window (Tab):** ↑/↓ scroll, PgUp/PgDn page, Home/End jump, Tab/Esc return

---

## Usage Guide

### Compression Recommendations
- **None** - Fastest, largest files
- **gzip** - Balanced, compatible (recommended)
- **pigz** - Parallel gzip for multi-core
- **zstd** - Fast, excellent ratio (best for SSD)
- **xz** - Maximum compression, slow

### Block Size
Use auto-detected optimal size (analyzes physical/logical sector size + optimal I/O). Manual: 64K-1M for modern drives.

### What DDI Automates
✓ SMART checks | ✓ Mount/unmount | ✓ Optimal block size | ✓ Free space check  
✓ Partition table backup | ✓ Checksums | ✓ Error tracking | ✓ Complete logging

### After Restore
1. Restore partition table: `sudo sfdisk /dev/sdX < backup.geometry`
2. Refresh: `sudo partprobe /dev/sdX`
3. Check filesystems if needed

---

## Block Map Visualization

**Characters:** `·` Pending | `▒` Writing | `█` Complete | `X` Error  
**Colors:** Green/Blue = Normal | White/Red = Error  
**Scale:** Each char = 64-256 MiB (based on disk size/terminal width)

Press **`v`** during operation to toggle between block map and progress bar views.

---

## FAQ

**Q: Why sudo/root required?**  
A: Direct disk access, mount/unmount operations, and `dd` require root privileges.

**Q: Which compression method?**  
A: **gzip** for compatibility/balance, **zstd** for SSD/speed, **xz** for archival/small files.

**Q: Can I resume interrupted operations?**  
A: No. The `dd` command doesn't support resuming. Start from beginning.

**Q: What if power fails during operation?**  
A: Backup = partial/corrupted file. Restore/Clone = target disk unusable. Always maintain backups.

**Q: "SMART not supported" message?**  
A: USB drives, some USB enclosures, VMs, and SD cards don't support SMART. DDI still works.

**Q: "Device busy" error?**  
A: Device still mounted. DDI auto-unmounts, but if failed: `sudo umount /dev/sdX*` or check: `sudo lsof | grep /dev/sdX`

**Q: SSH backup permission denied?**  
A: Ensure SSH keys configured (`ssh-copy-id user@host`), write permissions, test manually first.

**Q: Terminal display corrupted?**  
A: Resize to 80x24+, run `reset` before DDI, try different terminal, check locale (`echo $LANG`).

**Q: Backup vs Clone vs Restore?**  
A: **Backup** = create image file. **Clone** = direct disk-to-disk. **Restore** = write image to disk.

**Q: Typical backup speeds?**  
A: HDDs: 50-150 MiB/s, SSDs: 200-500 MiB/s (uncompressed). Depends on disk, compression, CPU.

---

## Development

### Testing
```bash
python3 -m py_compile ddi.py  # Syntax check
python3 -m flake8 ddi.py --max-line-length=100  # Lint
```

### Code Style
Python 3, UTF-8, 100-char lines, snake_case functions, PascalCase classes, UPPER_SNAKE_CASE constants  
See `AGENTS.md` for detailed guidelines.

---

## Contributing

**Bug Reports:** Check existing issues → include DDI version, Python version, distro, steps to reproduce, `ddi.log` output  
**Feature Requests:** Check existing → describe use case → ensure fits DDI philosophy (safety/simplicity/visualization)  
**Pull Requests:** Fork → feature branch → follow code style → test → update docs → clear commits → open PR

### Development Setup
```bash
git clone https://github.com/opensolutionsgroup/dd-interface.git
cd dd-interface
python3 -m venv venv && source venv/bin/activate
pip install flake8 pylint black
sudo python3 ddi.py
```

---

## Roadmap

- [ ] Resume interrupted operations
- [ ] Sparse/incremental backups
- [ ] BitLocker/LUKS detection
- [ ] Partition-level imaging
- [ ] Image format conversion (raw/qcow2/vmdk)
- [ ] GUI wrapper
- [ ] macOS/BSD support
- [ ] Config file support
- [ ] Scheduling & email notifications

---

## License

**GNU General Public License v3.0 (GPLv3)**

```
DD Interface (DDI) - Professional Disk Imaging Tool
Copyright (C) 2024 Paul Miskovsky

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
```

**Full license:** https://www.gnu.org/licenses/gpl-3.0.html

---

## About

**Author:** Paul Miskovsky  
**GitHub:** [@opensolutionsgroup](https://github.com/opensolutionsgroup)  
**Project:** [dd-interface](https://github.com/opensolutionsgroup/dd-interface)

**Inspired by:** [Clonezilla](https://clonezilla.org/) (disk imaging) & SpinRite (block map visualization)

### The `dd` Command History

The `dd` command dates back to 1970s Unix development at Bell Labs. The name comes from IBM JCL's "Data Definition" (DD). Its unusual `key=value` syntax reflects JCL heritage rather than typical Unix flags.

Despite earning the nickname "disk destroyer" due to its power (one typo can wipe a disk), `dd` remains essential for disk imaging, bootable USB creation, benchmarking, and data recovery. DDI makes `dd` safer and more accessible while maintaining its power.

---

## Disclaimer

**USE AT YOUR OWN RISK**

DDI performs low-level disk operations. While it includes extensive safety features, **you are responsible for selecting correct devices**.

**Always:** Double-check selections | Maintain backups | Test on non-critical systems | Understand operations before confirming

Authors/contributors are not responsible for data loss, hardware damage, or any issues from software use.

---

**Documentation:** Built-in help (F1) | `ddi.md` user guide | This README  
**Support:** Check [FAQ](#faq) → Review [GitHub Issues](https://github.com/opensolutionsgroup/dd-interface/issues) → Check `ddi.log` → Open new issue

---
