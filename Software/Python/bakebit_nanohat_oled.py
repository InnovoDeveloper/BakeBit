#!/usr/bin/env python3
import bakebit_128_64_oled as oled
from PIL import Image, ImageFont, ImageDraw
import time
import sys
import subprocess
import threading
import signal
import os
import socket
import fcntl
import struct
import logging

# Add logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/oled.log'),
        logging.StreamHandler()
    ]
)

logging.info("Starting OLED script...")

# Global variables
width = 128
height = 64
pageCount = 3
pageIndex = 1  # Start with System Info (IP address) page
showPageIndicator = False
pageSleep = 120  # Sleep after 2 minutes (120 seconds)
pageSleepCountdown = pageSleep
selectionIndex = 0  # Start with first item selected
lastActivityTime = time.time()
screenSleeping = False
nowplaying_scroll_offset = 0

# Initialize OLED
oled.init()
# oled.clearDisplay()  # Clear any garbage
oled.setNormalDisplay()
oled.setHorizontalMode()

# Drawing setup
drawing = False
image = Image.new('1', (width, height))
draw = ImageDraw.Draw(image)
fontb18 = ImageFont.truetype('DejaVuSansMono-Bold.ttf', 18)
font14 = ImageFont.truetype('DejaVuSansMono.ttf', 14)
font12 = ImageFont.truetype('DejaVuSansMono.ttf', 12)
smartFont = ImageFont.truetype('DejaVuSansMono-Bold.ttf', 10)
fontb12 = ImageFont.truetype('DejaVuSansMono-Bold.ttf', 12)
font10 = ImageFont.truetype('DejaVuSansMono.ttf', 10)

# Threading lock
lock = threading.Lock()

def get_ip_address(ifname):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        return socket.inet_ntoa(fcntl.ioctl(
            s.fileno(),
            0x8915,
            struct.pack('256s', ifname[:15].encode())
        )[20:24])
    except:
        return "N/A"

def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def get_mac_address(ifname='eth0'):
    try:
        with open(f'/sys/class/net/{ifname}/address', 'r') as f:
            return f.read().strip().upper()
    except:
        try:
            # Try wlan0 if eth0 fails
            with open('/sys/class/net/wlan0/address', 'r') as f:
                return f.read().strip().upper()
        except:
            return "N/A"

def wake_screen():
    global screenSleeping, pageSleepCountdown, lastActivityTime
    was_sleeping = screenSleeping
    if screenSleeping:
        oled.setNormalDisplay()  # Turn display back on
        screenSleeping = False
        logging.info("Screen woken up")
    pageSleepCountdown = pageSleep
    lastActivityTime = time.time()
    return was_sleeping  # Return True if screen was sleeping

