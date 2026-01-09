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
import json

from kycli.kycore import Kycore
from kycli.config import load_config, save_config, get_workspaces
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
                        '<style color="cyan">kyg [-s] &lt;k&gt;</style> : Get or Search\n'
                        '<style color="cyan">kypush &lt;k&gt; &lt;v&gt;</style> : Push to List\n'
                        '<style color="cyan">kyrem &lt;k&gt; &lt;v&gt;</style> : Remove from List\n'
                        '<style color="cyan">kyuse &lt;ws&gt;</style>    : Switch Workspace\n'
                        '<style color="cyan">kyws</style>            : List Workspaces\n'
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
        self.update_status()

    def update_status(self):
        ws = self.config.get("active_workspace", "default")
        self.history_frame.title = f"Audit Trail [{ws}]"

    def update_history(self):
        try:
            history = self.kv.get_history()
            # Show last 20 entries
            lines = []
            for h in history[:20]:
                lines.append(f"{h[2]} | {h[0]}: {str(h[1])[:30]}")
            self.history_area.text = "\n".join(lines)
        except:
            self.history_area.text = "Error loading history"

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
                # Workspace Commands
                if cmd in ["kyuse", "use"]:
                    if not args:
                        result = "Usage: kyuse <workspace>"
                    else:
                        target = args[0]
                        if not target.isalnum():
                            result = "❌ Invalid name."
                        else:
                            save_config({"active_workspace": target})
                            # Reload config and Kycore
                            self.config = load_config()
                            new_db_path = self.config.get("db_path")
                            self.kv = Kycore(db_path=new_db_path)
                            self.update_status() # Refresh title
                            self.update_history() # Refresh history for new DB
                            result = f"➡️ Switched to workspace: {target}"

                elif cmd in ["kyws", "workspaces"]:
                    wss = get_workspaces()
                    ws = self.config.get("active_workspace", "default")
                    lines = ["📂 Workspaces:"]
                    for w in wss:
                        marker = "✨ " if w == ws else "   "
                        lines.append(f"{marker}{w}")
                    result = "\n".join(lines)
                
                elif cmd in ["kys", "save"]:
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
                        if val.isdigit(): val = int(val)
                        elif val.lower() == "true": val = True
                        elif val.lower() == "false": val = False
                        elif val.startswith("[") or val.startswith("{"):
                            try: val = json.loads(val)
                            except: pass
                        
                        kv_to_use = self.kv
                        master_key = key_val
                        if master_key:
                            kv_to_use = Kycore(db_path=self.db_path, master_key=master_key)
                        
                        key = args[0]
                        if "." in key or "[" in key:
                            kv_to_use.patch(key, val, ttl=ttl_val)
                        else:
                            kv_to_use.save(key, val, ttl=ttl_val)
                        result = f"Saved: {key}"

                elif cmd in ["kyg", "get"]:
                    if not args: 
                        result = "Usage: kyg <key> OR kyg -s <query>"
                    else:
                        master_key = self.config.get("master_key")
                        search_mode = False
                        limit = 100
                        keys_only = False
                        new_args = []
                        skip = False
                        
                        for i, a in enumerate(args):
                            if skip:
                                skip = False
                                continue
                            if a == "--key" and i + 1 < len(args):
                                master_key = args[i+1]
                                skip = True
                            elif a in ["-s", "--search"]:
                                search_mode = True
                            elif a == "--limit" and i + 1 < len(args):
                                try: limit = int(args[i+1])
                                except: pass
                                skip = True
                            elif a == "--keys-only":
                                keys_only = True
                            else:
                                new_args.append(a)
                        
                        kv_to_use = self.kv
                        if master_key:
                            kv_to_use = Kycore(db_path=self.db_path, master_key=master_key)
                        
                        if search_mode:
                            query = " ".join(new_args)
                            res = kv_to_use.search(query, limit=limit, keys_only=keys_only)
                            if isinstance(res, (dict, list)):
                                result = json.dumps(res, indent=2)
                            else:
                                result = str(res)
                            if not result or result == "{}": result = "No matches found"
                        else:
                            if not new_args:
                                result = "Usage: kyg <key>"
                            else:
                                res_val = kv_to_use.getkey(new_args[0])
                                if isinstance(res_val, (dict, list)):
                                    res_val = json.dumps(res_val, indent=2)
                                result = str(res_val)

                elif cmd in ["kyl", "list", "ls"]:
                    pattern = args[0] if args else None
                    res = self.kv.listkeys(pattern)
                    result = f"🔑 Keys: {', '.join(res)}" if res else "No keys found"

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
                    if not args: result = "Usage: kyr <key>[.path]"
                    else:
                        result = self.kv.restore(args[0])

                elif cmd in ["kypush", "push"]:
                    if len(args) < 2: 
                        result = "Usage: kypush <key> <value> [--unique]"
                    else:
                        unique = "--unique" in args
                        val = args[1]
                        try: val = json.loads(val)
                        except: pass
                        result = self.kv.push(args[0], val, unique=unique)

                elif cmd in ["kyrem", "remove"]:
                    if not args: 
                        result = "Usage: kyrem <key> <value>"
                    else:
                        val = args[1]
                        try: val = json.loads(val)
                        except: pass
                        result = self.kv.remove(args[0], val)

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
                    if not args: result = "Usage: kyrt <timestamp> OR kyrt <key.path> --at <timestamp>"
                    elif "--at" in args:
                        idx = args.index("--at")
                        key_part = " ".join(args[:idx])
                        ts_part = " ".join(args[idx+1:])
                        result = self.kv.restore(key_part, timestamp=ts_part)
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
