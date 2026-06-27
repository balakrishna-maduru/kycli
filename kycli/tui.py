import os
import sys
import threading
import warnings
from datetime import datetime
from prompt_toolkit import Application
from prompt_toolkit.layout import Layout, HSplit, VSplit, Window, FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.widgets import Frame, TextArea
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import ANSI, HTML
from prompt_toolkit.completion import Completer, Completion
from rich.console import Console
from rich.table import Table
from io import StringIO
import json

from kycli import Kycore
from kycli.config import load_config, save_config, get_workspaces
from kycli.cli import get_help_text, _start_metrics_server
from kycli.logging_utils import get_logger
from kycli.utils import coerce_value, try_parse_json

logger = get_logger("kycli.tui")

COMMAND_NAMES = [
    "kyuse", "kyws", "kymv", "kydrop", "kys", "kyg", "kypatch", "kyl", "kyd",
    "kypush", "kyrem", "kypeek", "kypop", "kyack", "kynack", "kycount", "kyclear",
    "kyfo", "kyshell", "kyh", "kye", "kyi", "kyc", "kyv", "kyr", "kyrt", "kyco",
    "kyrotate", "kyttl", "kyacl", "kyprofile", "kystats", "kybackup", "kymetrics",
    "kyaudit", "exit", "quit",
]

WORKSPACE_ARG_COMMANDS = {"kyuse", "kydrop"}


