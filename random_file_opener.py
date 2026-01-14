import argparse
import atexit
import fnmatch
import hashlib
import json
import logging
import logging.handlers
import mimetypes
import os
import platform
import random
import shutil
import subprocess
import sys
import threading
import time
import traceback
import winreg
from collections import OrderedDict, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Lock, RLock
from typing import Any, Deque, Dict, Generic, List, Optional, Tuple, TypeVar, Union

# 检查Python版本
if sys.version_info < (3, 7):
    print("错误: 需要Python 3.7或更高版本")
    sys.exit(1)

# 类型变量定义
T = TypeVar('T')
K = TypeVar('K')
V = TypeVar('V')

# 检查必要模块
try:
    from dataclasses import dataclass, field, asdict
except ImportError as e:
    print(f"错误: 缺少必要的dataclasses模块: {e}")
    sys.exit(1)


@dataclass
class Config:
    """配置类，集中管理所有配置参数"""
    # 文件路径配置
    history_filename: str = ".file_opener_history.json"
    log_filename: str = ".file_opener_log.txt"
    config_filename: str = ".file_opener_config.json"
    extended_log_filename: str = ".file_opener_extended_log.json"
    
    # 性能配置
    max_retries: int = 2
    max_log_size: int = 512 * 1024  # 512KB
    cache_ttl: int = 5  # 缓存有效期（秒）
    max_backup_files: int = 10  # 最大备份文件数
    max_file_size_for_full_hash: int = 10 * 1024 * 1024  # 10MB，大于此大小的文件计算部分哈希
    hash_cache_size: int = 100  # 哈希缓存最大条目数
    pattern_cache_size: int = 500  # 模式匹配缓存最大条目数
    encoding_cache_size: int = 50  # 编码检测缓存大小
    file_type_cache_size: int = 200  # 文件类型检测缓存大小
    batch_scan_size: int = 100  # 批量扫描文件数
    max_preview_size: int = 1500  # 文本预览最大字符数
    max_encoding_check_size: int = 1024 * 1024  # 编码检测最大文件大小（1MB）
    max_extended_log_entries: int = 1000  # 最大扩展日志条目数
    
    # 符号链接配置
    symlink_max_depth: int = 20  # 符号链接最大解析深度
    
    # 日志配置
    log_level: str = "INFO"  # 日志级别: DEBUG, INFO, WARNING, ERROR
    enable_colors: bool = True  # 是否启用彩色输出
    log_to_console: bool = True  # 是否输出到控制台
    log_file_max_backups: int = 5  # 日志文件最大备份数
    
    # 文件排除配置
    exclude_patterns: List[str] = field(default_factory=lambda: [
        "*.pyc",
        "*.tmp",
        "~$*",  # Office临时文件
        "Thumbs.db",  # Windows缩略图缓存
        ".DS_Store",  # macOS系统文件
        "desktop.ini",  # Windows桌面配置文件
        "*.swp",  # Vim交换文件
        "*.swo",  # Vim交换文件
        "*.log",  # 日志文件（通常较大）
    ])
    
    text_extensions: List[str] = field(default_factory=lambda: [
        '.txt', '.md', '.json', '.xml', '.html', '.htm', '.css', '.js',
        '.py', '.java', '.cpp', '.c', '.h', '.cs', '.php', '.rb', '.go',
        '.rs', '.swift', '.kt', '.sql', '.yaml', '.yml', '.ini', '.cfg',
        '.conf', '.bat', '.sh', '.ps1', '.vbs', '.csv', '.tsv', '.log',
        '.toml', '.env', '.gitignore', '.dockerignore', '.editorconfig',
        '.properties', '.gradle', '.pom', '.xml', '.rst', '.tex', '.bib',
        '.asm', '.s', '.pas', '.pl', '.pm', '.tcl', '.lua', '.f', '.for',
        '.f90', '.m', '.mat', '.r', '.jl', '.scala', '.clj', '.hs', '.lhs',
        '.erl', '.ex', '.exs', '.vim', '.vimrc', '.bashrc', '.zshrc'
    ])
    
    system_executable_extensions: List[str] = field(default_factory=lambda: [
        '.exe', '.dll', '.sys', '.so', '.dylib', '.drv', '.vxd', '.ocx',
        '.scr', '.com', '.bat', '.cmd', '.msi', '.app', '.appimage',
        '.jar', '.war', '.ear', '.apk', '.ipa', '.dmg', '.pkg', '.deb',
        '.rpm', '.msm', '.msp', '.mst', '.chm', '.hlp', '.sys', '.vxd',
        '.bin', '.run', '.sh', '.bash', '.out', '.elf', '.ko', '.o', '.obj'
    ])
    
    # 网络配置
    network_timeout: float = 5.0  # 网络操作超时时间（秒）
    
    # 用户界面配置
    show_preview: bool = True  # 是否显示文本预览
    preview_max_lines: int = 10  # 预览最大行数
    show_progress: bool = True  # 是否显示进度信息
    
    # 高级配置
    enable_extended_logging: bool = False  # 是否启用扩展日志记录
    default_encoding: str = 'utf-8'  # 默认编码
    enable_file_type_detection: bool = True  # 是否启用文件类型检测
    enable_advanced_caching: bool = True  # 是否启用高级缓存
    
    # 新增配置
    exclude_symlinks: bool = True  # 是否排除符号链接
    enable_windows_long_path: bool = True  # 是否启用Windows长路径支持
    
    def __post_init__(self):
        """初始化配置值"""
        # 确保列表不为None并规范化
        self.exclude_patterns = self.exclude_patterns or []
        
        self.text_extensions = [ext.lower() for ext in (self.text_extensions or [])]
        self.system_executable_extensions = [ext.lower() for ext in (self.system_executable_extensions or [])]
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Config':
        """从字典创建配置"""
        # 过滤掉不存在的字段
        valid_fields = {field.name for field in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)
    
    def to_dict(self) -> Dict[str, Any]:
        """将配置转换为字典"""
        return asdict(self)


