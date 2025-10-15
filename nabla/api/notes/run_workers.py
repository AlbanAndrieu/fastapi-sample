# run_workers.py
import asyncio
from multiprocessing import Process

from worker import worker_loop


def start_worker():
    asyncio.run(worker_loop())


if __name__ == "__main__":
    num_workers = 4
    workers = [Process(target=start_worker) for _ in range(num_workers)]
    for w in workers:
        w.start()
