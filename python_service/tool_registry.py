"""
用户自定义工具注册系统
支持三种注入方式：
1. Tool（直接可调用的Python函数）
2. MCP Server（远程工具服务器）
3. Skill（完整的功能包）
"""

import os
import json
import uuid
import asyncio
import hashlib
from pathlib import Path
from typing import Any, Callable, Optional
from dataclasses import dataclass, field, asdict
from concurrent.futures import ThreadPoolExecutor
import importlib.util

# ============================================================================
# Paths
# ============================================================================

TOOLS_DIR = Path(os.getenv("MEMORY_DIR", "./memory")) / "user_tools"
TOOLS_DIR.mkdir(parents=True, exist_ok=True)

REGISTRY_PATH = TOOLS_DIR / "tool_registry.json"
MCP_CONFIG_PATH = TOOLS_DIR / "mcp_config.json"
SKILLS_CONFIG_PATH = TOOLS_DIR / "skills.json"

# ============================================================================
# Data Models
# ============================================================================


@dataclass
class ToolDef:
    """用户定义的工具"""
    id: str                        # 唯一ID
    name: str                      # 工具名称（英文，用于代码调用）
    display_name: str              # 显示名称（中文，用户友好）
    description: str               # 功能描述
    category: str                  # 分类：web/data/file/communication/ai/utility
    icon: str = "🔧"             # 图标
    enabled: bool = True           # 是否启用
    secret_keys: list[str] = field(default_factory=list)  # 需要的密钥名称列表
    config_schema: dict = field(default_factory=dict)    # 配置JSON Schema
    code: str = ""                # Python函数代码（可选）
    is_builtin: bool = False      # 是否内置


@dataclass
class MCPServer:
    """MCP Server 配置"""
    id: str
    name: str
    command: str                  # 启动命令，如 "npx" / "python"
    description: str = ""          # 描述
    enabled: bool = True           # 是否启用
    args: list[str] = field(default_factory=list)  # 命令行参数
    env: dict = field(default_factory=dict)        # 环境变量（含密钥）
    url: str = ""                 # HTTP MCP Server URL（可选）


@dataclass
class SkillDef:
    """Skill/Agent 配置"""
    id: str
    name: str
    description: str
    enabled: bool = True
    repo_url: str = ""            # Git repo URL
    install_command: str = ""      # 安装命令
    config: dict = field(default_factory=dict)   # 技能配置


# ============================================================================
# Tool Registry
# ============================================================================