class AtomicCounter:
    """高性能原子计数器"""
    def __init__(self, initial_value: int = 0):
        self._value = initial_value
        self._lock = Lock()
        
    def increment(self, amount: int = 1) -> int:
        """原子增加计数器值"""
        with self._lock:
            self._value += amount
            return self._value
    
    def decrement(self, amount: int = 1) -> int:
        """原子减少计数器值"""
        with self._lock:
            self._value -= amount
            return self._value
    
    def get(self) -> int:
        """获取当前值"""
        with self._lock:
            return self._value
    
    def set(self, value: int) -> None:
        """设置计数器值"""
        with self._lock:
            self._value = value
    
    def reset(self) -> int:
        """重置计数器并返回之前的值"""
        with self._lock:
            old_value = self._value
            self._value = 0
            return old_value


class SimpleLRUCache(Generic[K, V]):
    """简化的LRU缓存实现"""
    def __init__(self, max_size: int = 100):
        if max_size <= 0:
            raise ValueError("max_size必须大于0")
        self.max_size = max_size
        self._cache: OrderedDict[K, V] = OrderedDict()
        self._lock = RLock()
        self._hits = AtomicCounter(0)
        self._misses = AtomicCounter(0)
        
    def get(self, key: K) -> Optional[V]:
        """获取缓存值，更新访问时间"""
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._hits.increment()
                return self._cache[key]
            self._misses.increment()
            return None
    
    def put(self, key: K, value: V) -> None:
        """添加缓存值"""
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            elif len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)
            self._cache[key] = value
    
    def remove(self, key: K) -> bool:
        """移除指定键的缓存"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._hits.set(0)
            self._misses.set(0)
    
    def size(self) -> int:
        """获取缓存大小"""
        with self._lock:
            return len(self._cache)
    
    def stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self._lock:
            hits = self._hits.get()
            misses = self._misses.get()
            total = hits + misses
            hit_rate = hits / total if total > 0 else 0.0
            
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "hits": hits,
                "misses": misses,
                "hit_rate": hit_rate,
                "fullness": len(self._cache) / self.max_size if self.max_size > 0 else 0.0
            }
    
    def __len__(self) -> int:
        """获取缓存大小"""
        return self.size()


class FileDescriptorTracker:
    """简化的文件描述符跟踪器"""
    def __init__(self):
        self._lock = Lock()
        self._count = 0
        self._max_count = 0
        self._opened_count = AtomicCounter(0)
        self._closed_count = AtomicCounter(0)
    
    def track_open(self) -> None:
        """跟踪文件描述符打开"""
        with self._lock:
            self._count += 1
            self._opened_count.increment()
            if self._count > self._max_count:
                self._max_count = self._count
    
    def track_close(self) -> None:
        """跟踪文件描述符关闭"""
        with self._lock:
            if self._count > 0:
                self._count -= 1
            self._closed_count.increment()
    
    def get_count(self) -> int:
        """获取当前打开的文件描述符数量"""
        with self._lock:
            return self._count
    
    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        with self._lock:
            opened = self._opened_count.get()
            closed = self._closed_count.get()
            leaked = max(0, opened - closed)
            return {
                "current": self._count,
                "max": self._max_count,
                "opened": opened,
                "closed": closed,
                "leaked": leaked
            }


class RandomFileOpener:
    def __init__(self, config: Optional[Config] = None, target_dir: Optional[str] = None) -> None:
        print("正在初始化随机文件打开器...")
        
        # 设置工作目录
        try:
            if target_dir:
                self.script_dir = Path(target_dir).resolve()
                if not self.script_dir.exists():
                    raise ValueError(f"目标路径不存在: {self.script_dir}")
                if not self.script_dir.is_dir():
                    raise ValueError(f"目标路径不是目录: {self.script_dir}")
            else:
                # 判断是否在打包环境(Frozen)下运行
                if getattr(sys, 'frozen', False):
                    # PyInstaller打包后的可执行文件路径
                    self.script_dir = Path(sys.executable).resolve().parent
                else:
                    # 正常脚本运行
                    self.script_dir = Path(__file__).resolve().parent
        except Exception as e:
            print(f"设置工作目录失败: {e}")
            self.script_dir = Path.cwd()
        
        print(f"工作目录: {self.script_dir}")
        
        # 使用传入的配置或创建默认配置
        # 注意：配置加载逻辑现在由调用者(main)负责处理，以确保正确的优先级
        self.config = config or Config()
        
        # 设置文件路径
        try:
            self.history_file = self.script_dir / self.config.history_filename
            self.log_file = self.script_dir / self.config.log_filename
            self.config_file = self.script_dir / self.config.config_filename
            self.extended_log_file = self.script_dir / self.config.extended_log_filename
        except Exception as e:
            print(f"设置文件路径失败: {e}")
            # 使用默认值
            self.history_file = self.script_dir / ".file_opener_history.json"
            self.log_file = self.script_dir / ".file_opener_log.txt"
            self.config_file = self.script_dir / ".file_opener_config.json"
            self.extended_log_file = self.script_dir / ".file_opener_extended_log.json"
        
        # 添加必要的排除项
        try:
            script_name = Path(__file__).name
            essential_excludes = [
                script_name,
                self.config.history_filename,
                self.config.log_filename,
                self.config.config_filename,
                self.config.extended_log_filename
            ]
            
            for exclude in essential_excludes:
                if exclude not in self.config.exclude_patterns:
                    self.config.exclude_patterns.append(exclude)
        except Exception as e:
            print(f"添加排除项失败: {e}")
        
        # 初始化基本组件
        try:
            self._init_basic_components()
        except Exception as e:
            print(f"初始化基本组件失败: {e}")
            raise
        
        # 初始化缓存
        try:
            self._init_caches()
        except Exception as e:
            print(f"初始化缓存失败: {e}")
            self._file_hash_cache = SimpleLRUCache(max_size=50)
            self._exclude_patterns_cache = SimpleLRUCache(max_size=100)
            self._encoding_cache = SimpleLRUCache(max_size=20)
            self._file_access_cache = SimpleLRUCache(max_size=50)
            self._file_type_cache = SimpleLRUCache(max_size=50)
        
        # 注册退出处理
        atexit.register(self._cleanup_all_temp_files)
        
        # 初始化MIME类型检测
        try:
            mimetypes.init()
        except Exception:
            pass
        
        print("初始化完成!")
    
    def _init_basic_components(self):
        """初始化基本组件"""
        self.history_lock = Lock()
        self.log_lock = Lock()
        self.cache_lock = Lock()
        self.file_operation_lock = RLock()
        self.stats_lock = Lock()
        
        self.fd_tracker = FileDescriptorTracker()
        
        self._temp_files = set()
        self._temp_files_lock = Lock()
        
        self.start_time = time.time()
        self.file_operations = 0
        
        self.total_files_scanned = AtomicCounter(0)
        self.total_files_excluded = AtomicCounter(0)
        
        self._qualified_files_cache = None
        self._cache_timestamp = 0.0
        self._last_dir_mtime = None
        
        # 初始化并发日志系统
        self._setup_logging()
        
        # 性能监控
        self.performance_stats = {
            "file_scans": AtomicCounter(0),
            "hash_calculations": AtomicCounter(0),
            "pattern_checks": AtomicCounter(0),
            "file_type_checks": AtomicCounter(0),
        }

    def _setup_logging(self):
        """配置标准日志系统"""
        # 创建Logger
        # 创建Logger
        self.logger = logging.getLogger("RandomFileOpener")
        self.logger.setLevel(getattr(logging, self.config.log_level.upper(), logging.INFO))
        
        # 清除现有handlers，避免重复，并关闭它们以防止ResourceWarning
        if self.logger.hasHandlers():
            for handler in self.logger.handlers[:]:
                handler.close()
                self.logger.removeHandler(handler)
        self.logger.handlers = []

        # 格式器
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        try:
            # 确保日志目录存在
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            
            # 文件Handler (带轮转)
            file_handler = logging.handlers.RotatingFileHandler(
                self.log_file,
                maxBytes=self.config.max_log_size,
                backupCount=self.config.log_file_max_backups,
                encoding='utf-8'
            )
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
        except Exception as e:
            print(f"无法设置日志文件 handler: {e}")

        # 控制台Handler
        if self.config.log_to_console:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)

    def log_message(self, message: str, level: str = "INFO") -> None:
        """兼容旧接口的日志方法"""
        lvl = getattr(logging, level.upper(), logging.INFO)
        self.logger.log(lvl, message)

    
    def _init_caches(self):
        """初始化缓存"""
        cache_class = SimpleLRUCache
        
        self._file_hash_cache = cache_class(max_size=self.config.hash_cache_size)
        self._exclude_patterns_cache = cache_class(max_size=self.config.pattern_cache_size)
        self._encoding_cache = cache_class(max_size=self.config.encoding_cache_size)
        self._file_access_cache = cache_class(max_size=self.config.hash_cache_size // 2)
        self._file_type_cache = cache_class(max_size=self.config.file_type_cache_size)
    
    @staticmethod
    def load_config_from_file(config_path: Union[str, Path]) -> Dict[str, Any]:
        """从文件加载配置"""
        try:
            path = Path(config_path)
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"加载用户配置失败: {e}")
        return {}

    
    def _cleanup_all_temp_files(self):
        """清理所有临时文件"""
        try:
            with self._temp_files_lock:
                files_to_clean = list(self._temp_files)
            
            for temp_file in files_to_clean:
                try:
                    path = Path(temp_file)
                    if path.exists():
                        path.unlink()
                except OSError:
                    pass
        except Exception:
            pass
    

    
    
    def log_error(self, error_message: str) -> None:
        """记录错误信息"""
        self.logger.error(error_message)
    
    def log_warning(self, warning_message: str) -> None:
        """记录警告信息"""
        self.logger.warning(warning_message)
    
    def log_debug(self, debug_message: str) -> None:
        """记录调试信息"""
        self.logger.debug(debug_message)
    
    def get_file_hash(self, filepath: Union[str, Path]) -> str:
        """计算文件的哈希值"""
        path = Path(filepath)
        if not path.exists():
            return ""
        
        try:
            self.performance_stats["hash_calculations"].increment()
            
            # 检查缓存
            # Use string conversion for cache key and logging
            str_path = str(path)
            stat = path.stat()
            cache_key = f"{str_path}_{stat.st_size}_{stat.st_mtime}"
            cached_result = self._file_hash_cache.get(cache_key)
            if cached_result:
                return cached_result
            
            file_size = stat.st_size
            file_hash = hashlib.sha256()
            
            if file_size <= self.config.max_file_size_for_full_hash:
                with open(path, 'rb') as f:
                    self.fd_tracker.track_open()
                    try:
                        while True:
                            chunk = f.read(8192)
                            if not chunk:
                                break
                            file_hash.update(chunk)
                    finally:
                        self.fd_tracker.track_close()
                hash_result = file_hash.hexdigest()
            else:
                # 抽样哈希
                hash_result = self._get_sampling_hash(filepath, file_size)
            
            # 更新缓存
            self._file_hash_cache.put(cache_key, hash_result)
            
            return hash_result
        except Exception as e:
            self.log_error(f"获取文件哈希失败 ({filepath}): {e}")
            return ""
    
    def _get_sampling_hash(self, filepath: str, file_size: int) -> str:
        """对大文件使用抽样哈希算法"""
        try:
            file_hash = hashlib.sha256()
            
            with open(filepath, 'rb') as f:
                self.fd_tracker.track_open()
                try:
                    # 读取文件开头
                    start_data = f.read(65536)
                    if start_data:
                        file_hash.update(start_data)
                    
                    # 读取多个样本点
                    sample_count = min(8, max(3, file_size // (5 * 1024 * 1024)))
                    for i in range(sample_count):
                        pos = int((i / (sample_count - 1)) * file_size) if sample_count > 1 else file_size // 2
                        f.seek(max(0, pos - 8192))
                        sample_data = f.read(16384)
                        if sample_data:
                            file_hash.update(sample_data)
                    
                    # 读取文件结尾
                    if file_size > 65536:
                        f.seek(max(0, file_size - 65536))
                        end_data = f.read(65536)
                        if end_data:
                            file_hash.update(end_data)
                finally:
                    self.fd_tracker.track_close()
            
            return file_hash.hexdigest()
        except Exception as e:
            self.log_error(f"计算抽样哈希失败 ({filepath}): {e}")
            return ""
    
    def should_exclude(self, filename: str, filepath: Union[str, Path]) -> Tuple[bool, Optional[str]]:
        """判断文件是否应该被排除"""
        if not filename:
            return True, "文件名为空"
        
        path = Path(filepath)
        
        # 检查是否是隐藏文件
        if filename.startswith('.') or filename.startswith('~'):
            return True, "隐藏文件"
        
        # 检查排除模式
        for pattern in self.config.exclude_patterns:
            if not pattern:
                continue
            
            if pattern.startswith("*."):
                ext_pattern = pattern[1:].lower()
                if filename.lower().endswith(ext_pattern):
                    return True, "匹配排除模式"
            elif pattern in filename:
                return True, "匹配排除模式"
            elif "*" in pattern or "?" in pattern:
                if fnmatch.fnmatch(filename, pattern):
                    return True, "匹配排除模式"
        
        # 检查是否是系统可执行文件
        for ext in self.config.system_executable_extensions:
            if filename.lower().endswith(ext):
                return True, "系统可执行文件"
        
        # 检查文件是否可访问
        try:
            if not path.exists():
                return True, "文件不存在"
            if not path.is_file():
                return True, "不是文件"
            if not os.access(path, os.R_OK): # os.access works with Path
                return True, "文件不可读"
            if self.config.exclude_symlinks and path.is_symlink():
                return True, "符号链接"
        except Exception as e:
            return True, f"文件访问错误: {e}"
        
        return False, None
    
    def scan_qualified_files(self, force_refresh: bool = False) -> Tuple[List[str], bool, Optional[str]]:
        """扫描当前目录中符合条件的文件"""
        current_time = time.time()
        
        with self.cache_lock:
            if (not force_refresh and 
                self._qualified_files_cache is not None and 
                (current_time - self._cache_timestamp) < self.config.cache_ttl):
                return self._qualified_files_cache, True, None
        
        qualified_files = []
        
        try:
            # 检查目录是否可访问
            if not os.access(self.script_dir, os.R_OK):
                return [], False, f"目录不可访问: {self.script_dir}"
            
            if not self.script_dir.exists():
                return [], False, f"目录不存在: {self.script_dir}"
            
            # os.scandir accepts Path objects
            with os.scandir(self.script_dir) as files_in_dir:
                for entry in files_in_dir:
                    try:
                        if not entry.is_file():
                            continue
                        
                        self.total_files_scanned.increment()
                        item = entry.name
                        item_path = entry.path
                    except OSError:
                        continue
                    
                    exclude, reason = self.should_exclude(item, item_path)
                    if exclude:
                        self.total_files_excluded.increment()
                        continue
                    
                    qualified_files.append(item)

                
        except Exception as e:
            error_msg = f"扫描文件时出错: {e}"
            return [], False, error_msg
        
        # 更新缓存
        with self.cache_lock:
            self._qualified_files_cache = qualified_files
            self._cache_timestamp = current_time
        
        return qualified_files, True, None
    
    def load_history(self) -> Dict[str, Any]:
        """加载历史记录"""
        default_history = {
            "opened_files": [],
            "failed_files": [],
            "file_signatures": {},
            "statistics": {
                "total_opened": 0,
                "total_failed": 0,
                "last_reset": None,
                "reset_count": 0,
                "last_opened": None,
                "last_opened_file": None,
                "cleaned_opened": 0,
                "cleaned_failed": 0,
                "total_resets": 0
            }
        }
        
        with self.history_lock:
            try:
                if self.history_file.exists():
                    with open(self.history_file, 'r', encoding='utf-8') as f:
                        loaded = json.load(f)
                    
                    # 验证和修复历史记录结构
                    if not isinstance(loaded, dict):
                        return default_history
                    
                    # 确保所有必要的键都存在
                    for key in ["opened_files", "failed_files", "file_signatures", "statistics"]:
                        if key not in loaded:
                            loaded[key] = default_history[key]
                    
                    # 确保statistics结构完整
                    for key in default_history["statistics"]:
                        if key not in loaded["statistics"]:
                            loaded["statistics"][key] = default_history["statistics"][key]
                    
                    return loaded
                    
            except Exception as e:
                self.log_error(f"加载历史记录失败: {e}")
                return default_history
        
        return default_history
    
    def save_history(self, history: Dict[str, Any]) -> None:
        """保存历史记录"""
        try:
            with self.history_lock:
                # 确保目录存在
                self.history_file.parent.mkdir(parents=True, exist_ok=True)
                
                # 创建临时文件
                temp_file = f"{self.history_file}.tmp.{int(time.time())}.{os.getpid()}"
                
                with self._temp_files_lock:
                    self._temp_files.add(temp_file)
                
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(history, f, ensure_ascii=False, indent=2)
                
                # 原子性地替换原文件
                if self.history_file.exists():
                    os.replace(temp_file, self.history_file)
                else:
                    os.rename(temp_file, self.history_file)
                    
        except Exception as e:
            self.log_error(f"保存历史记录失败: {e}")
        finally:
            # 清理临时文件
            try:
                with self._temp_files_lock:
                    if temp_file in self._temp_files:
                        self._temp_files.remove(temp_file)
                if os.path.exists(temp_file):
                        os.remove(temp_file)
            except:
                pass
    
    def get_available_files(self) -> Tuple[List[str], Dict[str, Any], bool, Optional[str]]:
        """获取可用的文件列表"""
        history = self.load_history()
        
        opened_files = set(history.get("opened_files", []))
        failed_files = set(history.get("failed_files", []))
        
        all_qualified_files, success, error_msg = self.scan_qualified_files()
        
        if not success:
            return [], history, False, error_msg
        
        if not all_qualified_files:
            self.log_warning(f"在目录中未找到符合条件的文件: {self.script_dir}")
        
        available_files = []
        for filename in all_qualified_files:
            if filename in opened_files or filename in failed_files:
                continue
            available_files.append(filename)
        
        return available_files, history, True, None
    
    def _open_file_windows(self, filepath: Union[str, Path], filename: str) -> bool:
        """Windows系统下打开文件"""
        try:
            os.startfile(filepath)
            return True
        except OSError:
            try:
                # convert Path to str for subprocess
                subprocess.Popen(['start', '', str(filepath)], shell=True)
                return True
            except (OSError, subprocess.SubprocessError):
                pass
        
        return False
    
    def _open_file_macos(self, filepath: Union[str, Path], filename: str) -> bool:
        """macOS系统下打开文件"""
        try:
            subprocess.Popen(['open', str(filepath)])
            return True
        except (OSError, subprocess.SubprocessError):
            return False
    
    def _open_file_linux(self, filepath: Union[str, Path], filename: str) -> bool:
        """Linux系统下打开文件"""
        str_path = str(filepath)
        methods = [['xdg-open', str_path], ['gnome-open', str_path], ['kde-open', str_path]]
        
        for method in methods:
            try:
                result = subprocess.run(method, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if result.returncode == 0:
                    return True
            except (OSError, subprocess.SubprocessError):
                continue
        
        return False
    
    def open_file_with_retry(self, filename: str) -> bool:
        """尝试打开文件，支持重试"""
        filepath = self.script_dir / filename
        
        for attempt in range(self.config.max_retries):
            try:
                if attempt > 0:
                    self.log_message(f"重试打开文件: {filename} (第{attempt + 1}次)")
                
                system = platform.system()
                success = False
                
                if system == 'Windows':
                    success = self._open_file_windows(filepath, filename)
                elif system == 'Darwin':
                    success = self._open_file_macos(filepath, filename)
                else:
                    success = self._open_file_linux(filepath, filename)
                
                if success:
                    self.log_message(f"成功打开文件: {filename}")
                    return True
                
                if attempt < self.config.max_retries - 1:
                    time.sleep(0.3 * (attempt + 1))
                    
            except Exception as e:
                self.log_error(f"打开文件失败 ({filename}, 第{attempt + 1}次): {e}")
                if attempt < self.config.max_retries - 1:
                    time.sleep(0.3 * (attempt + 1))
        
        self.log_error(f"无法打开文件: {filename} (已尝试{self.config.max_retries}次)")
        return False
    
    def reset_history_if_needed(self, history: Dict[str, Any], available_files: List[str]) -> Tuple[List[str], Dict[str, Any]]:
        """如果需要，自动重置历史记录"""
        if not available_files:
            all_qualified_files, success, error_msg = self.scan_qualified_files(force_refresh=True)
            
            if not success:
                self.log_error(f"扫描目录失败，无法重置历史记录: {error_msg}")
                return available_files, history
            
            if all_qualified_files:
                self.log_message("所有文件都已打开过，自动重置历史记录")
                
                stats = history.get("statistics", {})
                stats["reset_count"] = stats.get("reset_count", 0) + 1
                stats["last_reset"] = datetime.now().isoformat()
                stats["total_resets"] = stats.get("total_resets", 0) + 1
                
                new_history = {
                    "opened_files": [],
                    "failed_files": [],
                    "file_signatures": {},
                    "statistics": stats
                }
                
                self.save_history(new_history)
                self.log_message(f"历史记录已重置 (第{stats['reset_count']}次重置)")
                
                with self.cache_lock:
                    self._qualified_files_cache = None
                
                self._file_hash_cache.clear()
                self._exclude_patterns_cache.clear()
                self._encoding_cache.clear()
                self._file_access_cache.clear()
                self._file_type_cache.clear()
                
                return all_qualified_files, new_history
            else:
                self.log_message("没有可用的文件")
        
        return available_files, history
    
    def show_statistics(self, history: Dict[str, Any]) -> None:
        """显示统计信息"""
        opened_files = history.get("opened_files", [])
        failed_files = history.get("failed_files", [])
        stats = history.get("statistics", {})
        
        opened_count = len(opened_files)
        failed_count = len(failed_files)
        
        all_qualified_files, success, _ = self.scan_qualified_files()
        
        if not success:
            self.log_error("无法获取统计信息")
            return
        
        total_count = len(all_qualified_files)
        
        opened_set = set(opened_files)
        failed_set = set(failed_files)
        processed_files = opened_set.union(failed_set)
        
        remaining_count = total_count - len(processed_files)
        
        run_time = time.time() - self.start_time
        
        self.log_message("=" * 60)
        self.log_message("统计信息")
        self.log_message("=" * 60)
        self.log_message(f"已成功打开文件数: {opened_count}")
        self.log_message(f"打开失败文件数: {failed_count}")
        self.log_message(f"目录中文件总数: {total_count}")
        self.log_message(f"剩余可打开文件数: {remaining_count}")
        self.log_message("-" * 60)
        self.log_message(f"累计成功打开: {stats.get('total_opened', 0)}")
        self.log_message(f"累计打开失败: {stats.get('total_failed', 0)}")
        self.log_message(f"总重置次数: {stats.get('total_resets', 0)}")
        self.log_message("-" * 60)
        self.log_message(f"程序运行时间: {run_time:.2f}秒")
        self.log_message(f"文件操作次数: {self.file_operations}")
        self.log_message(f"文件扫描次数: {self.total_files_scanned.get()}")
        self.log_message(f"文件排除次数: {self.total_files_excluded.get()}")
        
        if stats.get("last_opened_file"):
            self.log_message(f"上次打开文件: {stats['last_opened_file']}")
        
        self.log_message("=" * 60)
    
    def run(self) -> None:
        """主程序 - 自动随机打开文件"""
        try:
            self.log_message("=" * 60)
            self.log_message("随机文件打开器 - 自动模式")
            self.log_message("=" * 60)
            self.log_message(f"工作目录: {self.script_dir}")
            self.log_message(f"系统平台: {platform.system()} {platform.release()}")
            self.log_message(f"Python版本: {platform.python_version()}")
        except Exception as e:
            print(f"初始化日志失败: {e}")
        
        try:
            # 获取可用文件
            available_files, history, success, error_msg = self.get_available_files()
            
            if not success:
                self.log_error(f"无法获取可用文件: {error_msg}")
                self.log_message("程序无法继续执行")
                return
            
            # 如果没有可用文件，自动重置历史记录
            available_files, history = self.reset_history_if_needed(history, available_files)
            
            if not available_files:
                self.log_message("错误: 没有可用的文件可以打开")
                self.show_statistics(history)
                return
            
            # 随机选择一个文件
            selected_file = random.choice(available_files)
            self.log_message(f"随机选择文件: {selected_file}")
            
            # 尝试打开文件
            success = self.open_file_with_retry(selected_file)
            
            # 更新历史记录
            if success:
                opened_files = history.get("opened_files", [])
                if selected_file not in opened_files:
                    opened_files.append(selected_file)
                    history["opened_files"] = opened_files
                
                failed_files = history.get("failed_files", [])
                if selected_file in failed_files:
                    failed_files.remove(selected_file)
                    history["failed_files"] = failed_files
            else:
                failed_files = history.get("failed_files", [])
                if selected_file not in failed_files:
                    failed_files.append(selected_file)
                    history["failed_files"] = failed_files
                
                opened_files = history.get("opened_files", [])
                if selected_file in opened_files:
                    opened_files.remove(selected_file)
                    history["opened_files"] = opened_files
            
            # 更新统计信息
            stats = history.get("statistics", {})
            if success:
                stats["total_opened"] = stats.get("total_opened", 0) + 1
            else:
                stats["total_failed"] = stats.get("total_failed", 0) + 1
            
            stats["last_opened"] = datetime.now().isoformat()
            if success:
                stats["last_opened_file"] = selected_file
            history["statistics"] = stats
            
            # 保存历史记录
            self.save_history(history)
            
            # 显示统计信息
            self.show_statistics(history)
            
        except KeyboardInterrupt:
            self.log_message("程序被用户中断")
        except Exception as e:
            self.log_error(f"程序执行过程中发生未预期错误: {e}")
            import traceback
            self.log_error(traceback.format_exc())
        
        finally:
            self._cleanup_all_temp_files()
            
            fd_stats = self.fd_tracker.get_stats()
            if fd_stats['leaked'] > 0:
                self.log_warning(f"检测到可能的文件描述符泄漏: {fd_stats['leaked']}个未关闭")
            
            self.log_message("程序执行完成")
            self.log_message("=" * 60)


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="随机打开指定目录中的文件，确保不重复打开",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                    # 打开当前目录中的文件
  %(prog)s --dir /path/to/dir # 打开指定目录中的文件
        """
    )
    
    parser.add_argument(
        "--dir", "-d",
        type=str,
        help="要处理的目录路径（默认：程序所在目录）"
    )
    
    parser.add_argument(
        "--loglevel", "-l",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="日志级别 (默认: INFO)"
    )
    
    parser.add_argument(
        "--no-colors",
        action="store_true",
        help="禁用彩色输出"
    )
    
    parser.add_argument(
        "--no-console-log",
        action="store_true",
        help="禁用控制台日志输出"
    )
    
    parser.add_argument(
        "--wait-time",
        type=int,
        default=3,
        help="程序完成后的等待时间（秒）(默认: 3秒)"
    )
    
    parser.add_argument(
        "--show-config",
        action="store_true",
        help="显示当前配置"
    )
    
    parser.add_argument(
        "--reset-history",
        action="store_true",
        help="重置历史记录"
    )
    
    parser.add_argument(
        "--init-config",
        action="store_true",
        help="在当前目录生成默认配置文件"
    )

    parser.add_argument(
        "--register-menu",
        action="store_true",
        help="添加 Windows 右键菜单 (无需管理员权限)"
    )
    
    parser.add_argument(
        "--unregister-menu",
        action="store_true",
        help="移除 Windows 右键菜单"
    )

    parser.add_argument(
        "--count", "-n",
        type=int,
        default=1,
        help="一次打开的文件数量 (默认: 1)"
    )

    parser.add_argument(
        "--version",
        action="version",
        version="随机文件打开器 v1.6.6"
    )
    
    return parser.parse_args()


