import os
import psutil
from OS_DISK_READER.FAT32 import FAT32

def list_logical_disks():
    return [
        {'mountpoint': partition.mountpoint, 'filesystem_type': partition.fstype}
        for partition in psutil.disk_partitions(all=True)
    ]

class NTFS:
    def __init__(self, path):
        print("...")
    def draw_tree(self, path, indent='', is_last=True):
        print("...")
    def read_path(self, path):
        print("...")

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def main_screen():
    print("1. Automatically detect the format of each partition:")
    logical_disks = list_logical_disks()
    for disk in logical_disks:
        print(f"Disk: {disk['mountpoint']}, Filesystem Type: {disk['filesystem_type']}")
        
    drive_letter = input("\nInput drive name (e.g., C): ").strip()
    fs_type = ""
    found_disk = False
    for disk in logical_disks:
        if drive_letter.upper() == disk['mountpoint'][0]:
            fs_type = disk['filesystem_type']
            found_disk = True
            break
    if not found_disk:
        print(f"No disk found for drive: {drive_letter}")
        return
    
    path = r'\\.\\' + drive_letter.upper() + ":"
    if fs_type == "FAT32":
        drive = FAT32(path)
    else:
        drive = NTFS(path)
    
    clear_screen() 
    while True:
        print("\n-WORKING WITH DRIVE", path.upper(), f"({fs_type})")
        print("MENU") 
        print("2. Draw a tree of a particular directory ('rdet' if FAT32 / '5' if NTFS / path of a directory)")
        print("3. Display the content of a file or a directory.")
        print("4. Quit") 
        choice = input("Please input your choice: ").strip()
        if choice == '2':
            directory = input("Please enter a directory path: ").strip()
            drive.draw_tree(directory)
        elif choice == '3':
            path_to_file = input("Please enter a path: ").strip()
            drive.read_path(path_to_file)
        elif choice == '4':
            print("Quit")
            break
        else:
            print("Invalid choice, please choose again!")

if __name__ == "__main__":
    main_screen()
