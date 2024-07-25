import psutil
from datetime import datetime


def monitor():
    with open('cpu.txt', 'a') as f:
        while True:
            cpu = psutil.cpu_percent(interval=2)
            tstamp = datetime.isoformat(datetime.now(), timespec='seconds')
            print(f"{tstamp} {round(cpu) * '|'} ({cpu}%)", file=f)
            f.flush()


if __name__ == '__main__':
    monitor()
