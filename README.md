# 00klan macro
Mouse + keyboard macro recorder/player with a dark blue gaming UI.

**Hotkeys:** F6 record/stop · F7 play/stop · F8 stop all
**Auto Clicker tab:** record one key (or use left/right click), 1-2000 presses per second (slider or type a value), rebindable activation key or mouse button (middle / Mouse 4 / Mouse 5; default F9), mode Toggle / Hold / Once.

**Macro Recorder features:** record mouse moves/clicks/scroll + keystrokes, repeat count (0 = loop), speed 0.25x-4x, save/load `.klan` files.

## Run from source
    pip install -r requirements.txt
    python main.py

## Build the EXE + installer (Windows)
1. Install Python 3.10+ (tick "Add to PATH") and Inno Setup 6.
2. Double-click `build.bat`.
3. Output: `dist\00klan-macro.exe` and `installer_output\00klan-macro-setup.exe`.
