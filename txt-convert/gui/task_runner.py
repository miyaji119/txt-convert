"""后台任务执行器

用 functools.partial 机制性杜绝闭包陷阱：
- 参数在 submit 时通过 partial 冻结，不存在 lambda 惰性求值
- except 块中的异常对象通过 partial 立即绑定，即使 except 块结束后
  异常变量被 Python 清理，partial 已持有引用
- 回调通过 root.after 调度到主线程执行

用法：
    runner = TaskRunner(root, on_task_finished=app._task_finished)
    runner.submit(target, arg1, arg2, on_complete=cb, on_error=err_cb, kw=v)
    runner.cancel()
    runner.shutdown()
"""

import threading
import functools
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional, Any


class TaskRunner:
    """后台任务执行器（单任务串行）

    设计要点：
    - max_workers=1：同时只执行一个任务，避免并发问题
    - functools.partial：所有参数在提交时冻结，杜绝闭包陷阱
    - 协作取消：通过 cancel_flag Event，任务内部需自行检查
    """

    def __init__(self, root, on_task_finished: Callable = None):
        """
        Args:
            root: Tk 主窗口，用于 root.after 调度回调到主线程
            on_task_finished: 任务结束后的回调（在主线程执行），
                              无参数，由 app 更新 UI 状态
        """
        self.root = root
        self._on_task_finished = on_task_finished
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="task_worker"
        )
        self._current_future = None
        self._cancel_flag = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        # 用于阻塞式取消等待的锁
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # 兼容属性（供 app.py 旧代码访问）
    # ------------------------------------------------------------------
    @property
    def worker_thread(self) -> Optional[threading.Thread]:
        """当前工作线程（兼容旧代码 app.worker_thread 访问）"""
        return self._worker_thread

    @property
    def cancel_flag(self) -> threading.Event:
        """取消标志（兼容旧代码 app.cancel_flag 访问）"""
        return self._cancel_flag

    # ------------------------------------------------------------------
    # 任务提交
    # ------------------------------------------------------------------
    def submit(self, target: Callable, *args,
               on_complete: Callable = None,
               on_error: Callable = None,
               **kwargs) -> bool:
        """提交任务到后台线程执行

        所有参数（args/kwargs/on_complete/on_error）在提交时通过
        functools.partial 冻结，从机制上杜绝闭包惰性求值陷阱。

        Args:
            target: 任务函数
            *args: 位置参数
            on_complete: 成功回调，签名 on_complete(result)
            on_error: 失败回调，签名 on_error(exception)
            **kwargs: 关键字参数

        Returns:
            True=提交成功，False=已有任务运行
        """
        with self._lock:
            if self._current_future and not self._current_future.done():
                return False

            self._cancel_flag.clear()

            # 用 partial 冻结所有参数：target、args、kwargs、回调
            # 这样后台线程拿到的就是一个已绑定好所有参数的可调用对象，
            # 不存在任何闭包惰性求值的风险
            task_fn = functools.partial(
                self._execute_task,
                target, args, kwargs, on_complete, on_error
            )
            self._current_future = self._executor.submit(task_fn)
            return True

    def _execute_task(self, target: Callable, args: tuple,
                       kwargs: dict, on_complete: Callable,
                       on_error: Callable):
        """实际任务执行（在后台线程内）

        本方法的所有参数都是 partial 冻结的，不存在闭包陷阱。
        """
        self._worker_thread = threading.current_thread()
        try:
            result = target(*args, **kwargs)
            if on_complete:
                # 用 partial 冻结 result，即使 target 返回后
                # 局部变量 result 被回收，partial 已持有引用
                self._schedule_main(functools.partial(on_complete, result))
        except Exception as e:
            print(f"❌ 任务执行失败: {e}")
            if on_error:
                # 关键：用 partial 冻结异常对象 e
                # Python 的 except 块结束后会自动删除 e 变量，
                # 如果用 lambda: on_error(e) 会导致 NameError
                # partial 在此处立即捕获 e 的引用，安全传递到主线程
                self._schedule_main(functools.partial(on_error, e))
        finally:
            self._worker_thread = None
            if self._on_task_finished:
                self._schedule_main(self._on_task_finished)

    def _schedule_main(self, callback: Callable):
        """将回调调度到主线程执行

        使用 root.after(0, callback) 在 Tk 主循环中执行。
        若主窗口已关闭，静默忽略。
        """
        try:
            self.root.after(0, callback)
        except (RuntimeError, AttributeError):
            pass

    # ------------------------------------------------------------------
    # 取消与关闭
    # ------------------------------------------------------------------
    def cancel(self):
        """请求取消当前任务

        注意：Python 线程无法强制终止，本方法仅设置取消标志，
        任务内部需自行检查 self.cancel_flag.is_set() 并响应。
        """
        self._cancel_flag.set()

    def shutdown(self):
        """关闭任务执行器（不等待正在运行的任务）"""
        self._executor.shutdown(wait=False)
