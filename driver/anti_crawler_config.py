# === 反爬虫配置文件 ===
"""
反爬虫配置模块
包含浏览器指纹伪装、JavaScript 注入脚本、HTTP 头配置等
"""

import random
import os
import uuid
from typing import Dict, List, Optional, Any

from driver.user_agent import UserAgentGenerator


class AntiCrawlerConfig:
    """反爬虫配置管理类"""
    
    def __init__(self):
        self._ua_generator = UserAgentGenerator()
    
    # ========== HTTP 请求头配置 ==========
    
    HEADERS = {
        'accept': [
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8"
        ],
        'accept_language': [
            "zh-CN,zh;q=0.9,en;q=0.8",
            "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
            "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7"
        ]
    }
    
    # 时区配置
    TIMEZONES = [
        "Asia/Shanghai",
        "Asia/Beijing", 
        "Asia/Hong_Kong",
        "Asia/Taipei"
    ]
    
    # 语言配置
    LOCALES = [
        "zh-CN",
        "zh-TW", 
        "zh-HK"
    ]
    
    # ========== 配置生成方法 ==========
    
    def get_anti_crawler_config(self, mobile_mode: bool = False) -> Dict[str, Any]:
        """
        获取反爬虫配置（对应 PlaywrightController._get_anti_crawler_config）
        
        Args:
            mobile_mode: 是否为移动端模式
            
        Returns:
            Playwright context 配置字典
        """
        # 生成随机指纹
        fingerprint = self._generate_uuid()
        
        # 基础配置
        config = {
            "user_agent": self._ua_generator.get_realistic_user_agent(mobile_mode),
            "viewport": {
                "width": random.randint(1200, 1920) if not mobile_mode else 720,
                "height": random.randint(800, 1080) if not mobile_mode else 1920,
                "device_scale_factor": random.choice([1, 1.25, 1.5, 2])
            },
            "java_script_enabled": True,
            "ignore_https_errors": True,
            "bypass_csp": True,
            "extra_http_headers": self._get_http_headers(mobile_mode),
            "permissions": [],
        }
        
        # 移动端特殊配置
        if mobile_mode:
            config["extra_http_headers"].update({
                "User-Agent": config["user_agent"],
                "X-Requested-With": "com.tencent.mm"
            })
        
        return config
    
    def _get_http_headers(self, mobile_mode: bool = False) -> Dict[str, str]:
        """获取 HTTP 请求头"""
        headers = {
            "Accept": random.choice(self.HEADERS['accept']),
            "Accept-Language": random.choice(self.HEADERS['accept_language']),
            "Accept-Encoding": "gzip, deflate, br",
            # 注意：不能设置 Cache-Control 和 Upgrade-Insecure-Requests。
            # extra_http_headers 会作用于页面发出的所有请求（包括XHR），
            # 而真实浏览器只在页面导航请求上带这两个头；
            # 带上后 mp.weixin.qq.com 登录页初始化失败，
            # #app 一直保持 visibility:hidden，登录二维码无法加载
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }
        
        if mobile_mode:
            headers["X-Requested-With"] = "com.tencent.mm"
        
        return headers
    
    def _generate_uuid(self) -> str:
        """生成 UUID 指纹"""
        return str(uuid.uuid4()).replace("-", "")
    
    # ========== JavaScript 反爬虫脚本 ==========
    
    @staticmethod
    def get_init_script() -> str:
        """
        获取初始化注入脚本（对应 PlaywrightController._apply_anti_crawler_scripts 的 add_init_script）
        
        Returns:
            JavaScript 代码字符串
        """
        return """
        // ============================================================
        // Playwright 反检测增强脚本 - 针对主流检测网站优化
        // ============================================================

        // ========== 1. WebDriver 检测（关键！）==========
        // 多层防护：删除属性 + 重定义 getter
        delete Object.getPrototypeOf(navigator).webdriver;
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
            configurable: false,
            enumerable: true
        });
        
        // 防止通过原型链检测
        const originalGetOwnPropertyDescriptor = Object.getOwnPropertyDescriptor;
        Object.getOwnPropertyDescriptor = function(obj, prop) {
            if (prop === 'webdriver') {
                return undefined;
            }
            return originalGetOwnPropertyDescriptor.call(this, obj, prop);
        };

        // ========== 2. Navigator 属性完善 ==========
        // plugins - 模拟真实 Chrome 浏览器
        Object.defineProperty(navigator, 'plugins', {
            get: () => {
                const plugins = [
                    Object.create(Plugin.prototype, {
                        name: { value: 'PDF Viewer', enumerable: true },
                        description: { value: '', enumerable: true },
                        filename: { value: 'internal-pdf-viewer', enumerable: true },
                        length: { value: 1, enumerable: true },
                        item: { value: (i) => i === 0 ? { type: 'application/pdf', suffixes: 'pdf', description: '' } : null },
                        namedItem: { value: (name) => null }
                    }),
                    Object.create(Plugin.prototype, {
                        name: { value: 'Chrome PDF Plugin', enumerable: true },
                        description: { value: 'Portable Document Format', enumerable: true },
                        filename: { value: 'internal-pdf-viewer', enumerable: true },
                        length: { value: 1, enumerable: true },
                        item: { value: (i) => i === 0 ? { type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: 'Portable Document Format' } : null },
                        namedItem: { value: (name) => null }
                    }),
                    Object.create(Plugin.prototype, {
                        name: { value: 'Chromium PDF Plugin', enumerable: true },
                        description: { value: '', enumerable: true },
                        filename: { value: 'internal-pdf-viewer', enumerable: true },
                        length: { value: 1, enumerable: true },
                        item: { value: (i) => i === 0 ? { type: 'application/pdf', suffixes: 'pdf', description: '' } : null },
                        namedItem: { value: (name) => null }
                    })
                ];
                plugins.length = 3;
                plugins.item = (i) => plugins[i] || null;
                plugins.namedItem = (name) => plugins.find(p => p.name === name) || null;
                plugins.refresh = () => {};
                return plugins;
            },
            configurable: false,
            enumerable: true
        });

        // mimeTypes
        Object.defineProperty(navigator, 'mimeTypes', {
            get: () => {
                const mimeTypes = [
                    { type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format', enabledPlugin: { name: 'PDF Viewer' } },
                    { type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: 'Portable Document Format', enabledPlugin: { name: 'Chrome PDF Plugin' } }
                ];
                mimeTypes.length = 2;
                mimeTypes.item = (i) => mimeTypes[i] || null;
                mimeTypes.namedItem = (name) => mimeTypes.find(m => m.type === name) || null;
                return mimeTypes;
            },
            configurable: false,
            enumerable: true
        });

        // languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['zh-CN', 'zh', 'en-US', 'en'],
            configurable: false,
            enumerable: true
        });

        // platform
        Object.defineProperty(navigator, 'platform', {
            get: () => 'Win32',
            configurable: false,
            enumerable: true
        });

        // hardwareConcurrency
        Object.defineProperty(navigator, 'hardwareConcurrency', {
            get: () => 8,
            configurable: false,
            enumerable: true
        });

        // deviceMemory
        Object.defineProperty(navigator, 'deviceMemory', {
            get: () => 8,
            configurable: false,
            enumerable: true
        });

        // ========== 3. Chrome 对象检测 ==========
        // 添加 window.chrome 对象（Sannysoft 重点检测）
        if (!window.chrome) {
            window.chrome = {
                app: {
                    isInstalled: false,
                    InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
                    RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' }
                },
                runtime: {
                    OnInstalledReason: { CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update' },
                    OnRestartRequiredReason: { APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' },
                    PlatformArch: { ARM: 'arm', ARM64: 'arm64', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
                    PlatformNaclArch: { ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
                    PlatformOs: { ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' },
                    RequestUpdateCheckStatus: { NO_UPDATE: 'no_update', THROTTLED: 'throttled', UPDATE_AVAILABLE: 'update_available' },
                    connect: () => ({ onDisconnect: { addListener: () => {} }, onMessage: { addListener: () => {} }, postMessage: () => {} }),
                    sendMessage: () => {}
                },
                csi: () => ({ onloadT: Date.now(), pageT: Date.now(), startE: Date.now(), tran: 15 }),
                loadTimes: () => ({
                    requestTime: Date.now() / 1000,
                    startLoadTime: Date.now() / 1000,
                    commitLoadTime: Date.now() / 1000,
                    finishDocumentLoadTime: Date.now() / 1000,
                    finishLoadTime: Date.now() / 1000,
                    firstPaintTime: Date.now() / 1000,
                    firstPaintAfterLoadTime: 0,
                    navigationType: 'Other',
                    wasFetchedViaSpdy: true,
                    wasNpnNegotiated: true,
                    npnNegotiatedProtocol: 'h2',
                    wasAlternateProtocolAvailable: false,
                    connectionInfo: 'h2'
                })
            };
        }

        // ========== 4. Permissions API 修复 ==========
        const originalPermissionsQuery = navigator.permissions.query.bind(navigator.permissions);
        navigator.permissions.query = (parameters) => {
            if (parameters.name === 'notifications') {
                return Promise.resolve({ state: Notification.permission, onchange: null });
            }
            if (parameters.name === 'geolocation') {
                return Promise.resolve({ state: 'prompt', onchange: null });
            }
            if (parameters.name === 'camera' || parameters.name === 'microphone') {
                return Promise.resolve({ state: 'prompt', onchange: null });
            }
            return originalPermissionsQuery(parameters);
        };

        // ========== 5. iframe contentWindow 检测修复 ==========
        const originalContentWindow = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'contentWindow');
        Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
            get: function() {
                const window = originalContentWindow.get.call(this);
                if (window) {
                    try {
                        Object.defineProperty(window.navigator, 'webdriver', { get: () => undefined });
                    } catch (e) {}
                }
                return window;
            }
        });

        // ========== 6. window.external 检测 ==========
        Object.defineProperty(window, 'external', {
            get: () => ({
                AddSearchProvider: () => {},
                IsSearchProviderInstalled: () => 0,
                addSearchEngine: () => {}
            }),
            configurable: false
        });

        // ========== 7. WebGL 指纹伪装 ==========
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            // UNMASKED_VENDOR_WEBGL
            if (parameter === 37445) return 'Google Inc. (NVIDIA)';
            // UNMASKED_RENDERER_WEBGL
            if (parameter === 37446) return 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)';
            // MAX_TEXTURE_SIZE
            if (parameter === 3379) return 16384;
            // MAX_VERTEX_TEXTURE_IMAGE_UNITS
            if (parameter === 35660) return 16;
            return getParameter.apply(this, arguments);
        };

        if (typeof WebGL2RenderingContext !== 'undefined') {
            const getParameter2 = WebGL2RenderingContext.prototype.getParameter;
            WebGL2RenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Google Inc. (NVIDIA)';
                if (parameter === 37446) return 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)';
                if (parameter === 3379) return 16384;
                if (parameter === 35660) return 16;
                return getParameter2.apply(this, arguments);
            };
        }

        // ========== 8. Canvas 指纹防护 ==========
        const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function(type) {
            // 添加细微噪声
            const context = this.getContext('2d');
            if (context && this.width > 0 && this.height > 0) {
                try {
                    const imageData = context.getImageData(0, 0, this.width, this.height);
                    for (let i = 0; i < imageData.data.length; i += 4) {
                        imageData.data[i] = imageData.data[i] ^ (Math.random() * 1.5);
                    }
                    context.putImageData(imageData, 0, 0);
                } catch (e) {}
            }
            return originalToDataURL.apply(this, arguments);
        };

        // Canvas getImageData 伪装
        const originalGetImageData = CanvasRenderingContext2D.prototype.getImageData;
        CanvasRenderingContext2D.prototype.getImageData = function(x, y, w, h) {
            const imageData = originalGetImageData.apply(this, arguments);
            // 添加噪声
            for (let i = 0; i < imageData.data.length; i += 4) {
                imageData.data[i] = imageData.data[i] ^ (Math.random() * 1.5);
            }
            return imageData;
        };

        // ========== 9. AudioContext 指纹防护 ==========
        const audioContext = window.AudioContext || window.webkitAudioContext;
        if (audioContext) {
            const originalCreateAnalyser = audioContext.prototype.createAnalyser;
            audioContext.prototype.createAnalyser = function() {
                const analyser = originalCreateAnalyser.apply(this, arguments);
                const originalGetFloatFrequencyData = analyser.getFloatFrequencyData.bind(analyser);
                analyser.getFloatFrequencyData = function(array) {
                    originalGetFloatFrequencyData(array);
                    for (let i = 0; i < array.length; i++) {
                        array[i] += (Math.random() - 0.5) * 0.0001;
                    }
                };
                return analyser;
            };
        }

        // ========== 10. 字体指纹防护 ==========
        const originalMeasureText = CanvasRenderingContext2D.prototype.measureText;
        CanvasRenderingContext2D.prototype.measureText = function(text) {
            const result = originalMeasureText.apply(this, arguments);
            Object.defineProperty(result, 'width', {
                get: () => originalMeasureText.apply(this, arguments).width + (Math.random() * 0.0001)
            });
            return result;
        };

        // ========== 11. WebRTC 禁用（防止 IP 泄露）==========
        if (window.RTCPeerConnection) {
            window.RTCPeerConnection = undefined;
        }
        if (window.webkitRTCPeerConnection) {
            window.webkitRTCPeerConnection = undefined;
        }
        if (window.mozRTCPeerConnection) {
            window.mozRTCPeerConnection = undefined;
        }

        // ========== 12. Battery API 伪装 ==========
        if (navigator.getBattery) {
            const originalGetBattery = navigator.getBattery.bind(navigator);
            navigator.getBattery = () => Promise.resolve({
                charging: true,
                chargingTime: 0,
                dischargingTime: Infinity,
                level: 1,
                addEventListener: () => {},
                removeEventListener: () => {},
                dispatchEvent: () => true
            });
        }

        // ========== 13. Network Information API ==========
        if (navigator.connection) {
            Object.defineProperty(navigator, 'connection', {
                get: () => ({
                    effectiveType: '4g',
                    downlink: 10,
                    rtt: 50,
                    saveData: false,
                    type: 'wifi',
                    addEventListener: () => {},
                    removeEventListener: () => {},
                    dispatchEvent: () => true
                }),
                configurable: false
            });
        }

        // ========== 14. 自动化框架痕迹清除 ==========
        const propsToDelete = [
            '__playwright', '__puppeteer', '__selenium', '__webdriver_evaluate',
            '__selenium_evaluate', '__fxdriver_evaluate', '__driver_unwrapped',
            '__webdriver_unwrapped', '__selenium_unwrapped', '__fxdriver_unwrapped',
            '__webdriver_script_function', '__webdriver_script_func', '__webdriver_script_fn',
            '__nightmare', '__phantomas', '__bugzilla', '__driver_evaluate',
            'cdc_adoQpoasnfa76pfcZLmcfl_Array', 'cdc_adoQpoasnfa76pfcZLmcfl_Promise',
            'cdc_adoQpoasnfa76pfcZLmcfl_Symbol', 'cdc_adoQpoasnfa76pfcZLmcfl_JSON',
            'cdc_adoQpoasnfa76pfcZLmcfl_Object', 'callPhantom', '_phantom',
            '_phantomas', 'nightmare', 'domAutomation', 'domAutomationController'
        ];
        
        propsToDelete.forEach(prop => {
            try {
                delete window[prop];
                delete document[prop];
            } catch (e) {}
        });

        // ========== 15. Function.toString 检测防护 ==========
        const oldToString = Function.prototype.toString;
        Function.prototype.toString = function() {
            if (this === navigator.permissions.query) {
                return 'function query() { [native code] }';
            }
            return oldToString.call(this);
        };

        // ========== 16. Error 堆栈伪装 ==========
        Error.stackTraceLimit = 10;
        const originalErrorToString = Error.prototype.toString;
        Error.prototype.toString = function() {
            const stack = this.stack;
            if (stack && stack.includes('playwright')) {
                this.stack = stack.replace(/playwright/g, 'chrome');
            }
            return originalErrorToString.call(this);
        };

        // ========== 17. console 检测防护 ==========
        const originalConsoleDebug = console.debug;
        console.debug = function() {
            if (arguments[0] && arguments[0].toString().includes('webdriver')) {
                return;
            }
            return originalConsoleDebug.apply(console, arguments);
        };

        // ========== 18. timezone 伪装 ==========
        const originalDateTimeFormat = Intl.DateTimeFormat;
        Intl.DateTimeFormat = function(locale, options) {
            if (options && options.timeZone) {
                options.timeZone = 'Asia/Shanghai';
            }
            return new originalDateTimeFormat(locale, options);
        };
        Intl.DateTimeFormat.prototype = originalDateTimeFormat.prototype;

        // ========== 19. screen 属性伪装 ==========
        Object.defineProperty(screen, 'colorDepth', { get: () => 24 });
        Object.defineProperty(screen, 'pixelDepth', { get: () => 24 });
        
        // ========== 20. Notification 权限伪装 ==========
        if (window.Notification) {
            Object.defineProperty(Notification, 'permission', {
                get: () => 'default',
                configurable: true
            });
        }

        // ========== 21. 鼠标移动模拟 ==========
        let mousePositions = [];
        document.addEventListener('mousemove', (e) => {
            mousePositions.push({ x: e.clientX, y: e.clientY, time: Date.now() });
            if (mousePositions.length > 100) mousePositions.shift();
        });

        console.log('[反检测] 增强版用户特征保护已启用');
        """
    
    @staticmethod
    def get_behavior_script() -> str:
        """
        获取浏览器行为模拟脚本（对应 PlaywrightController._apply_anti_crawler_scripts 的 evaluate）
        
        Returns:
            JavaScript 代码字符串
        """
        return """
        // 随机延迟点击事件
        const originalAddEventListener = EventTarget.prototype.addEventListener;
        EventTarget.prototype.addEventListener = function(type, listener, options) {
            if (type === 'click') {
                const wrappedListener = function(...args) {
                    setTimeout(() => listener.apply(this, args), Math.random() * 100 + 50);
                };
                return originalAddEventListener.call(this, type, wrappedListener, options);
            }
            return originalAddEventListener.call(this, type, listener, options);
        };
        
        // 随机化鼠标移动
        document.addEventListener('mousemove', (e) => {
            if (Math.random() > 0.7) {
                e.stopImmediatePropagation();
            }
        }, true);
        """
    
    # ========== 视口配置 ==========
    
    @staticmethod
    def get_viewport(mobile_mode: bool = False) -> Dict[str, int]:
        """获取视口配置"""
        if mobile_mode:
            return {"width": 375, "height": 812}
        return {
            "width": random.randint(1200, 1920),
            "height": random.randint(800, 1080)
        }
    
    @staticmethod
    def get_device_scale_factor() -> float:
        """获取设备缩放因子"""
        return random.choice([1.0, 1.25, 1.5, 2.0])


