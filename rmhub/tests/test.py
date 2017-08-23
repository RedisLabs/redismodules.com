from unittest import TestCase
from rmhub import Hub
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

class TestRMHub(TestCase):
    def testHubCreation(self):
        hub = Hub()
        self.assertIsNotNone(hub)