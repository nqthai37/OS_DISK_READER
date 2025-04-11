import struct
import datetime
from collections import namedtuple
import logging
import sys
import lznt1  

# Constants
NTFS_SIGNATURE = b'NTFS    '
SECTOR_SIZE = 512


# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class NTFSFileEntry:
    def __init__(self):
        self.name = None
        self.used_size = 0
        self.size = 0
        self.created = None
        self.created_time = None
        self.created_date = None
        self.modified = None
        self.is_non_resident = False
        self.attributes = []
        self.is_directory = False
        self.parent_ref = None
        self.record_number = -1
        self.data = None
        self.ID = None
        self.data_runs = []
        self.is_sparse = False
        self.is_compressed = False
        self.compression_unit_size = 0  # Default 16 clusters per compression unit


class NTFS:
    def __init__(self, disk_path):
        self.disk_path = disk_path
        self.partition_offset = 0
        self.disk = None
        self.boot_sector = None
        self.bytes_per_cluster = 0
        self.cluster_size = 0
        self.files = []
        self.volume_serial = None
        self.mft_record_size = 0
        self.mft_cluster = 0

    def __enter__(self):
        self.open()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        
    def open(self):
        try:
            self.disk = open(self.disk_path, 'rb', buffering=0)
            logger.info(f"Successfully opened {self.disk_path}")
            return True
        except PermissionError:
            logger.error("Permission denied. Try running as Administrator.")
            return False
        except Exception as e:
            logger.error(f"Error opening disk: {e}")
            return False
            
    def close(self):
        if self.disk:
            self.disk.close()
            self.disk = None
            
    def read_boot_record(self):
        try:
            self.disk.seek(self.partition_offset * SECTOR_SIZE)
            data = self.disk.read(SECTOR_SIZE)
            
            if len(data) < 512:
                raise ValueError("Couldn't read full boot sector")
            
            if data[3:11] != NTFS_SIGNATURE:
                raise ValueError("Not a valid NTFS filesystem")
                
            bytes_per_sector = struct.unpack('<H', data[11:13])[0]
            if bytes_per_sector != 512 and bytes_per_sector != 4096:
                raise ValueError(f"Unsupported sector size: {bytes_per_sector}")
                
            sectors_per_cluster = struct.unpack('<B', data[13:14])[0]
            mft_record_size_raw = struct.unpack('<b', data[64:65])[0]
            
            mft_record_size = (2 ** abs(mft_record_size_raw) 
                             if mft_record_size_raw < 0 
                             else mft_record_size_raw * 1024)
            
            self.boot_sector = namedtuple('NTFSBootSector', [
                'oem_id', 'bytes_per_sector', 'sectors_per_cluster',
                'mft_cluster', 'mft_mirror_cluster', 'mft_record_size',
                'volume_serial', 'checksum'
            ])(
                oem_id=data[3:11].decode('ascii'),
                bytes_per_sector=bytes_per_sector,
                sectors_per_cluster=sectors_per_cluster,
                mft_cluster=struct.unpack('<Q', data[48:56])[0],
                mft_mirror_cluster=struct.unpack('<Q', data[56:64])[0],
                mft_record_size=mft_record_size,
                volume_serial=struct.unpack('<Q', data[72:80])[0],
                checksum=struct.unpack('<I', data[80:84])[0]
            )

            self.bytes_per_cluster = (self.boot_sector.bytes_per_sector 
                                    * self.boot_sector.sectors_per_cluster)
            self.cluster_size = (self.boot_sector.sectors_per_cluster 
                               * self.boot_sector.bytes_per_sector)
            self.volume_serial = self.boot_sector.volume_serial
            
            logger.info("Successfully read NTFS boot sector")
            return True
            
        except Exception as e:
            logger.error(f"Error reading boot sector: {e}")
            return False
            
    def read_mft_record(self, record_number):
        try:
            mft_offset = self.boot_sector.mft_cluster * self.bytes_per_cluster
            record_offset = record_number * self.boot_sector.mft_record_size
            absolute_offset = (self.partition_offset * self.boot_sector.bytes_per_sector 
                              + mft_offset 
                              + record_offset)
            # 2160C00
            if absolute_offset < 0:
                raise ValueError(f"Invalid negative offset: {absolute_offset}")
            
            # absolute_offset= 0x2160C00
            self.disk.seek(absolute_offset)
            record_data = self.disk.read(self.boot_sector.mft_record_size)
            
            if len(record_data) < 42:
                logger.debug(f"Record {record_number} too small")
                return None
                
            if record_data[0:4] != b'FILE':
                return None
            return record_data
            
        except Exception as e:
            logger.error(f"Error reading MFT record {record_number}: {e}")
            return None
            
    def parse_file_entry(self, record_data, record_number):
        try:
            entry = NTFSFileEntry()
            entry.record_number = record_number
            entry.flag = struct.unpack('<H', record_data[22:24])[0]
            entry.used_size = struct.unpack('<I', record_data[32:36])[0]
            entry.size = struct.unpack('<I', record_data[40:44])[0]
            entry.ID = struct.unpack('<I', record_data[44:48])[0]
            
            attr_offset = struct.unpack('<H', record_data[20:22])[0]
            
            while attr_offset + 24 <= len(record_data):
                attr_type = struct.unpack('<I', record_data[attr_offset:attr_offset+4])[0]
                attr_length = struct.unpack('<I', record_data[attr_offset+4:attr_offset+8])[0]
                # print (attr_offset, attr_length, attr_type)
                content_length = struct.unpack('<I', record_data[attr_offset+16:attr_offset+20])[0]
                is_non_resident = struct.unpack('<B', record_data[attr_offset+8:attr_offset+9])[0]
                # print (is_non_resident)
                content_offset = struct.unpack('<H', record_data[attr_offset+20:attr_offset+22])[0]
                content_offset += attr_offset
                if is_non_resident == 1:
                    entry.is_non_resident = True
                if attr_type == 0xFFFFFFFF or attr_length == 0:
                    break

                if attr_offset + attr_length > len(record_data):
                    logger.warning(f"Attribute at offset {attr_offset} exceeds record boundary")
                    break
                    
                attr_data = record_data[content_offset:content_offset+attr_length]
                
                self.parse_attribute(entry, attr_type, attr_data)
                
                attr_offset += attr_length
                
            return entry if entry.name else None
            
        except Exception as e:
            logger.error(f"Error parsing record {record_number}: {e}")
            return None
        
    def parse_attribute(self, entry, attr_type, attr_data):
        try:
            if attr_type == 0x10:  # Standard Information
                if len(attr_data) >= 48:
                    entry.created = self.parse_ntfs_time(struct.unpack('<Q', attr_data[0:8])[0])
                    entry.created_time = entry.created.strftime('%H:%M:%S') if entry.created else None
                    entry.created_date = entry.created.strftime('%Y-%m-%d') if entry.created else None
                    entry.modified = self.parse_ntfs_time(struct.unpack('<Q', attr_data[8:16])[0])
                    
            elif attr_type == 0x30:  # File Name
                if len(attr_data) >= 66:
                    padding = b'\x00\x00'
                    parent_ref = struct.unpack('<Q', attr_data[0:6]+ padding)[0]
                    for file in self.files:
                        if file.ID == parent_ref:
                            parent_ref = file.name
                        elif parent_ref == 5:
                            parent_ref = self.disk_path.split('\\')[-1]
                    
                    flags = struct.unpack('<I', attr_data[56:60])[0]
                    bin_flags = bin(flags)[2:].zfill(32)
                    attributes_offset = [0,1,2,5,28]
                    attributes_names = ["Read-Only", "Hidden", "System", "Archive", "Directory"]
                    for i in range(5):
                        if bin_flags[31 - attributes_offset[i]] == '1':
                            entry.attributes.append(attributes_names[i])
                    name_length = attr_data[64]

                    if 66 + name_length * 2 <= len(attr_data):
                        try:
                            name = attr_data[66:66+name_length*2].decode('utf-16le', errors='replace')
                            if not entry.name:
                                entry.name = name
                            entry.parent_ref = parent_ref
                            entry.is_directory = bool(flags & 0x10000000)
                        except UnicodeDecodeError:
                            logger.warning("Failed to decode filename")
                            
            elif attr_type == 0x80:  # Data
                if entry.is_non_resident == True:
                    # print ( "Non-resident data")
                    self.parse_non_resident_attribute(entry, attr_type, attr_data)
                else:
                    entry.data = attr_data.decode('utf-8', errors='replace')
                        
        except Exception as e:
            logger.warning(f"Error parsing attribute {hex(attr_type)}: {e}")

    def parse_non_resident_attribute(self, entry, attr_type, attr_data):
        """Parse non-resident $DATA attribute to extract data runs and content"""
        try:
            if attr_type != 0x80:  # Only handle $DATA attributes
                return

            # First verify we have enough data for the non-resident header (minimum 0x40 bytes)
            if len(attr_data) < 0x40:
                logger.error(f"Attribute data too small ({len(attr_data)} bytes) for non-resident header")
                return

            # Parse non-resident header with proper bounds checking
           
            start_vcn = struct.unpack('<Q', attr_data[0x10:0x18])[0]
            end_vcn = struct.unpack('<Q', attr_data[0x18:0x20])[0]
            compression_unit_size = struct.unpack('<H', attr_data[0x22:0x24])[0]
            data_run_offset = struct.unpack('<H', attr_data[0x20:0x22])[0]
            actual_size = struct.unpack('<Q', attr_data[0x30:0x38])[0]

            entry.size = actual_size
            
           
            entry.compression_unit_size = compression_unit_size

            data_runs = []
            offset = data_run_offset

            while offset < len(attr_data):
                # Check we have at least 1 byte for header
                if offset >= len(attr_data):
                    break

                header = attr_data[offset]
                if header == 0x00:
                    break

                length_bytes = header & 0x0F
                offset_bytes = (header >> 4) & 0x0F

                length = int.from_bytes(attr_data[offset+1:offset+1+length_bytes], 'little')
                relative_offset = int.from_bytes(attr_data[offset+1+length_bytes:offset+1+length_bytes+offset_bytes], 'little')
                data_run = (length,relative_offset)
                data_runs.append(data_run)
                offset += 1 + length_bytes + offset_bytes
                # print (data_runs)
                abs_cluster_number =0
                if compression_unit_size == 0:
                    for run in data_runs:
                        length, relative_offset = run
                        if length == 0 or relative_offset == 0:
                            continue

                        abs_cluster_number += relative_offset

                        data = self.read_cluster(abs_cluster_number, length).decode('utf-8', errors='replace')
                        if data:
                            pre_data = entry.data if entry.data else ""
                            data = pre_data + data
                            entry.data = data
                            # print (f"Data run: {length} clusters, offset: {relative_offset}, data: {data}")
                elif compression_unit_size > 0:
                    cluster_per_unit = 1<< compression_unit_size    
                    for run in data_runs:
                        length, relative_cluster_offset = run
                        if length == 0 or relative_offset == 0:
                            continue
                        abs_cluster_offset += relative_cluster_offset
                        data = self.read_cluster(abs_cluster_offset, length)                    
                        if data:
                            data = lznt1.decompress(data)
                            pre_data = entry.data if entry.data else ""
                            data = pre_data + data.decode('utf-8', errors='replace')
                            entry.data = data
                        partital_cluster = abs_cluster_offset % cluster_per_unit
                        if partital_cluster >0:
                            data = self.read_partital_cluster(abs_cluster_offset+ cluster_per_unit, entry.size - len(entry.data))
                            if data:
                                data = lznt1.decompress(data)
                                pre_data = entry.data if entry.data else ""
                                data = pre_data + data.decode('utf-8', errors='replace')
                                entry.data = data


                

        except Exception as e:
            logger.error(f"Error parsing non-resident attribute: {e}")
            return
                
    def read_partital_cluster(self, cluster_offset, data_size):
        try:
            offset = self.partition_offset * self.boot_sector.bytes_per_sector + cluster_offset * self.bytes_per_cluster
            self.disk.seek(offset)
            data = self.disk.read(data_size)
            
            return data
        except Exception as e:
            logger.error(f"Error reading partial cluster {cluster_offset}: {e}")
            return None


    def read_cluster(self, cluster_offset, cluster_number):
        try:
            offset = self.partition_offset * self.boot_sector.bytes_per_sector + cluster_offset * self.bytes_per_cluster
            self.disk.seek(offset)
            data = self.disk.read( cluster_number* self.bytes_per_cluster)
            
            return data
        except Exception as e:
            logger.error(f"Error reading cluster {cluster_number}: {e}")
            return None
    def parse_ntfs_time(self, ntfs_time):
            if ntfs_time == 0:
                return None
            try:
                return datetime.datetime(1601, 1, 1) + datetime.timedelta(microseconds=ntfs_time//10)
            except (OverflowError, ValueError):
                return None

    def get_total_mft_entries(self):
            if not self.boot_sector:
                if not self.read_boot_record():
                    return 0
            try:
                mft_size = self.boot_sector.mft_cluster * self.bytes_per_cluster
                return mft_size // self.boot_sector.mft_record_size
            except Exception as e:
                logger.error(f"Error estimating total MFT entries: {e}")
                return 0
            
    def scan_files(self):
            if not self.boot_sector:
                if not self.read_boot_record():
                    return False

            self.files = []
            valid_records = 0
            total_entries = self.get_total_mft_entries()

            for i in range(0, total_entries):
                try:
                    record_data = self.read_mft_record(i)
                    if not record_data:
                        continue

                    entry = self.parse_file_entry(record_data, i)
                    if entry:
                        self.files.append(entry)
                        valid_records += 1

                except Exception as e:
                    logger.error(f"Error reading MFT record {i}: {e}")
                    continue

            logger.info(f"Scanned {valid_records} valid files out of {total_entries} MFT records")
            return True    

    def print_files(self):
            print(f"\nFound {len(self.files)} files:")
            print("{:<8} {:<50} {:<10} {:<20} {:<10} {:<20}".format(
                "Record", "Name", "Size", "Created", "Type","Data"))
            print("-" * 120)
            
            for file in sorted(self.files, key=lambda x: x.record_number):
                file_type = "DIR" if file.is_directory else "FILE"
                created_str = file.created.strftime('%Y-%m-%d %H:%M') if file.created else "N/A"
                print("{:<8} {:<50} {:<10} {:<20} {:<10} {:<50}".format(
                    file.record_number,
                    file.name[:50] if file.name else "N/A",
                    file.size,
                    created_str,
                    file_type,
                    file.data[:50] if file.data else "N/A"
                    ))

if __name__ == "__main__": 
    if len(sys.argv) > 1:
        disk_path = sys.argv[1]
    else:
        disk_path = r'\\.\\E:'

    print(f"Attempting to scan {disk_path}...")
    
    try:
        with open(disk_path, 'rb', buffering=0) as test:
            test.read(512)
        print("Drive access verified")
    except PermissionError:
        print("ERROR: Access denied. Please run as Administrator.")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Cannot access drive: {e}")
        sys.exit(1)
    
    
    with NTFS(disk_path) as ntfs:
        print(disk_path) 
        if ntfs.read_boot_record():
            print("\nNTFS Boot Sector Information:")
            print(f"OEM ID: {ntfs.boot_sector.oem_id}")
            print(f"Bytes per sector: {ntfs.boot_sector.bytes_per_sector}")
            print(f"Sectors per cluster: {ntfs.boot_sector.sectors_per_cluster}")
            print(f"MFT starts at cluster: {ntfs.boot_sector.mft_cluster}")
            print(f"MFT record size: {ntfs.boot_sector.mft_record_size}")
            print(f"Volume serial: {hex(ntfs.boot_sector.volume_serial)}")
            
            print("\nScanning files...")
            if ntfs.scan_files():
                ntfs.print_files()
            else:
                print("Failed to scan files")