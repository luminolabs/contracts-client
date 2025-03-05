import threading


class ThreadHelper:
    def __init__(self, target):
        self.target = target
        self.running = False
        self.thread = None

    def run(self):
        self.running = True
        self.thread = threading.Thread(target=self._run_target)
        self.thread.start()
        return self

    def _run_target(self):
        while self.running:
            try:
                self.target()
            except Exception as e:
                print(f"Thread error: {e}")
                break

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
