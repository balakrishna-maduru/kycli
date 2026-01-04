import os
import sys
import threading
from datetime import datetime
from prompt_toolkit import Application
from prompt_toolkit.layout import Layout, HSplit, VSplit, Window, FormattedTextControl
from prompt_toolkit.widgets import Frame, TextArea
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import ANSI, HTML
from rich.console import Console
from rich.table import Table
from io import StringIO

from kycli.kycore import Kycore
from kycli.config import load_config

class KycliShell:
    def __init__(self, db_path=None):
        self.config = load_config()
        self.db_path = db_path or self.config.get("db_path")
        self.kv = Kycore(db_path=self.db_path)
        
        self.output_area = FormattedTextControl(
            text="[italic dim]Command output will appear here...[/italic dim]"
        )
        self.history_area = FormattedTextControl(text="")
        
        self.input_field = TextArea(
            height=3,
            prompt="kycli> ",
            style="class:input-field",
            multiline=False,
            wrap_lines=True,
        )

        # Set up command handling
        self.input_field.accept_handler = self.handle_command
        
        # Styles
        self.style = Style.from_dict({
            "frame.border": "#4444ff",
            "input-field": "bold #ffffff",
        })

        # Layout
        self.history_frame = Frame(Window(content=self.history_area, wrap_lines=True), title="Audit Trail")
        
        body = HSplit([
            VSplit([
                self.history_frame,
                Frame(Window(content=FormattedTextControl(
                    text=HTML(
                        '<b><style color="yellow">COMMANDS</style></b>\n'
                        '<style color="cyan">kys &lt;k&gt; &lt;v&gt;</style> : Save key/JSON\n'
                        '<style color="cyan">kyg &lt;k&gt;</style>     : Get/Deserialize\n'
                        '<style color="cyan">kyf &lt;q&gt;</style>     : FT Search\n'
                        '<style color="cyan">kyl [p]</style>     : List/Regex keys\n'
                        '<style color="cyan">kyv [-h|k]</style>  : Audit History\n'
                        '<style color="cyan">kyr &lt;k&gt;</style>     : Recover Deleted\n'
                        '<style color="cyan">kyd &lt;k&gt;</style>     : Secure Delete\n'
                        '<style color="cyan">kye &lt;f&gt;</style>     : Export Data\n'
                        '<style color="cyan">kyi &lt;f&gt;</style>     : Import Data\n'
                        '<style color="cyan">kyc &lt;k&gt; [a]</style>  : Execute Command\n'
                        '<style color="cyan">kyh</style>         : View Help\n'
                        '<style color="red">exit/quit</style>   : Quit Shell\n\n'
                        '<style color="gray">Env: KYCLI_DB_PATH overrides DB path.</style>'
                    )
                )), title="Advanced Help", width=35),
            ]),
            Frame(Window(content=self.output_area, wrap_lines=True), title="Results", height=6),
            self.input_field,
        ])
        
        self.kb = KeyBindings()
        @self.kb.add("c-c")
        @self.kb.add("c-q")
        def _(event):
            event.app.exit()

        self.app = Application(
            layout=Layout(body, focused_element=self.input_field),
            key_bindings=self.kb,
            style=self.style,
            full_screen=True,
            mouse_support=True,
        )
        
        self.update_history()

    def update_history(self):
        try:
            import shutil
            term_height = shutil.get_terminal_size().lines
            # Consumed lines: Results(6), Input(1), Borders/Separators(~5)
            max_entries = max(5, term_height - 12)
            
            history = self.kv.get_history("-h")[:max_entries]
            self.history_frame.title = f"Audit Trail (Last {len(history)})"
            
            term_width = shutil.get_terminal_size().columns
            content_width = max(40, term_width - 40)
            
            table = Table(box=None, padding=(0, 1), expand=True)
            table.add_column("TS", style="dim cyan")
            table.add_column("Key", style="yellow")
            table.add_column("Value", style="green")
            
            for key, val, ts in history:
                # Remove small truncation, allow rich to wrap
                v_str = str(val)
                display_val = v_str[:1000] + "..." if len(v_str) > 1000 else v_str
                table.add_row(ts, key, display_val)
            
            sio = StringIO()
            Console(file=sio, force_terminal=True, width=content_width).print(table)
            self.history_area.text = ANSI(sio.getvalue())
        except:
            pass

    def handle_command(self, buffer):
        cmd_line = buffer.text.strip()
        if not cmd_line:
            return
        
        if cmd_line.lower() in ["exit", "quit"]:
            self.app.exit()
            return

        parts = cmd_line.split()
        cmd = parts[0].lower()
        args = parts[1:]
        
        result = ""
        try:
            if cmd in ["kys", "save"]:
                if len(args) < 2: result = "Usage: kys <key> <value>"
                else:
                    self.kv.save(args[0], " ".join(args[1:]))
                    result = f"Saved: {args[0]}"
            elif cmd in ["kyg", "get"]:
                if not args: result = "Usage: kyg <key>"
                else: result = str(self.kv.getkey(args[0]))
            elif cmd in ["kyl", "list", "ls"]:
                pattern = args[0] if args else None
                res = self.kv.listkeys(pattern)
                result = f"Keys: {', '.join(res) if res else 'None'}"
            elif cmd in ["kyf", "search"]:
                if not args: result = "Usage: kyf <query>"
                else:
                    res = self.kv.search(" ".join(args))
                    result = "\n".join([f"{r[0]}: {r[1]}" for r in res]) if res else "No matches."
            elif cmd in ["kyv", "view", "history"]:
                target = args[0] if args else "-h"
                history = self.kv.get_history(target)
                if not history: result = "No history found."
                elif target == "-h":
                    result = "\n".join([f"{h[2]}: {h[0]}={h[1]}" for h in history[:10]])
                else:
                    result = str(history[0][1])
            elif cmd in ["kyr", "restore"]:
                if not args: result = "Usage: kyr <key>"
                else: result = self.kv.restore(args[0])
            elif cmd in ["kye", "export"]:
                if not args: result = "Usage: kye <file> [format]"
                else:
                    fmt = args[1] if len(args) > 1 else "csv"
                    self.kv.export_data(args[0], fmt)
                    result = f"Exported to {args[0]}"
            elif cmd in ["kyi", "import"]:
                if not args: result = "Usage: kyi <file>"
                else:
                    self.kv.import_data(args[0])
                    result = f"Imported from {args[0]}"
            elif cmd in ["kyc", "execute"]:
                if not args: result = "Usage: kyc <key> [args...]"
                else:
                    val = self.kv.getkey(args[0], deserialize=False)
                    if val == "Key not found": result = f"Key '{args[0]}' not found."
                    else:
                        import subprocess
                        full_cmd = val
                        if len(args) > 1: full_cmd = f"{val} {' '.join(args[1:])}"
                        try:
                            # Run in background to not block TUI (simple way)
                            threading.Thread(target=lambda: subprocess.run(full_cmd, shell=True)).start()
                            result = f"Started: {full_cmd}"
                        except Exception as e:
                            result = f"Exec Error: {e}"
            elif cmd in ["kyd", "delete"]:
                if not args: result = "Usage: kyd <key>"
                else:
                    self.kv.delete(args[0])
                    result = f"Deleted: {args[0]}"
            elif cmd == "kyh":
                result = "Check the Advanced Help panel on the right! ->"
            elif cmd == "kyshell":
                result = "⚡ You are already in the interactive shell."
            else:
                result = f"Unknown command: {cmd}"
        except Exception as e:
            result = f"Error: {e}"

        self.output_area.text = result
        self.update_history()

    def run(self):
        self.app.run()

def start_shell(db_path=None):
    shell = KycliShell(db_path)
    shell.run()
