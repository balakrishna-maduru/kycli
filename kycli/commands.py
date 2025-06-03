import os
import csv
import json
import re

from kycli.kycore import Kycore # Assuming Kycore remains in kycore.pyx

class Command:
    """Base class for all commands."""
    def __init__(self, kycore: Kycore):
        self.kycore = kycore

    def execute(self, args: list) -> str:
        raise NotImplementedError

class SaveCommand(Command):
    def execute(self, args: list) -> str:
        if len(args) == 2:
            self.kycore.save(args[0], args[1])
            return f"Saved: {args[0]}"
        return "Usage: kys <key> <value>"

class GetCommand(Command):
    def execute(self, args: list) -> str:
        if len(args) == 1:
            result = self.kycore.getkey(args[0])
            if isinstance(result, dict):
                return "\n".join([f"{k}: {v}" for k, v in result.items()])
            return str(result)
        return "Usage: kyg <key>"

class ListCommand(Command):
    def execute(self, args: list) -> str:
        pattern = args[0] if args else None
        keys = self.kycore.listkeys(pattern)
        return "Keys: " + ", ".join(keys)

class DeleteCommand(Command):
    def execute(self, args: list) -> str:
        if len(args) == 1:
            return self.kycore.delete(args[0])
        return "Usage: kyd <key>"

class ExportCommand(Command):
    def execute(self, args: list) -> str:
        if len(args) >= 1:
            export_path = args[0]
            export_format = args[1] if len(args) > 1 else "csv"
            self.kycore.export_data(export_path, export_format.lower())
            return f"Exported data to {export_path} as {export_format.upper()}"
        return "Usage: kye <file> [format]"

class ImportCommand(Command):
    def execute(self, args: list) -> str:
        if len(args) == 1:
            import_path = args[0]
            try:
                self.kycore.import_data(import_path)
                return f"Imported data from {import_path}"
            except ValueError as e:
                return str(e)
        return "Usage: kyi <file>"

class ExecCommand(Command):
    def execute(self, args: list) -> str:
        if len(args) >= 1:
            key = args[0]
            params = args[1:]

            stored_cmd = self.kycore.getkey(key)
            if isinstance(stored_cmd, dict):
                return "Ambiguous key pattern; multiple keys matched. Be more specific."
            if stored_cmd is None or stored_cmd == "Key not found":
                return "Key not found"

            try:
                cmd_to_run = stored_cmd.format(*params)
            except IndexError as e:
                return f"Missing parameters: {e}"
            except KeyError as e:
                return f"Invalid placeholder: {e}"

            os.system(cmd_to_run)
            return f"Executed: {cmd_to_run}"
        return "Usage: kyc <key> [params...]"

class HelpCommand(Command):
    def execute(self, args: list) -> str:
            return """
    Available commands:
    kys <key> <value>             - Save key-value
    kyg <key>                     - Get value by key
    kyl                           - List keys
    kyd <key>                     - Delete key
    kye <file> [format]           - Export data (default CSV; JSON if specified)
    kyi <file>                    - Import data (auto-detect CSV/JSON)
    kyh                           - Help
    kyc <key> [params...]         - Execute stored command with dynamic replacements
    """