import threading
import unittest

from bot_loker_wfh.office_events import EventBus


class EventBusTest(unittest.TestCase):
    def test_publish_delivers_copy_and_drops_oldest_when_full(self):
        bus = EventBus(maxsize=2)
        sub = bus.subscribe()
        event = {"type": "employee_work", "task": "hunt"}
        bus.publish(event)
        event["task"] = "mutated"
        bus.publish({"task": "screen"})
        bus.publish({"task": "draft"})
        self.assertEqual(sub.get(timeout=0.1)["task"], "screen")
        self.assertEqual(sub.get(timeout=0.1)["task"], "draft")
        sub.close()

    def test_concurrent_publish_is_safe(self):
        bus = EventBus(maxsize=1000)
        sub = bus.subscribe()
        threads = [threading.Thread(target=lambda: [bus.publish({"n": i}) for i in range(50)]) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sub.queue.qsize(), 200)
        sub.close()


if __name__ == "__main__":
    unittest.main()
