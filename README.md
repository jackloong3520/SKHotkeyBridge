# SKHotkeyBridge — Mac KM Link 对拷线快捷键桥接

为 **Mac KM Link（对拷线）** 补齐原厂缺失的全局快捷键：用键盘组合键或鼠标侧键，一键切换"鼠标键盘控制"与"剪贴簿分享"。

**不修改、不注入、不破解原程序。** 本工具只是一个独立的小托盘程序，向原程序窗口转发它自己的托盘菜单命令，本质是"替你点了一次右键菜单"。

---

## ⚠️ 适用版本

| 项目 | 值 |
|---|---|
| **适用版本** | **Mac KM Link V1.0.1325.47R** |
| 清单版本 | `1.0.1325.47`（`Deployment/Config/LoaderMenifest.xml`、`autorun.inf` 均为此值） |
| 产品标识 | `CompanyID="OTi"`，`ProductName="MacKMLink1325"` |
| 核心进程 | `MacKMLink.exe`（由 `SKLoader.exe` 释放到 `%APPDATA%\OTi\MacKMLink1325\FunctModules\{8AEC7F86-B5F4-499b-9ACE-203F46E4469D}\`） |
| 实测平台 | Windows 11 64 位 |

> **其他版本能否用？** 大概率可以，但需要自行核对三个参数：窗口类名、两个菜单命令号、托盘回调消息号。方法见下文[「适配其他版本」](#适配其他版本)。

---

## 功能

| 快捷键 | 作用 |
|---|---|
| `Ctrl + Alt + F11` | **一键同步开关** — 同时控制"鼠标键盘控制"和"剪贴簿分享" |
| `Ctrl + Alt + F9` | 只切换"鼠标键盘控制" |
| `Ctrl + Alt + F10` | 只切换"剪贴簿分享" |

**一键同步的切换规则：** 只要有一项是开启的，按下就全部关闭；全部关闭时按一次则全部开启。

即使两项状态不一致（比如你手动只关了剪贴簿），按一次会先统一成"全部关闭"，再按一次统一"全部开启" —— 会自动纠偏，不会越切越乱。

其他特性：

- 快捷键可任意修改，也可只保留一个（其余留空即停用）
- 托盘图标右键菜单：一键同步 / 全部开启 / 全部关闭 / 单独切换 / 查看当前状态 / 重新载入配置 / 退出
- 托盘提示实时显示当前状态（已共享 / 已暂停 / 不一致）
- 命令行模式，可挂进脚本、任务计划或快捷方式
- 单实例保护、配置热重载、UAC 完整性级别检测
- 零依赖（纯 Python 标准库 + Win32 API）

---

## 快速开始

### 方式一：直接下载 EXE（推荐）

下载 `SKHotkeyBridge.exe` 与 `SKHotkeyBridge.ini`，**放在同一目录**。

**固定下载直链**（永远指向最新版本，重装系统 / 换电脑后直接访问即可）：

```
https://github.com/jackloong3520/SKHotkeyBridge/releases/latest/download/SKHotkeyBridge.exe
https://github.com/jackloong3520/SKHotkeyBridge/releases/latest/download/SKHotkeyBridge.ini
```

前往 [Releases 页面](https://github.com/jackloong3520/SKHotkeyBridge/releases/latest) 可查看版本说明与 SHA-256。

### 换电脑 / 重装系统后一键部署

仓库附带 `install.ps1`，自动完成"下载最新版 → 安装到 `%LOCALAPPDATA%\SKHotkeyBridge` → 加入开机启动"：

```powershell
powershell -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/jackloong3520/SKHotkeyBridge/main/install.ps1 | iex"
```

或先下载再执行：

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

脚本只做三件事，不写注册表、不改系统设置，卸载时删除对应目录和启动项即可。

### 方式二：从源码运行

需要 Python 3.9+（Windows）。

```bat
python SKHotkeyBridge.py
```

### 使用步骤

1. 先正常启动原版 `SKLoader.exe`，确认对拷线已连接。
2. 运行 `SKHotkeyBridge.exe`，程序驻留托盘（无窗口、无控制台）。
3. 按 `Ctrl+Alt+F11` 试一下，托盘提示会在"已共享 / 已暂停"之间变化。
4. 开机自启：`Win + R` → `shell:startup` → 放入 `SKHotkeyBridge.exe` 的快捷方式。

---

## 绑定到罗技鼠标

以 Logitech Options+ / G Hub 为例：

1. 选中要绑定的鼠标按键（侧键、DPI 键等）。
2. 动作类型选 **"组合键" / Keystroke Assignment**。
3. 录制或手动输入 `Ctrl + Alt + F11`。
   - 若软件要求"录制"，用键盘实际按一次 `Ctrl+Alt+F11` 即可。
4. 保存。

> **提示：** 罗技的按键映射发生在驱动层，会被 Windows 识别为真实按键，因此能正常触发本工具的全局热键。若某款鼠标只能映射单键，可在本工具的 INI 中把热键改成 `CTRL+ALT+<你的键>`，或改用 `WIN+ALT+...` 等不与常用软件冲突的组合。

---

## 配置

编辑与 EXE 同目录的 `SKHotkeyBridge.ini`，保存后在托盘右键选择 **"重新载入配置"** 即可生效，无需重启。

```ini
[Hotkeys]
Both=CTRL+ALT+F11            ; 一键同步开关
KeyboardMouse=CTRL+ALT+F9    ; 只切换鼠标键盘控制
Clipboard=CTRL+ALT+F10       ; 只切换剪贴簿分享
```

只要一键同步：把另外两行留空即可。

```ini
[Hotkeys]
Both=CTRL+ALT+F11
KeyboardMouse=
Clipboard=
```

**支持的修饰键：** `Ctrl` / `Alt` / `Shift` / `Win`（大小写与顺序不限）。
**支持的主键：** `A-Z`、`0-9`、`F1-F24`，以及 `Space`、`Enter`、`Tab`、`Esc`、`Home`、`End`、`PageUp`、`PageDown`、`Insert`、`Delete`、方向键等。

### 状态检测

```ini
[State]
Detection=auto               ; auto=先读真实状态再发命令（推荐）；off=直接各切一次
HideProbeMenu=true           ; 读取状态时把菜单移到屏幕外，避免闪烁
VerifyAfterCommand=true      ; 发送命令后再读一次状态做校验
```

| 模式 | 行为 | 适用 |
|---|---|---|
| `auto` | 弹菜单读真实状态 → 只发必要的命令 → 再读一次校验 | 默认，最可靠 |
| `off` | 不读状态，直接两项各切一次 | 极端环境弹菜单失败时；代价是两项可能不同步 |

---

## 命令行

适合排错、脚本化或绑定到其他自动化工具。

```
SKHotkeyBridge.exe --state            读取当前开关状态（输出 JSON）
SKHotkeyBridge.exe --toggle-both      执行一次一键同步
SKHotkeyBridge.exe --all-on           全部开启
SKHotkeyBridge.exe --all-off          全部关闭
SKHotkeyBridge.exe --toggle-km        只切换鼠标键盘控制
SKHotkeyBridge.exe --toggle-clipboard 只切换剪贴簿分享
SKHotkeyBridge.exe --check-target     检查能否找到原程序窗口
SKHotkeyBridge.exe --self-test        运行内部自检
SKHotkeyBridge.exe --stop             停止正在运行的桥接
```

`--state` 输出示例：

```json
{
  "ok": true,
  "km": true,
  "clipboard": true,
  "km_text": "暂时关闭鼠标键盘控制",
  "clipboard_text": "暂时关闭剪贴簿分享"
}
```

> `--state` 返回 `km: true` 表示**当前处于开启（正在共享）**状态 —— 因为菜单文字是"暂时关闭…"，即"下一步可以关闭"。

---

## 工作原理

### 逆向结论（V1.0.1325.47R 实测）

| 项目 | 值 |
|---|---|
| 目标窗口类 | `SmartKMCCableWinClass` |
| 鼠标键盘控制命令 | `WM_COMMAND` wParam = **32776** |
| 剪贴簿分享命令 | `WM_COMMAND` wParam = **32777** |
| 托盘回调消息 | `0x8001`（`PostMessage(hwnd, 0x8001, 0, WM_RBUTTONUP)` 可程序化弹出菜单） |
| 托盘图标 ID | `0` |

### 状态是怎么读到的

要让"一个键同时控制两项"，必须先知道每项当前是开还是关，否则两个独立开关会越切越乱。难点在于：

- 程序**不把状态写入任何文件或注册表**，只能从托盘菜单读。
- 托盘提示文字**不随状态变化**，没有利用价值。
- 菜单**每次右键都重新创建**，关闭后句柄立即失效，无法缓存复用。

解法：程序化弹出原程序的托盘菜单 → 移到屏幕外 → 读取菜单文字 → 关闭菜单。全程约 20 毫秒，肉眼不可见。

菜单文字映射（**注意是反的**，因为菜单显示的是"下一步动作"）：

| 菜单文字 | 实际状态 |
|---|---|
| 暂时关闭鼠标键盘控制 / 暂时关闭剪贴簿分享 | **开启中** |
| 开启鼠标键盘控制 / 开启剪贴簿分享 | **已关闭** |

### 关闭菜单的坑

实测 `WM_CANCELMODE` 和 `EndMenu()` **都无效**，会把菜单卡死在屏幕上。唯一可靠的是 `PostMessage(hwnd, WM_CLOSE)`（失败时回退到模拟 Esc 按键）。识别菜单窗口时按 **类名 `#32768` + 所属进程 PID** 双重过滤，避免误操作其他程序的菜单。

