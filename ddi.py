#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import curses
import logging
import os
import re
import subprocess
import sys
import time
from textwrap import wrap

# --- Configuration ---
VERSION = "1.0.0"
APP_NAME = "DD Interface"
APP_DESCRIPTION = "Professional Disk Imaging Tool"

# Block size for dd command
BS = "64K"
# Options for dd command
DD_OPTS = f"conv=sync,noerror bs={BS}"
LOG_FILE = "ddi.log"

# --- Global logging object ---
log = logging.getLogger(__name__)

# --- Helper Functions ---

def check_root():
    """Exit if the script is not run as root."""
    if os.geteuid() != 0:
        print("❌ This script requires root privileges. Please run with 'sudo'.")
        sys.exit(1)

def detect_optimal_block_size(device):
    """Detect optimal block size for a device based on physical and logical sector sizes."""
    try:
        # Get physical block size (optimal I/O size)
        phys_cmd = f"sudo blockdev --getpbsz {device}"
        phys_result = subprocess.run(phys_cmd.split(), capture_output=True, text=True)
        phys_size = int(phys_result.stdout.strip()) if phys_result.returncode == 0 else None
        
        # Get logical block size
        log_cmd = f"sudo blockdev --getss {device}"
        log_result = subprocess.run(log_cmd.split(), capture_output=True, text=True)
        log_size = int(log_result.stdout.strip()) if log_result.returncode == 0 else None
        
        # Get optimal I/O size if available
        opt_cmd = f"sudo blockdev --getioopt {device}"
        opt_result = subprocess.run(opt_cmd.split(), capture_output=True, text=True)
        if opt_result.returncode == 0:
            opt_size = int(opt_result.stdout.strip()) if opt_result.stdout.strip() else 0
        else:
            opt_size = None
            log.warning(f"Could not get optimal I/O size for {device}: {opt_result.stderr}")
        
        # Also try to get from fdisk as it sometimes reports different/additional info
        fdisk_opt_size = None
        try:
            fdisk_cmd = f"sudo fdisk -l {device}"
            fdisk_result = subprocess.run(fdisk_cmd.split(), capture_output=True, text=True, timeout=5)
            if fdisk_result.returncode == 0:
                for line in fdisk_result.stdout.split('\n'):
                    if 'I/O size' in line and 'optimal' in line:
                        # Parse line like: "I/O size (minimum/optimal): 512 bytes / 512 bytes"
                        if ':' in line and '/' in line:
                            # Split by colon to get the values part
                            values_part = line.split(':')[1].strip()
                            # Split by / to separate minimum and optimal
                            parts = values_part.split('/')
                            if len(parts) >= 2:
                                # Extract the optimal part (second value)
                                optimal_part = parts[1].strip()
                                # Extract just the number (remove "bytes" and any other text)
                                import re
                                match = re.search(r'(\d+)', optimal_part)
                                if match:
                                    fdisk_opt_size = int(match.group(1))
                                    log.info(f"fdisk reports optimal I/O size: {fdisk_opt_size}")
                                    break
        except Exception as e:
            log.warning(f"Could not parse fdisk output for {device}: {e}")
        
        # Use fdisk value if blockdev didn't report one
        if (not opt_size or opt_size == 0) and fdisk_opt_size:
            opt_size = fdisk_opt_size
            log.info(f"Using optimal I/O size from fdisk: {opt_size}")
        
        log.info(f"Block size detection for {device}: logical={log_size}, physical={phys_size}, optimal={opt_size}")
        
        # Determine recommended block size
        # Priority: optimal I/O size > physical > logical, but cap at reasonable values
        if opt_size and opt_size > 0 and opt_size <= 1048576:  # Max 1M
            recommended = opt_size
        elif phys_size and phys_size >= 4096:
            recommended = max(phys_size, 65536)  # At least 64K for modern drives
        elif log_size and log_size >= 4096:
            recommended = 65536  # Default to 64K for 4K native drives
        else:
            recommended = 65536  # Safe default
        
        # Format for display
        if recommended >= 1048576:
            recommended_str = f"{recommended // 1048576}M"
        elif recommended >= 1024:
            recommended_str = f"{recommended // 1024}K"
        else:
            recommended_str = str(recommended)
        
        return {
            'logical': log_size,
            'physical': phys_size,
            'optimal': opt_size,
            'recommended': recommended,
            'recommended_str': recommended_str
        }
    except Exception as e:
        log.warning(f"Could not detect block size for {device}: {e}")
        return None

def get_block_size_choice(stdscr, app_h, operation_type="operation", device=None):
    """Display block size selection menu and return selected block size."""
    
    # Detect optimal block size if device provided
    detected = None
    if device:
        detected = detect_optimal_block_size(device)
    
    if detected:
        # Format optimal I/O size for display
        if detected['optimal'] and detected['optimal'] > 0:
            opt_str = f"{detected['optimal']} bytes"
        else:
            opt_str = "Not reported by drive"
        
        # Show detection information first
        show_message_box(stdscr, "Drive Alignment Detection", [
            f"Device: {device}",
            "",
            f"Logical sector size:  {detected['logical']} bytes",
            f"Physical sector size: {detected['physical']} bytes",
            f"Optimal I/O size:     {opt_str}",
            "",
            "",
            f"Recommended block size: {detected['recommended_str']}",
            "(Selected for optimal alignment and performance)"
        ], app_h)
        
        block_size_options = [
            f"{detected['recommended_str']} - RECOMMENDED for alignment (detected)",
            "512 bytes - Traditional sector size, slowest",
            "4K - Modern sector size, good balance",
            "64K - Fast for most drives",
            "1M - Fastest for large sequential operations"
        ]
    else:
        block_size_options = [
            "64K - Recommended default",
            "512 bytes - Traditional sector size, slowest",
            "4K - Modern sector size, good balance",
            "1M - Fastest for large sequential operations"
        ]
    
    bs_idx = get_menu_choice(stdscr, f"Select Block Size for {operation_type}", 
                             block_size_options, app_h)
    if bs_idx == -1:
        return None  # User cancelled
    
    # Map selection to actual block size
    if detected:
        block_sizes = [detected['recommended_str'], "512", "4K", "64K", "1M"]
    else:
        block_sizes = ["64K", "512", "4K", "1M"]
    
    return block_sizes[bs_idx]

def get_devices():
    """Get a list of block devices using lsblk, including their size in bytes."""
    try:
        cmd = "lsblk -d -b -n -o NAME,SIZE,MODEL"
        output = subprocess.check_output(cmd.split(), text=True).strip()
        devices = []
        for line in output.split('\n'):
            if not line: continue
            parts = line.split(maxsplit=2)
            if len(parts) < 2: continue
            
            name = f"/dev/{parts[0]}"
            # Skip loop devices as they're not useful for disk imaging
            if name.startswith('/dev/loop'): continue
            
            size_bytes = int(parts[1])
            model = parts[2].strip() if len(parts) > 2 else "N/A"
            size_str = format_bytes(size_bytes)
            
            devices.append({'name': name, 'size': size_str, 'model': model, 'bytes': size_bytes})
        log.info(f"Found {len(devices)} suitable devices.")
        return devices
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log.error(f"Failed to get devices: {e}")
        return []

def get_image_files(extension, directory='.'):
    """Scans the specified directory for files with a given extension."""
    try:
        files = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f)) and f.endswith(extension)]
        return sorted(files)
    except OSError as e:
        log.error(f"Cannot read directory: {e}")
        return []

def get_uncompressed_size(gz_path):
    """Get the uncompressed size of a .gz file."""
    try:
        cmd = ["gzip", "-l", gz_path]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        lines = result.stdout.strip().split('\n')
        if len(lines) > 1: return int(lines[1].split()[1])
    except (subprocess.CalledProcessError, FileNotFoundError, IndexError, ValueError) as e:
        log.error(f"Could not get uncompressed size for {gz_path}: {e}")
        return 0
    return 0

def check_smart_status(device):
    """Check SMART status of a device and return detailed diagnostics."""
    try:
        # First check if SMART is supported and enabled
        cmd = ["sudo", "smartctl", "-i", device]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode != 0 and "SMART support is: Unavailable" in result.stdout:
            log.info(f"SMART not supported on {device}")
            return None, {
                'status': 'unavailable',
                'message': 'SMART not supported on this device',
                'details': []
            }
        
        # Get health status
        cmd = ["sudo", "smartctl", "-H", device]
        health_result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        # Get detailed attributes
        cmd = ["sudo", "smartctl", "-A", device]
        attr_result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        # Parse health status
        health_passed = "PASSED" in health_result.stdout
        
        # Parse critical attributes
        attributes = {
            'reallocated_sectors': 0,
            'pending_sectors': 0,
            'uncorrectable_sectors': 0,
            'temperature': 0,
            'power_on_hours': 0,
            'spin_retry_count': 0
        }
        
        details = []
        for line in attr_result.stdout.split('\n'):
            # Parse SMART attribute lines
            # Format: ID# ATTRIBUTE_NAME FLAG VALUE WORST THRESH TYPE UPDATED WHEN_FAILED RAW_VALUE
            parts = line.split()
            if len(parts) < 10:
                continue
            
            try:
                attr_id = parts[0]
                attr_name = parts[1]
                raw_value = parts[9]
                
                # Reallocated Sector Count (5)
                if attr_id == '5' or 'Reallocated' in attr_name:
                    attributes['reallocated_sectors'] = int(raw_value)
                    details.append(f"Reallocated Sectors: {raw_value}")
                    
                # Current Pending Sector Count (197)
                elif attr_id == '197' or 'Current_Pending' in attr_name:
                    attributes['pending_sectors'] = int(raw_value)
                    details.append(f"Pending Sectors: {raw_value}")
                    
                # Offline Uncorrectable (198)
                elif attr_id == '198' or 'Offline_Uncorrectable' in attr_name:
                    attributes['uncorrectable_sectors'] = int(raw_value)
                    details.append(f"Uncorrectable Sectors: {raw_value}")
                    
                # Temperature (190, 194)
                elif attr_id in ['190', '194'] or 'Temperature' in attr_name:
                    if attributes['temperature'] == 0:
                        attributes['temperature'] = int(raw_value.split()[0])
                        details.append(f"Temperature: {raw_value.split()[0]}°C")
                        
                # Power On Hours (9)
                elif attr_id == '9' or 'Power_On_Hours' in attr_name:
                    attributes['power_on_hours'] = int(raw_value)
                    details.append(f"Power On Hours: {raw_value}")
                    
                # Spin Retry Count (10)
                elif attr_id == '10' or 'Spin_Retry' in attr_name:
                    attributes['spin_retry_count'] = int(raw_value)
                    if int(raw_value) > 0:
                        details.append(f"Spin Retry Count: {raw_value}")
            except (ValueError, IndexError):
                continue
        
        # Determine overall status
        critical_issues = []
        warnings = []
        
        if not health_passed:
            critical_issues.append("SMART Health Test: FAILED")
        
        if attributes['reallocated_sectors'] and attributes['reallocated_sectors'] > 0:
            critical_issues.append(f"Reallocated sectors detected: {attributes['reallocated_sectors']}")
            
        if attributes['pending_sectors'] and attributes['pending_sectors'] > 0:
            critical_issues.append(f"Pending sectors detected: {attributes['pending_sectors']}")
            
        if attributes['uncorrectable_sectors'] and attributes['uncorrectable_sectors'] > 0:
            critical_issues.append(f"Uncorrectable sectors detected: {attributes['uncorrectable_sectors']}")
            
        if attributes['spin_retry_count'] and attributes['spin_retry_count'] > 0:
            warnings.append(f"Spin retry events: {attributes['spin_retry_count']}")
        
        # Determine final status
        if critical_issues:
            status = 'failed'
            message = "CRITICAL: Drive has problems"
        elif warnings:
            status = 'warning'
            message = "WARNING: Drive shows minor issues"
        else:
            status = 'passed'
            message = "PASSED: Drive appears healthy"
        
        log.info(f"SMART check for {device}: {status.upper()} - {message}")
        log.info(f"Details: {details}")
        
        return (status == 'passed'), {
            'status': status,
            'message': message,
            'details': details,
            'critical_issues': critical_issues,
            'warnings': warnings,
            'health_passed': health_passed,
            'attributes': attributes
        }
        
    except FileNotFoundError:
        log.warning(f"smartctl not found")
        return None, {
            'status': 'unavailable',
            'message': 'smartctl utility not installed',
            'details': ['Install smartmontools package']
        }
    except Exception as e:
        log.warning(f"Could not run SMART check for {device}: {e}")
        return None, {
            'status': 'error',
            'message': f'Error running SMART check: {str(e)}',
            'details': []
        }

def show_smart_results(stdscr, device_name, smart_ok, smart_info, app_h):
    """Display detailed SMART check results."""
    if smart_ok is None:
        # SMART not available
        show_message_box(stdscr, "SMART Status Unavailable", [
            f"Device: {device_name}",
            "",
            smart_info['message'],
            "",
            "Cannot determine drive health.",
            "Proceed with caution."
        ] + smart_info['details'], app_h)
        return True  # Allow to continue
    
    if smart_ok:
        # SMART passed - show brief confirmation with key stats
        msg_lines = [
            f"Device: {device_name}",
            "",
            "✓ " + smart_info['message'],
            ""
        ] + smart_info['details']
        
        show_message_box(stdscr, "SMART Health Check: PASSED", msg_lines, app_h)
        return True
    else:
        # SMART failed - show detailed warning
        msg_lines = [
            f"Device: {device_name}",
            "",
            "✗ " + smart_info['message'],
            ""
        ]
        
        if smart_info.get('critical_issues'):
            msg_lines.append("CRITICAL ISSUES:")
            for issue in smart_info['critical_issues']:
                msg_lines.append(f"  • {issue}")
            msg_lines.append("")
        
        if smart_info.get('warnings'):
            msg_lines.append("WARNINGS:")
            for warning in smart_info['warnings']:
                msg_lines.append(f"  • {warning}")
            msg_lines.append("")
        
        if smart_info.get('details'):
            msg_lines.append("Drive Statistics:")
            for detail in smart_info['details']:
                msg_lines.append(f"  {detail}")
            msg_lines.append("")
        
        msg_lines.append("This drive may be failing or have errors.")
        msg_lines.append("Using it may result in data loss.")
        
        show_message_box(stdscr, "SMART Health Check: FAILED", msg_lines, app_h)
        
        # Ask if they want to continue
        return show_confirmation(stdscr, "Continue Despite SMART Failure?", [
            "The drive has SMART failures.",
            "Continuing may result in data corruption or loss.",
            "",
            "Continue anyway? (Not recommended)"
        ], app_h)

def is_device_mounted(device):
    """Check if a device or any of its partitions are mounted."""
    try:
        with open('/proc/mounts', 'r') as f:
            mounts = f.read()
        # Check if device or any partition (e.g., /dev/sda, /dev/sda1) is mounted
        for line in mounts.split('\n'):
            if not line.strip():
                continue
            mount_info = line.split()
            if len(mount_info) < 2:
                continue
            
            # Check only the first field (device field) in /proc/mounts
            mounted_device = mount_info[0]
            
            # Check if this line is about our device or one of its partitions
            # Must match exactly or be a partition (e.g., /dev/sda matches /dev/sda1)
            if mounted_device == device or mounted_device.startswith(device):
                mount_point = mount_info[1]
                log.warning(f"Device {mounted_device} is mounted at {mount_point}")
                return True, mount_point
        
        return False, None
    except Exception as e:
        log.error(f"Could not check mount status for {device}: {e}")
        return None, None

def unmount_device(device):
    """Unmount all partitions of a device."""
    try:
        with open('/proc/mounts', 'r') as f:
            mounts = f.read()
        
        mounted_partitions = []
        for line in mounts.split('\n'):
            if not line.strip():
                continue
            mount_info = line.split()
            if len(mount_info) < 2:
                continue
            
            mounted_device = mount_info[0]
            mount_point = mount_info[1]
            
            # Collect all partitions of this device
            if mounted_device == device or mounted_device.startswith(device):
                mounted_partitions.append((mounted_device, mount_point))
        
        if not mounted_partitions:
            log.info(f"No mounted partitions found for {device}")
            return True, "No partitions were mounted"
        
        # Unmount all partitions
        failed_unmounts = []
        for partition, mount_point in mounted_partitions:
            log.info(f"Unmounting {partition} from {mount_point}")
            result = subprocess.run(['sudo', 'umount', partition], 
                                  capture_output=True, text=True)
            if result.returncode != 0:
                log.error(f"Failed to unmount {partition}: {result.stderr}")
                failed_unmounts.append(partition)
            else:
                log.info(f"Successfully unmounted {partition}")
        
        if failed_unmounts:
            return False, f"Failed to unmount: {', '.join(failed_unmounts)}"
        
        # After unmounting, check if device is still accessible
        # Some systems auto-eject removable media after unmounting
        time.sleep(1)  # Give system time to settle
        try:
            result = subprocess.run(['sudo', 'blockdev', '--getsize64', device],
                                  capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                log.warning(f"Device {device} may have been ejected after unmount")
                return False, (f"Unmounted {len(mounted_partitions)} partition(s), "
                             f"but device appears to be ejected. "
                             f"Try re-inserting the device without mounting it.")
        except Exception as e:
            log.warning(f"Could not verify device accessibility: {e}")
        
        return True, f"Unmounted {len(mounted_partitions)} partition(s)"
    
    except Exception as e:
        log.error(f"Exception during unmount: {e}")
        return False, str(e)

def test_ssh_connection(host, user, port=22):
    """Test SSH connection to remote host."""
    try:
        cmd = ["ssh", "-p", str(port), "-o", "ConnectTimeout=5",
               "-o", "BatchMode=yes", f"{user}@{host}", "echo", "SSH_OK"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and "SSH_OK" in result.stdout:
            log.info(f"SSH connection to {user}@{host}:{port} successful")
            return True, "Connection successful"
        else:
            log.error(f"SSH connection to {user}@{host}:{port} failed")
            return False, result.stderr.strip() if result.stderr else "Connection failed"
    except subprocess.TimeoutExpired:
        log.error(f"SSH connection to {user}@{host}:{port} timed out")
        return False, "Connection timeout"
    except Exception as e:
        log.error(f"SSH connection error: {e}")
        return False, str(e)

def check_nfs_mount(nfs_path):
    """Check if NFS path is accessible."""
    try:
        # Parse NFS path (server:/path)
        if ':' not in nfs_path:
            return False, "Invalid NFS path format (expected server:/path)"
        
        server, path = nfs_path.split(':', 1)
        cmd = ["showmount", "-e", server]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            log.info(f"NFS server {server} is accessible")
            return True, "NFS server accessible"
        else:
            log.error(f"NFS server {server} not accessible")
            return False, result.stderr.strip() if result.stderr else "Server not accessible"
    except subprocess.TimeoutExpired:
        return False, "Connection timeout"
    except Exception as e:
        log.error(f"NFS check error: {e}")
        return False, str(e)

def check_free_space(path, required_bytes):
    """Check if there is enough free space at the given path."""
    try:
        stat = os.statvfs(path)
        free_bytes = stat.f_bavail * stat.f_frsize
        free_str = format_bytes(free_bytes)
        required_str = format_bytes(required_bytes)
        
        if free_bytes >= required_bytes:
            log.info(f"Free space check: {free_str} available, {required_str} required - OK")
            return True, free_str, required_str
        else:
            log.warning(f"Free space check: {free_str} available, {required_str} required - INSUFFICIENT")
            return False, free_str, required_str
    except Exception as e:
        log.error(f"Could not check free space: {e}")
        return None, "Unknown", format_bytes(required_bytes)

def generate_filename(base_name, device_name, extension):
    """Generate a filename with timestamp and device info."""
    from datetime import datetime
    import socket
    
    # Extract device name (e.g., /dev/sda -> sda)
    device_short = device_name.replace('/dev/', '').replace('/', '_')
    
    # Get current timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Build filename
    if base_name:
        filename = f"{base_name}_{device_short}_{timestamp}{extension}"
    else:
        # Use hostname instead of "disk" prefix
        hostname = socket.gethostname()
        filename = f"{hostname}_{device_short}_{timestamp}{extension}"
    
    log.info(f"Generated filename: {filename}")
    return filename

# --- Curses Logging Handler ---

class CursesHandler(logging.Handler):
    def __init__(self, screen_pad):
        super().__init__()
        self.screen_pad = screen_pad
        self.log_messages = []
        self.stdscr = None  # Will be set to main stdscr for proper refresh
        self.log_win_height = 8  # Default log window height
        self.scroll_pos = 0  # Current scroll position for log window

    def set_stdscr(self, stdscr):
        """Set the main screen reference for proper log window positioning."""
        self.stdscr = stdscr
    
    def set_log_height(self, height):
        """Set the log window height."""
        self.log_win_height = height

    def emit(self, record):
        msg = self.format(record)
        self.log_messages.append(msg)
        
        # Redraw the pad with new message
        h, w = self.screen_pad.getmaxyx()
        self.screen_pad.clear()
        
        start_line = max(0, len(self.log_messages) - (h - 1))
        for i, line in enumerate(self.log_messages[start_line:]):
            self.screen_pad.addstr(i, 0, line[:w-1])
        
        # Refresh the log window area if we have screen reference
        if self.stdscr:
            try:
                main_h, main_w = self.stdscr.getmaxyx()
                log_win_height = 8  # Same as in main function
                log_win_y = main_h - log_win_height
                self.screen_pad.refresh(start_line, 0, log_win_y + 1, 2, main_h - 2, main_w - 3)
            except:
                pass  # Ignore refresh errors

def setup_logging(curses_pad, stdscr=None):
    """Configures file and curses logging."""
    log.setLevel(logging.INFO)
    
    # File Handler
    file_handler = logging.FileHandler(LOG_FILE)
    file_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_format)
    log.addHandler(file_handler)
    
    # Curses Handler
    curses_handler = CursesHandler(curses_pad)
    curses_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    curses_handler.setFormatter(curses_format)
    if stdscr:
        curses_handler.set_stdscr(stdscr)
    log.addHandler(curses_handler)
    
    return curses_handler

# --- Curses UI Components (Clonezilla Style) ---

def init_colors():
    """Initializes color pairs for the Clonezilla theme."""
    curses.start_color()
    curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLUE)
    curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_CYAN)
    curses.init_pair(3, curses.COLOR_BLUE, curses.COLOR_WHITE)
    curses.init_pair(4, curses.COLOR_WHITE, curses.COLOR_RED)
    curses.init_pair(5, curses.COLOR_YELLOW, curses.COLOR_BLUE)
    curses.init_pair(6, curses.COLOR_GREEN, curses.COLOR_BLUE)
    curses.init_pair(7, curses.COLOR_GREEN, curses.COLOR_BLACK)

