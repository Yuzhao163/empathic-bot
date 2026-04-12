"""
定时任务调度 - APScheduler + 文件持久化
支持 Cron 表达式 / Interval / 一次性任务，启停删除列表，含拟人化回复
"""
import os, json, time, uuid, asyncio
from pathlib import Path
from dataclasses import dataclass, field, asdict

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.date import DateTrigger
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    HAS_APS = True
except Exception:
    HAS_APS = False

SCHED_DIR = Path(os.getenv("MEMORY_DIR", "./memory")) / "schedules"
SCHED_DIR.mkdir(parents=True, exist_ok=True)

@dataclass
class ScheduledTask:
    task_id: str
    user_id: str
    task_type: str
    content: str
    trigger_type: str
    trigger_time: float = 0.0
    cron_expr: str = ""
    interval_seconds: int = 0
    enabled: bool = True
    created_at: float = 0.0
    last_run: float = 0.0
    next_run: float = 0.0
    run_count: int = 0
    metadata: dict = field(default_factory=dict)

class SchedulerService:
    def __init__(self):
        self._tasks = {}
        self._sched = None
        if HAS_APS:
            self._sched = BackgroundScheduler(timezone="Asia/Shanghai")

    def start(self):
        if self._sched and not self._sched.running:
            self._sched.start()
        self._reload()

    def stop(self):
        if self._sched and self._sched.running:
            self._sched.shutdown()

    def create_task(self, user_id, task_type, content, trigger_type,
                   trigger_time=0.0, cron_expr="", interval_seconds=0,
                   metadata=None):
        task_id = str(uuid.uuid4())
        task = ScheduledTask(
            task_id=task_id, user_id=user_id, task_type=task_type,
            content=content, trigger_type=trigger_type,
            trigger_time=trigger_time, cron_expr=cron_expr,
            interval_seconds=interval_seconds, enabled=True,
            created_at=time.time(), metadata=metadata or {}
        )
        self._save_task(task)
        self._update_index(user_id, task_id, "add")
        self._schedule(task)
        return task

    def get_task(self, task_id):
        self._reload()
        return self._tasks.get(task_id)

    def list_tasks(self, user_id=None):
        self._reload()
        tasks = [t for t in self._tasks.values()
                 if user_id is None or t.user_id == user_id]
        return sorted(tasks, key=lambda t: t.next_run or 0)

    def delete_task(self, task_id):
        task = self._tasks.get(task_id)
        if not task:
            return False
        self._unschedule(task_id)
        self._delete_file(task_id)
        self._update_index(task.user_id, task_id, "remove")
        self._tasks.pop(task_id, None)
        return True

    def enable_task(self, task_id, enabled):
        task = self._tasks.get(task_id)
        if not task:
            return None
        task.enabled = enabled
        self._save_task(task)
        if enabled:
            self._schedule(task)
        else:
            self._unschedule(task_id)
        return task

    def _schedule(self, task):
        if not self._sched or not HAS_APS or not task.enabled:
            return
        now = time.time()
        try:
            if task.trigger_type == "once":
                if task.trigger_time <= now:
                    return
                trig = DateTrigger(run_date=task.trigger_time)
                task.next_run = task.trigger_time
            elif task.trigger_type == "cron":
                kwargs = {}
                for part in (task.cron_expr or "").split(","):
                    if "=" in part:
                        k, v = part.strip().split("=", 1)
                        kwargs[k.strip()] = v.strip()
                if kwargs:
                    trig = CronTrigger(**kwargs)
                else:
                    return
            elif task.trigger_type == "interval":
                if task.interval_seconds <= 0:
                    return
                trig = IntervalTrigger(seconds=task.interval_seconds)
                task.next_run = now + task.interval_seconds
            else:
                return
            self._sched.add_job(
                func=self._run_wrapper, trigger=trig,
                id=task.task_id, args=[task.task_id], replace_existing=True
            )
            self._save_task(task)
        except Exception as exc:
            print(f"[Scheduler] sched error {task.task_id}: {exc}")

    def _run_wrapper(self, task_id):
        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(self._execute(task_id))
            loop.close()
        except Exception as exc:
            print(f"[Scheduler] exec error {task_id}: {exc}")

    async def _execute(self, task_id):
        task = self._tasks.get(task_id)
        if not task or not task.enabled:
            return
        task.last_run = time.time()
        task.run_count += 1
        self._save_task(task)
        print(f"[Scheduler] task {task_id}: {task.content[:40]}")

    def _reload(self):
        self._tasks.clear()
        for p in SCHED_DIR.glob("*.json"):
            if p.stem.startswith("index"):
                continue
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
                task = ScheduledTask(**raw)
                self._tasks[task.task_id] = task
            except Exception:
                pass

    def _save_task(self, task):
        p = SCHED_DIR / f"{task.task_id}.json"
        p.write_text(json.dumps(asdict(task), ensure_ascii=False, indent=2), encoding="utf-8")
        self._tasks[task.task_id] = task

    def _delete_file(self, task_id):
        (SCHED_DIR / f"{task_id}.json").unlink(missing_ok=True)

    def _unschedule(self, task_id):
        if self._sched and HAS_APS:
            try:
                self._sched.remove_job(task_id)
            except Exception:
                pass

    def _update_index(self, user_id, task_id, action):
        idx = {}
        p = SCHED_DIR / f"index_{user_id}.json"
        if p.exists():
            try:
                idx = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
        if action == "add":
            idx[task_id] = True
        else:
            idx.pop(task_id, None)
        p.write_text(json.dumps(idx), encoding="utf-8")

scheduler = SchedulerService()
