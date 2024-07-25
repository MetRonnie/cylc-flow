import psutil

def monitor():
    while True:
        with open('cpu.txt', 'a') as f:
            print(psutil.cpu_percent(interval=5), file=f)

if __name__ == '__main__':
    monitor()