def draw_main_layout(stdscr, title, log_pad, log_win_height, log_focused=False):
    """Draws the main background, title, and log window."""
    try:
        h, w = stdscr.getmaxyx()
    except Exception as e:
        log.error(f"Failed to get screen size: {e}")
        raise
    app_h = h - log_win_height
    
    # Clear entire screen and redraw background
    stdscr.clear()
    stdscr.bkgd(' ', curses.color_pair(1))
    
    # Draw header with version
    header = f"{APP_NAME} v{VERSION} - {title}"
    version_info = f"[{APP_DESCRIPTION}]"
    stdscr.attron(curses.color_pair(5) | curses.A_BOLD)
    stdscr.addstr(0, 2, header[:w-len(version_info)-5])
    stdscr.attroff(curses.color_pair(5) | curses.A_BOLD)
    # Add version info on the right
    stdscr.attron(curses.color_pair(5))
    stdscr.addstr(0, w - len(version_info) - 2, version_info)
    stdscr.attroff(curses.color_pair(5))
    stdscr.hline(1, 1, curses.ACS_HLINE, w - 2)
    
    # Fill the main area with background color
    for y in range(2, app_h - 1):
        stdscr.hline(y, 0, ' ', w)
    
    # Log window border and title
    log_win_y = h - log_win_height
    stdscr.hline(log_win_y, 1, curses.ACS_HLINE, w - 2)
    # Show focus indicator
    if log_focused:
        stdscr.addstr(log_win_y, 3, " LOG [FOCUSED - Use ↑↓/PgUp/PgDn to scroll, Tab to return] ", 
                     curses.A_BOLD | curses.color_pair(6))
    else:
        stdscr.addstr(log_win_y, 3, " LOG [Tab to focus] ", curses.A_BOLD)
    
    # Add keyboard shortcuts footer
    footer_y = h - 1
    shortcuts = "↑↓:Navigate | Enter:Select | Esc:Back | Tab:Log | F1:Help | q:Quit"
    stdscr.addstr(footer_y, 2, shortcuts[:w-4], curses.color_pair(5))
    
    # Refresh the visible part of the log pad
    pad_h, _ = log_pad.getmaxyx()
    # Get the curses handler to access log messages
    curses_handler = None
    for handler in log.handlers:
        if isinstance(handler, CursesHandler):
            curses_handler = handler
            break
    if curses_handler:
        pad_start_line = max(0, len(curses_handler.log_messages) - (log_win_height - 2))
    else:
        pad_start_line = 0
    log_pad.refresh(pad_start_line, 0, log_win_y + 1, 2, h - 2, w - 3)
    
    stdscr.refresh()
    return app_h # Return height available for dialogs

def refresh_log_window(stdscr):
    """Refresh the log window to ensure it's always visible."""
    # Get the curses handler to access log messages
    curses_handler = None
    for handler in log.handlers:
        if isinstance(handler, CursesHandler):
            curses_handler = handler
            break
    
    if curses_handler and curses_handler.stdscr:
        try:
            h, w = stdscr.getmaxyx()
            log_win_height = curses_handler.log_win_height
            log_win_y = h - log_win_height
            pad_start_line = max(0, len(curses_handler.log_messages) - (log_win_height - 2))
            curses_handler.screen_pad.refresh(pad_start_line, 0, log_win_y + 1, 2, h - 2, w - 3)
        except Exception as e:
            # Don't crash if refresh fails - just skip it
            pass

def draw_bordered_window(stdscr, y, x, h, w, title):
    """Draws a bordered window (dialog box)."""
    win = stdscr.derwin(h, w, y, x)
    win.clear()
    win.bkgd(' ', curses.color_pair(2))
    win.box()
    win.addstr(0, 2, f" {title} ", curses.A_BOLD)
    return win

def handle_log_scroll_keys(stdscr, key, log_win_height):
    """Handle scrolling keys for the log window."""
    # Get the curses handler to access log messages and pad
    curses_handler = None
    for handler in log.handlers:
        if isinstance(handler, CursesHandler):
            curses_handler = handler
            break
    
    if not curses_handler:
        return
    
    h, w = stdscr.getmaxyx()
    log_win_y = h - log_win_height
    total_lines = len(curses_handler.log_messages)
    visible_lines = log_win_height - 2
    
    # Get current scroll position from handler or calculate default
    if not hasattr(curses_handler, 'scroll_pos'):
        curses_handler.scroll_pos = max(0, total_lines - visible_lines)
    
    scroll_pos = curses_handler.scroll_pos
    
    # Handle scrolling
    if key == curses.KEY_UP:
        scroll_pos = max(0, scroll_pos - 1)
    elif key == curses.KEY_DOWN:
        scroll_pos = min(max(0, total_lines - visible_lines), scroll_pos + 1)
    elif key == curses.KEY_PPAGE:  # Page Up
        scroll_pos = max(0, scroll_pos - visible_lines)
    elif key == curses.KEY_NPAGE:  # Page Down
        scroll_pos = min(max(0, total_lines - visible_lines), scroll_pos + visible_lines)
    elif key == curses.KEY_HOME:  # Home - jump to top
        scroll_pos = 0
    elif key == curses.KEY_END:  # End - jump to bottom
        scroll_pos = max(0, total_lines - visible_lines)
    
    # Save scroll position
    curses_handler.scroll_pos = scroll_pos
    
    # Refresh log window at new scroll position
    curses_handler.screen_pad.refresh(scroll_pos, 0, log_win_y + 1, 2, h - 2, w - 3)

def get_menu_choice(stdscr, title, menu_items, app_h):
    """Displays a menu in a centered, bordered window."""
    if not menu_items: return -1
    h, w = stdscr.getmaxyx()
    menu_height = len(menu_items) + 4
    menu_width = max(len(s) for s in menu_items) + 8
    menu_width = max(menu_width, len(title) + 5, 60)
    
    # Center within the app area (above log section)
    start_y = (app_h - menu_height) // 2
    start_x = (w - menu_width) // 2
    
    win = draw_bordered_window(stdscr, start_y, start_x, menu_height, menu_width, title)
    win_deleted = False  # Track if window was deleted
    
    # Ensure log is visible
    refresh_log_window(stdscr)
    
    current_row = 0
    log_focused = False  # Track if log window has focus
    
    while True:
        # Recreate win if it was deleted (after help screen or certain returns)
        if win_deleted:
            win = draw_bordered_window(stdscr, start_y, start_x, menu_height, menu_width, title)
            win_deleted = False
        
        # Clear the window content area before redrawing
        for i in range(2, menu_height - 2):
            win.hline(i, 1, ' ', menu_width - 2)
        
        for i, item in enumerate(menu_items):
            style = curses.color_pair(3) if i == current_row else curses.color_pair(2)
            # Show number for items 1-9
            if i < 9:
                number_str = f"[{i+1}] "
                win.addstr(i + 2, 3, number_str, style | curses.A_BOLD)
                win.addstr(i + 2, 3 + len(number_str), item.ljust(menu_width - 6 - len(number_str)), style)
            else:
                win.addstr(i + 2, 3, item.ljust(menu_width - 6), style)
        
        # Update log window border to show focus state
        log_win_height = 8
        log_win_y = h - log_win_height
        stdscr.hline(log_win_y, 1, curses.ACS_HLINE, w - 2)
        if log_focused:
            stdscr.addstr(log_win_y, 3, " LOG [FOCUSED - Use ↑↓/PgUp/PgDn to scroll, Tab to return] ", 
                         curses.A_BOLD | curses.color_pair(6))
        else:
            stdscr.addstr(log_win_y, 3, " LOG [Press Tab to focus] ", curses.A_BOLD)
        
        win.refresh()
        stdscr.refresh()
        key = stdscr.getch()

        if log_focused:
            # Handle log scrollback when log is focused
            if key == 9 or key == 27:  # Tab or ESC - return to menu
                log_focused = False
                # Reset scroll position to bottom when returning to menu
                curses_handler = None
                for handler in log.handlers:
                    if isinstance(handler, CursesHandler):
                        curses_handler = handler
                        break
                if curses_handler:
                    total_lines = len(curses_handler.log_messages)
                    visible_lines = log_win_height - 2
                    curses_handler.scroll_pos = max(0, total_lines - visible_lines)
                refresh_log_window(stdscr)
            else:
                # Handle log scrolling
                handle_log_scroll_keys(stdscr, key, log_win_height)
        else:
            # Handle menu navigation when menu is focused
            if key == curses.KEY_UP and current_row > 0: current_row -= 1
            elif key == curses.KEY_DOWN and current_row < len(menu_items) - 1: current_row += 1
            # Handle number keys 1-9 for quick selection
            elif key >= ord('1') and key <= ord('9'):
                num = key - ord('1')  # Convert to 0-based index
                if num < len(menu_items):
                    # Clean up window before returning
                    try:
                        win.clear()
                        win.refresh()
                        del win
                        win_deleted = True
                    except:
                        pass
                    stdscr.refresh()
                    return num
            # Handle 'q' or 'Q' for quit (same as ESC)
            elif key in [ord('q'), ord('Q')]:
                # Clean up window before returning
                try:
                    del win
                except:
                    pass
                stdscr.touchwin()
                stdscr.refresh()
                refresh_log_window(stdscr)
                return -1
            # Handle F1 or '?' for help
            elif key == curses.KEY_F1 or key == ord('?'):
                log.info(f"F1 pressed! key={key}, KEY_F1={curses.KEY_F1}")
                show_help_screen(stdscr, app_h)
                log.info("Returned from help screen")
                # Force complete redraw of all windows behind the help screen
                # Clear and redraw the entire screen background
                stdscr.clear()
                stdscr.bkgd(' ', curses.color_pair(1))
                
                # Redraw header with version
                header = f"{APP_NAME} v{VERSION}"
                version_info = f"[{APP_DESCRIPTION}]"
                try:
                    stdscr.attron(curses.color_pair(5) | curses.A_BOLD)
                    stdscr.addstr(0, 2, header[:w-len(version_info)-5])
                    stdscr.attroff(curses.color_pair(5) | curses.A_BOLD)
                    stdscr.attron(curses.color_pair(5))
                    stdscr.addstr(0, w - len(version_info) - 2, version_info)
                    stdscr.attroff(curses.color_pair(5))
                    stdscr.hline(1, 1, curses.ACS_HLINE, w - 2)
                except:
                    pass
                
                # Fill the main area with background color
                for y in range(2, app_h - 1):
                    try:
                        stdscr.hline(y, 0, ' ', w)
                    except:
                        pass
                
                # Redraw log window border and title
                log_win_height = 8
                log_win_y = h - log_win_height
                try:
                    stdscr.hline(log_win_y, 1, curses.ACS_HLINE, w - 2)
                    stdscr.addstr(log_win_y, 3, " LOG [Tab to focus] ", curses.A_BOLD)
                except:
                    pass
                
                # Redraw footer
                try:
                    footer_y = h - 1
                    shortcuts = "↑↓:Navigate | Enter:Select | Esc:Back | Tab:Log | F1:Help | q:Quit"
                    stdscr.addstr(footer_y, 2, shortcuts[:w-4], curses.color_pair(5))
                except:
                    pass
                
                stdscr.refresh()
                
                # Completely redraw the menu window
                try:
                    win.clear()
                    win.bkgd(' ', curses.color_pair(2))
                    win.box()
                    win.addstr(0, 2, f" {title} ", curses.A_BOLD)
                    win.touchwin()
                    win.refresh()
                except:
                    # If win was deleted, recreate it
                    win = draw_bordered_window(stdscr, start_y, start_x, menu_height, menu_width, title)
                
                # Refresh the log window content
                refresh_log_window(stdscr)
                log.info("Complete screen redraw after help")
                continue
            # Handle F12 for about/easter egg
            elif key == curses.KEY_F12:
                log.info(f"F12 pressed! key={key}, KEY_F12={curses.KEY_F12}")
                show_about_screen(stdscr, app_h)
                log.info("Returned from about screen")
                # Force complete redraw of all windows behind the about screen
                # Clear and redraw the entire screen background
                stdscr.clear()
                stdscr.bkgd(' ', curses.color_pair(1))
                
                # Redraw header with version
                header = f"{APP_NAME} v{VERSION}"
                version_info = f"[{APP_DESCRIPTION}]"
                try:
                    stdscr.attron(curses.color_pair(5) | curses.A_BOLD)
                    stdscr.addstr(0, 2, header[:w-len(version_info)-5])
                    stdscr.attroff(curses.color_pair(5) | curses.A_BOLD)
                    stdscr.attron(curses.color_pair(5))
                    stdscr.addstr(0, w - len(version_info) - 2, version_info)
                    stdscr.attroff(curses.color_pair(5))
                    stdscr.hline(1, 1, curses.ACS_HLINE, w - 2)
                except:
                    pass
                
                # Fill the main area with background color
                for y in range(2, app_h - 1):
                    try:
                        stdscr.hline(y, 0, ' ', w)
                    except:
                        pass
                
                # Redraw log window border and title
                log_win_height = 8
                log_win_y = h - log_win_height
                try:
                    stdscr.hline(log_win_y, 1, curses.ACS_HLINE, w - 2)
                    stdscr.addstr(log_win_y, 3, " LOG [Tab to focus] ", curses.A_BOLD)
                except:
                    pass
                
                # Redraw footer
                try:
                    footer_y = h - 1
                    shortcuts = "↑↓:Navigate | Enter:Select | Esc:Back | Tab:Log | F1:Help | q:Quit"
                    stdscr.addstr(footer_y, 2, shortcuts[:w-4], curses.color_pair(5))
                except:
                    pass
                
                stdscr.refresh()
                
                # Completely redraw the menu window
                try:
                    win.clear()
                    win.bkgd(' ', curses.color_pair(2))
                    win.box()
                    win.addstr(0, 2, f" {title} ", curses.A_BOLD)
                    win.touchwin()
                    win.refresh()
                except:
                    # If win was deleted, recreate it
                    win = draw_bordered_window(stdscr, start_y, start_x, menu_height, menu_width, title)
                
                # Refresh the log window content
                refresh_log_window(stdscr)
                log.info("Complete screen redraw after about screen")
                continue
            # Handle mouse events
            elif key == curses.KEY_MOUSE:
                try:
                    _, mx, my, _, button_state = curses.getmouse()
                    
                    # Left click - select item and confirm (like Enter)
                    if button_state & curses.BUTTON1_CLICKED:
                        # Check if click is within menu window bounds
                        menu_item_y_start = start_y + 2
                        menu_item_y_end = start_y + 2 + len(menu_items)
                        
                        if start_x <= mx < start_x + menu_width and menu_item_y_start <= my < menu_item_y_end:
                            # Click is on a menu item
                            clicked_row = my - menu_item_y_start
                            if 0 <= clicked_row < len(menu_items):
                                # Clean up window before returning
                                win.clear()
                                win.refresh()
                                del win
                                stdscr.refresh()
                                return clicked_row
                    
                    # Right click - cancel (like ESC)
                    elif button_state & curses.BUTTON3_CLICKED:
                        # Clean up window before returning
                        del win
                        stdscr.touchwin()
                        stdscr.refresh()
                        refresh_log_window(stdscr)
                        return -1
                    
                    # Scroll wheel
                    elif button_state & curses.BUTTON4_PRESSED:
                        current_row = max(0, current_row - 1)
                    elif button_state & curses.BUTTON5_PRESSED:
                        current_row = min(len(menu_items) - 1, current_row + 1)
                except:
                    pass  # Ignore mouse errors
            elif key == 9:  # Tab key - switch to log window
                log_focused = True
            elif key == curses.KEY_ENTER or key in [10, 13]: 
                # Clean up window before returning
                del win
                stdscr.touchwin()
                stdscr.refresh()
                # Ensure log is visible after cleanup
                refresh_log_window(stdscr)
                return current_row
            elif key == 27: 
                # Clean up window before returning
                del win
                stdscr.touchwin()
                stdscr.refresh()
                # Ensure log is visible after cleanup
                refresh_log_window(stdscr)
                return -1

def get_input_string(stdscr, prompt, app_h, default_value="", show_path=None):
    """Displays a prompt for text input in a bordered window with optional default value."""
    _, w = stdscr.getmaxyx()
    
    # Calculate window height based on what we need to show
    extra_lines = 0
    if show_path:
        extra_lines += 1
    if default_value:
        extra_lines += 2
    
    win_h = 5 + extra_lines
    win_w = w - 20
        
    # Center within the app area (above log section)
    start_y, start_x = (app_h - win_h) // 2, (w - win_w) // 2
    
    win = draw_bordered_window(stdscr, start_y, start_x, win_h, win_w, prompt)
    
    line_y = 2
    
    # Show path if provided
    if show_path:
        win.addstr(line_y, 2, f"Path: {show_path[:win_w-9]}")
        line_y += 1
    
    # Show default value if provided
    if default_value:
        win.addstr(line_y, 2, f"Default: {default_value[:win_w-12]}")
        line_y += 1
        win.addstr(line_y, 2, "(Press Enter for default, or type new value)")
        line_y += 1
    
    win.addstr(line_y, 2, "> ")
    input_y = line_y
    input_x = 4
    
    # Completely disable mouse reporting at terminal level
    curses.mousemask(0)
    curses.flushinp()
    
    # Custom input handler that filters out mouse events
    curses.curs_set(1)
    input_str = ""
    cursor_pos = 0
    max_len = win_w - 8
    escape_seq = False  # Track if we're in an escape sequence
    
    win.refresh()
    
    while True:
        # Display current input
        win.move(input_y, input_x)
        win.clrtoeol()
        display_str = input_str[:max_len]
        win.addstr(input_y, input_x, display_str)
        win.move(input_y, input_x + cursor_pos)
        win.refresh()
        
        # Get key with non-blocking to detect escape sequences
        win.nodelay(False)  # Blocking mode
        key = win.getch()
        
        # Filter out mouse events (KEY_MOUSE and high values that might be scroll events)
        if key == curses.KEY_MOUSE:
            # Clear mouse event from queue
            try:
                curses.getmouse()
            except:
                pass
            continue
        
        # Filter out other potential mouse-related keys (scroll wheel generates these on some terminals)
        if key > 255 and key not in [curses.KEY_BACKSPACE, curses.KEY_DC, curses.KEY_LEFT, 
                                       curses.KEY_RIGHT, curses.KEY_HOME, curses.KEY_END]:
            continue
        
        # Detect start of escape sequence (mouse scroll often sends ESC [ sequences)
        if key == 27:  # ESC
            # Check if there's more input immediately following (part of escape sequence)
            win.nodelay(True)  # Non-blocking
            next_key = win.getch()
            win.nodelay(False)  # Back to blocking
            
            if next_key == 91 or next_key == 79:  # '[' or 'O' - start of escape sequence
                # Consume the rest of the escape sequence
                while True:
                    win.nodelay(True)
                    ch = win.getch()
                    win.nodelay(False)
                    if ch == -1:  # No more input
                        break
                    if 64 <= ch <= 126:  # End of escape sequence
                        break
                continue  # Skip this escape sequence
            elif next_key == -1:  # Just ESC key pressed alone
                input_str = ""
                break
            else:
                # Unknown escape sequence, consume it
                continue
        
        # Handle Enter
        if key in [10, 13, curses.KEY_ENTER]:
            break
        
        # Handle Backspace
        elif key in [curses.KEY_BACKSPACE, 127, 8]:
            if cursor_pos > 0:
                input_str = input_str[:cursor_pos-1] + input_str[cursor_pos:]
                cursor_pos -= 1
        
        # Handle Delete
        elif key == curses.KEY_DC:
            if cursor_pos < len(input_str):
                input_str = input_str[:cursor_pos] + input_str[cursor_pos+1:]
        
        # Handle Left Arrow
        elif key == curses.KEY_LEFT:
            if cursor_pos > 0:
                cursor_pos -= 1
        
        # Handle Right Arrow
        elif key == curses.KEY_RIGHT:
            if cursor_pos < len(input_str):
                cursor_pos += 1
        
        # Handle Home
        elif key == curses.KEY_HOME:
            cursor_pos = 0
        
        # Handle End
        elif key == curses.KEY_END:
            cursor_pos = len(input_str)
        
        # Handle printable characters
        elif 32 <= key <= 126:
            if len(input_str) < max_len:
                input_str = input_str[:cursor_pos] + chr(key) + input_str[cursor_pos:]
                cursor_pos += 1
    
    curses.curs_set(0)
    
    # Re-enable mouse events
    curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
    
    # If user just pressed Enter and there was a default, use the default
    if not input_str and default_value:
        input_str = default_value
    
    # Clean up window before returning
    del win
    stdscr.touchwin()
    stdscr.refresh()
    
    return input_str

def show_final_warning(stdscr, title, messages, app_h):
    """Displays a final warning dialog requiring specific user confirmation."""
    _, w = stdscr.getmaxyx()
    msg_lines = sum(len(wrap(msg, w - 26)) for msg in messages)
    win_h = msg_lines + 8
    win_w = max(len(s) for s in messages) + 6 if messages else 40
    win_w = max(win_w, 60)
    # Center within the app area (above log section)
    start_y, start_x = (app_h - win_h) // 2, (w - win_w) // 2

    win = draw_bordered_window(stdscr, start_y, start_x, win_h, win_w, title)
    
    # Always use the red 'danger' color scheme for final warnings
    win.bkgd(' ', curses.color_pair(4))
    win.box()
    win.addstr(0, 2, f" {title} ", curses.A_BOLD | curses.color_pair(4))
    
    y_offset = 2
    for msg in messages:
        for line in wrap(msg, win_w - 4):
            win.addstr(y_offset, 3, line); y_offset += 1

    win.addstr(win_h - 4, 3, "Type 'YES' to continue:", curses.A_BOLD)
    win.addstr(win_h - 3, 3, "Any other key to cancel...")
    win.refresh()

    # Get user input
    curses.curs_set(1); curses.echo()
    try:
        user_input = win.getstr(win_h - 2, 3, 10).decode('utf-8').strip()
    except:
        user_input = ""
    curses.noecho(); curses.curs_set(0)
    
    # Clean up window before returning
    del win
    stdscr.touchwin()
    stdscr.refresh()
    refresh_log_window(stdscr)
    
    return user_input.upper() == "YES"

def get_compression_choice(stdscr, app_h):
    """Display compression options and return choice."""
    compression_options = [
        "None - No compression (fastest, largest file)",
        "gzip - Good compression, widely compatible (recommended)",
        "pigz - Parallel gzip (faster on multi-core CPUs)",
        "zstd - Modern compression (fast, excellent ratio)",
        "xz - Maximum compression (slowest, smallest file)"
    ]
    
    choice_idx = get_menu_choice(stdscr, "Select Compression Method", compression_options, app_h)
    if choice_idx == -1:
        return None  # Cancelled
    
    # Map to compression info: (extension, command, description)
    compression_map = {
        0: (None, None, "no compression"),
        1: (".gz", "gzip -c", "gzip compression"),
        2: (".gz", "pigz -c", "parallel gzip compression"),
        3: (".zst", "zstd -c", "zstd compression"),
        4: (".xz", "xz -c", "xz compression")
    }
    
    return compression_map[choice_idx]

def show_confirmation(stdscr, title, messages, app_h):
    """Displays a confirmation dialog with a red background."""
    _, w = stdscr.getmaxyx()
    msg_lines = sum(len(wrap(msg, w - 26)) for msg in messages)
    win_h = msg_lines + 6
    win_w = max(len(s) for s in messages) + 6 if messages else 40
    win_w = max(win_w, 60)
    # Center within the app area (above log section)
    start_y, start_x = (app_h - win_h) // 2, (w - win_w) // 2

    win = draw_bordered_window(stdscr, start_y, start_x, win_h, win_w, title)
    
    # Always use the red 'danger' color scheme for confirmations
    win.bkgd(' ', curses.color_pair(4))
    win.box()
    win.addstr(0, 2, f" {title} ", curses.A_BOLD | curses.color_pair(4))
    
    y_offset = 2
    for msg in messages:
        for line in wrap(msg, win_w - 4):
            win.addstr(y_offset, 3, line); y_offset += 1

    win.addstr(win_h - 2, 3, "Continue? (y/n)")
    # Ensure log section is visible before showing dialog
    refresh_log_window(stdscr)
    win.refresh()

    while True:
        key = stdscr.getch()
        
        # Ignore mouse clicks - require explicit y/n
        if key == curses.KEY_MOUSE:
            try:
                curses.getmouse()  # Clear the mouse event
            except:
                pass
            continue
        
        if key in [ord('y'), ord('Y')]: 
            # Clean up window before returning
            del win
            stdscr.touchwin()
            stdscr.refresh()
            refresh_log_window(stdscr)
            return True
        elif key in [ord('n'), ord('N'), 27, ord('q'), ord('Q')]: 
            # Clean up window before returning
            del win
            stdscr.touchwin()
            stdscr.refresh()
            refresh_log_window(stdscr)
            return False