def manage_context_menu(action: str) -> None:
    """管理Windows右键菜单注册"""
    if platform.system() != "Windows":
        print("错误: 右键菜单功能仅支持 Windows 系统")
        return

    # 这里的逻辑是：
    # 1. 确定 EXE 路径
    if getattr(sys, 'frozen', False):
        exe_path = sys.executable
    else:
        # 如果是脚本运行，就用 python.exe 调用脚本
        # 注意：这在非打包环境下可能不稳定，但主要服务于 EXE
        exe_path = f'"{sys.executable}" "{Path(__file__).resolve()}"'

    menu_name = "🎲 随机打开文件"
    command = f'{exe_path} --dir "%V"'
    
    # 注册表路径 (HKCU 不需要管理员权限)
    # 1. Directory\shell (文件夹右键)
    # 2. Directory\Background\shell (文件夹空白处右键)
    keys = [
        r"Software\Classes\Directory\shell\RandomFileOpener",
        r"Software\Classes\Directory\Background\shell\RandomFileOpener"
    ]

    try:
        if action == "register":
            for key_path in keys:
                # 创建主键
                key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
                winreg.SetValue(key, "", winreg.REG_SZ, menu_name)
                winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, sys.executable if getattr(sys, 'frozen', False) else "shell32.dll,3")
                
                # 创建 command 子键
                cmd_key = winreg.CreateKey(key, "command")
                winreg.SetValue(cmd_key, "", winreg.REG_SZ, command)
                winreg.CloseKey(cmd_key)
                winreg.CloseKey(key)
            print(f"成功注册右键菜单: {menu_name}")
            print("现在您可以在任意文件夹上点击右键使用了。")
            
        elif action == "unregister":
            for key_path in keys:
                try:
                    # 递归删除比较麻烦，winreg没有DeleteKeyTree
                    # 这里必须先删 command 再删主键
                    try:
                        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path +r"\command")
                    except FileNotFoundError:
                        pass
                    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
                except FileNotFoundError:
                    pass
                except Exception as e:
                    print(f"删除注册表项 {key_path} 失败: {e}")
            print("已移除右键菜单。")
            
    except Exception as e:
        print(f"操作注册表失败: {e}")


