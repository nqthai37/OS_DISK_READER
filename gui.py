import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import os
import psutil
from FAT32 import FAT32
from FAT32 import describe_attributes, convert_fat_date, convert_fat_time
from NTFS import NTFS

class DiskExplorerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Disk Explorer")
        self.root.geometry("900x700")
        
        # Variables
        self.drive_var = tk.StringVar()
        self.fs_type_var = tk.StringVar()
        self.path_var = tk.StringVar(value="rdet")
        self.drive = None
        
        # Create main frames
        self.create_disk_selection_frame()
        self.create_explorer_frame()
        self.create_content_frame()
        
        # Initialize with disk selection
        self.setup_tree_expansion()
        self.populate_disk_list()
    
    def create_disk_selection_frame(self):
        frame = ttk.LabelFrame(self.root, text="Disk Selection", padding=10)
        frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        
        ttk.Label(frame, text="Available Disks:").grid(row=0, column=0, sticky="w")
        self.disk_combobox = ttk.Combobox(frame, textvariable=self.drive_var, state="readonly")
        self.disk_combobox.grid(row=0, column=1, padx=5, sticky="ew")
        
        ttk.Label(frame, text="Filesystem:").grid(row=0, column=2, padx=5, sticky="w")
        ttk.Label(frame, textvariable=self.fs_type_var).grid(row=0, column=3, padx=5, sticky="w")
        
        ttk.Button(frame, text="Select Disk", command=self.select_disk).grid(row=0, column=4, padx=5)
        
        # Configure grid weights
        frame.columnconfigure(1, weight=1)
    
    def create_explorer_frame(self):
        frame = ttk.LabelFrame(self.root, text="Explorer", padding=10)
        frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        
        # Tree view for directory structure
        self.tree = ttk.Treeview(frame, columns=("size", "type", "date"), show="tree")
        self.tree.heading("#0", text="Name")
        self.tree.heading("size", text="Size")
        self.tree.heading("type", text="Type")
        self.tree.heading("date", text="Created")
        
        # Configure column widths
        self.tree.column("#0", width=300)
        self.tree.column("size", width=100)
        self.tree.column("type", width=100)
        self.tree.column("date", width=150)
        
        # Add scrollbars
        yscroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        
        # Grid layout
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        
        # Bind double click event
        self.tree.bind("<Double-1>", self.on_tree_item_double_click)
        
        # Configure grid weights
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
    
    def create_content_frame(self):
        frame = ttk.LabelFrame(self.root, text="Content Viewer", padding=10)
        frame.grid(row=0, column=1, rowspan=2, padx=10, pady=10, sticky="nsew")
        
        # Path display
        ttk.Label(frame, text="Current Path:").grid(row=0, column=0, sticky="w")
        self.path_entry = ttk.Entry(frame, textvariable=self.path_var, state="readonly")
        self.path_entry.grid(row=0, column=1, sticky="ew", pady=5)
        
        # Content display
        self.content_text = scrolledtext.ScrolledText(frame, wrap=tk.WORD, width=50, height=30)
        self.content_text.grid(row=1, column=0, columnspan=2, sticky="nsew")
        
        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=5, sticky="ew")
        
        ttk.Button(btn_frame, text="View Tree", command=self.view_tree).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="View Content", command=self.view_content).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Clear", command=self.clear_content).pack(side=tk.LEFT, padx=5)
        
        # Configure grid weights
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(1, weight=1)
    
    def populate_disk_list(self):
        disks = []
        for partition in psutil.disk_partitions(all=True):
            if partition.mountpoint:
                disk = f"{partition.mountpoint} ({partition.fstype})"
                disks.append((partition.mountpoint, partition.fstype, disk))
        
        self.disk_info = {disk[2]: (disk[0], disk[1]) for disk in disks}
        self.disk_combobox["values"] = list(self.disk_info.keys())
        
        if disks:
            self.disk_combobox.current(0)
            self.update_disk_info()
    
    def update_disk_info(self):
        selected = self.disk_combobox.get()
        if selected in self.disk_info:
            mountpoint, fstype = self.disk_info[selected]
            self.drive_var.set(mountpoint)
            self.fs_type_var.set(fstype)
    
    def select_disk(self):
        selected = self.disk_combobox.get()
        if not selected:
            messagebox.showwarning("Warning", "Please select a disk first")
            return
        
        mountpoint, fstype = self.disk_info[selected]
        path = rf"\\.\{mountpoint[0].upper()}:"
        
        try:
            if fstype == "FAT32":
                self.drive = FAT32(path)
            else:
                self.drive = NTFS(path)
            
            self.path_var.set("rdet" if fstype == "FAT32" else "5")
            self.populate_tree()
            self.view_content()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to access disk: {str(e)}")
            
    def populate_tree(self):
        if not self.drive:
            return
        
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        root_text = "Root Directory" if self.fs_type_var.get() == "FAT32" else "MFT Root"
        root_id = self.tree.insert("", "end", text=root_text, values=("", "Directory", ""), open=True)
        
        self.drive.draw_tree(self.tree, root_id, self.path_var.get())
    
    def add_tree_items(self, parent_id, path):
        if not self.drive:
            return
        
        try:
            entries = self.drive.read_directory(self.drive.travel_to(path))
            
            for entry in entries:
                name = entry[0]
                size = entry[3]
                attr = entry[1]
                date = self.convert_fat_date_time(entry[5], entry[6])
                
                if describe_attributes(attr) == 'D':  # Directory
                    item_id = self.tree.insert(
                        parent_id, "end", text=name, 
                        values=(size, "Directory", date)
                    )
                    # Add a dummy child to make it expandable
                    self.tree.insert(item_id, "end", text="Loading...")
                else:  # File
                    self.tree.insert(
                        parent_id, "end", text=name, 
                        values=(size, "File", date)
                    )
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read directory: {str(e)}")
    
    def on_tree_item_double_click(self, event):
        item = self.tree.focus()
        item_text = self.tree.item(item, "text")
        item_values = self.tree.item(item, "values")
        
        # Skip if it's the "Loading..." placeholder
        if item_text == "Loading...":
            return
        
        # Get the full path of the selected item
        path_parts = [item_text]
        parent = self.tree.parent(item)
        
        while parent:
            parent_text = self.tree.item(parent, "text")
            if parent_text not in ["Root Directory", "MFT Root"]:
                path_parts.insert(0, parent_text)
            parent = self.tree.parent(parent)
        
        full_path = "\\".join(path_parts)
        
        # Update path variable
        self.path_var.set(full_path)
        
        # If it's a directory, expand it
        if item_values[1] == "Directory":
            # Clear existing children (the "Loading..." placeholder)
            for child in self.tree.get_children(item):
                self.tree.delete(child)
            
            # Add actual children
            self.add_tree_items(item, full_path)
        
        # Show content
        self.view_content()
    
    def view_tree(self):
        path = self.path_var.get()
        if not self.drive:
            messagebox.showwarning("Warning", "Please select a disk first")
            return
        
        try:
            self.populate_tree(path=path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to draw tree: {str(e)}")
    
    def view_content(self):
        path = self.path_var.get()
        if not self.drive:
            messagebox.showwarning("Warning", "Please select a disk first")
            return
        
        self.content_text.delete(1.0, tk.END)
        
        try:
            entry = self.drive.travel_to(path)
            if entry[3] == -1:
                self.content_text.insert(tk.END, f"Path '{path}' is invalid")
                return
            
            # Display path information
            self.content_text.insert(tk.END, "---\nPATH INFORMATION\n")
            self.content_text.insert(tk.END, f"NAME: {entry[0]}\n")
            
            if describe_attributes(entry[1]) == 'D':
                self.content_text.insert(tk.END, "ATTRIBUTE: Directory\n")
            elif describe_attributes(entry[1]) == 'A':
                self.content_text.insert(tk.END, "ATTRIBUTE: File/Archive\n")
            
            created_date = convert_fat_date(entry[5])
            created_time = convert_fat_time(entry[6])
            self.content_text.insert(tk.END, f"Created on: {created_date} {created_time}\n")
            self.content_text.insert(tk.END, f"SIZE: {entry[3]}\n")
            self.content_text.insert(tk.END, "---\nPATH CONTENT:\n")
            
            if describe_attributes(entry[1]) == 'D':
                entries = self.drive.read_directory(entry)
                for ent in entries:
                    self.content_text.insert(tk.END, f"{ent[0]}\n")
            else:
                # Get file content and display it
                content = self.drive.read_file(entry, path)
                self.content_text.insert(tk.END, content)  # Add this line
    
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read path: {str(e)}")
    
    def clear_content(self):
        self.content_text.delete(1.0, tk.END)
    
    def convert_fat_date_time(self, date_val, time_val):
        if date_val == 0 and time_val == 0:
            return ""
        date_str = convert_fat_date(date_val)
        time_str = convert_fat_time(time_val)
        return f"{date_str} {time_str}"
    
    
    def setup_tree_expansion(self):
        """Setup event handling for tree expansion"""
        self.tree.bind('<<TreeviewOpen>>', self.on_tree_expand)

    def on_tree_expand(self, event):
        """Handle tree node expansion"""
        item = self.tree.focus()
        
        # Check if this node has a "Loading..." child
        children = self.tree.get_children(item)
        if children and self.tree.item(children[0], 'text') == "Loading...":
            # Remove the placeholder
            self.tree.delete(children[0])
            
            # Get the full path of the expanded item
            path_parts = [self.tree.item(item, 'text')]
            parent = self.tree.parent(item)
            
            while parent:
                parent_text = self.tree.item(parent, 'text')
                if parent_text not in ["Root Directory", "MFT Root"]:
                    path_parts.insert(0, parent_text)
                parent = self.tree.parent(parent)
            
            full_path = "\\".join(path_parts)
            
            # Draw the contents of this directory
            self.drive.draw_tree(self.tree, item, full_path)


if __name__ == "__main__":
    root = tk.Tk()
    app = DiskExplorerApp(root)
    root.mainloop()