def show_message_box(stdscr, title, messages, app_h):
    """Displays an informational message box."""
    _, w = stdscr.getmaxyx()
    msg_lines = sum(len(wrap(msg, w - 26)) for msg in messages)
    win_h = msg_lines + 5
    win_w = max(len(s) for s in messages) + 6 if messages else 40
    win_w = max(win_w, 60)
    # Center within the app area (above log section)
    start_y, start_x = (app_h - win_h) // 2, (w - win_w) // 2
    
    win = draw_bordered_window(stdscr, start_y, start_x, win_h, win_w, title)
    
    y_offset = 2
    for msg in messages:
        if msg == "":
            # Blank line - just advance y_offset
            y_offset += 1
        else:
            for line in wrap(msg, win_w - 4):
                win.addstr(y_offset, 3, line)
                y_offset += 1
            
    win.addstr(win_h - 2, 3, "Press any key to continue...")
    # Ensure log section is visible before showing dialog
    refresh_log_window(stdscr)
    win.refresh()
    
    # Wait for any key (ignore mouse clicks)
    while True:
        key = stdscr.getch()
        
        # Ignore mouse clicks
        if key == curses.KEY_MOUSE:
            try:
                curses.getmouse()  # Clear the mouse event
            except:
                pass
            continue  # Don't break, wait for keyboard
        else:
            # Any keyboard key
            break
    
    # Clean up window before returning
    del win
    stdscr.touchwin()
    stdscr.refresh()
    refresh_log_window(stdscr)

def run_utility_command(command):
    """Runs a utility command, captures its output, and logs it."""
    log.info(f"Executing utility command: {command}")
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.stdout:
            log.info(f"Command STDOUT:\n{result.stdout.strip()}")
        if result.stderr:
            log.warning(f"Command STDERR:\n{result.stderr.strip()}")
        
        if result.returncode == 0:
            log.info("Utility command finished successfully.")
            return True, result.stdout.strip()
        else:
            log.error(f"Utility command failed with exit code {result.returncode}.")
            return False, result.stderr.strip()
    except Exception as e:
        log.error(f"Exception during utility command: {e}")
        return False, str(e)