---

## 适配其他版本

若你用的不是 V1.0.1325.47R，按以下步骤核对参数：

1. **查窗口类名与进程名**

   ```bat
   SKHotkeyBridge.exe --check-target
   ```

   找不到就用 Spy++ / Window Detective 找 `MacKMLink.exe` 的隐藏窗口类名，填入 `[Target]` 的 `WindowClass`。

2. **查两个命令号**

   用任意能读菜单的工具（如 Spy++ 的消息日志）右键托盘图标，观察 `WM_COMMAND` 的 wParam；或直接跑：

   ```python
   # 弹出菜单后枚举所有菜单项的 ID 与文字
   # 找到"鼠标键盘控制"和"剪贴簿分享"对应的 ID
   ```

   填入 `[Target]` 的 `KeyboardMouseCommand` / `ClipboardCommand`。

3. **查托盘回调消息号**

   本版本为 `0x8001`。若不同，改 `[Target]` 的 `TrayMessage`。这个值通常在 `WM_APP(0x8000) ~ 0xBFFF` 区间。

4. **非中文界面**

   同步修改 `[State]` 里的四个菜单文字，或依赖内置的英文回退规则（含 `disable` → 开启中，含 `enable` → 已关闭）。

---

## 自行构建

```bat
pip install pyinstaller
pyinstaller --noconfirm --clean --noupx --onefile --noconsole ^
  --name SKHotkeyBridge --distpath dist --workpath build SKHotkeyBridge.py
```