class ToolRegistry:
    """用户工具注册表"""

    def __init__(self):
        self.tools: dict[str, ToolDef] = {}
        self.mcp_servers: dict[str, MCPServer] = {}
        self.skills: dict[str, SkillDef] = {}
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._tool_modules: dict[str, Any] = {}
        self._load_all()

    # -------------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------------

    def _load_all(self) -> None:
        self.tools = self._load_registry(REGISTRY_PATH, ToolDef)
        self.mcp_servers = self._load_registry(MCP_CONFIG_PATH, MCPServer)
        self.skills = self._load_registry(SKILLS_CONFIG_PATH, SkillDef)

    def _load_registry(self, path: Path, cls: type):
        if path.exists():
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return {k: cls(**v) for k, v in data.items()}
        return {}

    def _save_registry(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({k: asdict(v) for k, v in data.items()}, f, ensure_ascii=False, indent=2)

    # -------------------------------------------------------------------------
    # Tool CRUD
    # -------------------------------------------------------------------------

    def register_tool(self, tool: ToolDef) -> str:
        tool.id = tool.id or hashlib.md5(tool.name.encode()).hexdigest()[:12]
        self.tools[tool.id] = tool
        self._save_registry(REGISTRY_PATH, self.tools)
        if tool.code:
            self._compile_tool(tool)
        return tool.id

    def unregister_tool(self, tool_id: str) -> bool:
        if tool_id in self.tools:
            del self.tools[tool_id]
            self._save_registry(REGISTRY_PATH, self.tools)
            self._tool_modules.pop(tool_id, None)
            return True
        return False

    def get_tool(self, tool_id: str) -> Optional[ToolDef]:
        return self.tools.get(tool_id)

    def list_tools(self, category: str = None, enabled_only: bool = True) -> list[ToolDef]:
        result = self.tools.values()
        if enabled_only:
            result = [t for t in result if t.enabled]
        if category:
            result = [t for t in result if t.category == category]
        return sorted(result, key=lambda t: t.name)

    def set_tool_enabled(self, tool_id: str, enabled: bool) -> None:
        if tool_id in self.tools:
            self.tools[tool_id].enabled = enabled
            self._save_registry(REGISTRY_PATH, self.tools)

    def call_tool(self, tool_id: str, params: dict, session_id: str = None) -> Any:
        """调用用户工具（在线程池中执行）"""
        tool = self.tools.get(tool_id)
        if not tool or not tool.enabled:
            raise ValueError(f"Tool not found or disabled: {tool_id}")

        mod = self._tool_modules.get(tool_id)
        if not mod:
            raise ValueError(f"Tool not compiled: {tool_id}")

        func = getattr(mod, tool.name, None)
        if not func:
            raise ValueError(f"Function {tool.name} not found in tool module")

        # Inject session context if function accepts it
        import inspect
        sig = inspect.signature(func)
        kwargs = dict(params)
        if "session_id" in sig.parameters:
            kwargs["session_id"] = session_id

        loop = asyncio.new_event_loop()
        try:
            if inspect.iscoroutinefunction(func):
                return loop.run_until_complete(func(**kwargs))
            else:
                future = self._executor.submit(func, **kwargs)
                return future.result(timeout=30)
        finally:
            loop.close()

    def _compile_tool(self, tool: ToolDef) -> None:
        """将工具代码字符串编译为可导入的模块"""
        try:
            spec = importlib.util.spec_from_loader(
                f"user_tool_{tool.id}",
                loader=None,
            )
            mod = importlib.util.module_from_spec(spec)
            exec(tool.code, mod.__dict__)
            self._tool_modules[tool.id] = mod
        except Exception as e:
            print(f"[ToolRegistry] Failed to compile tool {tool.id}: {e}")

    # -------------------------------------------------------------------------
    # MCP Server
    # -------------------------------------------------------------------------

    def register_mcp(self, server: MCPServer) -> str:
        server.id = server.id or hashlib.md5(server.name.encode()).hexdigest()[:12]
        self.mcp_servers[server.id] = server
        self._save_registry(MCP_CONFIG_PATH, self.mcp_servers)
        return server.id

    def unregister_mcp(self, server_id: str) -> bool:
        if server_id in self.mcp_servers:
            del self.mcp_servers[server_id]
            self._save_registry(MCP_CONFIG_PATH, self.mcp_servers)
            return True
        return False

    def list_mcp_servers(self, enabled_only: bool = True) -> list[MCPServer]:
        result = self.mcp_servers.values()
        if enabled_only:
            result = [s for s in result if s.enabled]
        return sorted(result, key=lambda s: s.name)

    # -------------------------------------------------------------------------
    # Skills
    # -------------------------------------------------------------------------

    def register_skill(self, skill: SkillDef) -> str:
        skill.id = skill.id or hashlib.md5(skill.name.encode()).hexdigest()[:12]
        self.skills[skill.id] = skill
        self._save_registry(SKILLS_CONFIG_PATH, self.skills)
        return skill.id

    def unregister_skill(self, skill_id: str) -> bool:
        if skill_id in self.skills:
            del self.skills[skill_id]
            self._save_registry(SKILLS_CONFIG_PATH, self.skills)
            return True
        return False

    def list_skills(self, enabled_only: bool = True) -> list[SkillDef]:
        result = self.skills.values()
        if enabled_only:
            result = [s for s in result if s.enabled]
        return sorted(result, key=lambda s: s.name)

    # -------------------------------------------------------------------------
    # Preset Built-in Tools (zero-code helpers)
    # -------------------------------------------------------------------------

    def register_preset_tools(self) -> None:
        """注册一组开箱即用的预设工具"""
        presets = [
            ToolDef(
                id="calc",
                name="calculator",
                display_name="计算器",
                description="执行数学计算，支持加减乘除、指数、对数、三角函数等",
                category="utility",
                icon="🧮",
                code="""
def calculator(expression: str) -> str:
    try:
        import math
        result = eval(expression, {"__builtins__": {}, "math": math})
        return str(result)
    except Exception as e:
        return f"计算错误: {e}"
""",
            ), ToolDef(
                id="hash",
                name="text_hash",
                display_name="文本哈希",
                description="计算文本的MD5/SHA256哈希值",
                category="utility",
                icon="🔐",
                code="""
import hashlib

def text_hash(text: str, algorithm: str = "sha256") -> str:
    h = hashlib.new(algorithm)
    h.update(text.encode())
    return h.hexdigest()
""",
            ),
            ToolDef(
                id="sentiment",
                name="simple_sentiment",
                display_name="简易情感分析",
                description="对中文文本进行情感打分（正面/负面/中性），返回0-1之间的分数",
                category="ai",
                icon="💬",
                code="""
def simple_sentiment(text: str) -> dict:
    positives = ["好","棒","开心","喜欢","赞","优秀","完美","感谢","爱你","高兴","满意","不错"]
    negatives = ["差","烂","讨厌","失望","生气","难过","糟糕","垃圾","后悔","可恶","不满","郁闷"]
    pos = sum(1 for w in positives if w in text)
    neg = sum(1 for w in negatives if w in text)
    total = pos + neg
    if total == 0:
        return {"score": 0.5, "label": "neutral"}
    score = pos / total
    return {"score": round(score, 3), "label": "positive" if score > 0.6 else "negative" if score < 0.4 else "neutral"}
""",
            ),
            ToolDef(
                id="word-count",
                name="count_words",
                display_name="字数统计",
                description="统计文本的字数、字符数、行数",
                category="utility",
                icon="📝",
                code="""
def count_words(text: str) -> dict:
    chars = len(text)
    chinese = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    words = len(text.split())
    lines = text.count('\\n') + 1
    return {"chars": chars, "chinese_chars": chinese, "words": words, "lines": lines}
""",
            ),
            ToolDef(
                id="url-encode",
                name="url_encoder",
                display_name="URL编码解码",
                description="对字符串进行URL编码或解码",
                category="utility",
                icon="🔗",
                code="""
from urllib.parse import quote, unquote

def url_encoder(text: str, encode: bool = True) -> str:
    if encode:
        return quote(text, safe='')
    return unquote(text)
""",
            ),
            ToolDef(
                id="timezone",
                name="time_converter",
                display_name="时区转换",
                description="将时间在不同城市/时区之间转换",
                category="utility",
                icon="🌍",
                code="""
from datetime import datetime
import pytz

CITIES = {
    "北京": "Asia/Shanghai",
    "上海": "Asia/Shanghai",
    "东京": "Asia/Tokyo",
    "纽约": "America/New_York",
    "伦敦": "Europe/London",
    "巴黎": "Europe/Paris",
    "悉尼": "Australia/Sydney",
    "旧金山": "America/Los_Angeles",
    "香港": "Asia/Hong_Kong",
    "新加坡": "Asia/Singapore",
}

def time_converter(time_str: str, from_city: str, to_city: str) -> str:
    from_tz = pytz.timezone(CITIES.get(from_city, "UTC"))
    to_tz = pytz.timezone(CITIES.get(to_city, "UTC"))
    dt = from_tz.localize(datetime.fromisoformat(time_str))
    converted = dt.astimezone(to_tz)
    return converted.isoformat()
""",
            ),
            ToolDef(
                id="json-format",
                name="json_formatter",
                display_name="JSON格式化",
                description="美化或压缩JSON字符串",
                category="utility",
                icon="📋",
                code="""
import json

def json_formatter(text: str, pretty: bool = True) -> str:
    try:
        obj = json.loads(text)
        if pretty:
            return json.dumps(obj, ensure_ascii=False, indent=2)
        return json.dumps(obj, separators=(',', ':'))
    except Exception as e:
        return f"JSON解析错误: {e}"
""",
            ),
            ToolDef(
                id="unit-convert",
                name="unit_convert",
                display_name="单位换算",
                description="常用单位之间换算（长度/重量/温度/货币）",
                category="utility",
                icon="⚖️",
                code="""
def unit_convert(value: float, from_unit: str, to_unit: str) -> float:
    conversions = {
        ("km", "m"): 1000,
        ("m", "km"): 0.001,
        ("km", "mi"): 0.621371,
        ("mi", "km"): 1.60934,
        ("kg", "g"): 1000,
        ("g", "kg"): 0.001,
        ("kg", "lb"): 2.20462,
        ("lb", "kg"): 0.453592,
        ("c", "f"): lambda v: v * 9/5 + 32,
        ("f", "c"): lambda v: (v - 32) * 5/9,
        ("c", "k"): lambda v: v + 273.15,
        ("k", "c"): lambda v: v - 273.15,
    }
    key = (from_unit.lower(), to_unit.lower())
    factor = conversions.get(key)
    if factor is None:
        return f"不支持的换算: {from_unit} -> {to_unit}"
    if callable(factor):
        return round(factor(value), 6)
    return round(value * factor, 6)
""",
            ),
        ]

        for tool in presets:
            tool.is_builtin = True
            self.register_tool(tool)


# Global singleton
registry = ToolRegistry()
registry.register_preset_tools()