def show_help_screen(stdscr, app_h):
    """Display scrollable help screen."""
    log.info("show_help_screen: Starting")
    
    # Load help text from ddi.md file with word wrapping
    help_text = []
    help_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ddi.md")
    
    h, w = stdscr.getmaxyx()
    help_width = min(85, w - 4)  # Wider window
    wrap_width = help_width - 6  # Account for borders and padding
    
    try:
        with open(help_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.rstrip()
                if len(line) > wrap_width and not line.startswith("#") and not line.startswith("---"):
                    # Word wrap long lines (except headers and dividers)
                    wrapped = wrap(line, wrap_width, break_long_words=False, break_on_hyphens=False)
                    help_text.extend(wrapped)
                else:
                    help_text.append(line)
        log.info(f"Loaded and wrapped {len(help_text)} lines from {help_file}")
    except FileNotFoundError:
        log.error(f"Help file not found: {help_file}")
        # Show error message dialog
        show_message_box(stdscr, "Error", 
                        [f"Help file not found: {help_file}", 
                         "", 
                         "Please ensure ddi.md is in the same directory as ddi.py"],
                        app_h)
        return
    except Exception as e:
        log.error(f"Error loading help file: {e}")
        show_message_box(stdscr, "Error",
                        [f"Error loading help file: {e}",
                         "",
                         "For complete documentation, see ddi.md in the application directory"],
                        app_h)
        return
    
    # Add footer instruction
    help_text.append("")
    help_text.append("Press Esc, q, or F1 to close (↑/↓/Scroll to navigate)")
    
    # Make window smaller - take 2 lines off bottom (app_h - 4 instead of app_h - 2)
    help_height = min(len(help_text) + 4, app_h - 4)
    
    # Move window up by 1 row - changed from +2 to +1
    start_y = max(2, (app_h - help_height) // 2 + 1)
    start_x = max(1, (w - help_width) // 2)
    
    log.info(f"Help window: h={help_height}, w={help_width}, y={start_y}, x={start_x}, screen={h}x{w}, app_h={app_h}")
    win = draw_bordered_window(stdscr, start_y, start_x, help_height, help_width, "DDI Help (F1)")
    
    # Scrolling support
    scroll_pos = 0
    visible_lines = help_height - 4  # Leave room for borders and title
    max_scroll = max(0, len(help_text) - visible_lines)
    
    # Helper function to get formatting for a line
    def get_line_format(line):
        """Return the curses attributes for a line based on markdown syntax."""
        if line.startswith("# "):  # H1 - Main title
            return curses.A_BOLD | curses.color_pair(5)
        elif line.startswith("## "):  # H2 - Section headers
            return curses.A_BOLD | curses.color_pair(6)
        elif line.startswith("### "):  # H3 - Subsection headers
            return curses.A_BOLD | curses.color_pair(3)
        elif line.startswith("---"):  # Horizontal rule
            return curses.color_pair(5)
        elif line.startswith("- **") or line.startswith("  - **"):  # Bold list items
            return curses.color_pair(2)
        elif line.startswith("⚠️"):  # Warning lines
            return curses.A_BOLD | curses.color_pair(6)
        elif line.startswith("**") and line.endswith("**"):  # Bold headings
            return curses.A_BOLD | curses.color_pair(3)
        else:
            return curses.color_pair(2)
    
    while True:
        # Clear content area before redrawing
        for i in range(2, help_height - 2):
            win.move(i, 1)
            win.clrtoeol()
        
        # Display visible portion of content
        for i, line_idx in enumerate(range(scroll_pos, min(scroll_pos + visible_lines, len(help_text)))):
            if i + 2 >= help_height - 2:
                break
            try:
                line = help_text[line_idx]
                display_line = line[:help_width - 6] if len(line) > help_width - 6 else line
                
                # Special handling for horizontal rules
                if line.startswith("---"):
                    display_line = "─" * (help_width - 6)
                
                # Get formatting and display
                line_format = get_line_format(line)
                win.addstr(i + 2, 2, display_line, line_format)
            except:
                pass  # Skip lines that don't fit
        
        # Show scroll indicator if needed
        if max_scroll > 0:
            scroll_info = f"[{scroll_pos + 1}-{min(scroll_pos + visible_lines, len(help_text))} of {len(help_text)}]"
            try:
                win.addstr(help_height - 1, help_width - len(scroll_info) - 2, scroll_info, curses.color_pair(5))
            except:
                pass
        
        # Refresh window once
        win.refresh()
        
        # Wait for key input
        key = stdscr.getch()
        
        # Handle scrolling
        if key in [curses.KEY_UP, ord('k')] and scroll_pos > 0:
            scroll_pos -= 1
        elif key in [curses.KEY_DOWN, ord('j')] and scroll_pos < max_scroll:
            scroll_pos += 1
        elif key == curses.KEY_PPAGE:  # Page Up
            scroll_pos = max(0, scroll_pos - visible_lines)
        elif key == curses.KEY_NPAGE:  # Page Down
            scroll_pos = min(max_scroll, scroll_pos + visible_lines)
        elif key == curses.KEY_HOME:
            scroll_pos = 0
        elif key == curses.KEY_END:
            scroll_pos = max_scroll
        # Handle mouse scroll wheel
        elif key == curses.KEY_MOUSE:
            try:
                _, mx, my, _, button_state = curses.getmouse()
                # Scroll wheel up (button 4)
                if button_state & curses.BUTTON4_PRESSED:
                    scroll_pos = max(0, scroll_pos - 3)
                # Scroll wheel down (button 5)
                elif button_state & (1 << 21):  # BUTTON5_PRESSED
                    scroll_pos = min(max_scroll, scroll_pos + 3)
            except:
                pass
        # Close on Esc, q, Q, or F1
        elif key in [27, ord('q'), ord('Q'), curses.KEY_F1]:
            break
    
    # Clean up - properly clear the help window area before deleting it
    log.info("show_help_screen: Cleaning up")
    win.clear()
    win.refresh()
    del win
    # Mark the entire screen for redraw
    stdscr.touchwin()
    stdscr.refresh()
    log.info("show_help_screen: Returning to menu")


def show_about_screen(stdscr, app_h):
    """Display about/credits screen (Easter egg accessed via F12)."""
    h, w = stdscr.getmaxyx()
    
    # Prepare about text
    about_text = [
        "",
        "DD Interface (DDI)",
        f"Version {VERSION}",
        "",
        "═" * 60,
        "",
        "Written by:",
        "  Paul Miskovsky",
        "",
        "Licensed under:",
        "  GNU General Public License v3.0 (GPLv3)",
        "",
        "License Information:",
        "  This program is free software: you can redistribute it",
        "  and/or modify it under the terms of the GNU General",
        "  Public License as published by the Free Software",
        "  Foundation, either version 3 of the License, or (at",
        "  your option) any later version.",
        "",
        "  This program is distributed in the hope that it will",
        "  be useful, but WITHOUT ANY WARRANTY; without even the",
        "  implied warranty of MERCHANTABILITY or FITNESS FOR A",
        "  PARTICULAR PURPOSE. See the GNU General Public License",
        "  for more details.",
        "",
        "Full License Text:",
        "  https://www.gnu.org/licenses/gpl-3.0.html",
        "",
        "Source Code:",
        "  https://github.com/opensolutionsgroup/dd-interface",
        "",
        "═" * 60,
        "",
        "Built with Python and ncurses",
        "Inspired by Clonezilla",
        "",
        "Press any key to return...",
    ]
    
    # Calculate window size
    content_height = min(len(about_text) + 4, app_h - 4)
    content_width = min(w - 4, 70)
    start_y = max(2, (app_h - content_height) // 2)
    start_x = max(1, (w - content_width) // 2)
    
    # Create window
    win = draw_bordered_window(stdscr, start_y, start_x, content_height, content_width, "About DDI")
    
    # Scrolling support
    scroll_pos = 0
    visible_lines = content_height - 4
    max_scroll = max(0, len(about_text) - visible_lines)
    
    while True:
        # Clear content area
        for i in range(2, content_height - 2):
            win.move(i, 1)
            win.clrtoeol()
        
        # Display visible portion of content
        for i, line_idx in enumerate(range(scroll_pos, min(scroll_pos + visible_lines, len(about_text)))):
            if i + 2 >= content_height - 2:
                break
            try:
                line = about_text[line_idx]
                display_line = line[:content_width - 6] if len(line) > content_width - 6 else line
                
                # Apply formatting
                if line.startswith("DD Interface"):
                    # Title - bold and colored
                    win.addstr(i + 2, 2, display_line, curses.A_BOLD | curses.color_pair(5))
                elif line.startswith("Version"):
                    # Version - colored
                    win.addstr(i + 2, 2, display_line, curses.color_pair(6))
                elif line.startswith("═"):
                    # Separator - colored
                    win.addstr(i + 2, 2, display_line, curses.color_pair(5))
                elif line.startswith("Written by:") or line.startswith("Licensed under:") or \
                     line.startswith("License Information:") or line.startswith("Full License Text:") or \
                     line.startswith("Source Code:"):
                    # Section headers - bold
                    win.addstr(i + 2, 2, display_line, curses.A_BOLD | curses.color_pair(6))
                elif line.strip().startswith("Paul Miskovsky"):
                    # Author name - highlighted
                    win.addstr(i + 2, 2, display_line, curses.A_BOLD | curses.color_pair(3))
                elif "https://" in line:
                    # URLs - colored
                    win.addstr(i + 2, 2, display_line, curses.color_pair(3))
                elif line.strip().startswith("GNU General Public License"):
                    # License name - highlighted
                    win.addstr(i + 2, 2, display_line, curses.color_pair(6))
                else:
                    # Regular text
                    win.addstr(i + 2, 2, display_line)
            except:
                pass  # Skip lines that don't fit
        
        # Show scroll indicator if needed
        if max_scroll > 0:
            scroll_info = f"[{scroll_pos + 1}-{min(scroll_pos + visible_lines, len(about_text))} of {len(about_text)}]"
            try:
                win.addstr(content_height - 1, content_width - len(scroll_info) - 2, scroll_info, curses.color_pair(5))
            except:
                pass
        
        win.refresh()
        
        # Wait for key input
        key = stdscr.getch()
        
        # Handle scrolling
        if key in [curses.KEY_UP, ord('k')] and scroll_pos > 0:
            scroll_pos -= 1
        elif key in [curses.KEY_DOWN, ord('j')] and scroll_pos < max_scroll:
            scroll_pos += 1
        elif key == curses.KEY_PPAGE:  # Page Up
            scroll_pos = max(0, scroll_pos - visible_lines)
        elif key == curses.KEY_NPAGE:  # Page Down
            scroll_pos = min(max_scroll, scroll_pos + visible_lines)
        elif key == curses.KEY_HOME:
            scroll_pos = 0
        elif key == curses.KEY_END:
            scroll_pos = max_scroll
        # Handle mouse scroll
        elif key == curses.KEY_MOUSE:
            try:
                _, mx, my, _, button_state = curses.getmouse()
                if button_state & curses.BUTTON4_PRESSED:  # Scroll up
                    scroll_pos = max(0, scroll_pos - 3)
                elif button_state & (1 << 21):  # Scroll down
                    scroll_pos = min(max_scroll, scroll_pos + 3)
            except:
                pass
        else:
            # Any other key closes the window
            break
    
    # Clean up
    win.clear()
    win.refresh()
    del win
    stdscr.touchwin()
    stdscr.refresh()


def format_bytes(b):
    if b is None or b < 0: return "N/A"
    if b == 0: return "0.0 B"
    power = 1024; n = 0
    power_labels = {0: 'B', 1: 'KiB', 2: 'MiB', 3: 'GiB', 4: 'TiB'}
    while b >= power and n < len(power_labels): b /= power; n += 1
    return f"{b:.2f} {power_labels[n]}"

def format_time(seconds):
    if seconds is None or seconds < 0: return "??:??:??"
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d}"

# --- SSH File Browser Functions ---

def parse_ssh_ls_output(output):
    """Parse ls -la output from SSH into structured directory entries.
    
    Returns list of dicts with: name, is_dir, size, date, permissions
    """
    entries = []
    for line in output.split('\n'):
        line = line.strip()
        if not line or line.startswith('total'):
            continue
        
        # Parse: drwxr-xr-x 2 user group 4096 Nov 29 10:30 filename
        parts = line.split(None, 8)
        if len(parts) < 9:
            continue
        
        # Extract fields
        permissions = parts[0]
        is_dir = permissions.startswith('d')
        is_link = permissions.startswith('l')
        
        # Parse size
        try:
            size = int(parts[4])
        except (ValueError, IndexError):
            size = 0
        
        # Date is parts 5, 6, 7
        date_str = f"{parts[5]} {parts[6]} {parts[7]}"
        
        # Name is everything after (may contain spaces)
        name = parts[8]
        
        # Skip . and .. (we'll add .. manually)
        if name in ['.', '..']:
            continue
        
        # For symlinks, extract just the name (before ->)
        if is_link and '->' in name:
            name = name.split('->')[0].strip()
        
        entries.append({
            'name': name,
            'is_dir': is_dir or is_link,
            'size': size,
            'date': date_str,
            'permissions': permissions
        })
    
    # Sort: directories first, then by name
    entries.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
    return entries

def ssh_list_directory(ssh_user, ssh_host, path):
    """List directory contents via SSH using ls -la.
    
    Returns (entries, error_message) where entries is a list of dicts,
    or (None, error_msg) if listing fails.
    """
    # Escape path for shell
    safe_path = path.replace("'", "'\\''")
    cmd = f"ssh -o ConnectTimeout=10 {ssh_user}@{ssh_host} 'ls -la \"{safe_path}\" 2>&1'"
    
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, 
                              text=True, timeout=15)
        
        if result.returncode != 0:
            return None, result.stderr or result.stdout or "Unknown error"
        
        entries = parse_ssh_ls_output(result.stdout)
        return entries, None
        
    except subprocess.TimeoutExpired:
        return None, "SSH connection timeout"
    except Exception as e:
        return None, str(e)

def format_file_entry(entry, max_width=60):
    """Format a file/directory entry for display in the browser.
    
    Returns formatted string with icon, name, size, and date.
    """
    # Choose icon based on type
    if entry['is_dir']:
        icon = ""
        size_str = "<DIR>    "
    else:
        icon = ""
        size_str = format_bytes(entry['size']).rjust(9)
    
    # Truncate name if needed
    name = entry['name']
    max_name_len = max_width - 30  # Reserve space for size and date
    if len(name) > max_name_len:
        name = name[:max_name_len-3] + "..."
    
    # Format the entry
    return f"{name:<{max_name_len}} {size_str}  {entry['date']}"

def ssh_browse_directory(stdscr, ssh_user, ssh_host, start_path, log_pad, log_win_height,
                         file_filter=None, filter_dirs_only=False):
    """Browse remote SSH directory with Midnight Commander-style interface.
    
    Args:
        stdscr: curses screen object
        ssh_user: SSH username
        ssh_host: SSH hostname/IP
        start_path: Initial directory path
        log_pad: Curses pad for logging
        log_win_height: Height of log window
        file_filter: List of file extensions to show (e.g., ['.img', '.img.gz'])
                    None = show all files
        filter_dirs_only: If True, only show directories (for backup destination)
    
    Returns:
        Selected file/directory path, or None if cancelled
    """
    current_path = start_path
    
    while True:
        # List directory contents
        app_h = draw_main_layout(stdscr, "Browsing Remote Directory", 
                                 log_pad, log_win_height)
        
        log.info(f"Listing remote directory: {ssh_user}@{ssh_host}:{current_path}")
        entries, error = ssh_list_directory(ssh_user, ssh_host, current_path)
        
        if error or entries is None:
            show_message_box(stdscr, "Error", [
                f"Cannot list directory: {current_path}",
                f"Error: {error}",
                "",
                "Press any key to go back..."
            ], app_h)
            
            # Go to parent directory if current fails
            if current_path != '/':
                current_path = os.path.dirname(current_path) or '/'
                continue
            else:
                return None  # Can't list root, give up
        
        # Filter entries based on requirements
        if filter_dirs_only:
            # Only show directories
            filtered_entries = [e for e in (entries or []) if e['is_dir']]
        elif file_filter:
            # Show directories and files matching extensions
            filtered_entries = [e for e in (entries or []) if 
                              e['is_dir'] or 
                              any(e['name'].endswith(ext) for ext in file_filter)]
        else:
            # Show everything
            filtered_entries = entries or []
        
        # Add parent directory (..) if not at root
        if current_path != '/':
            filtered_entries.insert(0, {
                'name': '..',
                'is_dir': True,
                'size': 0,
                'date': '',
                'permissions': 'drwxr-xr-x'
            })
        
        # Add "Select this directory" option if filtering dirs only
        if filter_dirs_only:
            filtered_entries.insert(0, {
                'name': '<Select this directory>',
                'is_dir': False,  # Special marker
                'size': 0,
                'date': '',
                'permissions': '-rw-r--r--'
            })
        
        if not filtered_entries:
            show_message_box(stdscr, "Empty Directory", [
                f"No matching files/directories in: {current_path}",
                "",
                "Press any key to continue..."
            ], app_h)
            if current_path != '/':
                current_path = os.path.dirname(current_path) or '/'
            continue
        
        # Check if directory has too many entries
        if len(filtered_entries) > 100:
            # Too many files - show warning and ask to enter path manually
            app_h = draw_main_layout(stdscr, "Too Many Files", log_pad, log_win_height)
            show_message_box(stdscr, "Directory Too Large", [
                f"Directory {current_path} has {len(filtered_entries)} items.",
                "This is too many to display in the browser.",
                "",
                "Please use manual path entry or navigate to a subdirectory.",
                "",
                "Press any key to go back..."
            ], app_h)
            
            # Go back to parent directory
            if current_path != '/':
                current_path = os.path.dirname(current_path) or '/'
            continue
        
        # Format entries for display
        menu_items = [format_file_entry(e, max_width=70) for e in filtered_entries]
        
        # Show file browser
        app_h = draw_main_layout(stdscr, "Browse Remote Directory", 
                                 log_pad, log_win_height)
        
        try:
            choice_idx = get_menu_choice(stdscr, 
                                         f"{ssh_user}@{ssh_host}:{current_path}",
                                         menu_items, app_h)
        except curses.error as e:
            log.error(f"Curses error displaying menu: {e}")
            log.error(f"Directory: {current_path}, entries: {len(menu_items)}")
            show_message_box(stdscr, "Display Error", [
                "Cannot display this directory (too many items or screen too small).",
                f"Directory: {current_path}",
                f"Entries: {len(menu_items)}",
                "",
                "Press any key to go back..."
            ], app_h)
            
            # Go back to parent
            if current_path != '/':
                current_path = os.path.dirname(current_path) or '/'
            continue
        
        if choice_idx == -1:
            log.info("Browse cancelled by user")
            return None  # User cancelled
        
        selected = filtered_entries[choice_idx]
        log.info(f"User selected: '{selected['name']}', is_dir={selected['is_dir']}")
        
        # Handle special "Select this directory" option
        if selected['name'] == '<Select this directory>':
            log.info(f"Returning selected directory: {current_path}")
            return current_path
        
        # Handle parent directory (..)
        if selected['name'] == '..':
            current_path = os.path.dirname(current_path) or '/'
            log.info(f"Navigating to parent: {current_path}")
            continue
        
        # Handle directory navigation
        if selected['is_dir']:
            # Navigate into directory
            if current_path == '/':
                current_path = '/' + selected['name']
            else:
                current_path = current_path.rstrip('/') + '/' + selected['name']
            log.info(f"Navigating into directory: {current_path}")
            continue
        
        # File selected - return full path
        if current_path == '/':
            file_path = '/' + selected['name']
        else:
            file_path = current_path.rstrip('/') + '/' + selected['name']
        log.info(f"Returning selected file: {file_path}")
        return file_path


def _refresh_log_window(stdscr):
    """Force refresh of the log window to keep it visible during operations."""
    try:
        # Get log_pad from global log handler
        for handler in log.handlers:
            if isinstance(handler, CursesHandler):
                log_pad = handler.screen_pad
                log_win_height = handler.log_win_height
                
                # Refresh the log window
                h, w = stdscr.getmaxyx()
                log_win_y = h - log_win_height
                log_messages = handler.log_messages
                start_line = max(0, len(log_messages) - (log_win_height - 2))
                
                try:
                    log_pad.refresh(start_line, 0, log_win_y + 1, 2, h - 2, w - 3)
                except:
                    pass
                break
    except:
        pass  # Ignore errors

def run_dd_with_progress(stdscr, command_str, total_size_bytes, source_str, dest_str, app_h, display_mode="progress", operation_name="Operation"):
    """Runs a dd command and displays real-time visualization with toggle support.
    
    Args:
        display_mode: "progress" for progress bar (default), "blockmap" for SpinRite-style block map
        operation_name: Name of operation for block map display
        
    Key bindings during operation:
        v or V - Toggle between progress bar and block map views
    """
    log.info(f"Executing: {command_str}")
    
    # Start the dd process once
    process = subprocess.Popen(command_str, shell=True, stderr=subprocess.PIPE, text=True, bufsize=1)
    start_time = time.time()
    dd_re = re.compile(r"(\d+)\s+bytes")
    error_re = re.compile(r"(error reading|error writing|Input/output error|Cannot allocate memory)", re.IGNORECASE)
    stderr_lines = []
    
    # Track current display mode (can be toggled)
    current_mode = display_mode
    previous_mode = None
    
    # Shared state
    last_bytes_copied = 0
    last_percentage = 0
    first_draw = True
    
    # Error tracking for block map
    error_ranges = []  # List of (start_byte, end_byte) tuples where errors occurred
    last_error_position = 0
    
    while process.poll() is None:
        # Check for key press (non-blocking)
        stdscr.nodelay(True)
        try:
            key = stdscr.getch()
            if key in [ord('v'), ord('V')]:
                # Toggle display mode
                previous_mode = current_mode
                current_mode = "blockmap" if current_mode == "progress" else "progress"
                
                # Clean up the old window before switching
                if previous_mode == "progress" and hasattr(_draw_progress_bar, 'prog_win'):
                    try:
                        _draw_progress_bar.prog_win.clear()
                        _draw_progress_bar.prog_win.refresh()
                        del _draw_progress_bar.prog_win
                    except:
                        pass
                elif previous_mode == "blockmap" and hasattr(_draw_block_map, 'block_win'):
                    try:
                        _draw_block_map.block_win.clear()
                        _draw_block_map.block_win.refresh()
                        del _draw_block_map.block_win
                    except:
                        pass
                
                # Redraw the entire main layout (title + log window)
                # Get log_pad and log_win_height from the global log handler
                log_pad = None
                log_win_height = 8  # Default
                for handler in log.handlers:
                    if isinstance(handler, CursesHandler):
                        log_pad = handler.screen_pad
                        log_win_height = handler.log_win_height
                        break
                
                if log_pad:
                    draw_main_layout(stdscr, operation_name, log_pad, log_win_height)
                else:
                    # Fallback if handler not found
                    stdscr.clear()
                    stdscr.refresh()
                
                first_draw = True  # Need to redraw window for new mode
        except:
            pass
        stdscr.nodelay(False)
        
        # Read dd output
        if process.stderr and not process.stderr.closed:
            line = process.stderr.readline()
            if not line: 
                time.sleep(0.1)
                continue
            stderr_lines.append(line)
        else:
            break
        
        # Check for errors in dd output
        if error_re.search(line):
            # Record error at current position (we'll update the end when we get next byte count)
            log.warning(f"dd error detected: {line.strip()}")
            last_error_position = last_bytes_copied
            
        match = dd_re.search(line)
        if not match: 
            continue
        
        bytes_copied = int(match.group(1))
        
        # If we recorded an error, add the range now that we have the current byte position
        if last_error_position > 0:
            error_ranges.append((last_error_position, bytes_copied))
            last_error_position = 0
        
        elapsed_time = time.time() - start_time
        speed_bps = bytes_copied / elapsed_time if elapsed_time > 0 else 0
        percentage = (bytes_copied / total_size_bytes) * 100 if total_size_bytes > 0 else 0
        percentage = min(percentage, 100)
        eta = ((total_size_bytes - bytes_copied) / speed_bps) if speed_bps > 0 else -1
        
        # Update display based on current mode
        if current_mode == "progress":
            _draw_progress_bar(stdscr, app_h, source_str, dest_str, bytes_copied, total_size_bytes, 
                             percentage, speed_bps, elapsed_time, eta, first_draw, error_ranges)
        else:
            _draw_block_map(stdscr, app_h, operation_name, source_str, dest_str, bytes_copied, 
                          total_size_bytes, percentage, speed_bps, elapsed_time, eta, first_draw, error_ranges)
        
        first_draw = False  # Only first iteration or after mode change
        last_bytes_copied = bytes_copied
        last_percentage = percentage
    
    # Process finished
    process.wait()
    
    # Read remaining stderr
    if process.stderr:
        remaining = process.stderr.read()
        if remaining:
            stderr_lines.extend(remaining.split('\n'))
    
    # Check success
    stderr_text = ''.join(stderr_lines)
    operation_succeeded = False
    
    if process.returncode == 0:
        operation_succeeded = True
    elif process.returncode == 1 and "No space left on device" in stderr_text:
        operation_succeeded = True
        log.info("Operation completed successfully (target device filled)")
    
    # Show final result
    _show_operation_result(stdscr, app_h, operation_succeeded, process.returncode, current_mode, 
                          operation_name, source_str, dest_str, total_size_bytes)
    
    return operation_succeeded

def _draw_progress_bar(stdscr, app_h, source_str, dest_str, bytes_copied, total_size_bytes, 
                       percentage, speed_bps, elapsed_time, eta, first_draw=False, error_ranges=None):
    """Draw the progress bar display.
    
    Args:
        first_draw: If True, create window and draw static elements
        error_ranges: List of (start_byte, end_byte) tuples where errors occurred
    
    Returns:
        The progress window object
    """
    if error_ranges is None:
        error_ranges = []
    _, w = stdscr.getmaxyx()
    prog_h, prog_w = 12, w - 10
    start_y, start_x = (app_h - prog_h) // 2, (w - prog_w) // 2
    
    # Create new window or get existing one
    if first_draw or not hasattr(_draw_progress_bar, 'prog_win'):
        # Clean up old window if switching modes
        if hasattr(_draw_progress_bar, 'prog_win'):
            try:
                _draw_progress_bar.prog_win.clear()
                _draw_progress_bar.prog_win.refresh()
                del _draw_progress_bar.prog_win
            except:
                pass
        
        _draw_progress_bar.prog_win = draw_bordered_window(stdscr, start_y, start_x, prog_h, prog_w, "Operation in Progress")
        prog_win = _draw_progress_bar.prog_win
        
        # Draw static elements once (with bounds checking)
        max_text_len = prog_w - 6  # Leave margin for borders
        try:
            prog_win.addstr(2, 3, f"From: {source_str}"[:max_text_len])
        except:
            pass
        try:
            prog_win.addstr(3, 3, f"To:   {dest_str}"[:max_text_len])
        except:
            pass
        prog_win.hline(4, 2, curses.ACS_HLINE, prog_w - 4)
        prog_win.hline(7, 2, curses.ACS_HLINE, prog_w - 4)
        
        # Add toggle hint
        try:
            prog_win.addstr(10, 3, "Press 'v' to toggle view"[:max_text_len], curses.color_pair(2))
        except:
            pass
    else:
        prog_win = _draw_progress_bar.prog_win
    
    # Update dynamic fields with proper bounds checking
    max_text_len = prog_w - 6  # Leave margin for borders
    
    # Update percentage
    prog_win.move(5, 3)
    prog_win.clrtoeol()
    try:
        prog_win.addstr(5, 3, f"Overall Progress: {percentage:.1f}%"[:max_text_len])
    except:
        pass
    
    # Update progress bar (using SpinRite-style characters for better visibility)
    bar_width = max(1, prog_w - 6)  # Ensure positive width
    filled_len = int(bar_width * percentage / 100)
    bar = '█' * filled_len + '·' * (bar_width - filled_len)  # '·' (middle dot) for empty
    try:
        prog_win.addstr(6, 3, bar[:bar_width], curses.color_pair(6) | curses.A_BOLD)
    except:
        pass
    
    # Build single-line stats to avoid overflow
    stats_line1 = f"Size: {format_bytes(total_size_bytes)} | Speed: {format_bytes(speed_bps)}/s"
    stats_line2 = f"Transferred: {format_bytes(bytes_copied)} | Time: {format_time(elapsed_time)} / {format_time(eta)}"
    
    # Update stats line 1
    prog_win.move(8, 3)
    prog_win.clrtoeol()
    try:
        prog_win.addstr(8, 3, stats_line1[:max_text_len])
    except:
        pass
    
    # Update stats line 2
    prog_win.move(9, 3)
    prog_win.clrtoeol()
    try:
        prog_win.addstr(9, 3, stats_line2[:max_text_len])
    except:
        pass
    
    prog_win.refresh()
    
    # Refresh log window to keep it visible during operation
    _refresh_log_window(stdscr)
    
    return prog_win

def _draw_block_map(stdscr, app_h, operation_name, source_str, dest_str, bytes_copied, 
                   total_size_bytes, percentage, speed_bps, elapsed_time, eta, first_draw=False, error_ranges=None):
    """Draw the block map display.
    
    Args:
        first_draw: If True, create window and draw static elements
        error_ranges: List of (start_byte, end_byte) tuples where errors occurred
    
    Returns:
        The block map window object
    """
    if error_ranges is None:
        error_ranges = []
    h, w = stdscr.getmaxyx()
    
    # Calculate block map dimensions
    map_width = w - 20
    map_height = app_h - 15
    
    win_h = map_height + 12
    win_w = map_width + 4
    start_y = 2
    start_x = (w - win_w) // 2
    
    # Create new window or get existing one
    if first_draw or not hasattr(_draw_block_map, 'block_win'):
        # Clean up old window if switching modes
        if hasattr(_draw_block_map, 'block_win'):
            try:
                _draw_block_map.block_win.clear()
                _draw_block_map.block_win.refresh()
                del _draw_block_map.block_win
            except:
                pass
        
        _draw_block_map.block_win = draw_bordered_window(stdscr, start_y, start_x, win_h, win_w, f"{operation_name} - Block Map")
        block_win = _draw_block_map.block_win
        
        # Draw static elements with bounds checking
        max_text_len = win_w - 6
        try:
            block_win.addstr(2, 2, f"Device: {dest_str}"[:max_text_len])
        except:
            pass
        try:
            block_win.addstr(3, 2, f"Source: {source_str}"[:max_text_len])
        except:
            pass
        block_win.hline(4, 1, curses.ACS_HLINE, win_w - 2)
        
        # Legend - use single line to avoid overflow
        legend_y = win_h - 5
        try:
            block_win.addstr(legend_y, 2, "Legend:", curses.A_BOLD)
        except:
            pass
        
        # Build legend as single string to control length (SpinRite-style characters)
        legend_text = "·=Pending  ▒=Writing  █=Complete  X=Error"
        try:
            block_win.addstr(legend_y + 1, 2, legend_text[:max_text_len])
        except:
            pass
        
        block_win.hline(legend_y - 1, 1, curses.ACS_HLINE, win_w - 2)
        
        # Add toggle hint
        try:
            block_win.addstr(legend_y + 2, 2, "Press 'v' to toggle view"[:max_text_len], curses.color_pair(2))
        except:
            pass
        
        # Store dimensions for later use
        _draw_block_map.map_width = map_width
        _draw_block_map.map_height = map_height
        _draw_block_map.map_start_y = 5
        _draw_block_map.stats_y = win_h - 7
    else:
        block_win = _draw_block_map.block_win
        map_width = _draw_block_map.map_width
        map_height = _draw_block_map.map_height
        map_start_y = _draw_block_map.map_start_y
        stats_y = _draw_block_map.stats_y
    
    # Update block map
    total_chars = map_width * map_height
    filled_chars = int(total_chars * percentage / 100)
    
    map_start_y = _draw_block_map.map_start_y
    
    # Calculate bytes per character for error detection
    bytes_per_char = total_size_bytes / total_chars if total_chars > 0 else 1
    
    for row in range(map_height):
        for col in range(map_width):
            char_index = row * map_width + col
            y_pos = map_start_y + row
            x_pos = 2 + col
            
            # Calculate byte range this character represents
            char_start_byte = int(char_index * bytes_per_char)
            char_end_byte = int((char_index + 1) * bytes_per_char)
            
            # Check if this character's byte range overlaps with any error range
            has_error = False
            for error_start, error_end in error_ranges:
                if not (char_end_byte < error_start or char_start_byte > error_end):
                    # Ranges overlap - this block has an error
                    has_error = True
                    break
            
            if has_error:
                # Error blocks - show in red with 'X' marker (SpinRite style)
                block_win.addstr(y_pos, x_pos, "X", curses.color_pair(4) | curses.A_BOLD)
            elif char_index < filled_chars:
                # Completed blocks - solid block (SpinRite style) - use green on blue like progress bar
                block_win.addstr(y_pos, x_pos, "█", curses.color_pair(6) | curses.A_BOLD)
            elif char_index == filled_chars:
                # Currently writing block - medium shade (SpinRite style, more distinct)
                block_win.addstr(y_pos, x_pos, "▒", curses.color_pair(6) | curses.A_BOLD)
            else:
                # Pending blocks - middle dot (SpinRite style) - use green on blue like progress bar
                block_win.addstr(y_pos, x_pos, "·", curses.color_pair(6))
    
    # Update stats
    stats_y = _draw_block_map.stats_y
    
    # Get window dimensions to avoid overflow
    win_h, win_w = block_win.getmaxyx()
    max_text_width = win_w - 5  # Leave extra margin for borders (1 left + 2 right + safety)
    
    # First stats line: Progress, Speed, ETA
    block_win.move(stats_y, 2)
    block_win.clrtoeol()
    stats_line1 = f"Progress: {percentage:.1f}% | Speed: {format_bytes(speed_bps)}/s | ETA: {format_time(eta)}"
    # Truncate to fit within window
    if len(stats_line1) > max_text_width:
        stats_line1 = stats_line1[:max_text_width]
    # Use try/except to prevent curses errors if text is still too long
    try:
        block_win.addstr(stats_y, 2, stats_line1[:max_text_width])
    except:
        pass  # Ignore curses errors if text doesn't fit
    
    # Second stats line: Written progress
    block_win.move(stats_y + 1, 2)
    block_win.clrtoeol()
    stats_line2 = f"Written: {format_bytes(bytes_copied)} / {format_bytes(total_size_bytes)}"
    # Truncate to fit within window
    if len(stats_line2) > max_text_width:
        stats_line2 = stats_line2[:max_text_width]
    # Use try/except to prevent curses errors if text is still too long
    try:
        block_win.addstr(stats_y + 1, 2, stats_line2[:max_text_width])
    except:
        pass  # Ignore curses errors if text doesn't fit
    
    block_win.refresh()
    
    # Refresh log window to keep it visible during operation
    _refresh_log_window(stdscr)
    
    return block_win

def _show_operation_result(stdscr, app_h, operation_succeeded, return_code, display_mode, 
                          operation_name, source_str, dest_str, total_size_bytes):
    """Show the final result of the operation."""
    if display_mode == "progress":
        # Use progress window
        if hasattr(_draw_progress_bar, 'prog_win'):
            prog_win = _draw_progress_bar.prog_win
            _, w = stdscr.getmaxyx()
            prog_h, prog_w = 12, w - 10
            
            final_color = curses.color_pair(7) if operation_succeeded else curses.color_pair(4)
            prog_win.bkgd(' ', final_color)
            prog_win.clear()
            prog_win.box()
            
            final_title = " Success " if operation_succeeded else " Failed "
            prog_win.addstr(0, 2, final_title, curses.A_BOLD)
            
            msg = "Operation completed successfully." if operation_succeeded else f"Operation failed with code {return_code}."
            log.info(msg)
            prog_win.addstr(prog_h//2 - 1, (prog_w - len(msg))//2, msg)
            prog_win.addstr(prog_h//2 + 1, (prog_w - 25)//2, "Press any key to continue...")
            prog_win.refresh()
            stdscr.getch()
            
            # Clean up
            prog_win.clear()
            prog_win.refresh()
            del _draw_progress_bar.prog_win
    else:
        # Use block map window
        if hasattr(_draw_block_map, 'block_win'):
            block_win = _draw_block_map.block_win
            map_width = _draw_block_map.map_width
            map_height = _draw_block_map.map_height
            map_start_y = _draw_block_map.map_start_y
            stats_y = _draw_block_map.stats_y
            
            # Fill entire map with final state
            for row in range(map_height):
                for col in range(map_width):
                    y_pos = map_start_y + row
                    x_pos = 2 + col
                    if operation_succeeded:
                        block_win.addstr(y_pos, x_pos, "█", curses.color_pair(7) | curses.A_BOLD)
                    else:
                        block_win.addstr(y_pos, x_pos, "X", curses.color_pair(4) | curses.A_BOLD)
            
            final_color = curses.color_pair(7) if operation_succeeded else curses.color_pair(4)
            block_win.bkgd(' ', final_color)
            
            msg = "Operation completed successfully!" if operation_succeeded else f"Operation failed with code {return_code}"
            log.info(msg)
            
            block_win.move(stats_y + 2, 2)
            block_win.clrtoeol()
            block_win.addstr(stats_y + 2, 2, msg, curses.A_BOLD)
            block_win.addstr(stats_y + 3, 2, "Press any key to continue...")
            block_win.refresh()
            stdscr.getch()
            
            # Clean up
            block_win.clear()
            block_win.refresh()
            del _draw_block_map.block_win

def run_dd_with_block_map(stdscr, command_str, total_size_bytes, source_str, dest_str, app_h, operation_name="Operation"):
    """Runs a dd command with SpinRite-style block map visualization."""
    h, w = stdscr.getmaxyx()
    
    # Calculate block map dimensions
    # Use most of the screen width for the block map
    map_width = w - 20  # Leave margins
    map_height = app_h - 15  # Leave room for header, stats, and log
    
    # Calculate grid dimensions (each character represents multiple blocks)
    blocks_per_char = max(1, total_size_bytes // (1024 * 1024) // (map_width * map_height))  # Rough estimate
    
    # Create window
    win_h = map_height + 12
    win_w = map_width + 4
    start_y = 2
    start_x = (w - win_w) // 2
    
    block_win = draw_bordered_window(stdscr, start_y, start_x, win_h, win_w, f"{operation_name} - Block Map")
    
    # Draw static elements
    block_win.addstr(2, 2, f"Device: {dest_str[:win_w-12]}")
    block_win.addstr(3, 2, f"Source: {source_str[:win_w-12]}")
    block_win.hline(4, 1, curses.ACS_HLINE, win_w - 2)
    
    # Legend (SpinRite-style characters for better visibility)
    legend_y = win_h - 5
    block_win.addstr(legend_y, 2, "Legend:", curses.A_BOLD)
    block_win.addstr(legend_y + 1, 4, "·", curses.color_pair(2))
    block_win.addstr(legend_y + 1, 6, "= Pending")
    block_win.addstr(legend_y + 1, 20, "▒", curses.color_pair(6) | curses.A_BOLD)
    block_win.addstr(legend_y + 1, 22, "= Writing")
    block_win.addstr(legend_y + 1, 36, "█", curses.color_pair(7) | curses.A_BOLD)
    block_win.addstr(legend_y + 1, 38, "= Complete")
    
    block_win.hline(legend_y - 1, 1, curses.ACS_HLINE, win_w - 2)
    block_win.refresh()
    
    log.info(f"Executing: {command_str}")
    
    process = subprocess.Popen(command_str, shell=True, stderr=subprocess.PIPE, text=True, bufsize=1)
    start_time = time.time()
    dd_re = re.compile(r"(\d+)\s+bytes")
    stderr_lines = []
    
    # Calculate block map grid
    total_chars = map_width * map_height
    
    # Stats position
    stats_y = win_h - 7
    
    while process.poll() is None:
        if process.stderr and not process.stderr.closed:
            line = process.stderr.readline()
            if not line: break
            stderr_lines.append(line)
        else:
            break
        match = dd_re.search(line)
        if not match: continue
        
        bytes_copied = int(match.group(1))
        
        elapsed_time = time.time() - start_time
        speed_bps = bytes_copied / elapsed_time if elapsed_time > 0 else 0
        percentage = (bytes_copied / total_size_bytes) * 100 if total_size_bytes > 0 else 0
        percentage = min(percentage, 100)
        eta = ((total_size_bytes - bytes_copied) / speed_bps) if speed_bps > 0 else -1
        
        # Calculate how many chars should be filled
        filled_chars = int(total_chars * percentage / 100)
        
        # Draw block map
        map_start_y = 5
        for row in range(map_height):
            for col in range(map_width):
                char_index = row * map_width + col
                y_pos = map_start_y + row
                x_pos = 2 + col
                
                if char_index < filled_chars:
                    # Completed blocks - solid block (SpinRite style) - use green on blue like progress bar
                    block_win.addstr(y_pos, x_pos, "█", curses.color_pair(6) | curses.A_BOLD)
                elif char_index == filled_chars:
                    # Currently writing block - medium shade (SpinRite style, more distinct)
                    block_win.addstr(y_pos, x_pos, "▒", curses.color_pair(6) | curses.A_BOLD)
                else:
                    # Pending blocks - middle dot (SpinRite style) - use green on blue like progress bar
                    block_win.addstr(y_pos, x_pos, "·", curses.color_pair(6))
        
        # Update stats (clear line first)
        max_text_width = win_w - 5  # Leave extra margin for borders (1 left + 2 right + safety)
        
        block_win.move(stats_y, 2)
        block_win.clrtoeol()
        stats_line1 = f"Progress: {percentage:.1f}% | Speed: {format_bytes(speed_bps)}/s | ETA: {format_time(eta)}"
        # Truncate to fit within window
        if len(stats_line1) > max_text_width:
            stats_line1 = stats_line1[:max_text_width]
        # Use try/except to prevent curses errors if text is still too long
        try:
            block_win.addstr(stats_y, 2, stats_line1[:max_text_width])
        except:
            pass  # Ignore curses errors if text doesn't fit
        
        block_win.move(stats_y + 1, 2)
        block_win.clrtoeol()
        stats_line2 = f"Written: {format_bytes(bytes_copied)} / {format_bytes(total_size_bytes)}"
        # Truncate to fit within window
        if len(stats_line2) > max_text_width:
            stats_line2 = stats_line2[:max_text_width]
        # Use try/except to prevent curses errors if text is still too long
        try:
            block_win.addstr(stats_y + 1, 2, stats_line2[:max_text_width])
        except:
            pass  # Ignore curses errors if text doesn't fit
        
        block_win.refresh()
    
    process.wait()
    
    # Read remaining stderr
    if process.stderr:
        remaining = process.stderr.read()
        if remaining:
            stderr_lines.extend(remaining.split('\n'))
    
    # Check success
    stderr_text = ''.join(stderr_lines)
    operation_succeeded = False
    
    if process.returncode == 0:
        operation_succeeded = True
    elif process.returncode == 1 and "No space left on device" in stderr_text:
        operation_succeeded = True
        log.info("Operation completed successfully (target device filled)")
    
    # Final display - fill entire map
    map_start_y = 5
    for row in range(map_height):
        for col in range(map_width):
            y_pos = map_start_y + row
            x_pos = 2 + col
            if operation_succeeded:
                block_win.addstr(y_pos, x_pos, "█", curses.color_pair(7) | curses.A_BOLD)
            else:
                block_win.addstr(y_pos, x_pos, "X", curses.color_pair(4) | curses.A_BOLD)
    
    final_color = curses.color_pair(7) if operation_succeeded else curses.color_pair(4)
    block_win.bkgd(' ', final_color)
    
    msg = "Operation completed successfully!" if operation_succeeded else f"Operation failed with code {process.returncode}"
    log.info(msg)
    
    block_win.move(stats_y + 2, 2)
    block_win.clrtoeol()
    block_win.addstr(stats_y + 2, 2, msg, curses.A_BOLD)
    block_win.addstr(stats_y + 3, 2, "Press any key to continue...")
    block_win.refresh()
    stdscr.getch()
    
    # Cleanup
    del block_win
    stdscr.touchwin()
    stdscr.refresh()

# --- Main Application Logic ---

def clone_logic(stdscr, log_pad, log_win_height):
    app_h = draw_main_layout(stdscr, "Local Clone", log_pad, log_win_height)
    devices = get_devices()
    if len(devices) < 2:
        log.error("Clone requires at least two disks.")
        show_message_box(stdscr, "Error", ["Need at least two disks to perform a clone."], app_h)
        return

    device_menu_items = [f"{d['name']:<12} │ {d['size']:<10} │ {d['model']}" for d in devices]
    source_idx = get_menu_choice(stdscr, "Select SOURCE Device", device_menu_items, app_h)
    if source_idx == -1: 
        log.info("Clone cancelled by user at source selection.")
        return
    source_device = devices[source_idx]
    
    # Check if source device is mounted
    is_mounted, mount_point = is_device_mounted(source_device['name'])
    if is_mounted:
        app_h = draw_main_layout(stdscr, "Device Mounted", log_pad, log_win_height)
        if show_confirmation(stdscr, "Source Device Mounted", [
            f"Source device {source_device['name']} is mounted at {mount_point}.",
            "For best results, the device should be unmounted before cloning.",
            "Automatically unmount all partitions now?"
        ], app_h):
            # Attempt to unmount
            success, message = unmount_device(source_device['name'])
            app_h = draw_main_layout(stdscr, "Unmount Result", log_pad, log_win_height)
            
            # Check if device became ejected/inaccessible after unmount
            if not success and "ejected" in message.lower():
                show_message_box(stdscr, "Device Ejected", [
                    "The device was unmounted but appears to have been auto-ejected.",
                    "Please re-insert the device without mounting it,",
                    "then run the clone operation again."
                ], app_h)
                log.warning(f"Device unmounted but auto-ejected: {message}")
                return
            elif success:
                show_message_box(stdscr, "Success", [
                    f"Unmount successful: {message}",
                    "Continuing with clone operation..."
                ], app_h)
                log.info(f"Device unmounted successfully: {message}")
                time.sleep(1)
            else:
                show_message_box(stdscr, "Error", [
                    f"Unmount failed: {message}",
                    "Cannot proceed with clone.",
                    "You may need to manually unmount the device."
                ], app_h)
                log.error(f"Unmount failed: {message}")
                return
        else:
            log.info("Clone cancelled - user declined to unmount source.")
            return
    
    # Check SMART status of source
    smart_ok, smart_info = check_smart_status(source_device['name'])
    app_h = draw_main_layout(stdscr, "SMART Check", log_pad, log_win_height)
    if not show_smart_results(stdscr, source_device['name'], smart_ok, smart_info, app_h):
        log.info("Clone cancelled - user declined after SMART check.")
        return

    # Redraw layout for target selection
    app_h = draw_main_layout(stdscr, "Local Clone", log_pad, log_win_height)
    target_devices = [d for i, d in enumerate(devices) if i != source_idx]
    target_menu_items = [f"{d['name']:<15} {d['size']:<10} {d['model']}" for d in target_devices]
    target_idx = get_menu_choice(stdscr, "Select TARGET Device to OVERWRITE", target_menu_items, app_h)
    if target_idx == -1: 
        log.info("Clone cancelled by user at target selection.")
        return
    target_device = target_devices[target_idx]
    
    if source_device['name'] == target_device['name']:
        log.error("Source and Target cannot be the same device.")
        show_message_box(stdscr, "Error", ["Source and target cannot be the same device."], app_h)
        return
    
    # Check if target device is mounted
    is_mounted, mount_point = is_device_mounted(target_device['name'])
    if is_mounted:
        app_h = draw_main_layout(stdscr, "Device Mounted", log_pad, log_win_height)
        if show_confirmation(stdscr, "Target Device Mounted", [
            f"Target device {target_device['name']} is mounted at {mount_point}.",
            "The device must be unmounted before cloning.",
            "Automatically unmount all partitions now?"
        ], app_h):
            # Attempt to unmount
            success, message = unmount_device(target_device['name'])
            app_h = draw_main_layout(stdscr, "Unmount Result", log_pad, log_win_height)
            
            # Check if device became ejected/inaccessible after unmount
            if not success and "ejected" in message.lower():
                show_message_box(stdscr, "Device Ejected", [
                    "The device was unmounted but appears to have been auto-ejected.",
                    "Please re-insert the device without mounting it,",
                    "then run the clone operation again."
                ], app_h)
                log.warning(f"Device unmounted but auto-ejected: {message}")
                return
            elif success:
                show_message_box(stdscr, "Success", [
                    f"Unmount successful: {message}",
                    "Continuing with clone operation..."
                ], app_h)
                log.info(f"Device unmounted successfully: {message}")
                time.sleep(1)
            else:
                show_message_box(stdscr, "Error", [
                    f"Unmount failed: {message}",
                    "Cannot proceed with clone.",
                    "You may need to manually unmount the device."
                ], app_h)
                log.error(f"Unmount failed: {message}")
                return
        else:
            log.info("Clone cancelled - user declined to unmount target.")
            return
    
    # Check SMART status of target
    # Check SMART status
    smart_ok, smart_info = check_smart_status(target_device['name'])
    app_h = draw_main_layout(stdscr, "SMART Check", log_pad, log_win_height)
    if not show_smart_results(stdscr, target_device['name'], smart_ok, smart_info, app_h):
        log.info("Clone cancelled - user declined after SMART check.")
        return

    # Redraw layout for block size choice
    app_h = draw_main_layout(stdscr, "Local Clone", log_pad, log_win_height)
    block_size = get_block_size_choice(stdscr, app_h, "Clone", source_device['name'])
    if block_size is None:
        log.info("Clone cancelled - no block size selected.")
        return

    full_cmd = f"sudo dd if={source_device['name']} of={target_device['name']} conv=sync,noerror bs={block_size} status=progress"

    # Redraw layout for confirmation
    app_h = draw_main_layout(stdscr, "Local Clone Confirmation", log_pad, log_win_height)
    if show_confirmation(stdscr, "Confirm Clone Operation", [
        f"Source: {source_device['name']} ({source_device['size']})",
        f"Target: {target_device['name']} ({target_device['size']})",
        f"Model: {target_device['model']}",
        f"Block size: {block_size}"
    ], app_h):
        # Final warning requiring explicit confirmation
        app_h = draw_main_layout(stdscr, "FINAL WARNING", log_pad, log_win_height)
        if show_final_warning(stdscr, "⚠️ IRREVERSIBLE OPERATION ⚠️", [
            f"CLONE from '{source_device['name']}' to '{target_device['name']}'.",
            f"ALL DATA on the target disk ({target_device['name']}) will be PERMANENTLY ERASED.",
            "This operation cannot be undone and may result in complete data loss."
        ], app_h):
            run_dd_with_progress(stdscr, full_cmd, source_device['bytes'], source_device['name'], target_device['name'], app_h)

def backup_logic(stdscr, log_pad, log_win_height):
    app_h = draw_main_layout(stdscr, "Local Backup", log_pad, log_win_height)
    devices = get_devices()
    if not devices:
        log.error("No block devices found for backup.")
        show_message_box(stdscr, "Error", ["No block devices found for backup."], app_h)
        return
    device_menu_items = [f"{d['name']:<12} │ {d['size']:<10} │ {d['model']}" for d in devices]
    choice_idx = get_menu_choice(stdscr, "Select SOURCE for Backup", device_menu_items, app_h)
    if choice_idx == -1: 
        log.info("Backup cancelled.")
        return
    source_device = devices[choice_idx]
    
    # Check if device is mounted
    is_mounted, mount_point = is_device_mounted(source_device['name'])
    if is_mounted:
        app_h = draw_main_layout(stdscr, "Device Mounted", log_pad, log_win_height)
        if show_confirmation(stdscr, "Device Mounted", [
            f"Device {source_device['name']} is mounted at {mount_point}.",
            "For best results, the device should be unmounted before backup.",
            "Automatically unmount all partitions now?"
        ], app_h):
            # Attempt to unmount
            success, message = unmount_device(source_device['name'])
            app_h = draw_main_layout(stdscr, "Unmount Result", log_pad, log_win_height)
            
            # Check if device became ejected/inaccessible after unmount
            if not success and "ejected" in message.lower():
                # Device was unmounted but became inaccessible (auto-eject)
                show_message_box(stdscr, "Device Ejected", [
                    "The device was unmounted but appears to have been auto-ejected.",
                    "Please re-insert the device without mounting it,",
                    "then run the backup operation again."
                ], app_h)
                log.warning(f"Device unmounted but auto-ejected: {message}")
                return
            elif success:
                show_message_box(stdscr, "Success", [
                    f"Unmount successful: {message}",
                    "Continuing with backup operation..."
                ], app_h)
                log.info(f"Device unmounted successfully: {message}")
                # Give the system a moment to settle
                time.sleep(1)
            else:
                show_message_box(stdscr, "Error", [
                    f"Unmount failed: {message}",
                    "Cannot proceed with backup.",
                    "You may need to manually unmount the device."
                ], app_h)
                log.error(f"Unmount failed: {message}")
                return
        else:
            log.info("Backup cancelled - user declined to unmount.")
            return
    
    # Check SMART status
    # Check SMART status
    smart_ok, smart_info = check_smart_status(source_device['name'])
    app_h = draw_main_layout(stdscr, "SMART Check", log_pad, log_win_height)
    if not show_smart_results(stdscr, source_device['name'], smart_ok, smart_info, app_h):
        log.info("Backup cancelled - user declined after SMART check.")
        return

    # Redraw layout for compression choice
    app_h = draw_main_layout(stdscr, "Local Backup", log_pad, log_win_height)
    compression_choice = get_compression_choice(stdscr, app_h)
    if compression_choice is None:
        log.info("Backup cancelled - no compression selected.")
        return
    
    compression_ext, compression_cmd, compression_desc = compression_choice
    
    # Redraw layout for block size choice
    app_h = draw_main_layout(stdscr, "Local Backup", log_pad, log_win_height)
    block_size = get_block_size_choice(stdscr, app_h, "Backup", source_device['name'])
    if block_size is None:
        log.info("Backup cancelled - no block size selected.")
        return
    
    # Generate default filename with timestamp and device info
    extension = ".img" + (compression_ext if compression_ext else "")
    default_filename = generate_filename("", source_device['name'], extension)
    
    # Get output directory
    app_h = draw_main_layout(stdscr, "Local Backup", log_pad, log_win_height)
    current_path = os.getcwd()
    output_dir = get_input_string(stdscr, "Enter output directory", app_h, current_path)
    if not output_dir:
        output_dir = current_path
    
    # Validate directory exists
    if not os.path.isdir(output_dir):
        app_h = draw_main_layout(stdscr, "Invalid Directory", log_pad, log_win_height)
        show_message_box(stdscr, "Directory Error", [
            f"Directory does not exist: {output_dir}",
            "Please create it first or choose another directory."
        ], app_h)
        log.error(f"Invalid directory specified: {output_dir}")
        return
    
    # Redraw layout for filename input (with default shown)
    app_h = draw_main_layout(stdscr, "Local Backup", log_pad, log_win_height)
    final_filename = get_input_string(stdscr, "Enter filename (edit or press Enter)", app_h, default_filename, show_path=output_dir)
    log.info(f"After get_input_string, got: '{final_filename}'")
    if not final_filename:
        final_filename = default_filename
    log.info(f"Final filename will be: '{final_filename}'")
    
    final_output_file = os.path.join(output_dir, final_filename)
    log.info(f"Full output path: '{final_output_file}'")
    
    # Check free space
    required_space = source_device['bytes']
    if compression_cmd:
        required_space = int(required_space * 0.4)  # Estimate 40% of original size for compression
    
    has_space, free_str, required_str = check_free_space(output_dir, required_space)
    if has_space is False:
        app_h = draw_main_layout(stdscr, "Insufficient Space", log_pad, log_win_height)
        if not show_confirmation(stdscr, "Low Disk Space Warning", [
            f"Free space: {free_str}",
            f"Required: {required_str} (estimated)",
            "Insufficient space available. Continue anyway?"
        ], app_h):
            log.info("Backup cancelled - insufficient disk space.")
            return
    
    dd_cmd = f"sudo dd if={source_device['name']} conv=sync,noerror bs={block_size} status=progress"
    if compression_cmd:
        full_cmd = f"{dd_cmd} | {compression_cmd} > \"{final_output_file}\""
    else:
        full_cmd = f"{dd_cmd} of=\"{final_output_file}\""

    # Redraw layout for final confirmation
    app_h = draw_main_layout(stdscr, "Local Backup Confirmation", log_pad, log_win_height)
    if show_confirmation(stdscr, "Confirm Backup Operation", [
        f"Source: {source_device['name']} ({source_device['size']})",
        f"Model: {source_device['model']}",
        f"Destination: {final_output_file}",
        f"Compression: {compression_desc}",
        f"Block size: {block_size}"
    ], app_h):
        # Final warning requiring explicit confirmation
        app_h = draw_main_layout(stdscr, "FINAL WARNING", log_pad, log_win_height)
        if show_final_warning(stdscr, "⚠️ BACKUP OPERATION ⚠️", [
            f"BACKUP from '{source_device['name']}' to '{final_output_file}'.",
            "This will create a complete disk image of the source device.",
            "The operation may take considerable time and disk space."
        ], app_h):
            run_dd_with_progress(stdscr, full_cmd, source_device['bytes'], source_device['name'], final_output_file, app_h)
            
            # Automatically save geometry (no prompt)
            fdisk_file = final_output_file.replace('.img.gz', '_fdisk.info').replace('.img', '_fdisk.info')
            success, _ = run_utility_command(f"sudo fdisk -l {source_device['name']} > \"{fdisk_file}\"")
            app_h = draw_main_layout(stdscr, "Backup Complete", log_pad, log_win_height)
            if success:
                show_message_box(stdscr, "Geometry Saved", [
                    "Partition table information saved:",
                    os.path.basename(fdisk_file)
                ], app_h)
            else:
                show_message_box(stdscr, "Geometry Warning", [
                    "Failed to save partition table info.",
                    "Backup image is still valid."
                ], app_h)
            
            # Directly offer checksum algorithm selection (no prompt)
            app_h = draw_main_layout(stdscr, "Select Hash Algorithm", log_pad, log_win_height)
            hash_menu = ["MD5 (faster, less secure)", "SHA-256 (slower, more secure)", "Both MD5 and SHA-256", "Skip checksum creation"]
            hash_choice = get_menu_choice(stdscr, "Select Checksum Algorithm", hash_menu, app_h)
            
            # Check if user chose to skip or cancelled
            if hash_choice != -1 and hash_choice != 3:  # Not cancelled and not "Skip"
                # Determine which checksums to create
                create_both = (hash_choice == 2)
                create_md5 = (hash_choice == 0 or create_both)
                create_sha256 = (hash_choice == 1 or create_both)
                
                # Build list of checksums to create
                checksums_to_create = []
                if create_md5:
                    checksums_to_create.append(("MD5", "md5sum", ".md5"))
                if create_sha256:
                    checksums_to_create.append(("SHA-256", "sha256sum", ".sha256"))
                
                # Calculate checksums
                all_success = True
                created_files = []
                
                for hash_name, hash_cmd, hash_ext in checksums_to_create:
                    checksum_file = f"{final_output_file}{hash_ext}"
                    log.info(f"Calculating {hash_name} checksum for {final_output_file}")
                    
                    try:
                        result = subprocess.run([hash_cmd, final_output_file], capture_output=True, text=True, check=True)
                        checksum_output = result.stdout.strip()
                        log.info(f"{hash_name} checksum calculated: {checksum_output}")
                        
                        # Write the checksum to file
                        with open(checksum_file, 'w') as f:
                            f.write(checksum_output + '\n')
                        
                        log.info(f"{hash_name} checksum file created: {checksum_file}")
                        created_files.append(f"{hash_name}: {os.path.basename(checksum_file)}")
                    except subprocess.CalledProcessError as e:
                        log.error(f"Failed to calculate {hash_name} checksum: {e}")
                        log.error(f"STDERR: {e.stderr}")
                        all_success = False
                    except Exception as e:
                        log.error(f"Exception while creating {hash_name} checksum: {e}")
                        all_success = False
                
                app_h = draw_main_layout(stdscr, "Checksum Result", log_pad, log_win_height)
                if all_success and created_files:
                    show_message_box(stdscr, "Success", ["Checksum file(s) created:"] + created_files, app_h)
                elif created_files:
                    show_message_box(stdscr, "Partial Success", ["Some checksum files created:"] + created_files, app_h)
                else:
                    show_message_box(stdscr, "Error", ["Failed to create checksum file(s)."], app_h)

def restore_logic(stdscr, log_pad, log_win_height):
    # Get image directory
    app_h = draw_main_layout(stdscr, "Local Restore", log_pad, log_win_height)
    current_path = os.getcwd()
    image_dir = get_input_string(stdscr, "Enter directory containing image files", app_h, current_path)
    if not image_dir:
        image_dir = current_path
    
    # Validate directory exists
    if not os.path.isdir(image_dir):
        app_h = draw_main_layout(stdscr, "Invalid Directory", log_pad, log_win_height)
        show_message_box(stdscr, "Directory Error", [
            f"Directory does not exist: {image_dir}",
            "Please create it first or choose another directory."
        ], app_h)
        log.error(f"Invalid directory specified: {image_dir}")
        return
    
    app_h = draw_main_layout(stdscr, "Local Restore", log_pad, log_win_height)
    image_files = get_image_files('.img', image_dir) + get_image_files('.img.gz', image_dir)
    if not image_files:
        log.warning(f"No image files found in {image_dir}")
        show_message_box(stdscr, "No Images", [
            f"No image files found in:",
            image_dir
        ], app_h)
        return
    
    image_choice_idx = get_menu_choice(stdscr, "Select Image to Restore", sorted(image_files), app_h)
    if image_choice_idx == -1: 
        log.info("Restore cancelled.")
        return
    image_filename = sorted(image_files)[image_choice_idx]
    image_file = os.path.join(image_dir, image_filename)

    is_compressed = image_file.endswith('.gz')
    total_size = get_uncompressed_size(image_file) if is_compressed else os.path.getsize(image_file)
    
    # Auto-detect and offer to verify checksum if it exists
    checksum_md5 = f"{image_file}.md5"
    checksum_sha256 = f"{image_file}.sha256"
    checksum_found = None
    hash_type = None
    
    if os.path.exists(checksum_sha256):
        checksum_found = checksum_sha256
        hash_type = "SHA-256"
    elif os.path.exists(checksum_md5):
        checksum_found = checksum_md5
        hash_type = "MD5"
    
    if checksum_found and hash_type:
        app_h = draw_main_layout(stdscr, "Checksum Found", log_pad, log_win_height)
        if show_confirmation(stdscr, "Verify Before Restore?", [
            f"Found {hash_type} checksum: {os.path.basename(checksum_found)}",
            "Verify image integrity before restoring? (Recommended)"
        ], app_h):
            # Verify the checksum
            verify_cmd = f"sha256sum -c \"{checksum_found}\"" if hash_type == "SHA-256" else f"md5sum -c \"{checksum_found}\""
            success, output = run_utility_command(verify_cmd)
            
            app_h = draw_main_layout(stdscr, "Verification Result", log_pad, log_win_height)
            if success:
                show_message_box(stdscr, "Verification Passed", [
                    f"{hash_type} verification: PASSED",
                    "Image integrity confirmed. Safe to restore."
                ], app_h)
            else:
                show_message_box(stdscr, "Verification Failed", [
                    f"{hash_type} verification: FAILED",
                    "Image may be corrupted!",
                    "Restore is NOT recommended."
                ], app_h)
                
                # Ask if they want to continue anyway
                app_h = draw_main_layout(stdscr, "Verification Failed", log_pad, log_win_height)
                if not show_confirmation(stdscr, "Continue Anyway?", [
                    "Checksum verification FAILED.",
                    "The image file may be corrupted or tampered with.",
                    "Continue with restore anyway? (NOT recommended)"
                ], app_h):
                    log.info("Restore cancelled - checksum verification failed.")
                    return

    # Redraw layout for target selection
    app_h = draw_main_layout(stdscr, "Local Restore", log_pad, log_win_height)
    devices = get_devices()
    if not devices:
        log.error("No block devices found to restore to.")
        show_message_box(stdscr, "Error", ["No block devices found to restore to."], app_h)
        return
    device_menu_items = [f"{d['name']:<12} │ {d['size']:<10} │ {d['model']}" for d in devices]
    choice_idx = get_menu_choice(stdscr, "Select TARGET Device to OVERWRITE", device_menu_items, app_h)
    if choice_idx == -1: 
        log.info("Restore cancelled.")
        return
    target_device = devices[choice_idx]
    
    # Check if device is mounted
    is_mounted, mount_point = is_device_mounted(target_device['name'])
    if is_mounted:
        app_h = draw_main_layout(stdscr, "Device Mounted", log_pad, log_win_height)
        if show_confirmation(stdscr, "Device Mounted", [
            f"Device {target_device['name']} is mounted at {mount_point}.",
            "The device must be unmounted before restoring.",
            "Automatically unmount all partitions now?"
        ], app_h):
            # Attempt to unmount
            success, message = unmount_device(target_device['name'])
            app_h = draw_main_layout(stdscr, "Unmount Result", log_pad, log_win_height)
            
            # Check if device became ejected/inaccessible after unmount
            if not success and "ejected" in message.lower():
                # Device was unmounted but became inaccessible (auto-eject)
                show_message_box(stdscr, "Device Ejected", [
                    "The device was unmounted but appears to have been auto-ejected.",
                    "Please re-insert the device without mounting it,",
                    "then run the restore operation again."
                ], app_h)
                log.warning(f"Device unmounted but auto-ejected: {message}")
                return
            elif success:
                show_message_box(stdscr, "Success", [
                    f"Unmount successful: {message}",
                    "Continuing with restore operation..."
                ], app_h)
                log.info(f"Device unmounted successfully: {message}")
                # Give the system a moment to settle
                time.sleep(1)
            else:
                show_message_box(stdscr, "Error", [
                    f"Unmount failed: {message}",
                    "Cannot proceed with restore.",
                    "You may need to manually unmount the device."
                ], app_h)
                log.error(f"Unmount failed: {message}")
                return
        else:
            log.info("Restore cancelled - user declined to unmount.")
            return
    
    # Check SMART status
    # Check SMART status
    smart_ok, smart_info = check_smart_status(target_device['name'])
    app_h = draw_main_layout(stdscr, "SMART Check", log_pad, log_win_height)
    if not show_smart_results(stdscr, target_device['name'], smart_ok, smart_info, app_h):
        log.info("Restore cancelled - user declined after SMART check.")
        return

    # Redraw layout for block size choice
    app_h = draw_main_layout(stdscr, "Local Restore", log_pad, log_win_height)
    block_size = get_block_size_choice(stdscr, app_h, "Restore", target_device['name'])
    if block_size is None:
        log.info("Restore cancelled - no block size selected.")
        return

    dd_cmd = f"sudo dd of={target_device['name']} conv=sync,noerror bs={block_size} status=progress"
    full_cmd = f"gunzip -c \"{image_file}\" | {dd_cmd}" if is_compressed else f"sudo dd if=\"{image_file}\" of={target_device['name']} conv=sync,noerror bs={block_size} status=progress"
    
    # Redraw layout for confirmation
    app_h = draw_main_layout(stdscr, "Local Restore Confirmation", log_pad, log_win_height)
    if show_confirmation(stdscr, "Confirm Restore Operation", [
        f"Image: {image_file}",
        f"Compressed: {'Yes' if is_compressed else 'No'}",
        f"Target: {target_device['name']} ({target_device['size']})",
        f"Model: {target_device['model']}",
        f"Block size: {block_size}"
    ], app_h):
        # Final warning requiring explicit confirmation
        app_h = draw_main_layout(stdscr, "FINAL WARNING", log_pad, log_win_height)
        if show_final_warning(stdscr, "⚠️ IRREVERSIBLE OPERATION ⚠️", [
            f"RESTORE image '{image_file}' to device '{target_device['name']}'.",
            "ALL DATA on the target device will be PERMANENTLY ERASED.",
            "This operation cannot be undone and will completely overwrite the target device."
        ], app_h):
            run_dd_with_progress(stdscr, full_cmd, total_size, image_file, target_device['name'], app_h)

def checksum_logic(stdscr, log_pad, log_win_height):
    # Get image directory
    app_h = draw_main_layout(stdscr, "Create Checksum", log_pad, log_win_height)
    current_path = os.getcwd()
    image_dir = get_input_string(stdscr, "Enter directory containing image files", app_h, current_path)
    if not image_dir:
        image_dir = current_path
    
    # Validate directory exists
    if not os.path.isdir(image_dir):
        app_h = draw_main_layout(stdscr, "Invalid Directory", log_pad, log_win_height)
        show_message_box(stdscr, "Directory Error", [
            f"Directory does not exist: {image_dir}",
            "Please create it first or choose another directory."
        ], app_h)
        log.error(f"Invalid directory specified: {image_dir}")
        return
    
    app_h = draw_main_layout(stdscr, "Create Checksum", log_pad, log_win_height)
    image_files = get_image_files('.img', image_dir) + get_image_files('.img.gz', image_dir)
    if not image_files:
        log.warning(f"No image files found in {image_dir}")
        show_message_box(stdscr, "No Images Found", [
            f"No .img or .img.gz files found in:",
            image_dir
        ], app_h)
        return

    image_choice_idx = get_menu_choice(stdscr, "Select Image for Checksum", sorted(image_files), app_h)
    if image_choice_idx == -1:
        log.info("Checksum creation cancelled.")
        return
    image_filename = sorted(image_files)[image_choice_idx]
    image_file = os.path.join(image_dir, image_filename)
    
    # Choose hash algorithm
    app_h = draw_main_layout(stdscr, "Select Hash Algorithm", log_pad, log_win_height)
    hash_menu = ["MD5 (faster, less secure)", "SHA-256 (slower, more secure)", "Both MD5 and SHA-256"]
    hash_choice = get_menu_choice(stdscr, "Select Checksum Algorithm", hash_menu, app_h)
    if hash_choice == -1:
        log.info("Checksum creation cancelled.")
        return
    
    # Determine which checksums to create
    create_both = (hash_choice == 2)
    create_md5 = (hash_choice == 0 or create_both)
    create_sha256 = (hash_choice == 1 or create_both)
    
    # Build list of checksums to create
    checksums_to_create = []
    if create_md5:
        checksums_to_create.append(("MD5", "md5sum", ".md5"))
    if create_sha256:
        checksums_to_create.append(("SHA-256", "sha256sum", ".sha256"))
    
    # Check if checksum files already exist
    existing_files = []
    for hash_name, _, hash_ext in checksums_to_create:
        checksum_file = f"{image_file}{hash_ext}"
        if os.path.exists(checksum_file):
            existing_files.append(checksum_file)
    
    if existing_files:
        app_h = draw_main_layout(stdscr, "Checksum Exists", log_pad, log_win_height)
        msg = ["The following checksum file(s) already exist:"] + existing_files + ["", "Overwrite them?"]
        if not show_confirmation(stdscr, "Overwrite Checksum", msg, app_h):
            log.info("Checksum creation cancelled - file(s) exist.")
            return

    # Confirm creation
    app_h = draw_main_layout(stdscr, "Create Checksum", log_pad, log_win_height)
    if create_both:
        confirm_msg = [f"Create MD5 and SHA-256 checksums for:", f"'{image_file}'?"]
    else:
        hash_name = checksums_to_create[0][0]
        confirm_msg = [f"Create {hash_name} checksum for:", f"'{image_file}'?"]
    
    if show_confirmation(stdscr, "Confirm Checksum Creation", confirm_msg, app_h):
        # Calculate the checksums
        all_success = True
        created_files = []
        
        for hash_name, hash_cmd, hash_ext in checksums_to_create:
            checksum_file = f"{image_file}{hash_ext}"
            log.info(f"Calculating {hash_name} checksum for {image_file}")
            
            try:
                result = subprocess.run([hash_cmd, image_file], capture_output=True, text=True, check=True)
                checksum_output = result.stdout.strip()
                log.info(f"{hash_name} checksum calculated: {checksum_output}")
                
                # Write the checksum to file
                with open(checksum_file, 'w') as f:
                    f.write(checksum_output + '\n')
                
                log.info(f"{hash_name} checksum file created: {checksum_file}")
                created_files.append(f"{hash_name}: {checksum_file}")
            except subprocess.CalledProcessError as e:
                log.error(f"Failed to calculate {hash_name} checksum: {e}")
                log.error(f"STDERR: {e.stderr}")
                all_success = False
            except Exception as e:
                log.error(f"Exception while creating {hash_name} checksum: {e}")
                all_success = False
        
        app_h = draw_main_layout(stdscr, "Checksum Result", log_pad, log_win_height)
        if all_success and created_files:
            show_message_box(stdscr, "Success", ["Checksum file(s) created:"] + created_files, app_h)
        elif created_files:
            show_message_box(stdscr, "Partial Success", ["Some checksum files created:"] + created_files, app_h)
        else:
            show_message_box(stdscr, "Error", ["Failed to create checksum file(s)."], app_h)

def verify_logic(stdscr, log_pad, log_win_height):
    # Get directory containing checksums
    app_h = draw_main_layout(stdscr, "Verify Image", log_pad, log_win_height)
    current_path = os.getcwd()
    checksum_dir = get_input_string(stdscr, "Enter directory containing checksum files", app_h, current_path)
    if not checksum_dir:
        checksum_dir = current_path
    
    # Validate directory exists
    if not os.path.isdir(checksum_dir):
        app_h = draw_main_layout(stdscr, "Invalid Directory", log_pad, log_win_height)
        show_message_box(stdscr, "Directory Error", [
            f"Directory does not exist: {checksum_dir}",
            "Please create it first or choose another directory."
        ], app_h)
        log.error(f"Invalid directory specified: {checksum_dir}")
        return
    
    app_h = draw_main_layout(stdscr, "Verify Image", log_pad, log_win_height)
    md5_files = get_image_files('.md5', checksum_dir)
    sha256_files = get_image_files('.sha256', checksum_dir)
    checksum_files = md5_files + sha256_files
    
    if not checksum_files:
        log.warning(f"No checksum files found in {checksum_dir}")
        show_message_box(stdscr, "No Checksums Found", [
            f"No .md5 or .sha256 files found in:",
            checksum_dir
        ], app_h)
        return

    # Create descriptive menu items showing what each checksum verifies
    menu_items = []
    for cf in sorted(checksum_files):
        # Extract the image filename from checksum filename (remove .md5 or .sha256)
        if cf.endswith('.md5'):
            img_name = cf[:-4]  # Remove .md5
            hash_type = "MD5"
        else:
            img_name = cf[:-7]  # Remove .sha256
            hash_type = "SHA256"
        menu_items.append(f"{img_name} ({hash_type})")
    
    checksum_choice_idx = get_menu_choice(stdscr, "Select Image to Verify", menu_items, app_h)
    if checksum_choice_idx == -1: log.info("Verify cancelled."); return
    checksum_filename = sorted(checksum_files)[checksum_choice_idx]
    checksum_file = os.path.join(checksum_dir, checksum_filename)
    
    # Determine hash type from file extension
    is_sha256 = checksum_file.endswith('.sha256')
    hash_name = "SHA-256" if is_sha256 else "MD5"
    
    # Pre-flight check: ensure the file listed in the checksum file exists
    try:
        with open(checksum_file, 'r') as f:
            line = f.readline().strip()
        # The format is HASH  FILENAME or HASH *FILENAME. The filename can contain spaces.
        parts = line.split(None, 1)
        if len(parts) < 2:
            raise ValueError("Malformed checksum line")
        # The filename part might start with a '*' for binary mode
        image_filename_in_checksum = parts[1].lstrip('* ')
        
        # Check if image exists in the same directory as checksum file
        image_full_path = os.path.join(checksum_dir, image_filename_in_checksum)
        if not os.path.exists(image_full_path):
            log.error(f"Image file '{image_filename_in_checksum}' referenced in '{checksum_file}' does not exist.")
            show_message_box(stdscr, "Error", [
                f"The image file '{image_filename_in_checksum}'",
                "listed in the checksum file was not found in:",
                checksum_dir
            ], app_h)
            return
    except Exception as e:
        log.error(f"Could not read or parse checksum file {checksum_file}: {e}")
        show_message_box(stdscr, "Error", [f"Could not read or parse checksum file: {checksum_file}"], app_h)
        return
    
    app_h = draw_main_layout(stdscr, "Verify Checksum", log_pad, log_win_height)
    if show_confirmation(stdscr, "Verify Image Integrity", [
        f"Image file: {image_filename_in_checksum}",
        f"Checksum type: {hash_name}",
        f"Checksum file: {checksum_filename}",
        "",
        "This will verify the image file has not been corrupted.",
        "Proceed with verification?"
    ], app_h):
        log.info(f"Verifying {image_filename_in_checksum} using {checksum_filename}")
        # Run verification from the checksum directory
        verify_cmd = f"cd \"{checksum_dir}\" && sha256sum -c \"{checksum_filename}\"" if is_sha256 else f"cd \"{checksum_dir}\" && md5sum -c \"{checksum_filename}\""
        success, output = run_utility_command(verify_cmd)
        app_h = draw_main_layout(stdscr, "Verification Result", log_pad, log_win_height)
        if success:
            show_message_box(stdscr, "Verification PASSED", [
                f"Image: {image_filename_in_checksum}",
                f"Checksum: {hash_name}",
                "",
                "✓ File integrity verified successfully!",
                "The image file has not been corrupted."
            ], app_h)
        else:
            show_message_box(stdscr, "Verification FAILED", [
                f"Image: {image_filename_in_checksum}",
                f"Checksum: {hash_name}",
                "",
                "✗ Verification FAILED!",
                "The image file may be corrupted or modified.",
                "Do NOT use this image for restore operations."
            ], app_h)

def create_image_logic(stdscr, log_pad, log_win_height):
    """Backup disk submenu - all backup operations including disk-to-disk."""
    while True:
        app_h = draw_main_layout(stdscr, "Backup Disk", log_pad, log_win_height)
        
        submenu = ["To Local File", "To Network (SSH)", "To Network (NFS)", 
                   "To Another Disk (Direct Copy)", "Manage Checksums", 
                   "Back to Main Menu"]
        choice = get_menu_choice(stdscr, "Backup Disk", submenu, app_h)
        
        if choice == 0:
            backup_logic(stdscr, log_pad, log_win_height)
        elif choice == 1:
            # Network backup via SSH
            network_backup_ssh_only(stdscr, log_pad, log_win_height, "ssh")
        elif choice == 2:
            # Network backup via NFS
            network_backup_ssh_only(stdscr, log_pad, log_win_height, "nfs")
        elif choice == 3:
            # Direct disk-to-disk copy (clone)
            clone_logic(stdscr, log_pad, log_win_height)
        elif choice == 4:
            # Manage checksums for existing backups
            checksum_management_logic(stdscr, log_pad, log_win_height)
        elif choice == 5 or choice == -1:
            log.info("Returning to main menu from backup disk.")
            return

def restore_image_logic(stdscr, log_pad, log_win_height):
    """Restore disk submenu - restore operations."""
    while True:
        app_h = draw_main_layout(stdscr, "Restore Disk", log_pad, log_win_height)
        
        submenu = ["From Local File", "From Network (SSH)", "From Network (NFS)", 
                   "Verify Checksum", "Back to Main Menu"]
        choice = get_menu_choice(stdscr, "Restore Disk", submenu, app_h)
        
        if choice == 0:
            restore_logic(stdscr, log_pad, log_win_height)
        elif choice == 1:
            # Network restore via SSH
            network_restore_ssh_only(stdscr, log_pad, log_win_height, "ssh")
        elif choice == 2:
            # Network restore via NFS
            network_restore_ssh_only(stdscr, log_pad, log_win_height, "nfs")
        elif choice == 3:
            # Verify checksum before restore
            verify_logic(stdscr, log_pad, log_win_height)
        elif choice == 4 or choice == -1:
            log.info("Returning to main menu from restore disk.")
            return

def clone_disk_logic(stdscr, log_pad, log_win_height):
    """Clone disk submenu - clone operations."""
    while True:
        app_h = draw_main_layout(stdscr, "Clone Disk", log_pad, log_win_height)
        
        submenu = ["Local Clone", "Back to Main Menu"]
        choice = get_menu_choice(stdscr, "Clone Disk", submenu, app_h)
        
        if choice == 0:
            clone_logic(stdscr, log_pad, log_win_height)
        elif choice == 1 or choice == -1:
            log.info("Returning to main menu from clone disk.")
            return

def checksum_management_logic(stdscr, log_pad, log_win_height):
    """Checksum management submenu for creating and verifying checksums."""
    while True:
        app_h = draw_main_layout(stdscr, "Checksum Management", log_pad, log_win_height)
        
        submenu = ["Create Checksum", "Verify Checksum", "Back to Main Menu"]
        choice = get_menu_choice(stdscr, "Checksum Management", submenu, app_h)
        
        if choice == 0:
            checksum_logic(stdscr, log_pad, log_win_height)
        elif choice == 1:
            verify_logic(stdscr, log_pad, log_win_height)
        elif choice == 2 or choice == -1:
            log.info("Returning to main menu from checksum management.")
            return

def network_backup_ssh_only(stdscr, log_pad, log_win_height, protocol):
    """Network backup with pre-selected protocol (called from submenu)."""
    app_h = draw_main_layout(stdscr, "Network Backup", log_pad, log_win_height)
    nfs_mount_point = "/tmp/disk_imager_nfs"
    
    # Select source device
    devices = get_devices()
    if not devices:
        log.error("No block devices found for backup.")
        show_message_box(stdscr, "Error", ["No block devices found."], app_h)
        return
    
    device_menu_items = [f"{d['name']:<12} │ {d['size']:<10} │ {d['model']}" for d in devices]
    choice_idx = get_menu_choice(stdscr, "Select SOURCE Device", device_menu_items, app_h)
    if choice_idx == -1:
        log.info("Network backup cancelled.")
        return
    source_device = devices[choice_idx]
    
    # Check if device is mounted
    is_mounted, mount_point = is_device_mounted(source_device['name'])
    if is_mounted:
        app_h = draw_main_layout(stdscr, "Device Mounted", log_pad, log_win_height)
        if show_confirmation(stdscr, "Device Mounted", [
            f"Device {source_device['name']} is mounted at {mount_point}.",
            "For best results, the device should be unmounted before backup.",
            "Automatically unmount all partitions now?"
        ], app_h):
            # Attempt to unmount
            success, message = unmount_device(source_device['name'])
            app_h = draw_main_layout(stdscr, "Unmount Result", log_pad, log_win_height)
            
            # Check if device became ejected/inaccessible after unmount
            if not success and "ejected" in message.lower():
                show_message_box(stdscr, "Device Ejected", [
                    "The device was unmounted but appears to have been auto-ejected.",
                    "Please re-insert the device without mounting it,",
                    "then run the backup operation again."
                ], app_h)
                log.warning(f"Device unmounted but auto-ejected: {message}")
                return
            elif success:
                show_message_box(stdscr, "Success", [
                    f"Unmount successful: {message}",
                    "Continuing with backup operation..."
                ], app_h)
                log.info(f"Device unmounted successfully: {message}")
                time.sleep(1)
            else:
                show_message_box(stdscr, "Error", [
                    f"Unmount failed: {message}",
                    "Cannot proceed with backup.",
                    "You may need to manually unmount the device."
                ], app_h)
                log.error(f"Unmount failed: {message}")
                return
        else:
            log.info("Network backup cancelled - user declined to unmount.")
            return
    
    # Check SMART status
    # Check SMART status
    smart_ok, smart_info = check_smart_status(source_device['name'])
    app_h = draw_main_layout(stdscr, "SMART Check", log_pad, log_win_height)
    if not show_smart_results(stdscr, source_device['name'], smart_ok, smart_info, app_h):
        log.info("Network backup cancelled - user declined after SMART check.")
        return
    
    if protocol == "ssh":
        # Get SSH connection details
        app_h = draw_main_layout(stdscr, "SSH Details", log_pad, log_win_height)
        ssh_host = get_input_string(stdscr, "Enter SSH hostname/IP", app_h)
        if not ssh_host:
            log.info("Network backup cancelled.")
            return
        
        app_h = draw_main_layout(stdscr, "SSH Details", log_pad, log_win_height)
        ssh_user = get_input_string(stdscr, "Enter SSH username", app_h)
        if not ssh_user:
            log.info("Network backup cancelled.")
            return
        
        # Test SSH connection first (moved up for browsing)
        app_h = draw_main_layout(stdscr, "Testing Connection", log_pad, log_win_height)
        ssh_ok, ssh_msg = test_ssh_connection(ssh_host, ssh_user)
        if not ssh_ok:
            show_message_box(stdscr, "SSH Error", [
                f"Cannot connect to {ssh_user}@{ssh_host}",
                ssh_msg
            ], app_h)
            return
        
        # Offer to browse or manually enter directory
        app_h = draw_main_layout(stdscr, "Directory Selection", log_pad, log_win_height)
        browse_choice = show_confirmation(stdscr, "Select Remote Directory", [
            "Browse remote directories?",
            "(No = manual path entry)"
        ], app_h)
        
        if browse_choice:
            # Browse remote directories
            remote_dir = ssh_browse_directory(stdscr, ssh_user, ssh_host, 
                                             "/home", log_pad, log_win_height, 
                                             filter_dirs_only=True)
            if not remote_dir:
                log.info("Network backup cancelled - no directory selected.")
                return
        else:
            # Manual entry
            app_h = draw_main_layout(stdscr, "SSH Details", log_pad, log_win_height)
            remote_dir = get_input_string(stdscr, "Enter remote directory", app_h)
            if not remote_dir:
                log.info("Network backup cancelled.")
                return
        
        
        app_h = draw_main_layout(stdscr, "Network Backup", log_pad, log_win_height)
        compression_choice = get_compression_choice(stdscr, app_h)
        if compression_choice is None:
            log.info("Network backup cancelled - no compression selected.")
            return
        
        compression_ext, compression_cmd, compression_desc = compression_choice
        
        # Generate default filename with timestamp
        extension = ".img" + (compression_ext if compression_ext else "")
        default_filename = generate_filename("", source_device['name'], extension)
        
        # Ensure screen is clean for filename prompt
        stdscr.clear()
        stdscr.refresh()
        app_h = draw_main_layout(stdscr, "Filename", log_pad, log_win_height)
        final_filename = get_input_string(stdscr, "Enter backup filename", app_h, default_filename)
        if not final_filename:
            final_filename = default_filename
        
        remote_path = f"{remote_dir}/{final_filename}"
        
        # Build SSH command
        if compression_cmd:
            full_cmd = (f"sudo dd if={source_device['name']} {DD_OPTS} "
                       f"status=progress | {compression_cmd} | "
                       f"ssh {ssh_user}@{ssh_host} 'cat > {remote_path}'")
        else:
            full_cmd = (f"sudo dd if={source_device['name']} {DD_OPTS} "
                       f"status=progress | "
                       f"ssh {ssh_user}@{ssh_host} 'cat > {remote_path}'")
        
        dest_str = f"{ssh_user}@{ssh_host}:{remote_path}"
        
    else:  # NFS
        app_h = draw_main_layout(stdscr, "NFS Details", log_pad, log_win_height)
        nfs_path = get_input_string(stdscr, "Enter NFS path (server:/path)", app_h)
        if not nfs_path:
            log.info("Network backup cancelled.")
            return
        
        # Check NFS availability
        app_h = draw_main_layout(stdscr, "Testing NFS", log_pad, log_win_height)
        nfs_ok, nfs_msg = check_nfs_mount(nfs_path)
        if not nfs_ok:
            show_message_box(stdscr, "NFS Error", [
                f"Cannot access NFS path {nfs_path}",
                nfs_msg
            ], app_h)
            return
        
        app_h = draw_main_layout(stdscr, "Network Backup", log_pad, log_win_height)
        # Mount NFS temporarily
        os.makedirs(nfs_mount_point, exist_ok=True)
        mount_cmd = f"sudo mount -t nfs {nfs_path} {nfs_mount_point}"
        mount_result = subprocess.run(mount_cmd, shell=True, capture_output=True)
        
        if mount_result.returncode != 0:
            show_message_box(stdscr, "Mount Error", [
                f"Failed to mount NFS path {nfs_path}"
            ], app_h)
            return
        
        app_h = draw_main_layout(stdscr, "Network Backup", log_pad, log_win_height)
        compression_choice = get_compression_choice(stdscr, app_h)
        if compression_choice is None:
            log.info("Network backup cancelled - no compression selected.")
            return
        
        compression_ext, compression_cmd, compression_desc = compression_choice
        
        
        # Generate default filename with timestamp
        extension = ".img" + (compression_ext if compression_ext else "")
        default_filename = generate_filename("", source_device['name'], extension)
        
        # Ensure screen is clean for filename prompt
        stdscr.clear()
        stdscr.refresh()
        app_h = draw_main_layout(stdscr, "Filename", log_pad, log_win_height)
        final_filename = get_input_string(stdscr, "Enter backup filename", app_h, default_filename)
        if not final_filename:
            final_filename = default_filename
        
        final_path = os.path.join(nfs_mount_point, final_filename)
        
        if compression_cmd:
            full_cmd = (f"sudo dd if={source_device['name']} {DD_OPTS} "
                       f"status=progress | {compression_cmd} > {final_path}")
        else:
            full_cmd = (f"sudo dd if={source_device['name']} {DD_OPTS} "
                       f"of={final_path} status=progress")
        
        dest_str = f"{nfs_path}/{final_filename}"
    
    # Confirmation
    app_h = draw_main_layout(stdscr, "Network Backup Confirmation", 
                            log_pad, log_win_height)
    if show_confirmation(stdscr, "Confirm Network Backup", [
        f"Source: {source_device['name']} ({source_device['size']})",
        f"Destination: {dest_str}",
        f"Protocol: {protocol.upper()}",
        f"Compression: {compression_desc}"
    ], app_h):
        app_h = draw_main_layout(stdscr, "FINAL WARNING", log_pad, log_win_height)
        if show_final_warning(stdscr, "⚠️ NETWORK BACKUP ⚠️", [
            f"BACKUP from '{source_device['name']}' to '{dest_str}'.",
            "This will create a complete disk image over the network.",
            "The operation may take considerable time."
        ], app_h):
            run_dd_with_progress(stdscr, full_cmd, source_device['bytes'],
                               source_device['name'], dest_str, app_h)
            
            # Cleanup NFS mount if used
            if protocol == "nfs":
                subprocess.run(f"sudo umount {nfs_mount_point}", 
                             shell=True, capture_output=True)
                try:
                    os.rmdir(nfs_mount_point)
                except:
                    pass

def network_restore_ssh_only(stdscr, log_pad, log_win_height, protocol):
    """Network restore with pre-selected protocol (called from submenu)."""
    app_h = draw_main_layout(stdscr, "Network Restore", log_pad, log_win_height)
    nfs_mount_point = "/tmp/disk_imager_nfs"
    
    # Select target device
    devices = get_devices()
    if not devices:
        log.error("No block devices found for restore.")
        show_message_box(stdscr, "Error", ["No block devices found."], app_h)
        return
    
    device_menu_items = [f"{d['name']:<15} {d['size']:<10} {d['model']}" 
                        for d in devices]
    choice_idx = get_menu_choice(stdscr, "Select TARGET Device to OVERWRITE",
                                 device_menu_items, app_h)
    if choice_idx == -1:
        log.info("Network restore cancelled.")
        return
    target_device = devices[choice_idx]
    
    # Check if device is mounted
    is_mounted, mount_point = is_device_mounted(target_device['name'])
    if is_mounted:
        app_h = draw_main_layout(stdscr, "Device Mounted", log_pad, log_win_height)
        if show_confirmation(stdscr, "Device Mounted", [
            f"Device {target_device['name']} is mounted at {mount_point}.",
            "The device must be unmounted before restoring.",
            "Automatically unmount all partitions now?"
        ], app_h):
            # Attempt to unmount
            success, message = unmount_device(target_device['name'])
            app_h = draw_main_layout(stdscr, "Unmount Result", log_pad, log_win_height)
            
            # Check if device became ejected/inaccessible after unmount
            if not success and "ejected" in message.lower():
                show_message_box(stdscr, "Device Ejected", [
                    "The device was unmounted but appears to have been auto-ejected.",
                    "Please re-insert the device without mounting it,",
                    "then run the restore operation again."
                ], app_h)
                log.warning(f"Device unmounted but auto-ejected: {message}")
                return
            elif success:
                show_message_box(stdscr, "Success", [
                    f"Unmount successful: {message}",
                    "Continuing with restore operation..."
                ], app_h)
                log.info(f"Device unmounted successfully: {message}")
                time.sleep(1)
            else:
                show_message_box(stdscr, "Error", [
                    f"Unmount failed: {message}",
                    "Cannot proceed with restore.",
                    "You may need to manually unmount the device."
                ], app_h)
                log.error(f"Unmount failed: {message}")
                return
        else:
            log.info("Network restore cancelled - user declined to unmount.")
            return
    
    # Check SMART status
    # Check SMART status
    smart_ok, smart_info = check_smart_status(target_device['name'])
    app_h = draw_main_layout(stdscr, "SMART Check", log_pad, log_win_height)
    if not show_smart_results(stdscr, target_device['name'], smart_ok, smart_info, app_h):
        log.info("Network restore cancelled - user declined after SMART check.")
        return
    
    if protocol == "ssh":
        # Get SSH connection details
        app_h = draw_main_layout(stdscr, "SSH Details", log_pad, log_win_height)
        ssh_host = get_input_string(stdscr, "Enter SSH hostname/IP", app_h)
        if not ssh_host:
            log.info("Network restore cancelled.")
            return
        
        app_h = draw_main_layout(stdscr, "SSH Details", log_pad, log_win_height)
        ssh_user = get_input_string(stdscr, "Enter SSH username", app_h)
        if not ssh_user:
            log.info("Network restore cancelled.")
            return
        
        app_h = draw_main_layout(stdscr, "SSH Details", log_pad, log_win_height)
        # Test SSH connection first (needed for browsing)
        app_h = draw_main_layout(stdscr, "Testing Connection", log_pad, log_win_height)
        ssh_ok, ssh_msg = test_ssh_connection(ssh_host, ssh_user)
        if not ssh_ok:
            show_message_box(stdscr, "SSH Error", [
                f"Cannot connect to {ssh_user}@{ssh_host}",
                ssh_msg
            ], app_h)
            return
        
        # Offer to browse or manually enter file path
        app_h = draw_main_layout(stdscr, "File Selection", log_pad, log_win_height)
        browse_choice = show_confirmation(stdscr, "Select Remote Image", [
            "Browse remote files?",
            "(No = manual path entry)"
        ], app_h)
        
        if browse_choice:
            # Browse remote files (filter for .img and .img.gz)
            remote_file = ssh_browse_directory(stdscr, ssh_user, ssh_host,
                                              "/home", log_pad, log_win_height,
                                              file_filter=['.img', '.img.gz'])
            if not remote_file:
                log.info("Network restore cancelled - no file selected.")
                return
        else:
            # Manual entry
            remote_file = get_input_string(stdscr, "Enter remote image path", app_h)
            if not remote_file:
                log.info("Network restore cancelled.")
                return
        
        # Auto-detect compression from filename
        is_compressed = remote_file.endswith('.gz')
        
        # Allow user to override if not compressed
        app_h = draw_main_layout(stdscr, "Network Restore", log_pad, log_win_height)
        if not is_compressed:
            is_compressed = show_confirmation(stdscr, "Compression",
                                            ["Is the remote file gzip compressed?"], app_h)
        
        # Build SSH command
        if is_compressed:
            full_cmd = (f"ssh {ssh_user}@{ssh_host} 'cat {remote_file}' | "
                       f"gunzip -c | sudo dd of={target_device['name']} "
                       f"{DD_OPTS} status=progress")
        else:
            full_cmd = (f"ssh {ssh_user}@{ssh_host} 'cat {remote_file}' | "
                       f"sudo dd of={target_device['name']} {DD_OPTS} "
                       f"status=progress")
        
        source_str = f"{ssh_user}@{ssh_host}:{remote_file}"
        total_size = target_device['bytes']  # Estimate
        
    else:  # NFS
        app_h = draw_main_layout(stdscr, "NFS Details", log_pad, log_win_height)
        nfs_path = get_input_string(stdscr, "Enter NFS path (server:/path)", app_h)
        if not nfs_path:
            log.info("Network restore cancelled.")
            return
        
        # Check NFS availability
        app_h = draw_main_layout(stdscr, "Testing NFS", log_pad, log_win_height)
        nfs_ok, nfs_msg = check_nfs_mount(nfs_path)
        if not nfs_ok:
            show_message_box(stdscr, "NFS Error", [
                f"Cannot access NFS path {nfs_path}",
                nfs_msg
            ], app_h)
            return
        
        # Mount NFS temporarily
        os.makedirs(nfs_mount_point, exist_ok=True)
        mount_cmd = f"sudo mount -t nfs {nfs_path} {nfs_mount_point}"
        mount_result = subprocess.run(mount_cmd, shell=True, capture_output=True)
        
        if mount_result.returncode != 0:
            show_message_box(stdscr, "Mount Error", [
                f"Failed to mount NFS path {nfs_path}"
            ], app_h)
            return
        
        # List available image files
        try:
            files = [f for f in os.listdir(nfs_mount_point) 
                    if f.endswith('.img') or f.endswith('.img.gz')]
            if not files:
                show_message_box(stdscr, "No Images", [
                    "No image files found on NFS share."
                ], app_h)
                subprocess.run(f"sudo umount {nfs_mount_point}", 
                             shell=True, capture_output=True)
                return
            
            app_h = draw_main_layout(stdscr, "Select Image", log_pad, log_win_height)
            file_idx = get_menu_choice(stdscr, "Select Image File", sorted(files), app_h)
            if file_idx == -1:
                subprocess.run(f"sudo umount {nfs_mount_point}", 
                             shell=True, capture_output=True)
                return
            
            image_file = sorted(files)[file_idx]
            image_path = os.path.join(nfs_mount_point, image_file)
            is_compressed = image_file.endswith('.gz')
            
            if is_compressed:
                total_size = get_uncompressed_size(image_path)
                full_cmd = (f"gunzip -c {image_path} | "
                           f"sudo dd of={target_device['name']} {DD_OPTS} "
                           f"status=progress")
            else:
                total_size = os.path.getsize(image_path)
                full_cmd = (f"sudo dd if={image_path} of={target_device['name']} "
                           f"{DD_OPTS} status=progress")
            
            source_str = f"{nfs_path}/{image_file}"
            
        except Exception as e:
            show_message_box(stdscr, "Error", [f"Error accessing NFS: {e}"], app_h)
            subprocess.run(f"sudo umount {nfs_mount_point}", 
                         shell=True, capture_output=True)
            return
    
    # Confirmation
    app_h = draw_main_layout(stdscr, "Network Restore Confirmation",
                            log_pad, log_win_height)
    if show_confirmation(stdscr, "Confirm Network Restore", [
        f"Source: {source_str}",
        f"Target: {target_device['name']} ({target_device['size']})",
        f"Protocol: {protocol.upper()}",
        f"Compressed: {'Yes' if is_compressed else 'No'}"
    ], app_h):
        app_h = draw_main_layout(stdscr, "FINAL WARNING", log_pad, log_win_height)
        if show_final_warning(stdscr, "⚠️ IRREVERSIBLE OPERATION ⚠️", [
            f"RESTORE from '{source_str}' to '{target_device['name']}'.",
            "ALL DATA on the target device will be PERMANENTLY ERASED.",
            "This operation cannot be undone."
        ], app_h):
            run_dd_with_progress(stdscr, full_cmd, total_size,
                               source_str, target_device['name'], app_h)
            
            # Cleanup NFS mount if used
            if protocol == "nfs":
                subprocess.run(f"sudo umount {nfs_mount_point}",
                             shell=True, capture_output=True)
                try:
                    os.rmdir(nfs_mount_point)
                except:
                    pass

def network_backup_logic(stdscr, log_pad, log_win_height):
    """Backup disk to remote location via SSH or NFS."""
    app_h = draw_main_layout(stdscr, "Network Backup", log_pad, log_win_height)
    
    # Choose network protocol
    protocol_menu = ["SSH (Secure Shell)", "NFS (Network File System)", "Cancel"]
    protocol_idx = get_menu_choice(stdscr, "Select Network Protocol", protocol_menu, app_h)
    if protocol_idx == -1 or protocol_idx == 2:
        log.info("Network backup cancelled.")
        return
    
    protocol = "ssh" if protocol_idx == 0 else "nfs"
    nfs_mount_point = "/tmp/disk_imager_nfs"
    
    # Select source device
    app_h = draw_main_layout(stdscr, "Network Backup", log_pad, log_win_height)
    devices = get_devices()
    if not devices:
        log.error("No block devices found for backup.")
        show_message_box(stdscr, "Error", ["No block devices found."], app_h)
        return
    
    device_menu_items = [f"{d['name']:<12} │ {d['size']:<10} │ {d['model']}" for d in devices]
    choice_idx = get_menu_choice(stdscr, "Select SOURCE Device", device_menu_items, app_h)
    if choice_idx == -1:
        log.info("Network backup cancelled.")
        return
    source_device = devices[choice_idx]
    
    # Check if device is mounted
    is_mounted, mount_point = is_device_mounted(source_device['name'])
    if is_mounted:
        app_h = draw_main_layout(stdscr, "Device Mounted", log_pad, log_win_height)
        if show_confirmation(stdscr, "Device Mounted", [
            f"Device {source_device['name']} is mounted at {mount_point}.",
            "For best results, the device should be unmounted before backup.",
            "Automatically unmount all partitions now?"
        ], app_h):
            # Attempt to unmount
            success, message = unmount_device(source_device['name'])
            app_h = draw_main_layout(stdscr, "Unmount Result", log_pad, log_win_height)
            
            # Check if device became ejected/inaccessible after unmount
            if not success and "ejected" in message.lower():
                show_message_box(stdscr, "Device Ejected", [
                    "The device was unmounted but appears to have been auto-ejected.",
                    "Please re-insert the device without mounting it,",
                    "then run the backup operation again."
                ], app_h)
                log.warning(f"Device unmounted but auto-ejected: {message}")
                return
            elif success:
                show_message_box(stdscr, "Success", [
                    f"Unmount successful: {message}",
                    "Continuing with backup operation..."
                ], app_h)
                log.info(f"Device unmounted successfully: {message}")
                time.sleep(1)
            else:
                show_message_box(stdscr, "Error", [
                    f"Unmount failed: {message}",
                    "Cannot proceed with backup.",
                    "You may need to manually unmount the device."
                ], app_h)
                log.error(f"Unmount failed: {message}")
                return
        else:
            log.info("Network backup cancelled - user declined to unmount.")
            return
    
    # Check SMART status
    # Check SMART status
    smart_ok, smart_info = check_smart_status(source_device['name'])
    app_h = draw_main_layout(stdscr, "SMART Check", log_pad, log_win_height)
    if not show_smart_results(stdscr, source_device['name'], smart_ok, smart_info, app_h):
        log.info("Checksum cancelled - user declined after SMART check.")
        return
    
    if protocol == "ssh":
        # Get SSH connection details
        app_h = draw_main_layout(stdscr, "SSH Details", log_pad, log_win_height)
        ssh_host = get_input_string(stdscr, "Enter SSH hostname/IP", app_h)
        if not ssh_host:
            log.info("Network backup cancelled.")
            return
        
        app_h = draw_main_layout(stdscr, "SSH Details", log_pad, log_win_height)
        ssh_user = get_input_string(stdscr, "Enter SSH username", app_h)
        if not ssh_user:
            log.info("Network backup cancelled.")
            return
        
        # Test SSH connection first (moved up for browsing)
        app_h = draw_main_layout(stdscr, "Testing Connection", log_pad, log_win_height)
        ssh_ok, ssh_msg = test_ssh_connection(ssh_host, ssh_user)
        if not ssh_ok:
            show_message_box(stdscr, "SSH Error", [
                f"Cannot connect to {ssh_user}@{ssh_host}",
                ssh_msg
            ], app_h)
            return
        
        # Offer to browse or manually enter directory
        app_h = draw_main_layout(stdscr, "Directory Selection", log_pad, log_win_height)
        browse_choice = show_confirmation(stdscr, "Select Remote Directory", [
            "Browse remote directories?",
            "(No = manual path entry)"
        ], app_h)
        
        if browse_choice:
            # Browse remote directories
            remote_dir = ssh_browse_directory(stdscr, ssh_user, ssh_host, 
                                             "/home", log_pad, log_win_height, 
                                             filter_dirs_only=True)
            if not remote_dir:
                log.info("Network backup cancelled - no directory selected.")
                return
        else:
            # Manual entry
            app_h = draw_main_layout(stdscr, "SSH Details", log_pad, log_win_height)
            remote_dir = get_input_string(stdscr, "Enter remote directory", app_h)
            if not remote_dir:
                log.info("Network backup cancelled.")
                return
        
        app_h = draw_main_layout(stdscr, "Network Backup", log_pad, log_win_height)
        compression_choice = get_compression_choice(stdscr, app_h)
        if compression_choice is None:
            log.info("Network backup cancelled - no compression selected.")
            return
        
        compression_ext, compression_cmd, compression_desc = compression_choice
        
        # Generate default filename with timestamp
        extension = ".img" + (compression_ext if compression_ext else "")
        default_filename = generate_filename("", source_device['name'], extension)
        
        # Ensure screen is clean for filename prompt
        stdscr.clear()
        stdscr.refresh()
        app_h = draw_main_layout(stdscr, "Filename", log_pad, log_win_height)
        final_filename = get_input_string(stdscr, "Enter backup filename", app_h, default_filename)
        if not final_filename:
            final_filename = default_filename
        
        remote_path = f"{remote_dir}/{final_filename}"
        
        # Build SSH command
        if compression_cmd:
            full_cmd = (f"sudo dd if={source_device['name']} {DD_OPTS} "
                       f"status=progress | {compression_cmd} | "
                       f"ssh {ssh_user}@{ssh_host} 'cat > {remote_path}'")
        else:
            full_cmd = (f"sudo dd if={source_device['name']} {DD_OPTS} "
                       f"status=progress | "
                       f"ssh {ssh_user}@{ssh_host} 'cat > {remote_path}'")
        
        dest_str = f"{ssh_user}@{ssh_host}:{remote_path}"
        
    else:  # NFS
        app_h = draw_main_layout(stdscr, "NFS Details", log_pad, log_win_height)
        nfs_path = get_input_string(stdscr, "Enter NFS path (server:/path)", app_h)
        if not nfs_path:
            log.info("Network backup cancelled.")
            return
        
        # Check NFS availability
        app_h = draw_main_layout(stdscr, "Testing NFS", log_pad, log_win_height)
        nfs_ok, nfs_msg = check_nfs_mount(nfs_path)
        if not nfs_ok:
            show_message_box(stdscr, "NFS Error", [
                f"Cannot access NFS path {nfs_path}",
                nfs_msg
            ], app_h)
            return
        
        app_h = draw_main_layout(stdscr, "Network Backup", log_pad, log_win_height)
        # Mount NFS temporarily
        os.makedirs(nfs_mount_point, exist_ok=True)
        mount_cmd = f"sudo mount -t nfs {nfs_path} {nfs_mount_point}"
        mount_result = subprocess.run(mount_cmd, shell=True, capture_output=True)
        
        if mount_result.returncode != 0:
            show_message_box(stdscr, "Mount Error", [
                f"Failed to mount NFS path {nfs_path}"
            ], app_h)
            return
        
        app_h = draw_main_layout(stdscr, "Network Backup", log_pad, log_win_height)
        compression_choice = get_compression_choice(stdscr, app_h)
        if compression_choice is None:
            log.info("Network backup cancelled - no compression selected.")
            return
        
        compression_ext, compression_cmd, compression_desc = compression_choice
        
        # Generate default filename with timestamp
        extension = ".img" + (compression_ext if compression_ext else "")
        default_filename = generate_filename("", source_device['name'], extension)
        
        # Ensure screen is clean for filename prompt
        stdscr.clear()
        stdscr.refresh()
        app_h = draw_main_layout(stdscr, "Filename", log_pad, log_win_height)
        final_filename = get_input_string(stdscr, "Enter backup filename", app_h, default_filename)
        if not final_filename:
            final_filename = default_filename
        
        final_path = os.path.join(nfs_mount_point, final_filename)
        
        if compression_cmd:
            full_cmd = (f"sudo dd if={source_device['name']} {DD_OPTS} "
                       f"status=progress | {compression_cmd} > {final_path}")
        else:
            full_cmd = (f"sudo dd if={source_device['name']} {DD_OPTS} "
                       f"of={final_path} status=progress")
        
        dest_str = f"{nfs_path}/{final_filename}"
    
    # Confirmation
    app_h = draw_main_layout(stdscr, "Network Backup Confirmation", 
                            log_pad, log_win_height)
    if show_confirmation(stdscr, "Confirm Network Backup", [
        f"Source: {source_device['name']} ({source_device['size']})",
        f"Destination: {dest_str}",
        f"Protocol: {protocol.upper()}",
        f"Compression: {compression_desc}"
    ], app_h):
        app_h = draw_main_layout(stdscr, "FINAL WARNING", log_pad, log_win_height)
        if show_final_warning(stdscr, "⚠️ NETWORK BACKUP ⚠️", [
            f"BACKUP from '{source_device['name']}' to '{dest_str}'.",
            "This will create a complete disk image over the network.",
            "The operation may take considerable time."
        ], app_h):
            run_dd_with_progress(stdscr, full_cmd, source_device['bytes'],
                               source_device['name'], dest_str, app_h)
            
            # Cleanup NFS mount if used
            if protocol == "nfs":
                subprocess.run(f"sudo umount {nfs_mount_point}", 
                             shell=True, capture_output=True)
                try:
                    os.rmdir(nfs_mount_point)
                except:
                    pass

def network_restore_logic(stdscr, log_pad, log_win_height):
    """Restore disk from remote location via SSH or NFS."""
    app_h = draw_main_layout(stdscr, "Network Restore", log_pad, log_win_height)
    
    # Choose network protocol
    protocol_menu = ["SSH (Secure Shell)", "NFS (Network File System)", "Cancel"]
    protocol_idx = get_menu_choice(stdscr, "Select Network Protocol", 
                                   protocol_menu, app_h)
    if protocol_idx == -1 or protocol_idx == 2:
        log.info("Network restore cancelled.")
        return
    
    protocol = "ssh" if protocol_idx == 0 else "nfs"
    nfs_mount_point = "/tmp/disk_imager_nfs"
    
    # Select target device
    app_h = draw_main_layout(stdscr, "Network Restore", log_pad, log_win_height)
    devices = get_devices()
    if not devices:
        log.error("No block devices found for restore.")
        show_message_box(stdscr, "Error", ["No block devices found."], app_h)
        return
    
    device_menu_items = [f"{d['name']:<15} {d['size']:<10} {d['model']}" 
                        for d in devices]
    choice_idx = get_menu_choice(stdscr, "Select TARGET Device to OVERWRITE",
                                 device_menu_items, app_h)
    if choice_idx == -1:
        log.info("Network restore cancelled.")
        return
    target_device = devices[choice_idx]
    
    # Check if device is mounted
    is_mounted, mount_point = is_device_mounted(target_device['name'])
    if is_mounted:
        app_h = draw_main_layout(stdscr, "Device Mounted", log_pad, log_win_height)
        if show_confirmation(stdscr, "Device Mounted", [
            f"Device {target_device['name']} is mounted at {mount_point}.",
            "The device must be unmounted before restoring.",
            "Automatically unmount all partitions now?"
        ], app_h):
            # Attempt to unmount
            success, message = unmount_device(target_device['name'])
            app_h = draw_main_layout(stdscr, "Unmount Result", log_pad, log_win_height)
            
            # Check if device became ejected/inaccessible after unmount
            if not success and "ejected" in message.lower():
                show_message_box(stdscr, "Device Ejected", [
                    "The device was unmounted but appears to have been auto-ejected.",
                    "Please re-insert the device without mounting it,",
                    "then run the restore operation again."
                ], app_h)
                log.warning(f"Device unmounted but auto-ejected: {message}")
                return
            elif success:
                show_message_box(stdscr, "Success", [
                    f"Unmount successful: {message}",
                    "Continuing with restore operation..."
                ], app_h)
                log.info(f"Device unmounted successfully: {message}")
                time.sleep(1)
            else:
                show_message_box(stdscr, "Error", [
                    f"Unmount failed: {message}",
                    "Cannot proceed with restore.",
                    "You may need to manually unmount the device."
                ], app_h)
                log.error(f"Unmount failed: {message}")
                return
        else:
            log.info("Network restore cancelled - user declined to unmount.")
            return
    
    # Check SMART status
    # Check SMART status
    smart_ok, smart_info = check_smart_status(target_device['name'])
    app_h = draw_main_layout(stdscr, "SMART Check", log_pad, log_win_height)
    if not show_smart_results(stdscr, target_device['name'], smart_ok, smart_info, app_h):
        log.info("Wipe cancelled - user declined after SMART check.")
        return
    
    if protocol == "ssh":
        # Get SSH connection details
        app_h = draw_main_layout(stdscr, "SSH Details", log_pad, log_win_height)
        ssh_host = get_input_string(stdscr, "Enter SSH hostname/IP", app_h)
        if not ssh_host:
            log.info("Network restore cancelled.")
            return
        
        app_h = draw_main_layout(stdscr, "SSH Details", log_pad, log_win_height)
        ssh_user = get_input_string(stdscr, "Enter SSH username", app_h)
        if not ssh_user:
            log.info("Network restore cancelled.")
            return
        
        app_h = draw_main_layout(stdscr, "SSH Details", log_pad, log_win_height)
        # Test SSH connection first (needed for browsing)
        app_h = draw_main_layout(stdscr, "Testing Connection", log_pad, log_win_height)
        ssh_ok, ssh_msg = test_ssh_connection(ssh_host, ssh_user)
        if not ssh_ok:
            show_message_box(stdscr, "SSH Error", [
                f"Cannot connect to {ssh_user}@{ssh_host}",
                ssh_msg
            ], app_h)
            return
        
        # Offer to browse or manually enter file path
        app_h = draw_main_layout(stdscr, "File Selection", log_pad, log_win_height)
        browse_choice = show_confirmation(stdscr, "Select Remote Image", [
            "Browse remote files?",
            "(No = manual path entry)"
        ], app_h)
        
        if browse_choice:
            # Browse remote files (filter for .img and .img.gz)
            remote_file = ssh_browse_directory(stdscr, ssh_user, ssh_host,
                                              "/home", log_pad, log_win_height,
                                              file_filter=['.img', '.img.gz'])
            if not remote_file:
                log.info("Network restore cancelled - no file selected.")
                return
        else:
            # Manual entry
            remote_file = get_input_string(stdscr, "Enter remote image path", app_h)
            if not remote_file:
                log.info("Network restore cancelled.")
                return
        
        # Auto-detect compression from filename
        is_compressed = remote_file.endswith('.gz')
        
        # Allow user to override if not compressed
        app_h = draw_main_layout(stdscr, "Network Restore", log_pad, log_win_height)
        if not is_compressed:
            is_compressed = show_confirmation(stdscr, "Compression",
                                            ["Is the remote file gzip compressed?"], app_h)
        
        # Build SSH command
        if is_compressed:
            full_cmd = (f"ssh {ssh_user}@{ssh_host} 'cat {remote_file}' | "
                       f"gunzip -c | sudo dd of={target_device['name']} "
                       f"{DD_OPTS} status=progress")
        else:
            full_cmd = (f"ssh {ssh_user}@{ssh_host} 'cat {remote_file}' | "
                       f"sudo dd of={target_device['name']} {DD_OPTS} "
                       f"status=progress")
        
        source_str = f"{ssh_user}@{ssh_host}:{remote_file}"
        total_size = target_device['bytes']  # Estimate
        
    else:  # NFS
        app_h = draw_main_layout(stdscr, "NFS Details", log_pad, log_win_height)
        nfs_path = get_input_string(stdscr, "Enter NFS path (server:/path)", app_h)
        if not nfs_path:
            log.info("Network restore cancelled.")
            return
        
        # Check NFS availability
        app_h = draw_main_layout(stdscr, "Testing NFS", log_pad, log_win_height)
        nfs_ok, nfs_msg = check_nfs_mount(nfs_path)
        if not nfs_ok:
            show_message_box(stdscr, "NFS Error", [
                f"Cannot access NFS path {nfs_path}",
                nfs_msg
            ], app_h)
            return
        
        # Mount NFS temporarily
        os.makedirs(nfs_mount_point, exist_ok=True)
        mount_cmd = f"sudo mount -t nfs {nfs_path} {nfs_mount_point}"
        mount_result = subprocess.run(mount_cmd, shell=True, capture_output=True)
        
        if mount_result.returncode != 0:
            show_message_box(stdscr, "Mount Error", [
                f"Failed to mount NFS path {nfs_path}"
            ], app_h)
            return
        
        # List available image files
        try:
            files = [f for f in os.listdir(nfs_mount_point) 
                    if f.endswith('.img') or f.endswith('.img.gz')]
            if not files:
                show_message_box(stdscr, "No Images", [
                    "No image files found on NFS share."
                ], app_h)
                subprocess.run(f"sudo umount {nfs_mount_point}", 
                             shell=True, capture_output=True)
                return
            
            app_h = draw_main_layout(stdscr, "Select Image", log_pad, log_win_height)
            file_idx = get_menu_choice(stdscr, "Select Image File", sorted(files), app_h)
            if file_idx == -1:
                subprocess.run(f"sudo umount {nfs_mount_point}", 
                             shell=True, capture_output=True)
                return
            
            image_file = sorted(files)[file_idx]
            image_path = os.path.join(nfs_mount_point, image_file)
            is_compressed = image_file.endswith('.gz')
            
            if is_compressed:
                total_size = get_uncompressed_size(image_path)
                full_cmd = (f"gunzip -c {image_path} | "
                           f"sudo dd of={target_device['name']} {DD_OPTS} "
                           f"status=progress")
            else:
                total_size = os.path.getsize(image_path)
                full_cmd = (f"sudo dd if={image_path} of={target_device['name']} "
                           f"{DD_OPTS} status=progress")
            
            source_str = f"{nfs_path}/{image_file}"
            
        except Exception as e:
            show_message_box(stdscr, "Error", [f"Error accessing NFS: {e}"], app_h)
            subprocess.run(f"sudo umount {nfs_mount_point}", 
                         shell=True, capture_output=True)
            return
    
    # Confirmation
    app_h = draw_main_layout(stdscr, "Network Restore Confirmation",
                            log_pad, log_win_height)
    if show_confirmation(stdscr, "Confirm Network Restore", [
        f"Source: {source_str}",
        f"Target: {target_device['name']} ({target_device['size']})",
        f"Protocol: {protocol.upper()}",
        f"Compressed: {'Yes' if is_compressed else 'No'}"
    ], app_h):
        app_h = draw_main_layout(stdscr, "FINAL WARNING", log_pad, log_win_height)
        if show_final_warning(stdscr, "⚠️ IRREVERSIBLE OPERATION ⚠️", [
            f"RESTORE from '{source_str}' to '{target_device['name']}'.",
            "ALL DATA on the target device will be PERMANENTLY ERASED.",
            "This operation cannot be undone."
        ], app_h):
            run_dd_with_progress(stdscr, full_cmd, total_size,
                               source_str, target_device['name'], app_h)
            
            # Cleanup NFS mount if used
            if protocol == "nfs":
                subprocess.run(f"sudo umount {nfs_mount_point}",
                             shell=True, capture_output=True)
                try:
                    os.rmdir(nfs_mount_point)
                except:
                    pass

def wipe_disk_logic(stdscr, log_pad, log_win_height):
    """Secure disk wiping with various algorithms."""
    app_h = draw_main_layout(stdscr, "Secure Disk Wipe", log_pad, log_win_height)
    
    # Get list of devices
    devices = get_devices()
    if not devices:
        show_message_box(stdscr, "No Devices", ["No devices found."], app_h)
        return
    
    # Select device to wipe
    device_labels = [f"{d['name']} - {d['size']} ({d['model']})" for d in devices]
    choice_idx = get_menu_choice(stdscr, "Select Disk to Wipe", device_labels, app_h)
    if choice_idx == -1:
        log.info("Disk wipe cancelled.")
        return
    
    target_device = devices[choice_idx]
    
    # Check if device is mounted
    is_mounted, mount_point = is_device_mounted(target_device['name'])
    if is_mounted:
        app_h = draw_main_layout(stdscr, "Device Mounted", log_pad, log_win_height)
        if show_confirmation(stdscr, "Device Mounted", [
            f"Device {target_device['name']} is mounted at {mount_point}.",
            "The device must be unmounted before wiping.",
            "Automatically unmount all partitions now?"
        ], app_h):
            # Attempt to unmount
            success, message = unmount_device(target_device['name'])
            app_h = draw_main_layout(stdscr, "Unmount Result", log_pad, log_win_height)
            
            # Check if device became ejected/inaccessible after unmount
            if not success and "ejected" in message.lower():
                # Device was unmounted but became inaccessible (auto-eject)
                show_message_box(stdscr, "Device Ejected", [
                    "The device was unmounted but appears to have been auto-ejected.",
                    "Please re-insert the device without mounting it,",
                    "then run the wipe operation again."
                ], app_h)
                log.warning(f"Device unmounted but auto-ejected: {message}")
                return
            elif success:
                show_message_box(stdscr, "Success", [
                    f"Unmount successful: {message}",
                    "Continuing with wipe operation..."
                ], app_h)
                log.info(f"Device unmounted successfully: {message}")
                # Give the system a moment to settle
                time.sleep(1)
            else:
                show_message_box(stdscr, "Error", [
                    f"Unmount failed: {message}",
                    "Cannot proceed with wipe.",
                    "You may need to manually unmount the device."
                ], app_h)
                log.error(f"Unmount failed: {message}")
                return
        else:
            log.info("Disk wipe cancelled - user declined to unmount.")
            return
    
    # Select block size with intelligent detection
    app_h = draw_main_layout(stdscr, "Select Block Size", log_pad, log_win_height)
    block_size = get_block_size_choice(stdscr, app_h, "Wipe", target_device['name'])
    if block_size is None:
        log.info("Disk wipe cancelled - no block size selected.")
        return
    log.info(f"User selected block size: {block_size}")
    
    # Verify device is still accessible before proceeding
    try:
        result = subprocess.run(['sudo', 'blockdev', '--getsize64', target_device['name']],
                              capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            app_h = draw_main_layout(stdscr, "Device Not Accessible", log_pad, log_win_height)
            show_message_box(stdscr, "Error", [
                f"Device {target_device['name']} is not accessible.",
                "It may have been ejected or disconnected.",
                "Please ensure the device is connected and not mounted,",
                "then try again."
            ], app_h)
            log.error(f"Device {target_device['name']} not accessible after unmount check")
            return
    except subprocess.TimeoutExpired:
        app_h = draw_main_layout(stdscr, "Device Not Responding", log_pad, log_win_height)
        show_message_box(stdscr, "Error", [
            f"Device {target_device['name']} is not responding.",
            "Please check the device connection and try again."
        ], app_h)
        log.error(f"Timeout checking device {target_device['name']} accessibility")
        return
    except Exception as e:
        log.warning(f"Could not verify device accessibility: {e}")
        # Continue anyway - the dd command will fail if device is truly inaccessible
    
    # Select wiping algorithm
    app_h = draw_main_layout(stdscr, "Select Wipe Method", log_pad, log_win_height)
    wipe_methods = [
        "Zero Fill (1 pass) - Fast, good for non-sensitive data",
        "Random Data (1 pass) - Fast, better security than zeros",
        "DoD 5220.22-M (3 passes) - US DoD standard",
        "Random Data (7 passes) - High security, slower",
        "Gutmann (35 passes) - Maximum security, very slow"
    ]
    
    method_idx = get_menu_choice(stdscr, "Select Wipe Algorithm", wipe_methods, app_h)
    if method_idx == -1:
        log.info("Disk wipe cancelled.")
        return
    
    log.info(f"User selected wipe method index {method_idx}")
    
    # Configure wipe parameters based on method
    method_name = ""
    passes = []
    
    if method_idx == 0:
        method_name = "Zero Fill"
        passes = [("zero", "0x00")]
    elif method_idx == 1:
        method_name = "Random Data (1 pass)"
        passes = [("random", "/dev/urandom")]
    elif method_idx == 2:
        method_name = "DoD 5220.22-M"
        passes = [("random", "/dev/urandom"), ("complement", "0xFF"), ("random", "/dev/urandom")]
    elif method_idx == 3:
        method_name = "Random Data (7 passes)"
        passes = [("random", "/dev/urandom")] * 7
    elif method_idx == 4:
        method_name = "Gutmann (35 passes)"
        # Simplified Gutmann - alternating random and patterns
        passes = [("random", "/dev/urandom")] * 4
        patterns = ["0x55", "0xAA", "0x92", "0x49", "0x24", "0x00", "0x11", "0x22", "0x33",
                   "0x44", "0x55", "0x66", "0x77", "0x88", "0x99", "0xAA", "0xBB", "0xCC",
                   "0xDD", "0xEE", "0xFF", "0x92", "0x49", "0x24", "0x6D", "0xB6", "0xDB"]
        for pattern in patterns:
            passes.append(("pattern", pattern))
        passes.extend([("random", "/dev/urandom")] * 4)
    else:
        log.error("Invalid wipe method selection")
        return
    
    # Final confirmation with strong warning
    app_h = draw_main_layout(stdscr, "FINAL WARNING", log_pad, log_win_height)
    if not show_final_warning(stdscr, "⚠ DESTRUCTIVE OPERATION ⚠", [
        f"You are about to PERMANENTLY ERASE ALL DATA on:",
        f"  Device: {target_device['name']}",
        f"  Size: {target_device['size']}",
        f"  Model: {target_device['model']}",
        f"  Method: {method_name} ({len(passes)} passes)",
        f"  Block size: {block_size}",
        "",
        "THIS OPERATION CANNOT BE UNDONE!",
        "ALL DATA WILL BE IRRETRIEVABLY LOST!"
    ], app_h):
        log.info("Disk wipe cancelled by user.")
        return
    
    # Perform the wipe
    device_path = target_device['name']
    log.info(f"Starting secure disk wipe of {device_path} using {method_name}")
    log.info(f"Block size: {block_size}")
    log.info(f"Total passes: {len(passes)}")
    
    for pass_num, (pass_type, pass_value) in enumerate(passes, 1):
        log.info(f"Pass {pass_num}/{len(passes)}: {pass_type} with {pass_value}")
        
        wipe_cmd = ""
        if pass_type == "zero":
            # Zero fill using dd with error handling
            wipe_cmd = f"dd if=/dev/zero of=\"{device_path}\" bs={block_size} conv=sync,noerror status=progress"
        elif pass_type == "random":
            # Random data using dd with error handling
            wipe_cmd = f"dd if={pass_value} of=\"{device_path}\" bs={block_size} conv=sync,noerror status=progress"
        elif pass_type in ["pattern", "complement"]:
            # Pattern fill using tr and dd with error handling
            # Convert hex pattern to octal for tr
            wipe_cmd = f"tr '\\000' '{pass_value}' < /dev/zero | dd of=\"{device_path}\" bs={block_size} conv=sync,noerror status=progress"
        
        if not wipe_cmd:
            log.error(f"Invalid pass type: {pass_type}")
            continue
            
        log.info(f"Executing: {wipe_cmd}")
        
        # Determine source and destination for display
        if pass_type == "zero":
            source_display = "/dev/zero"
        elif pass_type == "random":
            source_display = pass_value
        else:
            source_display = f"Pattern {pass_value}"
        
        dest_display = device_path
        operation_display = f"{method_name} - Pass {pass_num}/{len(passes)}"
        
        # Run the wipe command with block map visualization
        run_dd_with_progress(stdscr, wipe_cmd, target_device['bytes'], 
                           source_display, dest_display, app_h, 
                           display_mode="blockmap", operation_name=operation_display)
    
    # Success
    log.info(f"Disk wipe completed successfully: {device_path}")
    app_h = draw_main_layout(stdscr, "Wipe Complete", log_pad, log_win_height)
    show_message_box(stdscr, "Success", [
        f"Disk {device_path} has been securely wiped.",
        f"Method: {method_name}",
        f"Passes completed: {len(passes)}",
        "All data has been permanently erased."
    ], app_h)

def check_disk_logic(stdscr, log_pad, log_win_height):
    """Check disk health and display information using smartctl."""
    app_h = draw_main_layout(stdscr, "Check Disk Health", log_pad, log_win_height)
    
    # Get list of block devices
    devices = get_devices()
    if not devices:
        show_message_box(stdscr, "No Devices", ["No block devices found."], app_h)
        return
    
    # Select device to check
    device_labels = [f"{d['name']:<12} │ {d['size']:<10} │ {d['model']}" for d in devices]
    choice_idx = get_menu_choice(stdscr, "Select Device to Check", device_labels, app_h)
    if choice_idx == -1:
        log.info("Disk check cancelled.")
        return
    
    selected_device = devices[choice_idx]
    device_path = selected_device['name']
    
    log.info(f"Checking disk health for {device_path}")
    
    # Display interactive smartctl output viewer (will handle fetching data)
    show_smartctl_output(stdscr, device_path, selected_device, app_h, log_pad, log_win_height)

def show_smartctl_output(stdscr, device_path, device_info, app_h, log_pad, log_win_height):
    """Display smartctl output in a scrollable window with toggle between -a and -x."""
    h, w = stdscr.getmaxyx()
    
    # Start with -a flag (all information)
    use_extended = False  # False = -a, True = -x
    
    def fetch_smartctl_data(flag):
        """Fetch SMART data with specified flag."""
        try:
            cmd = ["sudo", "smartctl", flag, device_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            
            if result.returncode not in [0, 4]:  # 0=success, 4=some SMART commands failed
                if "SMART support is: Unavailable" in result.stdout:
                    return None, "SMART not supported"
                else:
                    return None, f"Error: {result.stderr[:200] if result.stderr else 'Unknown error'}"
            
            return result.stdout, None
        except subprocess.TimeoutExpired:
            return None, "Timeout while reading SMART data"
        except FileNotFoundError:
            return None, "smartctl utility not found"
        except Exception as e:
            return None, f"Error: {str(e)}"
    
    def format_smartctl_lines(smartctl_output, flag):
        """Format smartctl output into display lines."""
        lines = smartctl_output.split('\n')
        formatted = []
        
        # Add device header
        formatted.append(f"Device: {device_path}")
        formatted.append(f"Size: {device_info['size']}")
        formatted.append(f"Model: {device_info['model']}")
        formatted.append("")
        
        if flag == "-a":
            formatted.append("SMART Information (All Attributes)")
        else:
            formatted.append("SMART Information (Extended - All Data + Logs)")
        formatted.append("=" * 60)
        formatted.append("")
        
        # Add the smartctl output, wrapping long lines
        for line in lines:
            line = line.rstrip()
            if line:
                if len(line) > w - 10:
                    wrapped = wrap(line, w - 10, break_long_words=False, break_on_hyphens=False)
                    formatted.extend(wrapped)
                else:
                    formatted.append(line)
            else:
                formatted.append("")
        
        # Add instruction at the bottom
        formatted.append("")
        formatted.append("=" * 60)
        formatted.append("Use ↑↓/PgUp/PgDn to scroll | 't' to toggle -a/-x | Esc/q to return")
        
        return formatted
    
    # Initial data fetch
    data, error = fetch_smartctl_data("-a")
    if error:
        show_message_box(stdscr, "Error", [
            f"Failed to read SMART data from {device_path}",
            "",
            error
        ], app_h)
        return
    
    formatted_lines = format_smartctl_lines(data, "-a")
    
    # Create scrollable window
    content_height = min(len(formatted_lines) + 4, app_h - 4)
    content_width = min(w - 4, 100)
    start_y = max(2, (app_h - content_height) // 2)
    start_x = max(1, (w - content_width) // 2)
    
    win = draw_bordered_window(stdscr, start_y, start_x, content_height, content_width, "SMART Disk Information [t=toggle]")
    
    # Scrolling variables
    scroll_pos = 0
    visible_lines = content_height - 4
    max_scroll = max(0, len(formatted_lines) - visible_lines)
    loading = False
    
    while True:
        # Clear content area
        for i in range(2, content_height - 2):
            win.move(i, 1)
            win.clrtoeol()
        
        # Show loading message if fetching data
        if loading:
            loading_msg = "Loading SMART data..."
            try:
                win.addstr(content_height // 2, (content_width - len(loading_msg)) // 2, 
                          loading_msg, curses.A_BOLD | curses.color_pair(6))
            except:
                pass
        else:
            # Display visible portion of content
            for i, line_idx in enumerate(range(scroll_pos, min(scroll_pos + visible_lines, len(formatted_lines)))):
                if i + 2 >= content_height - 2:
                    break
                try:
                    display_line = formatted_lines[line_idx]
                    if len(display_line) > content_width - 4:
                        display_line = display_line[:content_width - 7] + "..."
                    
                    # Add some basic formatting for headers and important lines
                    if "===" in display_line:
                        win.addstr(i + 2, 2, display_line, curses.A_BOLD)
                    elif display_line.startswith("Device:") or display_line.startswith("Size:") or display_line.startswith("Model:"):
                        win.addstr(i + 2, 2, display_line, curses.color_pair(6) | curses.A_BOLD)
                    elif "SMART" in display_line and ":" in display_line:
                        win.addstr(i + 2, 2, display_line, curses.color_pair(5))
                    elif "test" in display_line.lower() and ("pass" in display_line.lower() or "fail" in display_line.lower()):
                        if "pass" in display_line.lower():
                            win.addstr(i + 2, 2, display_line, curses.color_pair(7))
                        else:
                            win.addstr(i + 2, 2, display_line, curses.color_pair(4))
                    else:
                        win.addstr(i + 2, 2, display_line)
                except:
                    pass  # Skip lines that don't fit
            
            # Show scroll indicator and mode indicator
            if max_scroll > 0:
                scroll_info = f"[{scroll_pos + 1}-{min(scroll_pos + visible_lines, len(formatted_lines))} of {len(formatted_lines)}]"
                try:
                    win.addstr(content_height - 1, content_width - len(scroll_info) - 2, scroll_info, curses.color_pair(5))
                except:
                    pass
            
            # Show current mode indicator
            mode_indicator = f"[Mode: smartctl {'- x' if use_extended else '-a'}]"
            try:
                win.addstr(content_height - 1, 2, mode_indicator, curses.color_pair(3) | curses.A_BOLD)
            except:
                pass
        
        # Keep log window visible
        refresh_log_window(stdscr)
        win.refresh()
        
        # Handle input
        key = stdscr.getch()
        
        if key == curses.KEY_UP and scroll_pos > 0:
            scroll_pos -= 1
        elif key == curses.KEY_DOWN and scroll_pos < max_scroll:
            scroll_pos += 1
        elif key == curses.KEY_PPAGE:  # Page Up
            scroll_pos = max(0, scroll_pos - visible_lines)
        elif key == curses.KEY_NPAGE:  # Page Down
            scroll_pos = min(max_scroll, scroll_pos + visible_lines)
        elif key == curses.KEY_HOME:
            scroll_pos = 0
        elif key == curses.KEY_END:
            scroll_pos = max_scroll
        elif key in [ord('t'), ord('T')]:  # Toggle between -a and -x
            loading = True
            win.refresh()  # Show loading message immediately
            
            # Toggle mode
            use_extended = not use_extended
            flag = "-x" if use_extended else "-a"
            
            # Fetch new data
            data, error = fetch_smartctl_data(flag)
            if error:
                # Show error but keep old data
                show_message_box(stdscr, "Error", [
                    f"Failed to fetch SMART data with {flag}",
                    "",
                    error,
                    "",
                    "Press any key to continue with previous data"
                ], app_h)
                use_extended = not use_extended  # Revert toggle
            else:
                # Update display with new data
                formatted_lines = format_smartctl_lines(data, flag)
                scroll_pos = 0  # Reset scroll to top
                visible_lines = content_height - 4
                max_scroll = max(0, len(formatted_lines) - visible_lines)
            
            loading = False
            # Redraw layout to clean up after message box
            stdscr.touchwin()
            stdscr.refresh()
            win.touchwin()
        elif key in [27, ord('q'), ord('Q')]:  # Esc or q
            break
        # Handle mouse scroll
        elif key == curses.KEY_MOUSE:
            try:
                _, mx, my, _, button_state = curses.getmouse()
                if button_state & curses.BUTTON4_PRESSED:  # Scroll up
                    scroll_pos = max(0, scroll_pos - 3)
                elif button_state & (1 << 21):  # Scroll down (BUTTON5_PRESSED)
                    scroll_pos = min(max_scroll, scroll_pos + 3)
            except:
                pass
    
    # Clean up
    del win
    stdscr.touchwin()
    stdscr.refresh()

def main(stdscr):
    """Main application loop."""
    curses.noecho(); curses.cbreak(); stdscr.keypad(True); curses.curs_set(0)
    # Enable mouse support
    curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
    init_colors()

    # Check for minimum terminal size
    h, w = stdscr.getmaxyx()
    min_h, min_w = 24, 80
    if h < min_h or w < min_w:
        curses.endwin()
        print(f"❌ Terminal too small ({w}x{h}).")
        print(f"Please resize to at least {min_w}x{min_h} and try again.")
        sys.exit(1)
    
    # Setup logging
    log_win_height = 8
    log_pad = curses.newpad(1000, w) # Pad can hold 1000 lines
    curses_handler = setup_logging(log_pad, stdscr)
    curses_handler.set_log_height(log_win_height)
    log.info("Application started.")

    should_exit = False
    try:
        while not should_exit:
            app_h = draw_main_layout(stdscr, "Main Menu", log_pad, log_win_height)
            # Ensure log section is visible by refreshing it explicitly
            h, w = stdscr.getmaxyx()
            log_win_y = h - log_win_height
            curses_handler = None
            for handler in log.handlers:
                if isinstance(handler, CursesHandler):
                    curses_handler = handler
                    break
            if curses_handler and len(curses_handler.log_messages) > 0:
                pad_start_line = max(0, len(curses_handler.log_messages) - (log_win_height - 2))
                log_pad.refresh(pad_start_line, 0, log_win_y + 1, 2, h - 2, w - 3)
            
            main_menu = [
                "Backup Disk  - Create disk image to local file or network",
                "Restore Disk - Restore disk image from local file or network",
                "Wipe Disk    - Securely erase disk data",
                "Check Disk   - Display disk health and information",
                "Exit         - Close DDI application"
            ]
            choice = get_menu_choice(stdscr, "Main Menu - Select Operation", main_menu, app_h)
            
            if choice == 0: create_image_logic(stdscr, log_pad, log_win_height)
            elif choice == 1: restore_image_logic(stdscr, log_pad, log_win_height)
            elif choice == 2: wipe_disk_logic(stdscr, log_pad, log_win_height)
            elif choice == 3: check_disk_logic(stdscr, log_pad, log_win_height)
            elif choice == 4 or choice == -1:
                # Exit immediately without confirmation (good UX practice)
                log.info("Application exiting.")
                should_exit = True
    except curses.error as e:
        # If a curses error happens, log it and exit gracefully.
        log.critical(f"A critical curses error occurred: {e}")
        # The finally block in __main__ will handle cleanup.


if __name__ == "__main__":
    check_root()
    try:
        curses.wrapper(main)
    except curses.error as e:
        # This catches errors during the initial setup before the main loop's try/except
        print(f"❌ Curses error during setup: {e}")
    except KeyboardInterrupt:
        print("\n👋 Exiting.")
    finally:
        if curses.has_colors():
            try: curses.endwin()
            except curses.error: pass

