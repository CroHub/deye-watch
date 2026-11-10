"""Link: постійне з'єднання з логером + одна повторна спроба після розриву «старого» з'єднання."""
import queue
import unittest

from pysolarmanv5 import NoSocketAvailableError

from deye.inverter import LINK_ERRORS, Link, describe_error
from helpers import READING, FakeClock, Inverter

LOGGER = "deye.inverter.link"


class LinkTest(unittest.TestCase):
    def reads(self, inverter: Inverter, n: int) -> tuple[Link, list, FakeClock]:
        clock = FakeClock()
        link = inverter.link(clock)
        out: list = []
        for _ in range(n):
            try:
                out.append(link.read())
            except LINK_ERRORS as e:
                out.append(e)
        return link, out, clock

    def test_reuses_open_connection(self):
        inv = Inverter([READING, READING])
        _, out, clock = self.reads(inv, 2)
        self.assertEqual(out, [READING, READING])
        self.assertEqual(len(inv.conns), 1)
        self.assertEqual(clock.slept, [])

    def test_stale_connection_dropped_retries_once_on_fresh(self):
        for err in (NoSocketAvailableError("Connection already closed."),
                    NoSocketAvailableError("Connection closed on read"),
                    ConnectionResetError(), queue.Empty()):
            with self.subTest(err=type(err).__name__):
                inv = Inverter([READING, err, READING])
                with self.assertLogs(LOGGER, "INFO") as logs:
                    _, out, clock = self.reads(inv, 2)
                self.assertEqual(out, [READING, READING])
                self.assertEqual(len(inv.conns), 2)
                self.assertTrue(inv.conns[0].closed)
                self.assertEqual(clock.slept, [1.0])
                self.assertEqual(len(logs.records), 1)

    def test_stale_and_fresh_both_fail_raises_after_two_connects(self):
        inv = Inverter([READING, OSError("a"), OSError("b")])
        with self.assertLogs(LOGGER, "INFO"):
            link, out, _ = self.reads(inv, 2)
        self.assertIsInstance(out[1], OSError)
        self.assertEqual(len(inv.conns), 2)
        self.assertFalse(link.connected)

    def test_fresh_connect_failure_is_not_retried(self):
        for err in (NoSocketAvailableError("No socket available"), OSError("refused")):
            with self.subTest(err=err):
                _, out, clock = self.reads(Inverter([], connect_errors=[err]), 1)
                self.assertIs(out[0], err)
                self.assertEqual(clock.slept, [])

    def test_fresh_read_timeout_is_not_retried_and_closes(self):
        inv = Inverter([queue.Empty()])
        _, out, clock = self.reads(inv, 1)
        self.assertIsInstance(out[0], queue.Empty)
        self.assertEqual(len(inv.conns), 1)
        self.assertTrue(inv.conns[0].closed)
        self.assertEqual(clock.slept, [])

    def test_disconnect_error_is_swallowed(self):
        inv = Inverter([READING, OSError("x"), READING])
        link = inv.link(FakeClock())
        link.read()
        inv.conns[0].fail_disconnect = True
        with self.assertLogs(LOGGER, "INFO"):
            self.assertEqual(link.read(), READING)

    def test_long_outage_retries_only_on_first_failed_poll(self):
        down = [OSError("down")] * 3
        inv = Inverter([READING, OSError("x")], connect_errors=[None, *down])
        with self.assertLogs(LOGGER, "INFO"):
            _, out, clock = self.reads(inv, 4)
        self.assertEqual(out[0], READING)
        self.assertTrue(all(isinstance(o, OSError) for o in out[1:]))
        self.assertEqual(len(clock.slept), 1)  # повтор лише на першому, далі — без циклів

    def test_non_link_error_propagates(self):
        with self.assertRaises(IndexError):
            self.reads(Inverter([IndexError("bug")]), 1)

    def test_describe_error_never_empty(self):
        self.assertEqual(describe_error(queue.Empty()), "тайм-аут відповіді")
        self.assertEqual(describe_error(OSError()), "OSError")
        self.assertEqual(describe_error(OSError("boom")), "boom")


if __name__ == "__main__":
    unittest.main()