产物 `dist\SKHotkeyBridge.exe`。

仓库已内置 GitHub Actions：推送 `v*` 标签即自动编译并把 EXE + INI 打包上传到 Release。

```bat
git tag v1.0.0
git push origin v1.0.0
```

---

## 风险与注意事项

- **权限一致：** 若原版对拷线以管理员身份运行，本工具也必须"以管理员身份运行"，否则 Windows UIPI 会拦截消息。工具会主动检测完整性级别并弹窗提示。
- **热键冲突：** 若快捷键被其他程序占用，注册会失败并弹窗提示。换一个组合即可。
- **未签名：** 本项目发布的 EXE **未做商业代码签名**，Windows SmartScreen 可能拦截，属正常现象。请以 Release 页面提供的 SHA-256 校验下载文件，或直接用源码自行构建。
- **杀毒软件误报：** PyInstaller 打包产物常被启发式引擎误报。源码完全开放，可自行审查后构建。
- **回滚方式：** 退出托盘程序或直接删除两个文件即可，原版程序不受任何影响。

---

## 免责声明

- 本项目**不分发、不包含** Mac KM Link 的任何原始二进制文件、许可证或受版权保护的资源。用户需自行持有正版软件。
- 本项目是**独立的外挂式小工具**，不修改目标程序磁盘文件、不注入目标进程、不绕过任何授权或付费机制，仅通过 Windows 公开的消息机制转发目标程序自身的菜单命令。
- 逆向分析过程仅用于实现软件自身的互操作与可访问性增强（为缺失的 UI 功能提供键盘/鼠标替代入口）。请遵守所在地法律法规及目标软件的最终用户许可协议。
- 软件按"原样"提供，作者不对使用造成的任何损失负责。

---

## 许可证

[MIT](LICENSE)
