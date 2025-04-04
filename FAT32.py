import os
import psutil

def little_endian(data: bytes) -> bytes:
    return data[::-1]

def raw_to_dec(data: bytes) -> int:
    return int.from_bytes(data, 'little')

def read_sectors(file_path: str, start_sector: int = 0, num_sectors: int = 1, bytes_per_sector: int = 512) -> bytes:
    """Read one or more sectors from file."""
    with open(file_path, 'rb') as fp:
        fp.seek(bytes_per_sector * start_sector)
        return fp.read(bytes_per_sector * num_sectors)

def read_offset(buffer: bytes, offset: int, size: int, to_int: bool = False, to_hex: bool = False):
    """Read a part of buffer at offset with given size."""
    data = buffer[offset:offset + size]
    if to_int:
        return raw_to_dec(data)
    if to_hex:
        return data.hex()
    return data

def read_dec_offset(buffer: bytes, offset: int, size: int) -> int:
    return read_offset(buffer, offset, size, to_int=True)

def read_hex_offset(buffer: bytes, offset: int, size: int) -> str:
    return read_offset(buffer, offset, size, to_hex=True)

def read_bin_offset(buffer: bytes, offset: int, size: int) -> bytes:
    return read_offset(buffer, offset, size)

def read_list_sectors(file_path: str, sectors: list, bytes_per_sector: int) -> bytes:
    """Read a list of sectors and concatenate their content."""
    data = b''
    for sector in sectors:
        data += read_sectors(file_path, sector, 1, bytes_per_sector)
    return data

def describe_attributes(attr: int) -> str:
    """Describe FAT file entry attributes."""
    attributes = {
        0x10: 'D',  # Directory
        0x20: 'A',  # Archive
        0x01: 'R',  # Read-only
        0x02: 'H',  # Hidden
        0x04: 'S',  # System
    }
    return ''.join(value for key, value in attributes.items() if attr & key)

def process_fat_lfn(entries: list) -> str:
    name = b''.join(
        read_offset(entry, 1, 10) +
        read_offset(entry, 0xE, 12) +
        read_offset(entry, 0x1C, 4)
        for entry in entries
    )
    return name.decode('utf-16le', errors='ignore').split('\x00', 1)[0]

def print_hex_dump(data: bytes):
    for offset in range(0, len(data), 16):
        chunk = data[offset:offset+16]
        hex_chunk = ' '.join(f'{byte:02X}' for byte in chunk)
        ascii_chunk = ''.join(chr(byte) if 32 <= byte <= 126 else '.' for byte in chunk)
        print(f'{offset:08X}: {hex_chunk.ljust(48)}  {ascii_chunk}')

def convert_fat_date(date_val: int) -> str:
    year = ((date_val >> 9) & 0x7F) + 1980
    month = (date_val >> 5) & 0x0F
    day = date_val & 0x1F
    return f"{year:04d}-{month:02d}-{day:02d}"

def convert_fat_time(time_val: int) -> str:
    hour = (time_val >> 11) & 0x1F
    minute = (time_val >> 5) & 0x3F
    second = (time_val & 0x1F) * 2
    return f"{hour:02d}:{minute:02d}:{second:02d}"