def draw_page():
    global drawing, pageSleepCountdown, lastActivityTime, screenSleeping, nowplaying_scroll_offset

    lock.acquire()
    is_drawing = drawing
    page_index = pageIndex
    sel_index = selectionIndex
    lock.release()

    if is_drawing or screenSleeping:
        return

    if pageSleepCountdown <= 1:
        if not screenSleeping:
            oled.clearDisplay()  # Clear display
            # Turn off display completely (not inverse which turns all pixels on)
            screenSleeping = True
            logging.info("Screen sleeping")
        pageSleepCountdown = 0
        return
    pageSleepCountdown -= 1

    lock.acquire()
    drawing = True
    lock.release()

    # Clear the image buffer
    draw.rectangle((0, 0, width, height), outline=0, fill=0)

    # --- Page 0: Date/Time + Model + Version ---
    if page_index == 0:
        # Date without day name (e.g., "26 Nov 2025") - using fontb12 (12pt, bigger)
        text = time.strftime("%d %b %Y")
        draw.text((2, 2), text, font=fontb12, fill=255)
        
        # Time
        text = time.strftime("%X")
        draw.text((2, 18), text, font=smartFont, fill=255)

        # Model name from file
        try:
            if os.path.exists('/mnt/dietpi_userdata/innovo/model'):
                with open('/mnt/dietpi_userdata/innovo/model', 'r') as f:
                    MODELNAME = f.read().strip()
                if not MODELNAME:
                    MODELNAME = "MC-DJ Player"
            else:
                MODELNAME = "MC-DJ Player"
        except Exception as e:
            logging.error(f"Error reading model: {e}")
            MODELNAME = "MC-DJ Player"
        draw.text((2, 34), MODELNAME, font=smartFont, fill=255)

        # Version from update and schema files - plain text format
        version = "0"
        schema = "100"
        
        # Read version from update file (plain text)
        try:
            if os.path.exists('/mnt/dietpi_userdata/innovo/update'):
                with open('/mnt/dietpi_userdata/innovo/update', 'r') as f:
                    version = f.read().strip()
                    if version:
                        logging.info(f"Found version: {version}")
                    else:
                        version = "0"
        except Exception as e:
            logging.error(f"Error reading version from update: {e}")
            version = "0"
        
        # Read schema from schema file (plain text)
        try:
            if os.path.exists('/mnt/dietpi_userdata/innovo/schema'):
                with open('/mnt/dietpi_userdata/innovo/schema', 'r') as f:
                    schema = f.read().strip()
                    if schema:
                        logging.info(f"Found schema: {schema}")
                    else:
                        schema = "100"
        except Exception as e:
            logging.error(f"Error reading schema: {e}")
            schema = "100"
        
        VERSION_INFO = f"V{version}S{schema}"
        draw.text((2, 50), VERSION_INFO, font=smartFont, fill=255)

    # --- Page 1: System Info ---
    elif page_index == 1:
        # Get IP Address
        try:
            IPAddress = get_ip_address('eth0')
            if IPAddress == "N/A":
                IPAddress = get_ip()
        except:
            IPAddress = get_ip()

        # Get MAC Address
        MACAddress = get_mac_address('eth0')

        # Get compact system stats
        try:
            cmd = "top -bn1 | grep 'Cpu' | awk '{print $2}' | cut -d'%' -f1"
            cpu_usage = subprocess.check_output(cmd, shell=True, timeout=2).decode('utf-8').strip()
            if not cpu_usage:
                cpu_usage = "N/A"
        except:
            cpu_usage = "N/A"
            
        try:
            cmd = "free | awk 'NR==2{printf \"%d\", $3*100/$2}'"
            mem_usage = subprocess.check_output(cmd, shell=True, timeout=2).decode('utf-8').strip()
            if not mem_usage:
                mem_usage = "N/A"
        except:
            mem_usage = "N/A"
            
        try:
            cmd = "df -h | awk '$NF==\"/\"{print $5}' | sed 's/%//'"
            disk_usage = subprocess.check_output(cmd, shell=True, timeout=2).decode('utf-8').strip()
            if not disk_usage:
                disk_usage = "N/A"
        except:
            disk_usage = "N/A"
            
        try:
            tempI = int(open('/sys/class/thermal/thermal_zone0/temp').read())
            if tempI > 1000:
                tempI = tempI / 1000
            temp_c = int(tempI)
            
            # Temperature status with warnings
            if temp_c < 40:
                temp_status = "Cool"
                temp_flash = False
            elif temp_c < 60:
                temp_status = "Normal"
                temp_flash = False
            elif temp_c < 70:
                temp_status = "Warm"
                temp_flash = False
            elif temp_c < 80:
                temp_status = "Hot"
                temp_flash = False
            else:
                temp_status = "TURN OFF"
                temp_flash = True  # Flash warning
            
            temp = f"{temp_c}C"
        except:
            temp = "N/A"
            temp_status = "N/A"
            temp_flash = False

        # Draw IP Address (medium size - using font14)
        draw.text((2, 0), IPAddress, font=font14, fill=255)
        
        # Draw MAC Address without "MAC:" prefix (12pt size - using font12)
        draw.text((2, 18), MACAddress, font=font12, fill=255)
        
        # Draw compact stats on one line without temperature (normal size - using font10)
        stats_line = f"CPU:{cpu_usage}% M:{mem_usage}% D:{disk_usage}%"
        draw.text((2, 36), stats_line, font=font10, fill=255)
        
        # Draw temperature on separate line with status
        # Flash the temperature line if critical (only show every other second)
        if temp_flash and int(time.time()) % 2 == 0:
            # Don't draw on flash-off cycle
            pass
        else:
            temp_line = f"T:{temp} {temp_status}"
            draw.text((2, 50), temp_line, font=font10, fill=255)

    # --- Page 2: Power Options ---
    elif page_index == 2:
        draw.text((2, 2), 'Power Options', font=fontb12, fill=255)
        options = ['Reboot', 'Shutdown', 'Reset Network']
        for i, option in enumerate(options):
            y = 20 + i * 14
            if sel_index == i:
                draw.rectangle((2, y, width-4, y+12), outline=255, fill=255)
                draw.text((4, y+1), option, font=font10, fill=0)
            else:
                draw.text((4, y+1), option, font=font10, fill=255)

    # --- Page 3: Reboot confirmation ---
    elif page_index == 3:
        draw.text((2, 2), 'Reboot?', font=fontb12, fill=255)
        options = ['Yes', 'No']
        for i, option in enumerate(options):
            y = 20 + i*14
            if sel_index == i:
                draw.rectangle((2, y, width-4, y+12), outline=255, fill=255)
                draw.text((4, y+1), option, font=font10, fill=0)
            else:
                draw.text((4, y+1), option, font=font10, fill=255)

    # --- Page 5: Shutdown confirmation ---
    elif page_index == 5:
        draw.text((2, 2), 'Shutdown?', font=fontb12, fill=255)
        options = ['Yes', 'No']
        for i, option in enumerate(options):
            y = 20 + i*14
            if sel_index == i:
                draw.rectangle((2, y, width-4, y+12), outline=255, fill=255)
                draw.text((4, y+1), option, font=font10, fill=0)
            else:
                draw.text((4, y+1), option, font=font10, fill=255)

    # --- Page 7: Rebooting ---
    elif page_index == 7:
        draw.text((2, 2), 'Rebooting', font=fontb12, fill=255)
        draw.text((2, 20), 'Please wait...', font=font10, fill=255)

    # --- Page 8: Shutting down ---
    elif page_index == 8:
        draw.text((2, 2), 'Shutting down', font=fontb12, fill=255)
        draw.text((2, 20), 'Please wait...', font=font10, fill=255)

    # --- Page 9: Reset Network confirmation ---
    elif page_index == 9:
        draw.text((2, 2), 'Reset Network?', font=fontb12, fill=255)
        options = ['Yes', 'No']
        for i, option in enumerate(options):
            y = 20 + i*14
            if sel_index == i:
                draw.rectangle((2, y, width-4, y+12), outline=255, fill=255)
                draw.text((4, y+1), option, font=font10, fill=0)
            else:
                draw.text((4, y+1), option, font=font10, fill=255)

    # Clear and redraw
    # oled.clearDisplay()
    oled.drawImage(image)

    lock.acquire()
    drawing = False
    lock.release()

