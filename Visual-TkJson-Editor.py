import json
import copy
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import re

# Constants for dark mode theme
DARK_BG = "#2e2e2e"
DARK_FG = "#ffffff"
SELECT_BG = "#5a5a5a"

# Color for the insertion indicator (blue line)
INDICATOR_COLOR = "blue"
# Color used for transparency (must be unique)
TRANSPARENT_COLOR = "magenta"


class JSONModel:
    """Manages JSON data along with undo/redo functionality."""
    def __init__(self):
        self.data = {}
        self.undo_stack = []
        self.redo_stack = []

    def push_undo(self):
        self.undo_stack.append(copy.deepcopy(self.data))
        self.redo_stack.clear()

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(copy.deepcopy(self.data))
            self.data = self.undo_stack.pop()

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(copy.deepcopy(self.data))
            self.data = self.redo_stack.pop()

    def load_from_file(self, filename):
        with open(filename, "r") as f:
            self.data = json.load(f)

    def save_to_file(self, filename):
        with open(filename, "w") as f:
            json.dump(self.data, f, indent=2)


class DragDropHandler:
    """
    Handles drag-and-drop for the Treeview using a persistent transparent Toplevel
    for the insertion indicator.
    """
    def __init__(self, tree, editor):
        self.tree = tree
        self.editor = editor
        self.drag_item = None
        self.current_target = None
        self.drop_mode = None
        # Create a persistent Toplevel for the indicator.
        self.indicator = tk.Toplevel(editor)
        self.indicator.overrideredirect(True)
        self.indicator.attributes("-topmost", True)
        # Set up a transparent background.
        self.indicator.configure(bg=TRANSPARENT_COLOR)
        self.indicator.attributes("-transparentcolor", TRANSPARENT_COLOR)
        self.indicator.withdraw()  # Hide it initially

    def on_press(self, event):
        self.drag_item = self.tree.identify_row(event.y)

    def on_motion(self, event):
        if not self.drag_item:
            return
        target = self.tree.identify_row(event.y)
        # If target changes, clear any previous UI state.
        if target != self.current_target:
            if self.current_target:
                self.tree.item(self.current_target, tags=())
            self.current_target = target

        if target:
            bbox = self.tree.bbox(target)
            if bbox:
                y_top, height = bbox[1], bbox[3]
                rel_y = event.y - y_top
                # Determine mode based on relative Y position:
                if rel_y < height * 0.25:
                    mode = "insert_before"
                elif rel_y > height * 0.75:
                    mode = "insert_after"
                else:
                    mode = "nest"
                self.drop_mode = mode

                if mode == "nest":
                    # Nesting: show highlight on target and hide blue line.
                    self.tree.item(target, tags=("drop_target",))
                    self.indicator.withdraw()
                else:
                    # Reordering: clear any highlight and show blue line.
                    self.tree.item(target, tags=())
                    if mode == "insert_before":
                        indicator_y = bbox[1]
                    else:  # insert_after
                        indicator_y = bbox[1] + height
                    tree_x = self.tree.winfo_rootx()
                    tree_y = self.tree.winfo_rooty()
                    tree_width = self.tree.winfo_width()
                    self.indicator.geometry(f"{tree_width}x2+{tree_x}+{tree_y + indicator_y}")
                    # Ensure previous indicator canvas is removed.
                    if hasattr(self, 'indicator_canvas'):
                        self.indicator_canvas.destroy()
                    self.indicator_canvas = tk.Canvas(self.indicator, bg=INDICATOR_COLOR,
                                                       highlightthickness=0)
                    self.indicator_canvas.pack(fill=tk.BOTH, expand=True)
                    self.indicator.deiconify()
            else:
                self.drop_mode = None
                self.indicator.withdraw()
                self.tree.item(target, tags=())
        else:
            self.current_target = None
            self.drop_mode = None
            self.indicator.withdraw()

    def on_release(self, event):
        self.indicator.withdraw()
        if self.current_target:
            self.tree.item(self.current_target, tags=())
        if not self.drag_item:
            return
        drop_item = self.tree.identify_row(event.y)
        if not drop_item or drop_item == self.drag_item:
            self.drag_item = None
            self.current_target = None
            return
        # Delegate moving logic to the editor based on current drop_mode.
        self.editor.advanced_move(self.drag_item, drop_item, self.drop_mode)
        self.drag_item = None
        self.current_target = None


