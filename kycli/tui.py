import os
import sys
import threading
import warnings
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
from kycli.cli import get_help_text

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
                        '<style color="cyan">kyfo</style>         : Optimize Search\n'
                        '<style color="cyan">kyl [p]</style>     : List/Regex keys\n'
                        '<style color="cyan">kyv [-h|k]</style>  : Audit History\n'
                        '<style color="cyan">kyr &lt;k&gt;</style>     : Recover Deleted\n'
                        '<style color="cyan">kyd &lt;k&gt;</style>     : Secure Delete\n'
                        '<style color="cyan">kye &lt;f&gt; [fm]</style>  : Export CSV/JSON\n'
                        '<style color="cyan">kyi &lt;f&gt;</style>     : Import CSV/JSON\n'
                        '<style color="cyan">kyrt &lt;ts&gt;</style>    : PIT Recovery\n'
                        '<style color="cyan">kyco [d]</style>     : Compact DB\n'
                        '<style color="cyan">kyc &lt;k&gt; [a]</style>  : Execute Script\n'
                        '<style color="cyan">kyh</style>         : Full Help\n'
                        '<style color="red">exit/quit</style>   : Quit Shell\n\n'
                        '<b><style color="yellow">SECURITY</style></b>\n'
                        '<style color="gray">Use --key &lt;k&gt; or set</style>\n'
                        '<style color="gray">KYCLI_MASTER_KEY env.</style>'
                    )
                )), title="Quick Help", width=35),
            ]),
            Frame(Window(content=self.output_area, wrap_lines=True), title="Results", height=12),
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
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            try:
                if cmd in ["kys", "save"]:
                    if len(args) < 2: 
                        result = "Usage: kys <key> <value> [--ttl <sec>] [--key <k>]"
                    else:
                        ttl_val = None
                        key_val = self.config.get("master_key")
                        val_parts = []
                        skip = False
                        for i, a in enumerate(args[1:]):
                            if skip:
                                skip = False
                                continue
                            if a == "--ttl" and i + 1 < len(args):
                                ttl_val = args[i+1]
                                skip = True
                            elif a == "--key" and i + 1 < len(args):
                                key_val = args[i+1]
                                skip = True
                            else:
                                val_parts.append(a)
                        
                        val = " ".join(val_parts)
                        # Re-init if key provided
                        kv_to_use = self.kv
                        if key_val:
                            kv_to_use = Kycore(db_path=self.db_path, master_key=key_val)
                        kv_to_use.save(args[0], val, ttl=ttl_val)
                        result = f"Saved: {args[0]}"

                elif cmd in ["kyg", "get"]:
                    if not args: 
                        result = "Usage: kyg <key> [--key <k>]"
                    else:
                        query_key = args[0]
                        master_key = self.config.get("master_key")
                        if "--key" in args:
                            idx = args.index("--key")
                            if idx + 1 < len(args):
                                master_key = args[idx+1]
                        
                        kv_to_use = self.kv
                        if master_key:
                            kv_to_use = Kycore(db_path=self.db_path, master_key=master_key)
                        result = str(kv_to_use.getkey(query_key))

                elif cmd in ["kyl", "list", "ls"]:
                    pattern = args[0] if args else None
                    res = self.kv.listkeys(pattern)
                    result = f"🔑 Keys: {', '.join(res)}" if res else "No keys found"

                elif cmd in ["kyf", "search", "find"]:
                    if not args: result = "Usage: kyf <query>"
                    else:
                        res = self.kv.search(" ".join(args))
                        result = "\n".join([f"{k}: {v}" for k, v in res.items()])
                        if not result: result = "No matches found"

                elif cmd in ["kyd", "delete", "rm"]:
                    if not args: result = "Usage: kyd <key>"
                    else:
                        self.kv.delete(args[0])
                        result = f"Deleted: {args[0]}"

                elif cmd in ["kyv", "history", "log"]:
                    if not args:
                        history = self.kv.get_history()
                        result = "📜 Full Audit History:\n" + "\n".join([str(h) for h in history[:10]])
                    else:
                        history = self.kv.get_history(args[0])
                        if history:
                            result = f"⏳ History for {args[0]}:\n" + "\n".join([str(h) for h in history])
                        else:
                            result = f"No history for {args[0]}"

                elif cmd in ["kyr", "restore"]:
                    if not args: result = "Usage: kyr <key>"
                    else:
                        result = self.kv.restore(args[0])

                elif cmd in ["kye", "export"]:
                    if len(args) < 1: result = "Usage: kye <file> [format]"
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
                        key = args[0]
                        val = self.kv.getkey(key, deserialize=False)
                        if val == "Key not found":
                            result = f"Error: Key '{key}' not found."
                        else:
                            cmd_to_run = val
                            if len(args) > 1:
                                cmd_to_run = f"{val} {' '.join(args[1:])}"
                            result = f"Started: {cmd_to_run}"
                            threading.Thread(target=os.system, args=(cmd_to_run,), daemon=True).start()

                elif cmd in ["kyfo", "optimize"]:
                    self.kv.optimize_index()
                    result = "⚡ Search index optimized."

                elif cmd in ["kyrt", "restore-to"]:
                    if not args: result = "Usage: kyrt <timestamp>"
                    else:
                        ts = " ".join(args)
                        result = self.kv.restore_to(ts)

                elif cmd in ["kyco", "compact"]:
                    retention = int(args[0]) if args else 15
                    result = self.kv.compact(retention)

                elif cmd == "kyh":
                    result = get_help_text()
                elif cmd == "kyshell":
                    result = "⚡ You are already in the interactive shell."
                else:
                    result = f"Unknown command: {cmd}. Type 'kyh' for help."

            except Exception as e:
                result = f"Error: {e}"
            
            # Combine warnings and result
            if w:
                warn_msgs = [f"⚠️ {warn.message}" for warn in w]
                result = "\n".join(warn_msgs) + ("\n" + result if result else "")

        self.output_area.text = result
        buffer.text = ""
        self.update_history()

    def run(self):
        self.app.run()

def start_shell(db_path=None):
    shell = KycliShell(db_path)
    shell.run()