def update_page_index(pi):
    global pageIndex, selectionIndex, lastActivityTime
    lock.acquire()
    pageIndex = pi
    selectionIndex = 0  # Reset selection to first item
    lastActivityTime = time.time()
    lock.release()
    wake_screen()

def update_selection_index():
    global selectionIndex, lastActivityTime, pageIndex
    lock.acquire()
    if pageIndex == 2:  # Power menu has 3 items
        selectionIndex = (selectionIndex + 1) % 3
    else:  # Yes/No dialogs have 2 items
        selectionIndex = (selectionIndex + 1) % 2
    lastActivityTime = time.time()
    lock.release()
    wake_screen()

def receive_signal(signum, stack):
    global pageIndex, selectionIndex
    
    logging.info(f"Received signal: {signum}")
    
    # If screen is sleeping, any button just wakes it up without performing action
    was_sleeping = wake_screen()
    if was_sleeping:
        logging.info("Screen was sleeping, ignoring button action")
        draw_page()  # Redraw the current page
        return  # Don't perform any button action, just wake up

    lock.acquire()
    page_index = pageIndex
    sel_index = selectionIndex
    lock.release()

    if signum == signal.SIGUSR1:  # Button K1 - Navigate/Select
        if page_index in [2, 3, 5, 9]:  # In menu pages
            update_selection_index()
        elif page_index == 0:
            update_page_index(1)
        elif page_index == 1:
            update_page_index(0)
        draw_page()

    elif signum == signal.SIGUSR2:  # Button K2 - Confirm/Select
        if page_index == 2:  # Power menu
            if sel_index == 0:
                update_page_index(3)  # Reboot confirm
            elif sel_index == 1:
                update_page_index(5)  # Shutdown confirm
            else:
                update_page_index(9)  # Reset network confirm
        elif page_index == 3:  # Reboot confirm
            if sel_index == 0:  # Yes
                update_page_index(7)
                draw_page()
                time.sleep(3)
                os.system('systemctl reboot')
            else:  # No
                update_page_index(0)
        elif page_index == 5:  # Shutdown confirm
            if sel_index == 0:  # Yes
                update_page_index(8)
                draw_page()
                time.sleep(3)
                os.system('systemctl poweroff')
            else:  # No
                update_page_index(0)
        elif page_index == 9:  # Reset network confirm
            if sel_index == 0:  # Yes
                # Add reset network logic here
                update_page_index(0)
            else:  # No
                update_page_index(0)
        else:
            update_page_index(0)
        draw_page()

    elif signum == signal.SIGALRM:  # Button K3 - Menu/Back
        if page_index == 2:
            update_page_index(0)
        else:
            update_page_index(2)
        draw_page()

# Main execution
try:
    # Display logo if it exists
    logo_path = 'innovo.png'
    if os.path.exists(logo_path):
        logging.info("Loading logo...")
        image0 = Image.open(logo_path).convert('1')
        oled.drawImage(image0)
        time.sleep(2)
        # oled.clearDisplay()

    signal.signal(signal.SIGUSR1, receive_signal)
    signal.signal(signal.SIGUSR2, receive_signal)
    signal.signal(signal.SIGALRM, receive_signal)

    logging.info("Starting main loop...")
    while True:
        try:
            draw_page()
            time.sleep(1)
                
        except KeyboardInterrupt:
            break
        except Exception as e:
            logging.error(f"Error in main loop: {e}")
            time.sleep(0.5)

except Exception as e:
    logging.error(f"Fatal error: {e}")
    import traceback
    traceback.print_exc()