class JsonEditor(tk.Tk):
    """
    A Visual JSON Editor (Dark Mode) using tkinter with:
      • Inline syntax highlighting
      • Find/Replace support
      • Advanced drag-and-drop with a lean, modern UI:
          - Uses a persistent transparent Toplevel for the insertion indicator
      • Undo/Redo functionality.
    """
    def __init__(self):
        super().__init__()
        self.title("Visual TkJSON Editor (Dark Mode)")
        self.geometry("900x600")
        self.configure(bg=DARK_BG)

        self.model = JSONModel()
        self.item_to_path = {}  # Maps tree item IDs to JSON key paths (lists)
        self.text_update_job = None

        self.create_widgets()
        self.bind_events()

    def create_widgets(self):
        # Create a PanedWindow for two panes.
        self.paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, bg=DARK_BG)
        self.paned.pack(fill=tk.BOTH, expand=True)

        # Left frame for the tree view.
        self.left_frame = tk.Frame(self.paned, bg=DARK_BG)
        self.paned.add(self.left_frame, minsize=200)

        # Right frame for the text editor.
        self.right_frame = tk.Frame(self.paned, bg=DARK_BG)
        self.paned.add(self.right_frame, minsize=200)

        # Configure Treeview style.
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview",
                        background=DARK_BG,
                        foreground=DARK_FG,
                        fieldbackground=DARK_BG,
                        bordercolor=DARK_BG,
                        borderwidth=0)
        style.map("Treeview", background=[("selected", SELECT_BG)])

        # Create the Treeview widget.
        self.tree = ttk.Treeview(self.left_frame, columns=("value",), selectmode="extended")
        self.tree.heading("#0", text="Key")
        self.tree.heading("value", text="Value")
        self.tree.column("value", stretch=True)
        self.tree.pack(fill=tk.BOTH, expand=True)

        # Tag for drop target highlighting.
        self.tree.tag_configure("drop_target", background="gray50")

        # Create the tree context menu.
        self.tree_menu = tk.Menu(self, tearoff=0, bg=DARK_BG, fg=DARK_FG)
        self.tree_menu.add_command(label="Add Child", command=self.add_child_node)
        self.tree_menu.add_command(label="Delete Node and Contents", command=self.delete_node_and_contents)
        self.tree_menu.add_command(label="Delete Node and Transfer Contents", command=self.delete_node_and_transfer)
        self.tree_menu.add_command(label="Group Nodes", command=self.group_nodes)

        # Create the Text widget for raw JSON editing.
        self.text = tk.Text(self.right_frame, wrap=tk.NONE, bg=DARK_BG, fg=DARK_FG,
                            insertbackground=DARK_FG)
        self.text.pack(fill=tk.BOTH, expand=True)

        # Create text widget context menu.
        self.text_menu = tk.Menu(self, tearoff=0, bg=DARK_BG, fg=DARK_FG)
        self.text_menu.add_command(label="Update Visual", command=self.update_from_text_manual)

        self.create_menu_bar()

    def create_menu_bar(self):
        menubar = tk.Menu(self, bg=DARK_BG, fg=DARK_FG)
        file_menu = tk.Menu(menubar, tearoff=0, bg=DARK_BG, fg=DARK_FG)
        file_menu.add_command(label="Open", command=self.load_json)
        file_menu.add_command(label="Save", command=self.save_json)
        menubar.add_cascade(label="File", menu=file_menu)
        edit_menu = tk.Menu(menubar, tearoff=0, bg=DARK_BG, fg=DARK_FG)
        edit_menu.add_command(label="Refresh Tree", command=self.refresh_tree)
        edit_menu.add_command(label="Find/Replace", command=self.show_find_replace_dialog)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        self.config(menu=menubar)

    def bind_events(self):
        self.bind("<Control-z>", lambda e: self.undo())
        self.bind("<Control-y>", lambda e: self.redo())
        self.text.bind("<Button-3>", self.on_text_right_click)
        self.text.bind("<KeyRelease>", self.on_text_change)
        self.tree.bind("<Double-1>", self.on_tree_double_click)
        self.tree.bind("<Button-3>", self.on_tree_right_click)
        # Bind drag-and-drop events using the new handler.
        self.dragdrop_handler = DragDropHandler(self.tree, self)
        self.tree.bind("<ButtonPress-1>", self.dragdrop_handler.on_press)
        self.tree.bind("<B1-Motion>", self.dragdrop_handler.on_motion)
        self.tree.bind("<ButtonRelease-1>", self.dragdrop_handler.on_release)

    def show_error(self, message):
        messagebox.showerror("Error", message)

    def load_json(self):
        filename = filedialog.askopenfilename(filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not filename:
            return
        try:
            self.model.load_from_file(filename)
            self.update_text_editor()
            self.refresh_tree()
        except Exception as e:
            self.show_error(f"Failed to load JSON:\n{e}")

    def save_json(self):
        filename = filedialog.asksaveasfilename(defaultextension=".json",
                                                filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not filename:
            return
        try:
            self.model.save_to_file(filename)
        except Exception as e:
            self.show_error(f"Failed to save JSON:\n{e}")

    def refresh_tree(self):
        # Save expansion state.
        expanded = set()
        def save_expansion(item):
            if self.tree.item(item, "open"):
                path = tuple(self.item_to_path.get(item, []))
                expanded.add(path)
            for child in self.tree.get_children(item):
                save_expansion(child)
        for item in self.tree.get_children():
            save_expansion(item)
        self.tree.delete(*self.tree.get_children())
        self.item_to_path = {}
        self.insert_items("", "root", self.model.data, [])
        def restore_expansion(item):
            path = tuple(self.item_to_path.get(item, []))
            if path in expanded:
                self.tree.item(item, open=True)
            for child in self.tree.get_children(item):
                restore_expansion(child)
        for item in self.tree.get_children():
            restore_expansion(item)

    def insert_items(self, parent, key, item, path):
        display_key = key if key != "" else "root"
        if isinstance(item, dict):
            node_id = self.tree.insert(parent, "end", text=display_key, values=("{...}",))
            self.item_to_path[node_id] = path.copy()
            for k, v in item.items():
                self.insert_items(node_id, k, v, path + [k])
        elif isinstance(item, list):
            node_id = self.tree.insert(parent, "end", text=display_key, values=("[...]",))
            self.item_to_path[node_id] = path.copy()
            for index, elem in enumerate(item):
                self.insert_items(node_id, str(index), elem, path + [index])
        else:
            node_id = self.tree.insert(parent, "end", text=display_key, values=(item,))
            self.item_to_path[node_id] = path.copy()

    def get_value_by_path(self, path):
        try:
            value = self.model.data
            for p in path:
                value = value[p]
            return value
        except Exception as e:
            self.show_error(f"Failed to get value by path {path}: {e}")
            return None

    def set_value_by_path(self, path, new_value):
        try:
            target = self.model.data
            for p in path[:-1]:
                target = target[p]
            target[path[-1]] = new_value
        except Exception as e:
            self.show_error(f"Failed to set value by path {path}: {e}")

    def update_text_editor(self):
        current_scroll = self.text.yview()
        self.text.delete("1.0", tk.END)
        json_content = json.dumps(self.model.data, indent=2)
        self.text.insert(tk.END, json_content)
        self.highlight_syntax()
        self.text.yview_moveto(current_scroll[0])

    def highlight_syntax(self):
        # Remove previous syntax tags.
        for tag in self.text.tag_names():
            if tag.startswith("syntax_"):
                self.text.tag_remove(tag, "1.0", tk.END)
        content = self.text.get("1.0", tk.END)
        string_pattern = r'("([^"\\]*(\\.[^"\\]*)*)")'
        number_pattern = r'\b\d+(\.\d+)?\b'
        boolean_pattern = r'\b(true|false|null)\b'
        for match in re.finditer(string_pattern, content):
            start = "1.0+%dc" % match.start()
            end = "1.0+%dc" % match.end()
            self.text.tag_add("syntax_string", start, end)
        for match in re.finditer(number_pattern, content):
            start = "1.0+%dc" % match.start()
            end = "1.0+%dc" % match.end()
            self.text.tag_add("syntax_number", start, end)
        for match in re.finditer(boolean_pattern, content, re.IGNORECASE):
            start = "1.0+%dc" % match.start()
            end = "1.0+%dc" % match.end()
            self.text.tag_add("syntax_boolean", start, end)
        self.text.tag_configure("syntax_string", foreground="#ce9178")
        self.text.tag_configure("syntax_number", foreground="#b5cea8")
        self.text.tag_configure("syntax_boolean", foreground="#569cd6")

    def on_tree_double_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region not in ("cell", "tree"):
            return
        column = "#0" if region == "tree" else self.tree.identify_column(event.x)
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return
        bbox = self.tree.bbox(item_id, column)
        if not bbox:
            return
        entry = tk.Entry(self.tree, bg=DARK_BG, fg=DARK_FG)
        entry.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
        current_text = (self.tree.item(item_id, "text") if column=="#0" 
                        else (self.tree.item(item_id, "values")[0] if self.tree.item(item_id, "values") else ""))
        entry.insert(0, current_text)
        entry.focus_set()
        def commit_edit(event=None):
            new_text = entry.get()
            entry.destroy()
            self.model.push_undo()
            if column=="#0":
                self.update_tree_item_key(item_id, new_text)
            else:
                self.update_tree_item_value(item_id, new_text)
            self.update_text_editor()
        entry.bind("<Return>", commit_edit)
        entry.bind("<FocusOut>", lambda e: commit_edit())

    def update_tree_item_key(self, item_id, new_key):
        path = self.item_to_path.get(item_id)
        if not path or path == []:
            self.show_error("Cannot edit root key")
            return
        old_key = path[-1]
        if new_key == old_key:
            return
        parent_path = path[:-1]
        parent = self.get_value_by_path(parent_path)
        if new_key in parent:
            self.show_error("Key already exists")
            return
        # For dicts, rebuild while preserving order
        if isinstance(parent, dict):
            new_parent = {}
            for k, v in parent.items():
                if k == old_key:
                    new_parent[new_key] = v
                else:
                    new_parent[k] = v
            parent.clear()
            parent.update(new_parent)
        else:
            parent[new_key] = parent.pop(old_key)

        def update_paths(item, old_key, new_key):
            p = self.item_to_path.get(item)
            if p and p[-1] == old_key:
                p[-1] = new_key
                self.item_to_path[item] = p
            for child in self.tree.get_children(item):
                update_paths(child, old_key, new_key)

        update_paths(item_id, old_key, new_key)
        self.tree.item(item_id, text=new_key)

    def update_tree_item_value(self, item_id, new_text):
        path = self.item_to_path.get(item_id)
        try:
            new_value = json.loads(new_text)
        except Exception:
            new_value = new_text
        self.set_value_by_path(path, new_value)
        self.tree.item(item_id, values=(new_value,))

    def on_tree_right_click(self, event):
        clicked_item = self.tree.identify_row(event.y)
        if not clicked_item:
            return
        if clicked_item not in self.tree.selection():
            self.tree.selection_set(clicked_item)
        self.configure_tree_menu(clicked_item)
        try:
            self.tree_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.tree_menu.grab_release()

    def configure_tree_menu(self, clicked_item):
        selected = self.tree.selection()
        if len(selected) > 1:
            self.tree_menu.entryconfig("Group Nodes", state="normal")
        else:
            self.tree_menu.entryconfig("Group Nodes", state="disabled")
        if len(selected) == 1:
            path = self.item_to_path.get(clicked_item, [])
            if not path or path == []:
                self.tree_menu.entryconfig("Delete Node and Contents", state="disabled")
                self.tree_menu.entryconfig("Delete Node and Transfer Contents", state="disabled")
            else:
                self.tree_menu.entryconfig("Delete Node and Contents", state="normal")
                self.tree_menu.entryconfig("Delete Node and Transfer Contents", state="normal")
        else:
            self.tree_menu.entryconfig("Delete Node and Contents", state="disabled")
            self.tree_menu.entryconfig("Delete Node and Transfer Contents", state="disabled")

    def advanced_move(self, source_item, drop_item, drop_mode):
        """Moves a node from source to target based on the drop mode, preserving order."""
        self.model.push_undo()
        source_path = self.item_to_path.get(source_item)
        if not source_path or source_path == []:
            self.show_error("Cannot move root node.")
            return
        source_parent_path = source_path[:-1]
        source_key = source_path[-1]
        source_container = self.get_value_by_path(source_parent_path)
        try:
            if isinstance(source_container, list):
                source_index = int(source_key)
                item_value = source_container.pop(source_index)
            elif isinstance(source_container, dict):
                item_value = source_container.pop(source_key)
            else:
                self.show_error("Unsupported source container type.")
                return
        except Exception as e:
            self.show_error(f"Error removing item: {e}")
            return

        target_path = self.item_to_path.get(drop_item)
        if target_path is None:
            self.show_error("Invalid drop target.")
            return
        target_value = self.get_value_by_path(target_path)
        if isinstance(target_value, (list, dict)):
            target_container = target_value
        else:
            parent_drop_item = self.tree.parent(drop_item)
            if not parent_drop_item:
                self.show_error("Invalid drop target.")
                return
            target_path = self.item_to_path.get(parent_drop_item)
            if target_path is None:
                self.show_error("Invalid drop target.")
                return
            target_container = self.get_value_by_path(target_path)

        same_container = (source_container is target_container)

        if isinstance(target_container, list):
            try:
                base_index = int(self.item_to_path.get(drop_item)[-1])
            except Exception:
                base_index = len(target_container)
            # Adjust index when moving within the same list.
            if same_container and isinstance(source_container, list) and source_index < base_index:
                base_index -= 1
            if drop_mode == "insert_before":
                drop_index = base_index
            elif drop_mode == "insert_after":
                drop_index = base_index + 1
            elif drop_mode == "nest":
                drop_value = self.get_value_by_path(self.item_to_path.get(drop_item))
                if isinstance(drop_value, list):
                    drop_value.append(item_value)
                    self.refresh_tree()
                    self.update_text_editor()
                    return
                elif isinstance(drop_value, dict):
                    new_key = source_key if isinstance(source_key, str) else "item"
                    counter = 1
                    orig_key = new_key
                    while new_key in drop_value:
                        new_key = f"{orig_key}_{counter}"
                        counter += 1
                    drop_value[new_key] = item_value
                    self.refresh_tree()
                    self.update_text_editor()
                    return
                else:
                    drop_index = len(target_container)
            else:
                drop_index = len(target_container)
            if drop_index > len(target_container):
                drop_index = len(target_container)
            target_container.insert(drop_index, item_value)

        elif isinstance(target_container, dict):
            if same_container:
                # Reorder within the same dict.
                keys = list(target_container.keys())
                try:
                    target_key = self.item_to_path.get(drop_item)[-1]
                    j = keys.index(target_key)
                except ValueError:
                    j = len(keys)
                new_index = j if drop_mode == "insert_before" else j + 1
                new_container = {}
                inserted = False
                for idx, k in enumerate(keys):
                    if idx == new_index:
                        new_container[source_key] = item_value
                        inserted = True
                    new_container[k] = target_container[k]
                if not inserted:
                    new_container[source_key] = item_value
                target_container.clear()
                target_container.update(new_container)
            else:
                # Moving into a different dict: choose a new key if needed.
                new_key = source_key if isinstance(source_key, str) else "item"
                counter = 1
                orig_key = new_key
                while new_key in target_container:
                    new_key = f"{orig_key}_{counter}"
                    counter += 1
                target_container[new_key] = item_value
        else:
            self.show_error("Unsupported target container type.")
            return

        self.refresh_tree()
        self.update_text_editor()

    def delete_node_and_contents(self):
        selected = self.tree.selection()
        if len(selected) != 1:
            self.show_error("Please select a single node to delete.")
            return
        self.model.push_undo()
        item_id = selected[0]
        path = self.item_to_path.get(item_id)
        if not path or path == []:
            self.show_error("Cannot delete root node.")
            return
        parent_value = self.get_value_by_path(path[:-1])
        key_to_delete = path[-1]
        if isinstance(parent_value, dict):
            del parent_value[key_to_delete]
        elif isinstance(parent_value, list):
            try:
                index = int(key_to_delete)
            except Exception:
                index = key_to_delete
            del parent_value[index]
        self.refresh_tree()
        self.update_text_editor()

    def delete_node_and_transfer(self):
        selected = self.tree.selection()
        if len(selected) != 1:
            self.show_error("Please select a single node to delete.")
            return
        self.model.push_undo()
        item_id = selected[0]
        path = self.item_to_path.get(item_id)
        if not path or path == []:
            self.show_error("Cannot delete root node.")
            return
        node_data = self.get_value_by_path(path)
        parent_value = self.get_value_by_path(path[:-1])
        if isinstance(parent_value, dict):
            if not isinstance(node_data, dict):
                self.show_error("Node content is not a dict and cannot be merged into parent dict.")
                return
            for k in node_data:
                if k in parent_value:
                    self.show_error(f"Key conflict: {k} already exists in parent.")
                    return
            parent_value.update(node_data)
            del parent_value[path[-1]]
        elif isinstance(parent_value, list):
            if not isinstance(node_data, list):
                self.show_error("Node content is not a list and cannot be merged into parent list.")
                return
            try:
                index = int(path[-1])
            except Exception:
                self.show_error("Invalid index for parent list.")
                return
            parent_value.pop(index)
            for offset, item in enumerate(node_data):
                parent_value.insert(index + offset, item)
        else:
            self.show_error("Unsupported parent container type.")
            return
        self.refresh_tree()
        self.update_text_editor()

    def group_nodes(self):
        selected = self.tree.selection()
        if len(selected) < 2:
            self.show_error("Please select at least two nodes to group.")
            return
        groups = {}
        for item in selected:
            parent_path = tuple(self.item_to_path.get(item, [])[:-1])
            groups.setdefault(parent_path, []).append(item)
        group_name = simpledialog.askstring("Group Nodes", "Enter group name:")
        if not group_name:
            return
        self.model.push_undo()
        for parent_path, items in groups.items():
            parent_value = self.get_value_by_path(list(parent_path))
            if isinstance(parent_value, dict):
                new_group = {}
                for item in items:
                    path = self.item_to_path.get(item)
                    key = path[-1]
                    new_group[key] = self.get_value_by_path(path)
                    del parent_value[key]
                final_group_name = group_name
                counter = 1
                while final_group_name in parent_value:
                    final_group_name = f"{group_name}_{counter}"
                    counter += 1
                parent_value[final_group_name] = new_group
            elif isinstance(parent_value, list):
                indices = []
                for item in items:
                    try:
                        indices.append(int(self.item_to_path.get(item)[-1]))
                    except Exception:
                        continue
                if not indices:
                    continue
                indices.sort()
                new_group = []
                for idx in reversed(indices):
                    new_group.insert(0, parent_value.pop(idx))
                parent_value.insert(indices[0], {group_name: new_group})
            else:
                self.show_error("Unsupported parent container type for grouping.")
                return
        self.refresh_tree()
        self.update_text_editor()

    def add_child_node(self):
        selected = self.tree.selection()
        if len(selected) > 1:
            self.show_error("Please select a single node to add a child.")
            return
        parent_item = selected[0] if selected else ""
        parent_path = self.item_to_path.get(parent_item, []) if parent_item else []
        parent_value = self.get_value_by_path(parent_path)
        if isinstance(parent_value, dict):
            new_key = simpledialog.askstring("Add Child", "Enter key for new child:")
            if not new_key:
                return
            if new_key in parent_value:
                self.show_error("Key already exists.")
                return
            self.model.push_undo()
            parent_value[new_key] = ""
        elif isinstance(parent_value, list):
            self.model.push_undo()
            parent_value.append("")
        else:
            self.show_error("Cannot add child to a non-container type.")
            return
        self.refresh_tree()
        self.update_text_editor()

    def on_text_right_click(self, event):
        try:
            self.text_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.text_menu.grab_release()

    def update_from_text_manual(self):
        self.update_from_text_auto()

    def on_text_change(self, event=None):
        if self.text_update_job:
            self.after_cancel(self.text_update_job)
        self.text_update_job = self.after(500, self.update_from_text_auto)

    def update_from_text_auto(self):
        content = self.text.get("1.0", tk.END)
        try:
            new_data = json.loads(content)
            self.model.data = new_data
            self.refresh_tree()
            self.text.configure(bg=DARK_BG)
            self.highlight_syntax()
        except Exception:
            self.text.configure(bg="#ffcccc")

    def undo(self):
        self.model.undo()
        self.refresh_tree()
        self.update_text_editor()

    def redo(self):
        self.model.redo()
        self.refresh_tree()
        self.update_text_editor()

    def show_find_replace_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("Find and Replace")
        dialog.geometry("400x150")
        dialog.configure(bg=DARK_BG)
        tk.Label(dialog, text="Find:", bg=DARK_BG, fg=DARK_FG).pack(pady=5)
        find_entry = tk.Entry(dialog, bg=DARK_BG, fg=DARK_FG, insertbackground=DARK_FG)
        find_entry.pack(fill=tk.X, padx=10)
        tk.Label(dialog, text="Replace:", bg=DARK_BG, fg=DARK_FG).pack(pady=5)
        replace_entry = tk.Entry(dialog, bg=DARK_BG, fg=DARK_FG, insertbackground=DARK_FG)
        replace_entry.pack(fill=tk.X, padx=10)

        def find_next():
            self.text.tag_remove("find_match", "1.0", tk.END)
            search_term = find_entry.get()
            if not search_term:
                return
            start = "1.0"
            pos = self.text.search(search_term, start, stopindex=tk.END)
            if pos:
                end_pos = f"{pos}+{len(search_term)}c"
                self.text.tag_add("find_match", pos, end_pos)
                self.text.tag_configure("find_match", background="#444444")
                self.text.see(pos)

        def replace():
            search_term = find_entry.get()
            replace_term = replace_entry.get()
            if not search_term:
                return
            content = self.text.get("1.0", tk.END)
            new_content = content.replace(search_term, replace_term)
            self.text.delete("1.0", tk.END)
            self.text.insert(tk.END, new_content)
            self.highlight_syntax()

        def replace_all():
            search_term = find_entry.get()
            replace_term = replace_entry.get()
            if not search_term:
                return
            content = self.text.get("1.0", tk.END)
            new_content = content.replace(search_term, replace_term)
            self.text.delete("1.0", tk.END)
            self.text.insert(tk.END, new_content)
            self.highlight_syntax()

        btn_frame = tk.Frame(dialog, bg=DARK_BG)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="Find Next", command=find_next, bg=DARK_BG, fg=DARK_FG).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Replace", command=replace, bg=DARK_BG, fg=DARK_FG).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Replace All", command=replace_all, bg=DARK_BG, fg=DARK_FG).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Close", command=dialog.destroy, bg=DARK_BG, fg=DARK_FG).pack(side=tk.LEFT, padx=5)


if __name__ == "__main__":
    app = JsonEditor()
    app.mainloop()
