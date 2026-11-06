import unittest
from calc import sum_to


class SumTo(unittest.TestCase):
    def test_sum_to_4(self):
        self.assertEqual(sum_to(4), 10)


if __name__ == "__main__":
    unittest.main()
