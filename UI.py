import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
from NTFS import NTFS
from FAT32py import FAT32

class FileExplorerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("File System Explorer")
        self.root.geometry("1000x700")
        
        # Variables
        self.current_fs = None
        self.current_path = ""
        self.fs_type = None
        
        # Create UI
        self.create_widgets()
        
    def create_widgets(self):
        # Top panel with drive selection
        top_frame = ttk.Frame(self.root)
        top_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(top_frame, text="Select Drive:").pack(side=tk.LEFT)
        
        self.drive_var = tk.StringVar()
        self.drive_combobox = ttk.Combobox(top_frame, textvariable=self.drive_var, width=15)
        self.drive_combobox.pack(side=tk.LEFT, padx=5)
        self.drive_combobox.bind("<<ComboboxSelected>>", self.on_drive_selected)
        
        # self.fs_type_var = tk.StringVar()
        # ttk.Label(top_frame, text="Filesystem:").pack(side=tk.LEFT, padx=5)
        # self.fs_type_label = ttk.Label(top_frame, textvariable=self.fs_type_var, width=10)
        # self.fs_type_label.pack(side=tk.LEFT)
        
        self.load_button = ttk.Button(top_frame, text="Load", command=self.load_filesystem)
        self.load_button.pack(side=tk.LEFT, padx=5)
        
        
        # Main content area
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Tree view for navigation
        self.tree_frame = ttk.Frame(main_frame, width=300)
        self.tree_frame.pack(side=tk.LEFT, fill=tk.Y)
        
        self.tree = ttk.Treeview(self.tree_frame)
        self.tree.pack(fill=tk.BOTH, expand=True)
        
        self.tree_scroll = ttk.Scrollbar(self.tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=self.tree_scroll.set)
        
        self.tree.bind("<<TreeviewOpen>>", self.on_tree_open)
        self.tree.bind("<Double-1>", self.on_tree_double_click)
        
        # File details view
        self.details_frame = ttk.Frame(main_frame)
        self.details_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # File info panel
        self.info_frame = ttk.LabelFrame(self.details_frame, text="File Information")
        self.info_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.info_text = tk.Text(self.info_frame, height=10, wrap=tk.WORD)
        self.info_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # File content panel (for text files)
        self.content_frame = ttk.LabelFrame(self.details_frame, text="File Content")
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.content_text = tk.Text(self.content_frame, wrap=tk.WORD)
        self.content_scroll = ttk.Scrollbar(self.content_frame, orient=tk.VERTICAL, command=self.content_text.yview)
        self.content_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.content_text.configure(yscrollcommand=self.content_scroll.set)
        self.content_text.pack(fill=tk.BOTH, expand=True)
        
        # Status bar
        self.status_var = tk.StringVar()
        self.status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN)
        self.status_bar.pack(fill=tk.X, padx=5, pady=5)
        
        # Initialize
        self.populate_drives()

    def detect_filesystem(self, drive):
        """Detect whether the drive is NTFS or FAT32"""
        try:
            # Try reading as NTFS first
            ntfs = NTFS(r'\\.\\' + drive[0] + ':')
            if ntfs.open() and ntfs.read_boot_sector():
                ntfs.close()
                return "NTFS"
            
            # Try reading as FAT32
            fat32 = FAT32(r'\\.\\' + drive[0] + ':')
            # Check FAT32 signature (we'll read the first sector and check for FAT signature)
            with open(r'\\.\\' + drive[0] + ':', 'rb') as f:
                boot_sector = f.read(512)
                if boot_sector[510:512] == b'\x55\xAA':  # Boot sector signature
                    if boot_sector[82:86] == b'FAT32' or boot_sector[54:58] == b'FAT32':
                        return "FAT32"
                    elif boot_sector[54:57] == b'FAT':  # Older FAT versions
                        return "FAT32"  # We'll treat all FAT as FAT32 for simplicity
        except Exception as e:
            print(f"Error detecting filesystem: {e}")
        
        return "Unknown"
        
    def populate_drives(self):
        """Populate the drive combobox with available drives and their filesystems"""
        drives = []
        fs_types = []
        
        for drive in range(ord('A'), ord('Z')+1):
            drive_letter = chr(drive) + ":\\"
            if os.path.exists(drive_letter):
                drives.append(drive_letter)
                fs_type = self.detect_filesystem(drive_letter)
                fs_types.append(fs_type)
        
        # Create display values showing both drive letter and filesystem
        display_values = [f"{drive} ({fs})" for drive, fs in zip(drives, fs_types)]
        
        self.drive_combobox['values'] = display_values
        if drives:
            self.drive_combobox.current(0)
            # Set the detected filesystem
            # self.fs_type_var.set(fs_types[0])

    def on_drive_selected(self, event):
        """Update filesystem type when drive is selected"""
        selected = self.drive_combobox.get()
        if selected:
            # Extract filesystem type from the display text (in parentheses)
            fs_type = selected[selected.find("(")+1:selected.find(")")]
            # self.fs_type_var.set(fs_type)
    def load_filesystem(self):
        """Load the selected filesystem"""
        selected = self.drive_combobox.get()
        if not selected:
            messagebox.showerror("Error", "Please select a drive")
            return
            
        # Extract drive letter (first character)
        drive = selected[0] + ":\\"
        fs_type = self.drive_combobox.get().split('(')[1].split(')')[0]
        
        if fs_type == "Unknown":
            messagebox.showerror("Error", "Could not detect filesystem type")
            return
            
        try:
            if fs_type == "NTFS":
                self.current_fs = NTFS(r'\\.\\' + drive[0] + ':')
                self.current_fs.open()
                if not self.current_fs.read_boot_sector():
                    raise Exception("Failed to read NTFS boot sector")
                if not self.current_fs.scan_files():
                    raise Exception("Failed to scan NTFS files")
                    
            elif fs_type == "FAT32":
                self.current_fs = FAT32(r'\\.\\' + drive[0] + ':')
                
            self.fs_type = fs_type
            self.status_var.set(f"Loaded {fs_type} filesystem on {drive}")
            self.populate_tree()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load filesystem: {str(e)}")
            self.status_var.set("Error loading filesystem")
            
    def populate_tree(self):
        """Populate the tree view with filesystem structure"""
        self.tree.delete(*self.tree.get_children())
        
        if self.fs_type == "NTFS":
            # Add root node
            root_node = self.tree.insert("", "end", text=self.drive_var.get(), 
                                       values=("", "Volume", ""), open=True)
            
            # Add files/directories
            for file in self.current_fs.files:
                # print (self.current_fs.files)
                # if file.parent_ref == self.drive_var.get().split('\\')[-1] or file.parent_ref == 5:
                    if file.is_directory:
                        node = self.tree.insert(root_node, "end", text=file.name, 
                                              values=(file.size, "Directory", 
                                                     file.created.strftime('%Y-%m-%d %H:%M') if file.created else ""))
                        # Add dummy node to make it expandable
                        self.tree.insert(node, "end", text="Loading...")
                    else:
                        self.tree.insert(root_node, "end", text=file.name, 
                                       values=(file.size, "File", 
                                              file.created.strftime('%Y-%m-%d %H:%M') if file.created else ""))
                        
        elif self.fs_type == "FAT32":
            root_node = self.tree.insert("", "end", text=self.drive_var.get(), 
                                       values=("", "Volume", ""), open=True)
            
            # Get root directory entries
            entries = self.current_fs.read_directory(['rdet', 0x10, self.current_fs.rdet_cluster_begin, 0, '', 0, 0])
            
            for entry in entries:
                if describe_attributes(entry[1]) == 'D':  # Directory
                    node = self.tree.insert(root_node, "end", text=entry[0], 
                                          values=(entry[3], "Directory", 
                                                 self.current_fs.convert_fat_date_time(entry[5], entry[6])))
                    # Add dummy node to make it expandable
                    self.tree.insert(node, "end", text="Loading...")
                else:  # File
                    self.tree.insert(root_node, "end", text=entry[0], 
                                    values=(entry[3], "File", 
                                           self.current_fs.convert_fat_date_time(entry[5], entry[6])))
    
    def on_tree_open(self, event):
        """Handle tree node expansion"""
        item = self.tree.focus()
        if not item:
            return
            
        # Check if this node has a "Loading..." child
        children = self.tree.get_children(item)
        if children and self.tree.item(children[0])['text'] == "Loading...":
            self.tree.delete(children[0])  # Remove the dummy node
            
            path = self.get_path_from_item(item)
            
            if self.fs_type == "NTFS":
                # Find the NTFS file entry for this directory
                parent_name = self.tree.item(self.tree.parent(item))['text']
                dir_name = self.tree.item(item)['text']
                
                for file in self.current_fs.files:
                    if file.name == dir_name and file.is_directory:
                        # Add child entries
                        for child in self.current_fs.files:
                            if child.parent_ref == file.name:
                                if child.is_directory:
                                    node = self.tree.insert(item, "end", text=child.name, 
                                                          values=(child.size, "Directory", 
                                                                 child.created.strftime('%Y-%m-%d %H:%M') if child.created else ""))
                                    # Add dummy node to make it expandable
                                    self.tree.insert(node, "end", text="Loading...")
                                else:
                                    self.tree.insert(item, "end", text=child.name, 
                                                   values=(child.size, "File", 
                                                          child.created.strftime('%Y-%m-%d %H:%M') if child.created else ""))
                        break
                        
            elif self.fs_type == "FAT32":
                # Get the directory entries for this path
                entry = self.current_fs.travel_to(path)
                if entry[3] != -1:  # Valid directory
                    entries = self.current_fs.read_directory(entry)
                    
                    for entry in entries:
                        if describe_attributes(entry[1]) == 'D':  # Directory
                            node = self.tree.insert(item, "end", text=entry[0], 
                                                  values=(entry[3], "Directory", 
                                                         self.current_fs.convert_fat_date_time(entry[5], entry[6])))
                            # Add dummy node to make it expandable
                            self.tree.insert(node, "end", text="Loading...")
                        else:  # File
                            self.tree.insert(item, "end", text=entry[0], 
                                           values=(entry[3], "File", 
                                                  self.current_fs.convert_fat_date_time(entry[5], entry[6])))
    
    def on_tree_double_click(self, event):
        """Handle double-click on tree item"""
        item = self.tree.focus()
        if not item:
            return
            
        # Get file info
        values = self.tree.item(item)['values']
        if not values or len(values) < 2:
            return
            
        file_type = values[1]
        file_name = self.tree.item(item)['text']
        
        # Update info panel
        self.info_text.config(state=tk.NORMAL)
        self.info_text.delete(1.0, tk.END)
        
        path = self.get_path_from_item(item)
        
        if self.fs_type == "NTFS":
            # Find the NTFS file entry
            for file in self.current_fs.files:
                if file.name == file_name:
                    if file.parent_ref == self.drive_var.get().split('\\')[-1] or file.parent_ref == 5:
                        parent_path = self.drive_var.get()
                    else:
                        parent_path = file.parent_ref
                    
                    self.info_text.insert(tk.END, f"Name: {file.name}\n")
                    self.info_text.insert(tk.END, f"Type: {'Directory' if file.is_directory else 'File'}\n")
                    self.info_text.insert(tk.END, f"Size: {file.size} bytes\n")
                    self.info_text.insert(tk.END, f"Created: {file.created.strftime('%Y-%m-%d %H:%M:%S') if file.created else 'N/A'}\n")
                    self.info_text.insert(tk.END, f"Modified: {file.modified.strftime('%Y-%m-%d %H:%M:%S') if file.modified else 'N/A'}\n")
                    # self.info_text.insert(tk.END, f"Accessed: {file.accessed.strftime('%Y-%m-%d %H:%M:%S') if file.accessed else 'N/A'}\n")
                    self.info_text.insert(tk.END, f"Attributes: {', '.join(file.attributes)}\n")
                    self.info_text.insert(tk.END, f"Path: {path}\n")
                    
                    # Show content if it's a file and we have data
                    self.content_text.config(state=tk.NORMAL)
                    self.content_text.delete(1.0, tk.END)
                    
                    if not file.is_directory and file.data:
                        self.content_text.insert(tk.END, file.data)
                    elif not file.is_directory:
                        self.content_text.insert(tk.END, "[Binary content not displayed]")
                    else:
                        self.content_text.insert(tk.END, "[Directory content shown in tree]")
                    
                    self.content_text.config(state=tk.DISABLED)
                    break
                    
        elif self.fs_type == "FAT32":
            entry = self.current_fs.travel_to(path)
            if entry[3] != -1:  # Valid entry
                self.info_text.insert(tk.END, f"Name: {entry[0]}\n")
                self.info_text.insert(tk.END, f"Type: {'Directory' if describe_attributes(entry[1]) == 'D' else 'File'}\n")
                self.info_text.insert(tk.END, f"Size: {entry[3]} bytes\n")
                self.info_text.insert(tk.END, f"Created: {self.current_fs.convert_fat_date_time(entry[5], entry[6])}\n")
                self.info_text.insert(tk.END, f"Attributes: {describe_attributes(entry[1])}\n")
                self.info_text.insert(tk.END, f"Path: {path}\n")
                
                # Show content if it's a file
                self.content_text.config(state=tk.NORMAL)
                self.content_text.delete(1.0, tk.END)
                
                if describe_attributes(entry[1]) == 'D':
                    self.content_text.insert(tk.END, "[Directory content shown in tree]")
                else:
                    content = self.current_fs.read_file(entry, path)
                    self.content_text.insert(tk.END, content)
                
                self.content_text.config(state=tk.DISABLED)
        
        self.info_text.config(state=tk.DISABLED)
        self.status_var.set(f"Selected: {path}")
    
    def get_path_from_item(self, item):
        """Get the full path for a tree item"""
        path_parts = []
        while item:
            path_parts.append(self.tree.item(item)['text'])
            item = self.tree.parent(item)
        return '\\'.join(reversed(path_parts))
    
    def on_drive_selected(self, event):
        """Handle drive selection change"""
        # You could add auto-detection of filesystem type here
        pass

def describe_attributes(attr):
    """Describe FAT file entry attributes (copied from FAT32py.py)."""
    attributes = {
        0x10: 'D',  # Directory
        0x20: 'A',  # Archive
        0x01: 'R',  # Read-only
        0x02: 'H',  # Hidden
        0x04: 'S',  # System
    }
    return ''.join(value for key, value in attributes.items() if attr & key)

if __name__ == "__main__":
    root = tk.Tk()
    app = FileExplorerApp(root)
    root.mainloop()