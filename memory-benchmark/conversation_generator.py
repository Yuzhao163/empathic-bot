"""
Memory Benchmark - 对话生成器
生成30天、1000+轮的真实感对话，覆盖多种话题和记忆重复场景
"""

import random
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any

class ConversationGenerator:
    def __init__(self, seed=42):
        random.seed(seed)
        self.user_profile = {
            "name": "Alex",
            "occupation": "全栈工程师",
            "projects": ["电商平台重构", "AI助手开发", "数据看板"],
            "tech_stack": ["Python", "TypeScript", "React", "Node.js", "PostgreSQL"],
            "preferences": {
                "coding_style": "函数式编程",
                "coffee": "美式咖啡，不加糖",
                "meeting": "异步优先，不喜欢过多会议",
                "vacation": "喜欢去海边，不喜欢爬山",
            },
            "ongoing_facts": {
                "电商平台重构": "预计Q2上线，正在进行数据库迁移",
                "AI助手": "正在接入ClawHub，计划做记忆系统评测",
                "数据看板": "用Dify做内部BI，本周完成第一版",
            }
        }
        
        # 关键事实池 - 这些事实会被多次提起
        self.key_facts_pool = [
            {"entity": "电商平台", "fact": "决定用Next.js重构前端，不用Vue", "importance": 0.95, "first_mentioned": None},
            {"entity": "数据库", "fact": "选型PostgreSQL，已完成迁移脚本", "importance": 0.9, "first_mentioned": None},
            {"entity": "AI助手", "fact": "接入ClawHub，用memory-benchmark做评测", "importance": 0.85, "first_mentioned": None},
            {"entity": "咖啡偏好", "fact": "只喝美式，不加糖，每天2杯", "importance": 0.7, "first_mentioned": None},
            {"entity": "会议习惯", "fact": "周三下午固定会议，其他时间异步沟通", "importance": 0.75, "first_mentioned": None},
            {"entity": "休假计划", "fact": "计划6月去日本赏樱花，已订机票", "importance": 0.8, "first_mentioned": None},
            {"entity": "代码风格", "fact": "偏好TypeScript strict mode，讨厌any", "importance": 0.85, "first_mentioned": None},
            {"entity": "数据看板", "fact": "用FastGPT做内部BI，已完成Demo", "importance": 0.75, "first_mentioned": None},
            {"entity": "开源项目", "fact": "计划开源记忆评测框架，仓库名memory-benchmark", "importance": 0.8, "first_mentioned": None},
            {"entity": "学习计划", "fact": "想学Rust，已看完the book前5章", "importance": 0.7, "first_mentioned": None},
            {"entity": "团队成员", "fact": "新来一个实习生小李，做后端", "importance": 0.65, "first_mentioned": None},
            {"entity": "硬件设备", "fact": "MacBook Pro 16寸，IDEA Ultimate用户", "importance": 0.6, "first_mentioned": None},
        ]
        
        self.conversation_templates = {
            "task_planning": [
                "今天要做什么来着？",
                "帮我看看今天的待办事项",
                "我昨天说到要处理{topic}的问题，搞定了吗？",
                "{topic}这个任务预计什么时候能完成？",
            ],
            "technical_discussion": [
                "关于{topic}，你觉得用什么方案好？",
                "我在{topic}上遇到了一个问题：{problem}",
                "帮我review一下{topic}的代码？",
                "{topic}这个设计是不是有改进空间？",
            ],
            "decision_making": [
                "我们决定用 {option_a} 还是 {option_b}？",
                "{topic}的选型我有几个选项，帮我分析一下",
                "这个决定会影响{impact}，确认一下：{decision}",
            ],
            "preference_expressing": [
                "我其实更喜欢{preference}，帮我记一下",
                "有个偏好要更新：{preference}",
                "我一直觉得{opinion}，这就是我的风格",
            ],
            "reference_past": [
                "之前我们讨论过{topic}，结论是什么来着？",
                "我记得关于{topic}有过一个决定，帮我翻一下",
                "上周提到要关注{topic}，现在进展如何？",
                "关于{topic}，上次得出的结论是{conclusion}",
            ],
            "daily_chitchat": [
                "今天心情不错，效率应该会高",
                "午饭吃了啥？我吃的{food}",
                "下午有个会，希望不要太长",
                "周末有什么计划吗？",
            ],
            "learning_progress": [
                "最近在看 {topic}，有些收获",
                "学到了{topic}的新用法，回头试试",
                "{topic}的文档写得很清楚，一下就懂了",
            ],
            "error_reporting": [
                "遇到一个bug：{problem}",
                "{topic}报错了，错误信息是{error}",
                "这个库有点坑，{issue}问题一直没解决",
            ],
        }
        
        self.problems_pool = [
            "连接超时", "内存泄漏", "类型不匹配", "并发冲突", "部署失败",
            "缓存不一致", "SQL注入漏洞", "负载过高", "Session丢失", "构建报错"
        ]
        
        self.topics_pool = [
            "电商平台前端架构", "AI记忆系统", "数据库优化", "微服务拆分",
            "CI/CD流程", "单元测试覆盖率", "API版本管理", "日志系统",
            "监控告警", "Docker Compose配置", "React性能优化", "Rust所有权"
        ]
        
    def _pick_template(self, category: str, topic=None) -> str:
        templates = self.conversation_templates[category]
        template = random.choice(templates)
        if topic is None:
            topic = random.choice(self.topics_pool)
        return template.format(
            topic=topic,
            problem=random.choice(self.problems_pool),
            error="connection refused" if random.random() > 0.5 else "undefined is not a function",
            preference=self._random_preference(),
            option_a=self._random_option(),
            option_b=self._random_option(),
            impact="可扩展性" if random.random() > 0.5 else "开发速度",
            decision="用GraphQL替代REST" if random.random() > 0.5 else "保持REST",
            conclusion="决定用A方案" if random.random() > 0.5 else "暂时搁置",
            food="牛肉面" if random.random() > 0.5 else "沙拉",
            opinion="代码要先写测试" if random.random() > 0.5 else "快速迭代比完美更重要",
            issue="版本兼容性" if random.random() > 0.5 else "文档缺失",
        )
    
    def _random_preference(self) -> str:
        prefs = [
            "深色主题",
            "快捷键操作",
            "自动化测试",
            "代码格式化",
            "简洁的函数名",
        ]
        return random.choice(prefs)
    
    def _random_option(self) -> str:
        options = [
            "TypeScript", "Go", "Rust", "Python",
            "PostgreSQL", "MongoDB", "Redis",
            "React", "Vue", "Svelte",
            "Docker", "K8s", "直接部署",
        ]
        return random.choice(options)
    
    def _generate_day_conversation(self, day_num: int, date: datetime) -> List[Dict]:
        """生成一天的多轮对话"""
        is_weekend = date.weekday() >= 5
        turns = []
        num_turns = random.randint(35, 40)
        
        if is_weekend:
            categories = ["daily_chitchat", "learning_progress", "preference_expressing", "reference_past"]
            topics_bias = ["Rust", "新技术", "个人项目", "学习计划"]
        else:
            categories = [
                "task_planning", "technical_discussion", "decision_making",
                "reference_past", "error_reporting", "daily_chitchat"
            ]
            topics_bias = list(self.user_profile["projects"]) + self.topics_pool[:6]
        
        # 决定哪些关键事实会在今天被提起
        facts_mentioned_today = []
        num_key_facts = random.randint(2, 5)
        for _ in range(num_key_facts):
            fact = random.choice(self.key_facts_pool)
            if fact not in facts_mentioned_today:
                facts_mentioned_today.append(fact)
        
        for i in range(num_turns):
            turn_id = f"d{day_num}_t{i+1}"
            hour = 9 + (i * 25 // 60)
            
            if random.random() < 0.3 and facts_mentioned_today:
                fact = random.choice(facts_mentioned_today)
                category = "reference_past"
                topic = fact["entity"]
                user_msg = self._pick_template(category, topic)
                mentioned_fact = fact["fact"]
            else:
                category = random.choice(categories)
                topic = random.choice(topics_bias)
                user_msg = self._pick_template(category, topic)
                mentioned_fact = None
            
            turn = {
                "turn_id": turn_id,
                "day": day_num,
                "date": date.isoformat(),
                "hour": hour,
                "user_message": user_msg,
                "topic": topic,
                "category": category,
                "mentioned_key_fact": mentioned_fact,
                "fact_importance": random.uniform(0.5, 1.0) if mentioned_fact else 0,
                "is_new_topic": random.random() < 0.2,
                "references_previous": random.random() < 0.25,
            }
            turns.append(turn)
        
        return turns
    
    def generate_full_conversation(self) -> Dict[str, Any]:
        """生成30天完整对话"""
        all_turns = []
        start_date = datetime(2026, 3, 1)
        
        for day in range(1, 31):
            date = start_date + timedelta(days=day-1)
            day_turns = self._generate_day_conversation(day, date)
            all_turns.extend(day_turns)
        
        for turn in all_turns:
            if turn["mentioned_key_fact"]:
                for fact in self.key_facts_pool:
                    if fact["fact"] == turn["mentioned_key_fact"]:
                        if fact["first_mentioned"] is None:
                            fact["first_mentioned"] = turn["day"]
        
        return {
            "total_days": 30,
            "total_turns": len(all_turns),
            "user_profile": self.user_profile,
            "key_facts": self.key_facts_pool,
            "conversations": all_turns,
        }
