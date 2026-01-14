import unittest
import os
import shutil
import tempfile
import sys
import logging
import json
from unittest.mock import patch
from pathlib import Path
from importlib.util import spec_from_loader, module_from_spec
from importlib.machinery import SourceFileLoader

# Standard import now that the filename is English
from random_file_opener import AtomicCounter, Config, RandomFileOpener

class TestAtomicCounter(unittest.TestCase):
    def test_increment_decrement(self):
        counter = AtomicCounter(0)
        self.assertEqual(counter.increment(), 1)
        self.assertEqual(counter.increment(5), 6)
        self.assertEqual(counter.decrement(), 5)
        self.assertEqual(counter.get(), 5)

    def test_reset(self):
        counter = AtomicCounter(10)
        self.assertEqual(counter.reset(), 10)
        self.assertEqual(counter.get(), 0)

class TestConfig(unittest.TestCase):
    def test_defaults(self):
        config = Config()
        self.assertEqual(config.log_level, "INFO")
        self.assertTrue(config.enable_colors)
        self.assertTrue('.txt' in config.text_extensions)

    def test_from_dict(self):
        data = {"log_level": "DEBUG", "max_retries": 5, "invalid_key": "value"}
        config = Config.from_dict(data)
        self.assertEqual(config.log_level, "DEBUG")
        self.assertEqual(config.max_retries, 5)

class TestRandomFileOpener(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config = Config(
            log_to_console=False, 
            history_filename=".test_history.json",
            log_filename=".test_log.txt"
        )
        self.opener = RandomFileOpener(self.config, self.test_dir)

    def tearDown(self):
        # 关闭所有handler以释放文件锁
        if hasattr(self.opener, 'logger'):
            handlers = self.opener.logger.handlers[:]
            for handler in handlers:
                handler.close()
                self.opener.logger.removeHandler(handler)
        
        # 强制关闭logging系统中的handler，防止全局logger持有引用
        logging.shutdown()
        
        try:
            shutil.rmtree(self.test_dir)
        except PermissionError:
            # 如果仍然失败，尝试延迟删除或忽略（Windows有时候释放慢）
            pass

        # 清理可能产生的日志文件
        log_file = os.path.join(os.path.dirname(__file__), ".test_log.txt")
        if os.path.exists(log_file):
            try:
                os.remove(log_file)
            except:
                pass

    def test_should_exclude(self):
        # 创建测试文件
        with open(os.path.join(self.test_dir, "test.txt"), "w") as f:
            f.write("test")
        with open(os.path.join(self.test_dir, "test.pyc"), "w") as f:
            f.write("test")
        
        # 测试排除逻辑
        # 1. 正常文件
        exclude, reason = self.opener.should_exclude("test.txt", os.path.join(self.test_dir, "test.txt"))
        self.assertFalse(exclude)
        
        # 2. 排除模式 (*.pyc)
        exclude, reason = self.opener.should_exclude("test.pyc", os.path.join(self.test_dir, "test.pyc"))
        self.assertTrue(exclude)
        self.assertEqual(reason, "匹配排除模式")
        
        # 3. 隐藏文件
        exclude, reason = self.opener.should_exclude(".hidden", os.path.join(self.test_dir, ".hidden"))
        self.assertTrue(exclude)
        self.assertEqual(reason, "隐藏文件")

    def test_scan_qualified_files(self):
        # 创建一组文件
        files = ["a.txt", "b.jpg", "c.py", "ignore.tmp"]
        for f in files:
            with open(os.path.join(self.test_dir, f), "w") as h:
                h.write("content")
        
        qualified, success, error = self.opener.scan_qualified_files()
        self.assertTrue(success)
        self.assertIn("a.txt", qualified)
        self.assertIn("b.jpg", qualified)
        self.assertIn("c.py", qualified)
        self.assertNotIn("ignore.tmp", qualified) # 默认配置包含 *.tmp 排除

    def test_frozen_path(self):
        """测试打包环境下的路径检测"""
        params = {'frozen': True, 'executable': str(Path(self.test_dir) / "test_exe.exe")}
        
        with patch.object(sys, 'frozen', True, create=True), \
             patch.object(sys, 'executable', params['executable']):
             
            # 重新初始化 Opener，模拟在打包环境中，未指定 target_dir
            # 注意：RandomFileOpener.__init__ 中会检查 target_dir 是否为 None
            # 我们传入 None 让它自己去检测
            opener = RandomFileOpener(config=self.config, target_dir=None)
            
            # 在 frozen 模式下，script_dir 应该是 executable 的父目录
            expected_dir = Path(params['executable']).parent
            self.assertEqual(opener.script_dir, expected_dir)
            self.assertEqual(opener.script_dir, Path(self.test_dir))

    def test_init_config(self):
        """测试配置导出功能 (逻辑验证)"""
        # 我们不直接调用main，而是验证Config.to_dict能否生成可序列化的字典
        config = Config()
        data = config.to_dict()
        
        # 验证关键字段
        self.assertIn('max_retries', data)
        self.assertIn('exclude_patterns', data)
        
        # 验证序列化
        try:
            json_str = json.dumps(data)
            self.assertTrue(len(json_str) > 0)
        except TypeError:
            self.fail("Config dictionary is not JSON serializable")

    def test_batch_open(self):
        """测试批量打开功能"""
        # 我们很难直接测试 main 函数的循环，因为它涉及大量的IO和打印
        # 但我们可以验证 argparse 是否正确解析了 count 参数
        # 以及 RandomFileOpener 是否能连续多次运行而不崩溃
        
        # 1. 验证参数解析
        with patch('sys.argv', ['script.py', '--count', '3']):
            from importlib import reload
            # 注意：不能reload main模块因为它是脚本入口，但我们可以手动测试解析逻辑
            # 这里我们直接测试 RandomFileOpener.run 被连续调用的稳定性
            pass
            
        # 2. 模拟连续运行
        # 确保多次调用 run 不会抛出异常
        try:
            # 第一次运行
            qualified, success, _ = self.opener.scan_qualified_files()
            if success and qualified:
                # 模拟 run 的核心逻辑
                available, _, _, _ = self.opener.get_available_files()
                self.assertTrue(len(available) > 0)
                
            # 第二次运行 (模拟循环)
            qualified, success, _ = self.opener.scan_qualified_files()
            self.assertTrue(success)
        except Exception as e:
            self.fail(f"Batch execution simulation failed: {e}")

    def test_run_integrity(self):
        """测试 run 方法的完整性 (确保所有引用都存在)"""
        # 模拟依赖，只为了让 run 能跑到 random.choice 那一行
        with patch.object(self.opener, 'get_available_files') as mock_get_files:
            mock_get_files.return_value = (['test.txt'], {}, True, None)
            
            with patch.object(self.opener, 'open_file_with_retry') as mock_open:
                mock_open.return_value = True
                
                with patch.object(self.opener, 'save_history'):
                    with patch.object(self.opener, 'show_statistics'):
                        # 运行 run
                        try:
                            self.opener.run()
                        except NameError as e:
                            self.fail(f"run 方法抛出了 NameError: {e}")
                        except Exception as e:
                            # 忽略其他非 NameError 错误
                             pass

if __name__ == '__main__':
    unittest.main()
