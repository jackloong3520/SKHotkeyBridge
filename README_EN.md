# SKHotkeyBridge

Adds missing global hotkeys to **Mac KM Link** (a KVM-style "对拷线" cable that lets one keyboard/mouse control two PCs and share files between them).

## Target version

| Item | Value |
|---|---|
| **Supported version** | **Mac KM Link V1.0.1325.47R** |
| Manifest version | `1.0.1325.47` (`ProductName="MacKMLink1325"`, `CompanyID="OTi"`) |
| Core process | `MacKMLink.exe` |
| Tested on | Windows 11 x64 |

Other versions likely work but may need different window-class / command IDs — see "Adapting to other versions" in the [Chinese README](README.md).

## What it does

The original program lets you toggle "Keyboard & Mouse Control" and "Clipboard Sharing" only from its tray icon's right-click menu — there is no hotkey setting anywhere. This tool adds them:

| Hotkey | Action |
|---|---|
| `Ctrl + Alt + F11` | **Sync toggle** — turns both channels on or off together |
| `Ctrl + Alt + F9` | Toggle keyboard/mouse control only |
| `Ctrl + Alt + F10` | Toggle clipboard sharing only |

Sync rule: if either channel is on, one press turns **both off**; when both are off, one press turns **both on**. Mixed states self-heal.

Designed to be bound to a Logitech mouse button (Options+ / G Hub → assign keystroke).

## How it works

No patching, no injection, no cracking. It is a standalone tray app that forwards the target program's **own** tray-menu commands:

| Item | Value |
|---|---|
| Window class | `SmartKMCCableWinClass` |
| Keyboard/mouse command | `WM_COMMAND` wParam = `32776` |
| Clipboard command | `WM_COMMAND` wParam = `32777` |
| Tray callback message | `0x8001` (icon id `0`) |

To make one key control both channels reliably, the real on/off state must be read first. The program does not persist state to disk or registry, and its tray tooltip does not reflect it, so this tool programmatically opens the tray menu, moves it off-screen, reads the captions, and closes it — roughly 20 ms, invisible to the user.

Caption mapping is inverted (the menu shows the *next* action): "暂时关闭…" / "Disable …" means currently **on**; "开启…" / "Enable …" means currently **off**.

## Usage

1. Start the original `SKLoader.exe`.
2. Run `SKHotkeyBridge.exe` (keep it in the same folder as `SKHotkeyBridge.ini`).
3. Press `Ctrl+Alt+F11`, or bind it to a mouse button.
4. Optional: put a shortcut in `shell:startup` for autostart.

Command line: `--state`, `--toggle-both`, `--all-on`, `--all-off`, `--toggle-km`, `--toggle-clipboard`, `--check-target`, `--self-test`, `--stop`.

## Build

```bat
pip install pyinstaller
pyinstaller --noconfirm --clean --noupx --onefile --noconsole --name SKHotkeyBridge SKHotkeyBridge.py
```

## Disclaimer

This project does **not** distribute any original Mac KM Link binaries or copyrighted assets; you must own a legitimate copy. It does not modify the target's files, inject into its process, or bypass any licensing. Reverse engineering was performed solely for interoperability — providing keyboard/mouse alternatives to UI-only functions. Provided "as is".

## License

[MIT](LICENSE)
