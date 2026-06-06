import yaml
import sys
import os
import argparse
from string import Template
from dotenv import load_dotenv
from core.print import print_warning, print_error,print_info
from .file import FileCrypto

load_dotenv()
class Config: 
    config_path=""
    config={}
    _config_cache = None  # 添加缓存变量
    def __init__(self, config_path=None, encrypt=False):
        self.args = self.parse_args()
        self.config_path = config_path or self.args.config

        # 确保目录存在
        if os.path.dirname(self.config_path) != "":
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        # 加密相关配置
        self.encryption_enabled = encrypt
        self.get_config()
        # 初始化加密设置
        self._init_encryption()
        
    def _init_encryption(self):
        """初始化加密设置"""
        key = os.getenv('ENCRYPTION_KEY', 'store.csol.store.werss')  # 默认密钥
        if self.encryption_enabled:
            try:
                self.crypto = FileCrypto(key)
            except Exception as e:
                print(f"加密初始化失败: {e}")
                self.encryption_enabled = False
    def parse_args(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('-config', help='配置文件', default='config.yaml')
        parser.add_argument('-job', help='启动任务', default=False)
        parser.add_argument('-init', help='初始化数据库,初始化用户', default=False)
        args, _ = parser.parse_known_args()
        return args
    def _encrypt(self, data):
        """加密数据"""
        if not self.encryption_enabled or not hasattr(self, 'crypto'):
            return data
        try:
            if isinstance(data, str):
                return self.crypto.encrypt(data.encode('utf-8')).decode('utf-8')
            return self.crypto.encrypt(data).decode('utf-8')
        except Exception as e:
            print(f"加密失败: {e}")
            return data

    def _decrypt(self, data):
        """解密数据"""
        if not self.encryption_enabled or not hasattr(self, 'crypto'):
            return data
        try:
            if isinstance(data, str):
                return self.crypto.decrypt(data.encode('utf-8')).decode('utf-8')
            return self.crypto.decrypt(data).decode('utf-8')
        except Exception as e:
            print(f"解密失败: {e}")
            return data  # 解密失败返回原始数据

    def save_config(self):
        config_to_save = self.config.copy()
        try:
                # 生成YAML内容
                yaml_content = yaml.dump(config_to_save)
                # 验证YAML格式是否合法
                try:
                    yaml.safe_load(yaml_content)
                except yaml.YAMLError as ye:
                    print_error(f"YAML格式验证失败: {ye}")
                    raise
                # 加密整个YAML内容
                encrypted_content = self._encrypt(yaml_content)
                # 直接写入临时文件，然后重命名（Windows下更安全的替换方式）
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    f.write(encrypted_content)
                self.reload()
             
        except Exception as e:
            print_error(f"保存配置文件失败: {e}")
            raise
    def replace_env_vars(self,data):
            if isinstance(data, dict):
                return {k: self.replace_env_vars(v) for k, v in data.items()}
            elif isinstance(data, list):
                return [self.replace_env_vars(item) for item in data]
            elif isinstance(data, str):
                try:
                    import re
                    # 匹配 ${VAR:-default} 或 ${VAR} 格式
                    pattern = re.compile(r'\$\{([^}:]+)(?::-([^}]*))?\}')
                    def replace_match(match):
                        var_name = match.group(1)
                        default_value = match.group(2)
                        return os.getenv(var_name, default_value) if default_value is not None else os.getenv(var_name, '')
                    return pattern.sub(replace_match, data)
                except:
                    return data
            return data
    def get_config(self):
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
                if self.encryption_enabled:
                    try:
                        # 尝试解密整个文件内容
                        decrypted_content = self._decrypt(content)
                        config = yaml.safe_load(decrypted_content)
                    except Exception as e:
                        print(f"解密配置文件失败: {e}")
                        sys.exit(1)
                else:
                    config = yaml.safe_load(content)
                
                if config is None:
                    config = {}
                
                self.config = config
                self._config = self.replace_env_vars(config)
               
                return self.config
        except Exception as e:
            print_error(f"加载配置文件 {self.config_path} 错误: {e}")
            # sys.exit(1)
    def reload(self):
        self.config=self.get_config()
    def set(self,key,default:any=None):
        self.config[key] = default
        self.save_config()
    def __fix(self,v:str):
        if v in ("", "''", '""', None):
            return ""
        try:
            # 尝试转换为布尔值
            if v.lower() in ('true', 'false'):
                return v.lower() == 'true'
            # 尝试转换为整数
            if v.isdigit():
                return int(v)
            # 尝试转换为浮点数
            if '.' in v and all(part.isdigit() for part in v.split('.') if part):
                return float(v)
            return v
        except:
            return v
    def get(self,key,default:any=None):
        _config=self.replace_env_vars(self.config)
        
        # 支持嵌套key访问
        keys = key.split('.') if isinstance(key, str) else [key]
        value = _config
        try:
            for k in keys:
                value = value[k]
            val=self.__fix(value)
            if val is None and default is not None  :
                return default
            else:
                return val
        except (KeyError, TypeError):
            # print_warning("Key {} not found in configuration".format(key))
            pass
        return default 

cfg=Config()
def set_config(key:str,value:str):
    cfg.set(key,value)
def save_config():
    cfg.save_config()
    
DEBUG=cfg.get("debug",False)
APP_NAME=cfg.get("app_name","we-mp-rss")
from core.base import *
print(f"名称:{APP_NAME}\n版本:{VERSION} API_BASE:{API_BASE}")