# 环境变量配置
ENV_CONFIG = {
    "ENABLE_STEALTH": os.getenv("ENABLE_STEALTH", "true").lower() == "true",
    "ENABLE_BEHAVIOR_SIMULATION": os.getenv("ENABLE_BEHAVIOR_SIMULATION", "true").lower() == "true",
    "ENABLE_ADVANCED_DETECTION": os.getenv("ENABLE_ADVANCED_DETECTION", "true").lower() == "true",
    "DETECTION_SENSITIVITY": float(os.getenv("DETECTION_SENSITIVITY", "0.8")),
    "MAX_DETECTION_ATTEMPTS": int(os.getenv("MAX_DETECTION_ATTEMPTS", "10")),
    "BEHAVIOR_SIMULATION_INTERVAL": int(os.getenv("BEHAVIOR_SIMULATION_INTERVAL", "2000")),
    "RANDOM_DELAY_MIN": int(os.getenv("RANDOM_DELAY_MIN", "100")),
    "RANDOM_DELAY_MAX": int(os.getenv("RANDOM_DELAY_MAX", "500"))
}


# 全局实例
_anti_crawler_config = AntiCrawlerConfig()


def get_anti_crawler_config(mobile_mode: bool = False) -> Dict[str, Any]:
    """获取反爬虫配置（便捷函数）"""
    return _anti_crawler_config.get_anti_crawler_config(mobile_mode)


def get_init_script() -> str:
    """获取初始化注入脚本（便捷函数）"""
    return AntiCrawlerConfig.get_init_script()


def get_behavior_script() -> str:
    """获取行为模拟脚本（便捷函数）"""
    return AntiCrawlerConfig.get_behavior_script()
