import psutil
from datetime import datetime


def monitor():
    with open('cpu.txt', 'a') as f:
        while True:
            cpus = psutil.cpu_percent(interval=2, percpu=True)
            tstamp = datetime.now().strftime('%H:%M:%S')
            bars = (
                f"{round(cpu / 4) * '|'}{(25 - round(cpu / 4)) * ' '}%"
                for cpu in cpus
            )
            print(f"{tstamp} {' '.join(bars)} {cpus}", file=f)
            f.flush()


if __name__ == '__main__':
    monitor()
