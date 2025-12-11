# DD Interface (DDI)

**Professional Disk Imaging Tool with Clonezilla-Inspired Interface**

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.x](https://img.shields.io/badge/python-3.x-blue.svg)](https://www.python.org/)
[![Platform: Linux](https://img.shields.io/badge/platform-linux-lightgrey.svg)]()

A modern, user-friendly TUI (Text User Interface) wrapper for the classic Unix `dd` command. DDI brings safety, visualization, and advanced features to disk imaging operations while maintaining the power and flexibility of `dd`.

![Version](https://img.shields.io/badge/version-1.0.0-green.svg)

---

## Table of Contents

- [Features](#features)
- [Screenshots](#screenshots)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Safety Features](#safety-features)
- [Network Operations](#network-operations)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [Block Map Visualization](#block-map-visualization)
- [FAQ](#faq)
- [Contributing](#contributing)
- [License](#license)
- [Author](#author)

---

## Features

### Core Disk Operations
- **Backup/Image Creation** - Create complete disk images with optional compression
- **Restore/Write Images** - Safely write images back to disks
- **Disk Cloning** - Direct disk-to-disk cloning operations
- **Secure Wipe** - Multi-pass secure data erasure (zero fill, random data, custom patterns)

### Network Capabilities
- **SSH Backup/Restore** - Transfer images over SSH connections to remote servers
- **NFS Backup/Restore** - Store images on NFS shares with automatic mounting
- **Remote File Browser** - Navigate remote directories via SSH
- **Automatic Space Checking** - Pre-flight checks prevent failed operations due to insufficient disk space

### Visualization & Monitoring
- **SpinRite-Style Block Map** - Real-time block-by-block progress visualization showing every sector
- **Traditional Progress Bar** - Clean progress display with detailed statistics
- **Toggle Views** - Switch between block map and progress bar views during operations (press `v`)
- **Error Visualization** - Visual indicators highlight read/write errors in real-time
- **Live Log Window** - Scrollable log output at the bottom of the screen

### Safety & Data Integrity
- **SMART Status Checking** - Pre-operation drive health analysis with detailed diagnostics
- **Mount Detection** - Automatically detects and offers to unmount mounted filesystems
- **Explicit Confirmations** - Keyboard-only (y/n) confirmations prevent accidental mouse clicks
- **Final Warning Dialogs** - Additional typed confirmation ("YES") for destructive operations
- **Automatic Checksum Creation** - Generate MD5, SHA-256, or both after backup operations
- **Automatic Checksum Verification** - Verify image integrity before restore operations
- **Geometry Preservation** - Partition table information automatically saved with backups

### Performance Optimization
- **Intelligent Block Size Detection** - Automatically detects optimal block size based on:
  - Physical sector size
  - Logical sector size
  - Optimal I/O size reported by the drive
- **Multiple Compression Options**:
  - None (fastest, no compression)
  - gzip (good compression, widely compatible)
  - pigz (parallel gzip for multi-core CPUs)
  - zstd (modern, fast compression with excellent ratios)
  - xz (maximum compression, slower)
- **Real-time Statistics** - Transfer speed, ETA, bytes transferred, progress percentage

### User Interface
- **Clonezilla-Inspired Design** - Professional blue/cyan/green color scheme
- **Full Keyboard Navigation** - Arrow keys, Enter, ESC, function keys
- **Mouse Support** - Scroll wheel navigation in menus and help screens
- **Scrollable Log Window** - Full history accessible via Tab key
- **Built-in Help** - Comprehensive help system (press F1)
- **Responsive Layout** - Adapts to terminal size

---

## Screenshots

### Main Menu
```
╔════════════════════════════════════════════════════════════════╗
║ DD Interface v1.0.0 - Main Menu    [Professional Disk Imaging]║
╠════════════════════════════════════════════════════════════════╣
║                                                                ║
║   [1] Backup Disk to Image File                                ║
║   [2] Restore Image File to Disk                               ║
║   [3] Clone Disk to Disk                                       ║
║   [4] Secure Wipe Disk                                         ║
║   [5] Network Operations (SSH/NFS)                             ║
║   [6] View Disk Information                                    ║
║   [7] Exit                                                     ║
║                                                                ║
╠════════════════════════════════════════════════════════════════╣
║ LOG [Tab to focus]                                             ║
║ 2024-01-15 10:30:45 - INFO - Application started               ║
║ 2024-01-15 10:30:45 - INFO - Found 3 suitable devices          ║
╚════════════════════════════════════════════════════════════════╝
↑↓:Navigate | Enter:Select | Esc:Back | Tab:Log | F1:Help | q:Quit
```

### Block Map Progress Visualization
```
╔════════════════════════════════════════════════════════════════╗
║ Backing up /dev/sdb to backup.img.gz                           ║
╠════════════════════════════════════════════════════════════════╣
║                                                                ║
║ Block Map (each char = 64 MiB):                                ║
║ ████████████████████████████████████▒························· ║
║ ·································································║
║                                                                ║
║ Progress: 45.2% | 32.1 GiB / 71.0 GiB                          ║
║ Speed: 125.3 MiB/s | ETA: 00:05:12 | Errors: 0                 ║
║                                                                ║
║ Press 'v' to toggle view                                       ║
╚════════════════════════════════════════════════════════════════╝
Legend: · = Pending | ▒ = Writing | █ = Complete | X = Error
```

---

## Requirements

### System Requirements
- **Operating System**: Linux (any modern distribution)
- **Python**: Python 3.6 or higher
- **Privileges**: Root/sudo access (required for disk operations)
- **Terminal**: Any terminal emulator with ncurses support

### Required Python Packages
All required packages are part of Python's standard library:
- `curses` - TUI interface
- `subprocess` - Command execution
- `os`, `sys`, `time` - System operations
- `re`, `logging` - Utilities
- `textwrap` - Text formatting

### Optional System Utilities
These are automatically detected and used if available:
- `smartctl` (from `smartmontools`) - For SMART drive diagnostics
- `pigz` - For parallel gzip compression
- `zstd` - For zstandard compression
- `gzip` - For gzip compression (usually pre-installed)
- `xz` - For xz compression (usually pre-installed)
- `ssh` - For SSH operations
- `showmount` - For NFS operations

### Installing Optional Utilities

**Debian/Ubuntu:**
```bash
sudo apt-get install smartmontools pigz zstd gzip xz-utils openssh-client nfs-common
```

**RHEL/CentOS/Fedora:**
```bash
sudo dnf install smartmontools pigz zstd gzip xz openssh-clients nfs-utils
```

**Arch Linux:**
```bash
sudo pacman -S smartmontools pigz zstd gzip xz openssh nfs-utils
```

---

## Installation

### Method 1: Direct Download

1. **Download the script:**
   ```bash
   wget https://raw.githubusercontent.com/opensolutionsgroup/dd-interface/main/ddi.py
   wget https://raw.githubusercontent.com/opensolutionsgroup/dd-interface/main/ddi.md
   ```

2. **Make it executable:**
   ```bash
   chmod +x ddi.py
   ```

3. **Run with sudo:**
   ```bash
   sudo ./ddi.py
   ```

### Method 2: Clone Repository

```bash
git clone https://github.com/opensolutionsgroup/dd-interface.git
cd dd-interface
chmod +x ddi.py
sudo ./ddi.py
```

### Method 3: System-Wide Installation

```bash
sudo cp ddi.py /usr/local/bin/ddi
sudo cp ddi.md /usr/local/share/doc/ddi/
sudo chmod +x /usr/local/bin/ddi
```

Then run from anywhere:
```bash
sudo ddi
```

---

## Quick Start

### Basic Backup Operation

1. **Start DDI:**
   ```bash
   sudo ./ddi.py
   ```

2. **Select "Backup Disk to Image File"** from the main menu

3. **Choose the source device** (e.g., /dev/sdb)
   - DDI will perform a SMART health check
   - Any mounted partitions will be automatically unmounted

4. **Select compression type** (gzip recommended for most cases)

5. **Choose block size** (or use auto-detected optimal size)

6. **Enter output directory and filename**
   - DDI checks for sufficient free space
   - Automatically generates timestamped filename

7. **Confirm the operation** (type "YES" for final confirmation)

8. **Monitor progress** with real-time block map visualization
   - Press `v` to toggle between block map and progress bar
   - Press `Tab` to scroll through the log

9. **Checksum creation** - Choose MD5, SHA-256, both, or skip

### Basic Restore Operation

1. **Start DDI** and select "Restore Image File to Disk"

2. **Browse and select your image file**
   - DDI automatically detects and verifies checksums

3. **Choose target device**
   - SMART health check performed
   - Final confirmation required

4. **Monitor the restore operation**

5. **Review partition geometry** - DDI reminds you to restore partition table if needed

---

## Usage

### Disk Backup

Create a complete image of a disk with optional compression:

**What DDI does automatically:**
- ✓ Checks SMART status of source drive
- ✓ Detects and unmounts mounted filesystems
- ✓ Determines optimal block size for the drive
- ✓ Checks available disk space
- ✓ Saves partition table geometry
- ✓ Creates checksums for integrity verification
- ✓ Logs all operations

**Compression recommendations:**
- **None** - Fastest backup, largest file size
- **gzip** - Good balance, widely compatible (recommended)
- **pigz** - Faster than gzip on multi-core systems
- **zstd** - Modern, fast, excellent compression ratio
- **xz** - Smallest files, slowest compression

### Disk Restore

Write an image back to a disk:

**What DDI does automatically:**
- ✓ Verifies checksum if available (.md5 or .sha256 files)
- ✓ Checks SMART status of target drive
- ✓ Detects and unmounts target filesystems
- ✓ Warns if target is smaller than image
- ✓ Reminds you to restore partition table

**Important:** After restoring, you may need to:
1. Restore partition table (if .geometry file exists)
2. Run `partprobe` to refresh partition table
3. Run filesystem checks if needed

### Disk Cloning

Direct disk-to-disk copy:

- No intermediate file needed
- Fastest method for identical disk copies
- Target disk must be equal or larger than source
- Both disks processed simultaneously

### Secure Wipe

Multi-pass data erasure:

**Wipe methods:**
- **Zero Fill** - Single pass with zeros (fastest)
- **Random Data** - Single pass with random data
- **DOD 3-Pass** - US Department of Defense standard
- **Gutmann 35-Pass** - Maximum security (slow)

### Network Operations

#### SSH Backup/Restore

**Backup to SSH server:**
1. Select "Network Operations" → "SSH Backup"
2. Enter SSH credentials (user@host:port)
3. Browse remote directory or enter path
4. Choose source device and compression
5. Image is created directly on remote server

**Restore from SSH server:**
1. Select "Network Operations" → "SSH Restore"
2. Connect to SSH server
3. Browse and select image file
4. Choose target device
5. Checksum verified before restore

#### NFS Backup/Restore

Store images on NFS shares:
- Automatic NFS mount checking
- Free space verification on NFS share
- Same workflow as local backup/restore

---

## Safety Features

### SMART Status Checking

Before every disk operation, DDI checks the drive's SMART status:

**Checks performed:**
- ✓ Overall SMART health test status
- ✓ Reallocated sector count
- ✓ Pending sector count
- ✓ Uncorrectable sector count
- ✓ Spin retry count
- ✓ Drive temperature
- ✓ Power-on hours

**SMART warnings:**
- **PASSED** - Drive appears healthy, safe to proceed
- **WARNING** - Minor issues detected, proceed with caution
- **FAILED** - Critical issues found, operation not recommended

### Mount Detection

DDI automatically:
1. Checks if device or any partition is mounted
2. Displays mount points if found
3. Offers to unmount automatically
4. Verifies unmount was successful
5. Detects if device was auto-ejected after unmount

### Confirmation System

**Three levels of protection:**

1. **Information dialogs** - Show operation details, press any key
2. **Yes/No confirmations** - Red background, keyboard only (y/n)
3. **Final warnings** - Type "YES" exactly for destructive operations

This prevents accidental confirmations via mouse clicks or enter key mashing.

### Checksum Verification

**Automatic checksum handling:**
- Creates `.md5` or `.sha256` files after backup
- Automatically detects checksum files during restore
- Verifies integrity before writing to disk
- Clear warnings if checksum fails

---

## Network Operations

### SSH Operations

**Prerequisites:**
- SSH key-based authentication configured (no password prompts)
- Target user has write permissions to destination directory
- Sufficient disk space on remote server

**Setup SSH keys:**
```bash
# Generate SSH key (if you don't have one)
ssh-keygen -t rsa -b 4096

# Copy to remote server
ssh-copy-id user@remote-server

# Test connection
ssh user@remote-server echo "Connection works"
```

**SSH File Browser:**
- Navigate remote directories with arrow keys
- Shows file sizes and dates
- Filters for image files (.img, .img.gz, etc.)
- Handles directories with many files gracefully

### NFS Operations

**Prerequisites:**
- NFS server configured and accessible
- Export permissions allow read/write
- `showmount` and NFS client utilities installed

**Verify NFS access:**
```bash
# Check available exports
showmount -e nfs-server-ip

# Test mount
sudo mount nfs-server:/export/path /mnt/test
```

---

## Keyboard Shortcuts

### Global Shortcuts

| Key | Action |
|-----|--------|
| `F1` | Show help screen |
| `F12` | Show about/credits (Easter egg) |
| `↑` / `↓` | Navigate menus up/down |
| `Enter` | Select menu item |
| `1`-`9` | Quick select menu items |
| `Esc` | Cancel/Go back |
| `q` / `Q` | Quit/Cancel |
| `Tab` | Switch focus to log window |

### During Operations

| Key | Action |
|-----|--------|
| `v` / `V` | Toggle between progress bar and block map views |

### Confirmations

| Key | Action |
|-----|--------|
| `y` / `Y` | Confirm/Yes |
| `n` / `N` | Cancel/No |

### Log Window (when focused)

| Key | Action |
|-----|--------|
| `↑` / `↓` | Scroll line by line |
| `PgUp` / `PgDn` | Scroll page by page |
| `Home` | Jump to top of log |
| `End` | Jump to bottom of log |
| `Tab` / `Esc` | Return to menu |

### Mouse Support

- **Scroll wheel** - Navigate menus and scrollable windows
- **Left click** - Select menu item (where applicable)
- **Right click** - Cancel/go back (where applicable)

**Note:** Confirmations require keyboard input for safety.

---

## Block Map Visualization

The block map provides a visual representation of the imaging progress at the sector level:

### Characters

| Symbol | Meaning |
|--------|---------|
| `·` (dot) | Pending blocks (not yet processed) |
| `▒` (medium shade) | Currently being written |
| `█` (solid block) | Completed successfully |
| `X` | Error during read/write operation |

### Colors

| Color | Status |
|-------|--------|
| Green on Blue | Normal operation, blocks processing successfully |
| White on Red | Error state, read/write failure |

### Interpreting the Display

```
████████████████████████████████████▒·························
```

In this example:
- 36 blocks completed successfully (█)
- 1 block currently being written (▒)
- 26 blocks pending (·)

**Each character represents:**
- The number of bytes per character is calculated based on:
  - Total disk size
  - Terminal width
  - Typically 64 MiB to 256 MiB per character

### Error Tracking

If errors occur during an operation:
- The problematic block is marked with `X`
- The character turns white on red background
- Error count is displayed in the statistics
- All errors are logged to the log window

**Press `v` during operation to toggle to progress bar view if you prefer traditional percentage display.**

---

## FAQ

### General Questions

**Q: Why does DDI require sudo/root privileges?**

A: Direct disk access, mounting/unmounting filesystems, and running `dd` all require root privileges. DDI must run as root to perform these operations safely.

**Q: Can I use DDI on non-Linux systems?**

A: Currently, DDI is Linux-only. It relies on Linux-specific utilities like `lsblk`, `blockdev`, and the `/proc` filesystem. macOS or BSD support could be added in the future.

**Q: How long does a disk backup take?**

A: This depends on:
- Disk size
- Disk speed (HDD vs SSD vs NVMe)
- Compression method chosen
- Block size
- System CPU (for compression)

Typical speeds: 50-150 MiB/s for HDDs, 200-500 MiB/s for SSDs (uncompressed).

**Q: What's the difference between cloning and backup/restore?**

A: 
- **Backup** creates a file (image) on another drive/location
- **Clone** directly copies one disk to another disk without an intermediate file
- **Restore** writes a backup image file back to a disk

### Safety Questions

**Q: What happens if I lose power during an operation?**

A: 
- **During backup**: The partial image file will exist but may be incomplete/corrupted
- **During restore/clone**: The target disk will be partially written and likely unusable
- **Recommendation**: Always have a backup before performing disk operations

**Q: Can DDI damage my hardware?**

A: No. DDI only performs read/write operations that the `dd` command would do. However, like any disk utility, **using the wrong source/target can result in data loss**. Always double-check your selections.

**Q: What if I select the wrong disk?**

A: DDI has multiple safety features:
1. SMART status check shows disk details
2. Device names, sizes, and models are clearly displayed
3. Final confirmation requires typing "YES"
4. All operations are logged

However, **you are responsible for verifying your selections before confirming**.

### Technical Questions

**Q: What block size should I use?**

A: Use the auto-detected optimal block size (recommended). DDI analyzes:
- Physical sector size (usually 512 bytes or 4096 bytes)
- Optimal I/O size reported by the drive
- Drive geometry

Modern drives usually work best with 64K-1M block sizes.

**Q: Which compression method is best?**

A: 
- **None**: Fastest, no CPU usage, largest files
- **gzip**: Good balance, universally compatible, moderate CPU (recommended for most users)
- **pigz**: Faster than gzip on multi-core systems
- **zstd**: Modern, fast compression and decompression, excellent ratio (recommended for SSD/NVMe)
- **xz**: Best compression ratio, very slow, high CPU usage (for archival/slow networks)

**Q: Why does DDI save partition table geometry separately?**

A: The `dd` command creates a bit-for-bit copy, which includes the partition table. However, having a separate `.geometry` file allows you to:
1. Verify the partition layout before restore
2. Restore the partition table to a differently-sized disk
3. Recover partition information if the image is corrupted

**Q: Can I resume an interrupted backup?**

A: No, not currently. The `dd` command doesn't support resuming. An interrupted backup must be restarted from the beginning.

### Troubleshooting

**Q: DDI shows "SMART not supported" for my drive**

A: Some devices don't support SMART:
- USB flash drives
- Some USB enclosures (SMART commands blocked)
- Virtual machines (virtual disks)
- SD cards

DDI will still work, but cannot check drive health.

**Q: SSH backup fails with "Permission denied"**

A: Ensure:
1. SSH key-based authentication is set up (`ssh-copy-id`)
2. Remote user has write permissions to the target directory
3. SSH connection works manually first: `ssh user@host`

**Q: The terminal display looks corrupted**

A: Try:
1. Resize your terminal to at least 80x24
2. Run `reset` command before starting DDI
3. Use a different terminal emulator
4. Check that your locale is set correctly (`echo $LANG`)

**Q: "Device or resource busy" error when imaging**

A: The device or one of its partitions is still mounted or in use:
1. DDI should auto-detect and offer to unmount
2. If auto-unmount fails, manually unmount: `sudo umount /dev/sdX*`
3. Check for processes using the disk: `sudo lsof | grep /dev/sdX`
4. Some systems auto-mount removable media - disable this in your desktop environment

---

## Development

### Building from Source

DDI is a single Python script with no build process needed.

### Testing

```bash
# Syntax check
python3 -m py_compile ddi.py

# Linting
python3 -m flake8 ddi.py --max-line-length=100
```

### Code Style

DDI follows these conventions:
- Python 3 syntax
- UTF-8 encoding
- 100-character line limit
- Snake_case for functions and variables
- PascalCase for classes
- UPPER_SNAKE_CASE for constants
- Comprehensive docstrings
- Error handling with logging

See `AGENTS.md` for detailed development guidelines.

---

## Contributing

Contributions are welcome! Please follow these guidelines:

### Reporting Bugs

1. Check existing issues first
2. Include DDI version (`ddi.py --version` or check VERSION in code)
3. Include Python version (`python3 --version`)
4. Include Linux distribution and version
5. Provide steps to reproduce
6. Include relevant log output from `ddi.log`

### Feature Requests

1. Check existing issues/feature requests
2. Describe the use case and benefit
3. Consider if it fits DDI's philosophy (safety, simplicity, visualization)

### Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Follow the existing code style
4. Test your changes thoroughly
5. Update documentation (README.md, ddi.md) if needed
6. Commit with clear messages
7. Push to your fork
8. Open a Pull Request

### Development Setup

```bash
git clone https://github.com/opensolutionsgroup/dd-interface.git
cd dd-interface

# Create a virtual environment (optional, but recommended)
python3 -m venv venv
source venv/bin/activate

# Install development dependencies
pip install flake8 pylint black

# Make changes and test
sudo python3 ddi.py
```

---

## Roadmap

Future enhancements under consideration:

- [ ] Resume interrupted operations
- [ ] Sparse image support
- [ ] Differential/incremental backups
- [ ] BitLocker/LUKS detection and warnings
- [ ] Partition-level imaging (not just whole disk)
- [ ] Image format conversion (raw ↔ qcow2 ↔ vmdk)
- [ ] GUI wrapper option
- [ ] macOS/BSD support
- [ ] Configuration file support
- [ ] Automated backup scheduling
- [ ] Email notifications on completion
- [ ] Web interface for remote management

**Want to see a feature?** Open an issue with the `enhancement` label!

---

## Acknowledgments

- **Inspired by**: [Clonezilla](https://clonezilla.org/) - The excellent open-source disk imaging solution
- **Inspired by**: SpinRite - For the block map visualization concept
- **Built with**: Python, ncurses
- **Thanks to**: The Unix/Linux community for the `dd` command and related utilities

### About the `dd` Command

The `dd` command is one of Unix's classic utilities, dating back to the early days of Unix development in the 1970s at Bell Labs.

The name "dd" stands for "convert and copy" - though the naming comes from the IBM Job Control Language (JCL) convention, where DD stood for "Data Definition."

Despite being somewhat dangerous (earning the nickname "disk destroyer" due to its power), `dd` remains widely used today for tasks like creating disk images, writing bootable USB drives, benchmarking disk performance, and low-level data recovery.

DDI aims to make `dd` safer and more accessible while maintaining its power and flexibility.

---

## License

**DD Interface (DDI)** is licensed under the **GNU General Public License v3.0 (GPLv3)**.

This means:
- ✓ You can use DDI for any purpose
- ✓ You can study and modify the source code
- ✓ You can distribute copies
- ✓ You can distribute modified versions
- ⚠ You must disclose the source code when distributing
- ⚠ You must license modifications under GPLv3
- ⚠ You must include a copy of the license and copyright notice

**Full license text**: https://www.gnu.org/licenses/gpl-3.0.html

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

---

## Author

**Paul Miskovsky**

- GitHub: [@opensolutionsgroup](https://github.com/opensolutionsgroup)
- Project: [dd-interface](https://github.com/opensolutionsgroup/dd-interface)

---

## Support

### Documentation

- **Built-in Help**: Press `F1` while running DDI
- **User Guide**: See `ddi.md` in the repository
- **This README**: Comprehensive usage guide

### Getting Help

1. Check the [FAQ](#faq) section above
2. Review existing [GitHub Issues](https://github.com/opensolutionsgroup/dd-interface/issues)
3. Check the log file: `ddi.log` in the current directory
4. Open a new issue with details

### Disclaimer

**USE AT YOUR OWN RISK**

DD Interface is a powerful tool that performs low-level disk operations. While it includes numerous safety features, **you are responsible for selecting the correct source and target devices**. 

**Always:**
- Double-check device selections
- Maintain backups of important data
- Test on non-critical systems first
- Understand what each operation does before confirming

The authors and contributors are not responsible for data loss, hardware damage, or any other issues arising from the use of this software.

---

## Star History

If you find DDI useful, please consider giving it a star on GitHub!

---

**Made with ❤️ for the Linux community**

*Making `dd` safe, visual, and accessible since 2024*
