# DDI - DD Interface
## Professional Disk Imaging Tool

Version 1.0 | A user-friendly interface for the dd command

---

## FEATURES

### Disk Operations
- **Backup/Image Creation** - Create complete disk images with compression
- **Restore/Write Images** - Write images back to disks safely
- **Clone Disks** - Direct disk-to-disk cloning
- **Secure Wipe** - Multi-pass secure data erasure (zero, random, custom patterns)

### Network Operations
- **SSH Backup/Restore** - Transfer images over SSH connections
- **NFS Backup/Restore** - Use NFS shares for image storage
- **Automatic Free Space Checking** - Prevents failed operations

### Visualization
- **SpinRite-Style Block Map** - Real-time block-by-block progress visualization
- **Progress Bar View** - Traditional progress bar with statistics
- **Toggle Views (Press 'v')** - Switch between block map and progress bar during operations
- **Error Detection** - Visual indicators for read/write errors in block map

### Safety Features
- **SMART Status Checking** - Pre-operation drive health analysis
- **Mount Detection** - Automatic detection and unmounting of mounted filesystems
- **Explicit Confirmations** - Keyboard-only (y/n) confirmations prevent accidental clicks
- **Final Warning Dialog** - Additional confirmation for destructive operations

### Data Integrity
- **Automatic Checksum Creation** - MD5, SHA-256, or both after backup
- **Automatic Checksum Verification** - Verify images before restore
- **Automatic Geometry Saving** - Partition table information saved with backups
- **Error Tracking** - Records and displays I/O errors during operations

### Performance
- **Intelligent Block Size Detection** - Automatic optimal block size selection
- **Multiple Compression Options** - gzip, pigz (parallel), zstd, xz, or none
- **Real-time Statistics** - Speed, ETA, transferred bytes, progress percentage

### User Interface
- **Clonezilla-Inspired Color Scheme** - Professional blue/cyan/green palette
- **Live Log Window** - Real-time operation logging at bottom of screen
- **Keyboard Navigation** - Full keyboard control, arrow keys, Enter, ESC
- **Mouse Support** - Scroll wheel navigation in menus (confirmations require keyboard)

---

## KEYBOARD SHORTCUTS

### Global
- **F1** - Show this help
- **ESC / q / Q** - Cancel/Back/Quit
- **Arrow Keys** - Navigate menus
- **Enter** - Select menu item
- **Tab** - Switch focus (menus/log window)

### During Operations
- **v / V** - Toggle between progress bar and block map views

### Confirmations
- **y / Y** - Yes/Confirm
- **n / N / q / Q / ESC** - No/Cancel

### Log Window (when focused)
- **↑ / ↓** - Scroll line by line
- **PgUp / PgDn** - Scroll page by page
- **Home / End** - Jump to top/bottom

---

## BLOCK MAP LEGEND

**Characters:**
- **·** (dot) = Pending blocks (not yet processed)
- **▒** (medium shade) = Currently writing
- **█** (solid block) = Completed successfully
- **X** = Error during read/write

**Colors:**
- Green on Blue = Normal operations
- White on Red = Errors

---

## TYPICAL WORKFLOW

### Creating a Backup
1. Select "Backup Disk" from main menu
2. Choose source device
3. Select compression type (or none)
4. Choose block size (or use auto-detected optimal size)
5. Enter output directory and filename
6. Confirm operation
7. Operation runs with real-time visualization
8. Partition table automatically saved
9. Choose checksum algorithm (MD5, SHA-256, both, or skip)

### Restoring an Image
1. Select "Restore Disk" from main menu
2. Enter directory containing images
3. Select image file
4. Auto-detected checksum verified (if available)
5. Choose target device
6. Confirm operation
7. Operation runs with real-time visualization

### Cloning a Disk
1. Select "Clone Disk" from main menu
2. Choose source device
3. Choose target device
4. Select block size
5. Confirm operation
6. Operation runs with block map visualization

---

## SAFETY TIPS

⚠️ **ALWAYS double-check source and target devices before confirming**
⚠️ **Backup important data before any disk operations**
⚠️ **Verify checksums when restoring critical images**
⚠️ **Unmount filesystems before imaging (DDI does this automatically)**
⚠️ **Pay attention to SMART warnings - they indicate drive problems**

---

## HISTORY: THE dd COMMAND

The dd command is one of Unix's classic utilities, dating back to the early days of Unix development in the 1970s at Bell Labs.

The name "dd" stands for "convert and copy" - though that's not immediately obvious from the letters themselves. The naming comes from the IBM Job Control Language (JCL) convention, where DD stood for "Data Definition." The Unix developers borrowed this naming pattern, and dd became the command for low-level data conversion and copying operations.

There's also a bit of Unix humor/folklore around the name. Some people joke that it stands for "disk destroyer" or "data destroyer" because of how easily you can overwrite the wrong disk or partition if you mix up the if= (input file) and of= (output file) parameters. One typo with dd can wipe out an entire drive!

The command's syntax is notably different from most Unix commands - instead of using the typical - flags, it uses a key=value format (like if=/dev/sda of=/dev/sdb bs=4M), which again reflects its JCL heritage rather than the Unix convention that evolved later.

Despite being somewhat dangerous and having an unusual syntax, dd remains widely used today for tasks like creating disk images, writing bootable USB drives, benchmarking disk performance, and low-level data recovery.
