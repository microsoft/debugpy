import threading
event_set = False

def method():
    while not event_set:
        import time
        time.sleep(.1)
        
t = threading.Thread(target=method)
t.start()

print('break here')
event_set = True
t.join()
print('TEST SUCEEDED!')