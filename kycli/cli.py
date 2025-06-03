import sys
import os
from kycli.kycore import Kycore
from kycli.commands import (
    SaveCommand, GetCommand, ListCommand, DeleteCommand,
    ExportCommand, ImportCommand, ExecCommand, HelpCommand
)

class KycliFactory:
    def __init__(self):
        self._kycore = Kycore()
        self._commands = {
            "kys": SaveCommand(self._kycore),
            "kyg": GetCommand(self._kycore),
            "kyl": ListCommand(self._kycore),
            "kyd": DeleteCommand(self._kycore),
            "kye": ExportCommand(self._kycore),
            "kyi": ImportCommand(self._kycore),
            "kyc": ExecCommand(self._kycore),
            "kyh": HelpCommand(self._kycore)
        }

    def get_command(self, prog_name: str):
        return self._commands.get(prog_name)

def main():
    factory = KycliFactory()
    args = sys.argv[1:]
    prog = os.path.basename(sys.argv[0])

    # If the program name is explicitly 'kyh' or 'help', always show help.
    if prog in ["kyh", "help"]:
        help_command = factory.get_command(prog)
        print(help_command.execute(args)) # Pass args in case help ever needs them
        return

    # If no arguments are provided and it's not a help command,
    # we should still try to execute the command associated with 'prog'.
    # For commands that require arguments (like kys, kyg, kyd, kyc),
    # their respective execute methods will return a "Usage" message.
    # For 'kyl' with no arguments, it should list all keys.
    command_to_execute = factory.get_command(prog)

    if command_to_execute:
        output = command_to_execute.execute(args)
        print(output)
    else:
        # This case handles if the script name itself isn't a recognized command,
        # or if the user just ran 'python -m kycli.cli' without any arguments.
        # In such cases, we print the general help.
        print(factory.get_command("kyh").execute([]))

if __name__ == "__main__":
    main()