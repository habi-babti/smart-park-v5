import queue
import threading
from notifier import notify_user

notification_queue = queue.Queue()
MAX_RETRIES = 3

def worker():
    while True:
        item = notification_queue.get()
        for attempt in range(MAX_RETRIES):
            if notify_user(item['contact'], item['message']):
                break
        notification_queue.task_done()

# Start worker thread
threading.Thread(target=worker, daemon=True).start()

def add_to_queue(contact, message):
    notification_queue.put({'contact': contact, 'message': message})