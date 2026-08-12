import os
import sys
import unittest


sys.path.insert(0, os.path.dirname(__file__))

from _bot_loader import import_bot_module


class GlobalInteractionCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bot_module = import_bot_module()

    def test_global_slash_check_is_registered_on_command_tree(self):
        self.assertIs(
            self.bot_module.bot.tree.interaction_check,
            self.bot_module.log_all_slash_commands,
        )


if __name__ == "__main__":
    unittest.main()