class KycliCompleter(Completer):
    """Tab-completion for command names, and workspace names as the second
    token of `kyuse`/`kydrop`."""

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        words = text.split(" ")
        if len(words) <= 1:
            word = words[0] if words else ""
            for cmd in COMMAND_NAMES:
                if cmd.startswith(word):
                    yield Completion(cmd, start_position=-len(word))
        elif len(words) == 2 and words[0] in WORKSPACE_ARG_COMMANDS:
            word = words[1]
            try:
                for ws in get_workspaces():
                    if ws.startswith(word):
                        yield Completion(ws, start_position=-len(word))
            except Exception:
                return


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
            completer=KycliCompleter(),
            complete_while_typing=True,
        )

        # Set up command handling
        self.input_field.accept_handler = self.handle_command

        # Styles
        self.style = Style.from_dict({
            "frame.border": "#4444ff",
            "input-field": "bold", # Removed #ffffff for adaptive theme
        })

        # Layout
        self.history_frame = Frame(Window(content=self.history_area, wrap_lines=True), title="Audit Trail")
        
        # Status Bar
        self.status_bar = FormattedTextControl(text="")
        
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
                        '<style color="cyan">kypush/kypop</style>   : Queue/Stack ops\n'
                        '<style color="cyan">kyttl/kyacl</style>    : TTL/ACL policy\n'
                        '<style color="cyan">kystats/kybackup</style> : Stats/Backup\n'
                        '<style color="cyan">kyh</style>         : Full Help\n'
                        '<style color="red">exit/quit</style>   : Quit Shell\n\n'
                        '<b><style color="yellow">SECURITY</style></b>\n'
                        '<style color="gray">Use --key &lt;k&gt; or set</style>\n'
                        '<style color="gray">KYCLI_MASTER_KEY env.</style>'
                    )
                )), title="Quick Help", width=35),
            ], height=Dimension(weight=1)),
            Frame(Window(content=self.output_area, wrap_lines=True), title="Results", height=Dimension(weight=1)),
            self.input_field,
            Window(content=self.status_bar, height=1, style="class:status-bar"),
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
        db = os.path.basename(self.db_path)
        user = os.environ.get("USER", "kycli")
        
        # Update Prompt
        new_prompt = HTML(f'<style color="ansigreen">kycli</style>(<style color="ansiblue">{ws}</style>)> ')
        # We handle prompt update by recreating the TextArea logic or finding a way to update it.
        # TextArea doesn't support dynamic prompt easily without recreating or subclassing?
        # Actually, prompt is a buffer prefix. Let's try just setting it.
        # Wait, TextArea.__init__ takes prompt. To update it we might need to access the control or just simulate it.
        # A simpler way: update the bottom Status Bar and Title.
        
        self.history_frame.title = f"Audit Trail [{ws}]"
        
        # Update Status Bar Text
        status_text = HTML(
            f' <b>User:</b> {user} | '
            f'<b>Workspace:</b> <style color="ansiblue">{ws}</style>'
        )
        self.status_bar.text = status_text
        
        # HACK: Update prompt text physically? prompt_toolkit TextArea prompt is static str usually?
        # Let's check prompt_toolkit TextArea docs mentally. It creates a Window with BufferControl.
        # To change prompt dynamically, we can reconstruct the input_field or just accept static prompt "kycli> "
        # and rely on the status bar for context.
        # BUT user asked for "kycli(workspace)> ".
        # We can implement get_prompt function for TextArea or just update the window.
        # Since we initialized it with a string, let's try to update `window.content.buffer_control...?`
        # Actually easier: The TextArea helper class is high level. Let's just live with static prompt OR 
        # use the Window directly.
        # Let's sticking to Status Bar for now to avoid breaking UI loop, as requested in roadmap Phase 1.

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
                logger.info("command=%s workspace=%s", cmd, self.config.get("active_workspace", "default"))
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
                            self.db_path = new_db_path # <--- Update instance variable
                            self.kv = Kycore(db_path=new_db_path)
                            self.update_status() # Refresh title and footer
                            self.input_field.buffer.cursor_position = 0 
                            self.update_history() # Refresh history for new DB
                            result = f"➡️ Switched to workspace: {target}"
                            
                elif cmd in ["kydrop", "drop"]:
                    if not args:
                        result = "Usage: kydrop <workspace> [--confirm]"
                    else:
                        target = args[0]
                        ws = self.config.get("active_workspace", "default")
                        is_active = (target == ws)
                        
                        from kycli.config import DATA_DIR
                        target_db = os.path.join(DATA_DIR, f"{target}.db")
                        
                        if not os.path.exists(target_db):
                            result = f"❌ Workspace '{target}' not found."
                        elif "--confirm" not in args:
                            msg = f"⚠️  To delete '{target}', add --confirm flag."
                            if is_active:
                                msg += " (Active workspace will be switched to 'default')"
                            result = msg
                        else:
                            try:
                                os.remove(target_db)
                                result = f"✅ Workspace '{target}' deleted."
                                if is_active:
                                    save_config({"active_workspace": "default"})
                                    self.config = load_config()
                                    self.db_path = self.config.get("db_path")
                                    self.kv = Kycore(db_path=self.db_path)
                                    self.update_status()
                                    self.update_history()
                                    result += "\n🔄 Switched to 'default' workspace."
                            except Exception as e:
                                result = f"Error: {e}"

                elif cmd in ["kyws", "workspaces"]:
                    if args and args[0] == "view":
                        if len(args) < 2:
                            result = "Usage: kyws view <prefix>"
                        else:
                            result = json.dumps(self.kv.view_prefix(args[1]), indent=2)
                    elif args and args[0] == "create":
                        if len(args) < 2:
                            result = "Usage: kyws create <workspace> --type <queue|stack|priority_queue>"
                        else:
                            target = args[1]
                            wtype = "kv"
                            if "--type" in args:
                                idx = args.index("--type")
                                if idx + 1 < len(args):
                                    wtype = args[idx + 1]
                            from kycli.config import DATA_DIR
                            target_db = os.path.join(DATA_DIR, f"{target}.db")
                            try:
                                with Kycore(db_path=target_db) as target_kv:
                                    target_kv.set_type(wtype)
                                result = f"✅ Workspace '{target}' created with type '{wtype}'."
                            except Exception as e:
                                result = f"❌ Failed to create workspace: {e}"
                    else:
                        wss = get_workspaces()
                        ws = self.config.get("active_workspace", "default")
                        lines = ["📂 Workspaces:"]
                        for ws_item in wss:
                            marker = "✨ " if ws_item == ws else "   "
                            lines.append(f"{marker}{ws_item}")
                        result = "\n".join(lines)

                elif cmd in ["kymv", "mv", "move"]:
                    if len(args) < 2:
                        result = "Usage: kymv <key> <target_workspace>"
                    else:
                        key, target_ws = args[0], args[1]
                        ws = self.config.get("active_workspace", "default")
                        if target_ws == ws:
                            result = "⚠️ Source and target workspaces are the same."
                        else:
                            val = self.kv.getkey(key)
                            if val == "Key not found":
                                result = f"❌ Key '{key}' not found in '{ws}'."
                            else:
                                from kycli.config import DATA_DIR
                                target_db = os.path.join(DATA_DIR, f"{target_ws}.db")
                                with Kycore(db_path=target_db) as target_kv:
                                    target_kv.save(key, val)
                                self.kv.delete(key)
                                result = f"✅ Moved '{key}' to '{target_ws}'."

                elif cmd in ["kyttl"]:
                    if not args:
                        result = "Usage: kyttl set|get [ttl]"
                    elif args[0] == "get":
                        result = str(self.kv.get_default_ttl())
                    elif args[0] == "set" and len(args) > 1:
                        result = f"✅ Default TTL set to {self.kv.set_default_ttl(args[1])}"
                    else:
                        result = "Usage: kyttl set|get [ttl]"

                elif cmd in ["kyacl"]:
                    if not args:
                        result = "Usage: kyacl readonly on|off|status OR kyacl key set|get|clear [value]"
                    elif args[0] == "readonly":
                        if len(args) < 2 or args[1] == "status":
                            result = "on" if self.kv.get_read_only() else "off"
                        else:
                            enabled = args[1].lower() == "on"
                            self.kv.set_read_only(enabled)
                            result = f"✅ Read-only {'enabled' if enabled else 'disabled'}."
                    elif args[0] == "key" and len(args) > 1:
                        if args[1] == "get":
                            result = self.kv.get_access_key() or ""
                        elif args[1] == "clear":
                            self.kv.set_access_key(None)
                            result = "✅ Access key cleared."
                        elif args[1] == "set" and len(args) > 2:
                            self.kv.set_access_key(args[2])
                            result = "✅ Access key set."
                        else:
                            result = "Usage: kyacl key set|get|clear [value]"
                    else:
                        result = "Usage: kyacl readonly on|off|status OR kyacl key set|get|clear [value]"

                elif cmd in ["kyprofile"]:
                    from kycli.config import save_profile, use_profile, list_profiles, load_config as _load_config
                    if not args:
                        result = "Usage: kyprofile list|use|save <name>"
                    elif args[0] == "list":
                        result = "\n".join(list_profiles())
                    elif len(args) < 2:
                        result = "Usage: kyprofile list|use|save <name>"
                    elif args[0] == "use":
                        use_profile(args[1])
                        result = f"✅ Active profile set to '{args[1]}'."
                    elif args[0] == "save":
                        raw_config = _load_config()
                        save_profile(args[1], {
                            "active_workspace": raw_config.get("active_workspace", "default"),
                            "export_format": raw_config.get("export_format", "csv"),
                        })
                        result = f"✅ Saved profile '{args[1]}'."
                    else:
                        result = "Usage: kyprofile list|use|save <name>"

                elif cmd in ["kyrotate", "rotate"]:
                    new_key = None
                    old_key = None
                    dry_run = "--dry-run" in args
                    backup_flag = "--backup" in args
                    if "--new-key" in args:
                        idx = args.index("--new-key")
                        if idx + 1 < len(args):
                            new_key = args[idx + 1]
                    if "--old-key" in args:
                        idx = args.index("--old-key")
                        if idx + 1 < len(args):
                            old_key = args[idx + 1]
                    if not new_key:
                        result = "Usage: kyrotate --new-key <key> [--old-key <key>] [--dry-run] [--backup]"
                    else:
                        count = self.kv.rotate_master_key(new_key, old_key=old_key, dry_run=dry_run, backup=backup_flag)
                        result = f"🧪 Dry run: {count} values would be re-encrypted." if dry_run else f"✅ Rotation complete. Re-encrypted {count} values."

                elif cmd in ["kystats"]:
                    result = json.dumps(self.kv.get_stats(), indent=2)

                elif cmd in ["kybackup"]:
                    if not args:
                        result = "Usage: kybackup <file> OR kybackup restore <file>"
                    elif args[0] == "restore":
                        if len(args) < 2:
                            result = "Usage: kybackup restore <file>"
                        else:
                            self.kv.restore_backup(args[1])
                            result = f"✅ Backup restored from {args[1]}"
                    else:
                        result = f"✅ Backup created: {self.kv.backup(args[0])}"

                elif cmd in ["kymetrics"]:
                    port = args[0] if args else "8765"
                    _start_metrics_server(self.kv, port)
                    result = f"✅ Metrics endpoint started on http://127.0.0.1:{port}"

                elif cmd in ["kyaudit"]:
                    if not args or args[0] != "export" or len(args) < 2:
                        result = "Usage: kyaudit export <file> [format]"
                    else:
                        fmt = args[2] if len(args) > 2 else "json"
                        count = self.kv.export_audit(args[1], fmt=fmt)
                        result = f"📤 Exported {count} audit rows."
                
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
                        val = coerce_value(val, json_mode="startswith")
                        
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
                    if not args:
                        result = "Usage: kyr <key>[.path] [--at <timestamp>]"
                    elif "--at" in args:
                        idx = args.index("--at")
                        key_part = " ".join(args[:idx])
                        ts_part = " ".join(args[idx + 1:])
                        result = self.kv.restore(key_part, timestamp=ts_part)
                    else:
                        result = self.kv.restore(args[0])

                elif cmd in ["kypush", "push"]:
                    wtype = self.kv.get_type()
                    if wtype != "kv":
                        priority = None
                        delay = None
                        value_args = []
                        skip = False
                        for i, a in enumerate(args):
                            if skip:
                                skip = False
                                continue
                            if a == "--priority" and i + 1 < len(args):
                                try: priority = int(args[i + 1])
                                except ValueError: pass
                                skip = True
                            elif a == "--delay" and i + 1 < len(args):
                                delay = args[i + 1]
                                skip = True
                            else:
                                value_args.append(a)
                        if not value_args:
                            result = "Usage: kypush <value> [--priority N] [--delay <ttl>]"
                        else:
                            val = try_parse_json(" ".join(value_args))
                            result = self.kv.push(val, priority=priority, ttl=delay)
                    elif len(args) < 2:
                        result = "Usage: kypush <key> <value> [--unique]"
                    else:
                        unique = "--unique" in args
                        val = args[1]
                        val = try_parse_json(val)
                        result = self.kv.push(args[0], val, unique=unique)

                elif cmd in ["kypeek", "peek"]:
                    result = str(self.kv.peek())

                elif cmd in ["kypop", "pop"]:
                    lease = None
                    count = 1
                    skip = False
                    for i, a in enumerate(args):
                        if skip:
                            skip = False
                            continue
                        if a == "--lease" and i + 1 < len(args):
                            lease = args[i + 1]
                            skip = True
                        elif a == "--n" and i + 1 < len(args):
                            try: count = int(args[i + 1])
                            except ValueError: pass
                            skip = True
                    result = str(self.kv.pop(count=count, lease=lease))

                elif cmd in ["kyack"]:
                    if not args: result = "Usage: kyack <receipt_id>"
                    else: result = self.kv.ack(args[0])

                elif cmd in ["kynack"]:
                    if not args:
                        result = "Usage: kynack <receipt_id> [--delay <ttl>]"
                    else:
                        delay = None
                        if "--delay" in args:
                            idx = args.index("--delay")
                            if idx + 1 < len(args):
                                delay = args[idx + 1]
                        result = self.kv.nack(args[0], delay=delay)

                elif cmd in ["kycount", "count"]:
                    result = str(self.kv.count())

                elif cmd in ["kyclear", "clear"]:
                    if "--confirm" not in args:
                        result = "⚠️  This clears the current queue/stack. Re-run with --confirm."
                    else:
                        result = self.kv.clear()

                elif cmd in ["kyrem", "remove"]:
                    if not args: 
                        result = "Usage: kyrem <key> <value>"
                    else:
                        val = args[1]
                        val = try_parse_json(val)
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
                logger.exception("tui_command_failed")
                result = f"Error: {e}"
            
            # Combine warnings and result
            if w:
                warn_msgs = []
                for warn in w:
                    msg = warn.message if hasattr(warn, 'message') else str(warn)
                    warn_msgs.append(f"⚠️ {msg}")
                result = "\n".join(warn_msgs) + ("\n" + result if result else "")

        self.output_area.text = result
        buffer.text = ""
        self.update_history()

    def run(self):
        self.app.run()

def start_shell(db_path=None):
    shell = KycliShell(db_path)
    shell.run()
