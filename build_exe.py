import os
import sys
import subprocess
import shutil
from pathlib import Path

def check_pyinstaller():
    """检查是否安装了PyInstaller"""
    try:
        import PyInstaller
        return True
    except ImportError:
        print("错误: 未安装 PyInstaller。")
        print("请运行: pip install pyinstaller")
        return False

def generate_version_info(file_path):
    """生成Windows版本信息文件"""
    content = """
# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(1, 6, 6, 0),
    prodvers=(1, 6, 6, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'080404b0',
        [StringStruct(u'CompanyName', u'Open Source'),
        StringStruct(u'FileDescription', u'Random File Opener Tool'),
        StringStruct(u'FileVersion', u'1.6.6'),
        StringStruct(u'InternalName', u'RandomFileOpener'),
        StringStruct(u'LegalCopyright', u'MIT License'),
        StringStruct(u'OriginalFilename', u'RandomFileOpener.exe'),
        StringStruct(u'ProductName', u'Random File Opener'),
        StringStruct(u'ProductVersion', u'1.6.6')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [2052, 1200])])
  ]
)
"""
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

def build_exe():
    """构建可执行文件"""
    if not check_pyinstaller():
        return

    # 设置路径
    work_dir = Path("build_output")
    dist_dir = work_dir / "dist"
    build_temp_dir = work_dir / "build"
    script_path = Path("random_file_opener.py").resolve()
    
    if not script_path.exists():
        print(f"错误: 找不到脚本文件 {script_path}")
        return
    
    # 清理旧构建
    if work_dir.exists():
        try:
            shutil.rmtree(work_dir)
        except Exception as e:
            print(f"警告: 无法清理构建目录: {e}")

    # 准备版本信息
    version_file = work_dir / "file_version_info.txt"
    work_dir.mkdir(parents=True, exist_ok=True)
    generate_version_info(version_file)
    
    # 查找图标
    icon_path = Path("icon.ico")
    
    # PyInstaller 命令参数
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",  # 单文件模式
        "--console",  # 显示控制台
        "--name", "RandomFileOpener",
        "--clean",
        "--distpath", str(dist_dir),
        "--workpath", str(build_temp_dir),
        "--specpath", str(work_dir),
        f"--version-file={version_file.resolve()}",
    ]
    
    # 查找UPX
    upx_path = shutil.which("upx")
    if upx_path:
        print(f"发现 UPX 压缩工具: {upx_path}")
        cmd.append("--upx-dir={}".format(str(Path(upx_path).parent)))
    else:
        print("未发现 UPX，生成的 EXE 体积可能会稍大。")
        # 尝试查找当前目录下的 upx
        local_upx = Path("upx")
        if local_upx.exists() and local_upx.is_dir():
             print(f"发现本地 UPX 目录: {local_upx}")
             cmd.append(f"--upx-dir={local_upx}")

    if icon_path.exists():
        print(f"发现图标文件: {icon_path}")
        cmd.append(f"--icon={icon_path}")
    
    cmd.append(str(script_path))
    
    print("开始构建...")
    print(f"命令: {' '.join(cmd)}")
    
    try:
        subprocess.check_call(cmd)
        print("\n" + "="*50)
        print(f"构建成功! 可执行文件位于:\n{dist_dir / 'RandomFileOpener.exe'}")
        print("="*50)
    except subprocess.CalledProcessError as e:
        print(f"\n构建失败: {e}")
    except Exception as e:
        print(f"\n发生错误: {e}")

if __name__ == "__main__":
    build_exe()
