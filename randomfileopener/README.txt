Random File Opener / 随机文件打开器 v1.6.6
================================================================================

[English Section]

Random File Opener is a powerful and lightweight tool designed to open a random 
file from a specified directory (and its subdirectories). It's perfect for 
reviewing large collections of documents, images, or exploring codebases.

--- Features ---
* High Performance: Uses fast scanning algorithms.
* Smart Filtering: Automatically ignores system/hidden/temp files.
* No Duplicates: Tracks opened files to prevent repetition.
* Standalone: Single EXE, no installation required.
* Context Menu: Integrate into Windows right-click menu.
* Batch Open: Open multiple files at once.

--- Quick Start ---
1. Run Directly: Double-click RandomFileOpener.exe.
2. Command Line: RandomFileOpener.exe -d "C:\My Photos"

--- Advanced Usage ---

[Context Menu Integration (Recommended)]
Add "Random File Opener" to your Windows right-click menu:
Command: RandomFileOpener.exe --register-menu

Now you can right-click any folder and select "🎲 随机打开文件".
To remove: RandomFileOpener.exe --unregister-menu

[Batch Open]
Open 5 files at once:
Command: RandomFileOpener.exe --count 5

[Configuration]
Export default config to customize:
Command: RandomFileOpener.exe --init-config

--- License ---
MIT License


================================================================================

[中文部分 / Chinese Section]

随机文件打开器 是一个强大且轻量级的工具，用于从指定目录及其子目录中随机打开文件。
特别适合用于回顾大量文档、图片素材或随机浏览代码库。

--- 功能特点 ---
* 高性能: 快速扫描数万个文件。
* 智能过滤: 自动过滤系统/隐藏/临时文件。
* 防重复: 记录已打开文件，避免重复。
* 独立运行: 单个 EXE，无需安装。
* 右键菜单: 支持集成到 Windows 右键菜单。
* 批量打开: 支持一次打开多个文件。

--- 快速开始 ---
1. 直接运行: 双击 RandomFileOpener.exe。
2. 命令行: RandomFileOpener.exe -d "C:\My Photos"

--- 高级用法 ---

[右键菜单集成 (推荐)]
将工具集成到系统右键菜单：
命令: RandomFileOpener.exe --register-menu

之后，在任意文件夹上右键，点击 "🎲 随机打开文件" 即可运行。
移除菜单: RandomFileOpener.exe --unregister-menu

[批量打开]
一次性打开 5 个文件：
命令: RandomFileOpener.exe --count 5

[修改配置]
生成默认配置文件：
命令: RandomFileOpener.exe --init-config

--- 许可证 ---
MIT License
