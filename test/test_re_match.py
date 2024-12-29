import unittest
import re

def _contains_pattern(pattern, item):
    return re.search(pattern, item, re.IGNORECASE) is not None

class TestContainsPattern(unittest.TestCase):
    def test_pattern_found(self):
        self.assertTrue(_contains_pattern("Intel.*GPU", "intel integrated gpu"))
        self.assertTrue(_contains_pattern("ntel.*distributed", "Intel xxx Distributed xxx Systems"))
        self.assertTrue(_contains_pattern("ntel.*Triton", "Intel xxx Triton xxx"))
        self.assertTrue(_contains_pattern("gpu_type", "gpu_type: 1"))

    def test_pattern_not_found(self):
        self.assertFalse(_contains_pattern("Intel.*GPU", "AMD integrated gpu"))
        self.assertFalse(_contains_pattern("ntel.*distributed", "Intel xxx"))
        self.assertFalse(_contains_pattern("ntel.*Triton", "Intel xxx\nTriton xxx"))
        self.assertFalse(_contains_pattern("gpu_type", "gpu__type: 1"))

if __name__ == "__main__":
    unittest.main()