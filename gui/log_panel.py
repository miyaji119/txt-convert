"""日志重定向：将 print 输出重定向到 GUI 日志区"""

import queue


class TextRedirector:
    """将 print 输出重定向到 GUI 日志队列

    用法：
        log_queue = queue.Queue()
        sys.stdout = TextRedirector(log_queue)
    """

    def __init__(self, log_queue: queue.Queue):
        self.log_queue = log_queue

    def write(self, text):
        if text and text.strip():
            self.log_queue.put(text)

    def flush(self):
        pass
