from django.test import TestCase
from .tasks import example_add

class ExampleAddTestCase(TestCase):
    def test_example_add(self):
        """
        Test the example_add task to ensure it adds two numbers correctly.
        """
        result = example_add.delay(3, 5)
        self.assertEqual(result.get(timeout=10), 8)