class FAT32:
    def __init__(self, path):
        self.path = path
        bootsector = read_sectors(path, 0, 1, 512)
        self.n_bytes_sector = read_dec_offset(bootsector, 0x0B, 2)
        self.n_sectors_cluster = read_dec_offset(bootsector, 0x0D, 1)
        self.n_sectors_bootsector = read_dec_offset(bootsector, 0x0E, 2)
        self.n_fat_tables = read_dec_offset(bootsector, 0x10, 1)
        self.volume_size = read_dec_offset(bootsector, 0x20, 4)
        self.n_sectors_fat_table = read_dec_offset(bootsector, 0x24, 4)
        self.rdet_cluster_begin = read_dec_offset(bootsector, 0x2C, 4)
        self.sub_sector = read_dec_offset(bootsector, 0x30, 2)
        self.n_sectors_store_bootsector = read_dec_offset(bootsector, 0x32, 2)
        # FAT32 layout: BOOT SECTOR -> RESERVED -> FAT TABLE -> ROOT DIRECTORY -> DATA AREA    
        self.rdet_sector_begin = self.n_sectors_bootsector + self.n_fat_tables * self.n_sectors_fat_table
        self.data_sector_begin = self.rdet_sector_begin
        self.fat_data = read_sectors(self.path, self.n_sectors_bootsector, self.n_sectors_fat_table, self.n_bytes_sector)
        
    # def bootsector(self):
    #     print("FAT32 BOOT SECTOR")
    #     print(" - Bytes/sector: ", self.n_bytes_sector)
    #     print(" - Sectors/cluster: ", self.n_sectors_cluster)
    #     print(" - Sectors/boot sector: ", self.n_sectors_bootsector)
    #     print(" - FAT Table: ", self.n_fat_tables)
    #     print(" - Sectors in disk: ", self.volume_size)
    #     print(" - Sectors in FAT table: ", self.n_sectors_fat_table)
    #     print(" - RDET Cluster Begin: ", self.rdet_cluster_begin)
    #     print(" - RDET Sector Begin: ", self.rdet_sector_begin)
    #     print(" - Subsector: ", self.sub_sector)
    #     print(" - Sector Store Boot sector: ", self.n_sectors_store_bootsector)
        
    def cluster_to_sectors(self, cluster_n):
        sector_begin = (self.n_sectors_bootsector + self.n_fat_tables * self.n_sectors_fat_table 
                        + (cluster_n - 2) * self.n_sectors_cluster)
        return [sector_begin + i for i in range(self.n_sectors_cluster)]
    
    def sectors_chain(self, cluster_begin):
        cluster_n = cluster_begin
        sectors_chain = []
        eof_markers = {0x00000000, 0xFFFFFF0, 0xFFFFFFF, 0xFFFFFF7, 0xFFFFFF8, 0xFFFFFFF0}
        while cluster_n not in eof_markers:
            sectors_chain += self.cluster_to_sectors(cluster_n)
            fat_offset = cluster_n * 4
            fat_entry_bytes = self.fat_data[fat_offset:fat_offset + 4]
            cluster_n = raw_to_dec(fat_entry_bytes)
        return sectors_chain
    
    def read_entry(self, buffer):
        name = read_bin_offset(buffer, 0, 8).decode('utf-8', errors='ignore').strip()
        attr = read_dec_offset(buffer, 0xB, 1)
        cluster_begin = read_dec_offset(buffer, 0x1A, 2)
        size = read_dec_offset(buffer, 0x1C, 4)
        e5 = read_hex_offset(buffer, 0, 1)
        creation_time = read_dec_offset(buffer, 14, 2)
        creation_date = read_dec_offset(buffer, 16, 2)
        return name, attr, cluster_begin, size, e5, creation_date, creation_time
    
    def read_directory(self, entry):
        sectors = self.sectors_chain(entry[2])
        buffer = read_list_sectors(self.path, sectors, self.n_bytes_sector)
        # Skip the first two entries if needed (adjust as in your original code)
        buffer = buffer[32*2:]
        entries = []
        sub_entries = []
        for i in range(0, len(buffer), 32):
            entry_bytes = buffer[i:i+32]
            ent = self.read_entry(entry_bytes)
            if ent[1] != 15:  # Not LFN entry
                if sub_entries:
                    sub_name = process_fat_lfn(sub_entries)
                    ent = list(ent)
                    ent[0] = sub_name
                    sub_entries.clear()
                else:
                    ent = list(ent)
                    ent[0] = ent[0].lower()
                if ent[4] not in ['00', 'e5']:
                    entries.append(tuple(ent))
            else:
                sub_entries.insert(0, entry_bytes)
        return entries
    
    def print_text_file(self, entry):
        sectors = self.sectors_chain(entry[2])
        content_txt_file = read_list_sectors(self.path, sectors, self.n_bytes_sector)
        content_txt_file = content_txt_file[:entry[3]]
        print(content_txt_file.decode('utf-8', errors='ignore'))

    
    def travel_to(self, path):
        directories = path.split('\\')
        entry = ['rdet', 0x10, self.rdet_cluster_begin, 0, '', 0, 0]
        for directory in directories:
            entries = self.read_directory(entry)
            found = False
            for ent in entries:
                if directory == ent[0]:
                    entry = ent
                    found = True
                    break
            if not found:
                return ['', 0x04, '', -1, '', 0, 0]
        return entry 
    
    def read_file(self, entry, path):
        apps = {
            'pptx': 'PowerPoint',
            'csv': 'Spreadsheet Software',
            'json': 'Text Editor or JSON Viewer',
            'pdf': 'PDF Reader',
            'jpg': 'Image Viewer',
            'mp3': 'Audio Player',
            'mp4': 'Video Player',
            'png': 'Photos'
        }
        if describe_attributes(entry[1]) == "A" and entry[3] != -1:
            self.print_text_file(entry)
        else:
            file_extension = path.split('.')[-1].lower()   
            suggested_application = apps.get(file_extension, 'Unknown app')
            print("We currently do not support reading this file. You can use:", suggested_application)
    
    def read_path(self, path):
        if path == 'rdet':
            entry = ['rdet', 0x10, self.rdet_cluster_begin, 1, '', 0, 0]
        else:
            entry = self.travel_to(path)
            if entry[3] == -1:
                print(path, "is invalid")
                return
        print("---")
        print("PATH INFORMATION")
        print("NAME: ", entry[0])
        if describe_attributes(entry[1]) == 'D':
            print("ATTRIBUTE: Directory")
        elif describe_attributes(entry[1]) == 'A':
            print("ATTRIBUTE: File/Archive")
        # print("CLUSTER BEGIN: ", entry[2])
        created_date = convert_fat_date(entry[5])
        created_time = convert_fat_time(entry[6])
        print("Created on: ", created_date, created_time)
        print("SIZE: ", entry[3])
        print("---")
        print("PATH CONTENT: ")
        if describe_attributes(entry[1]) == 'D':
            self.print_directory(self.read_directory(entry))
        else:
            self.read_file(entry, path)
    
    def draw_tree(self, path, indent='', is_last=True):
        if path != 'rdet':
            entry_begin = self.travel_to(path)
        else:
            entry_begin = ['rdet', 0x10, self.rdet_cluster_begin, 1, '', 0, 0]
        if describe_attributes(entry_begin[1]) != 'D' or entry_begin[3] == -1:
            print(path, ": is invalid!")
            return
        print(indent, end='')
        if is_last:
            print("└── ", end='')
            indent += "    "
        else:
            print("├── ", end='')
            indent += "│   "
        print(entry_begin[0])
        entries = self.read_directory(entry_begin)
        for i, entry in enumerate(entries):
            last = (i == len(entries) - 1)
            if describe_attributes(entry[1]) == 'D':
                item_path = path + "\\" + entry[0] if path != 'rdet' else entry[0]
                self.draw_tree(item_path, indent, last)
            else:
                print(indent, end='')
                print("└── " if last else "├── ", end='')
                print(entry[0])