def main() -> None:
    """程序入口点"""
    # 解析命令行参数
    args = parse_args()
    
    # -1. 处理右键菜单注册/注销
    if args.register_menu:
        manage_context_menu("register")
        sys.exit(0)
        
    if args.unregister_menu:
        manage_context_menu("unregister")
        sys.exit(0)
    
    # 0. 处理初始化配置请求
    if args.init_config:
        config_filename = Config().config_filename
        # 在当前工作目录生成
        target_path = Path.cwd() / config_filename
        
        try:
            if target_path.exists():
                print(f"配置文件已存在: {target_path}")
                overwrite = input("是否覆盖? (y/n): ").lower()
                if overwrite != 'y':
                    print("操作已取消")
                    sys.exit(0)
            
            default_config = Config().to_dict()
            with open(target_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, ensure_ascii=False, indent=4)
            print(f"成功生成默认配置文件: {target_path}")
            print("您可以修改此文件来自定义程序行为。")
        except Exception as e:
            print(f"生成配置文件失败: {e}")
        sys.exit(0)
    
    # 计算目标目录
    target_dir = args.dir
    if target_dir:
        target_dir = Path(target_dir).resolve()
    else:
        # 判断是否在打包环境(Frozen)下运行
        if getattr(sys, 'frozen', False):
            target_dir = Path(sys.executable).resolve().parent
        else:
            target_dir = Path(__file__).resolve().parent
        
    try:
        # 1. 初始默认配置
        config_dict = Config().to_dict()
        
        # 2. 如果存在配置文件，加载并覆盖
        # 使用Config类定义的默认配置文件名
        config_filename = Config().config_filename
        config_file_path = target_dir / config_filename
        if config_file_path.exists():
            try:
                with open(config_file_path, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                    config_dict.update(user_config)
                    # print(f"已加载配置文件: {config_file_path}")
            except Exception as e:
                print(f"加载配置文件失败: {e}")

        # 3. 应用CLI参数（如果有）
        if args.loglevel:
            config_dict['log_level'] = args.loglevel
            
        # 注意：这里处理布尔值有点棘手，因为argparse如果没传flag是默认值。
        # 我们假设CLI参数总是覆盖配置文件。
        # 如果用户想在配置文件里开启 enable_colors=True 但 CLI 传了 --no-colors，
        # args.no_colors 为 True。
        if args.no_colors:
            config_dict['enable_colors'] = False
        
        if args.no_console_log:
            config_dict['log_to_console'] = False

        # 创建最终配置对象
        config = Config.from_dict(config_dict)
        
        # 创建程序实例
        opener = RandomFileOpener(config, args.dir)
        
        # 显示配置
        if args.show_config:
            config_dict = config.to_dict()
            print("当前配置:")
            for key, value in config_dict.items():
                if isinstance(value, list):
                    if key in ["text_extensions", "system_executable_extensions", "exclude_patterns"]:
                        print(f"  {key}: [{', '.join(str(v) for v in value[:10])}... ({len(value)}个)]")
                    else:
                        print(f"  {key}: [{', '.join(str(v) for v in value)}]")
                else:
                    print(f"  {key}: {value}")
            return
        
        # 重置历史记录
        if args.reset_history:
            history = opener.load_history()
            stats = history.get("statistics", {})
            stats["reset_count"] = stats.get("reset_count", 0) + 1
            stats["last_reset"] = datetime.now().isoformat()
            stats["total_resets"] = stats.get("total_resets", 0) + 1
            
            new_history = {
                "opened_files": [],
                "failed_files": [],
                "file_signatures": {},
                "statistics": stats
            }
            
            opener.save_history(new_history)
            print("历史记录已重置")
            return
            
    except Exception as e:
        print(f"初始化程序失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    try:
        # 批量打开逻辑
        count = max(1, args.count)
        for i in range(count):
            if count > 1:
                print(f"\n[正在打开第 {i+1}/{count} 个文件]")
            
            opener.run()
            
            # 如果不是最后一个，且不是第一个，稍微等待一下避免系统卡顿
            if i < count - 1:
                time.sleep(0.5)
                
    except KeyboardInterrupt:
        print("\n程序被用户中断")
    except Exception as e:
        print(f"致命错误: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 等待退出
    try:
        wait_time = args.wait_time
        if wait_time > 0:
            print(f"\n将在{wait_time}秒后退出...")
            time.sleep(wait_time)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n程序已取消")
    except SystemExit as e:
        if e.code and e.code != 0:
             print(f"\n程序异常退出 (代码 {e.code})")
             input("按回车键退出...")
        raise
    except Exception as e:
        print(f"\n发生未预期的错误: {e}")
        traceback.print_exc()
        input("\n按回车键退出...")
        sys.exit(1)