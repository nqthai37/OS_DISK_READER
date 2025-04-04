import struct
import datetime
from collections import namedtuple
import logging
import sys

# Constants
NTFS_SIGNATURE = b'NTFS    '
SECTOR_SIZE = 512
ATTRIBUTE_TYPES = {
    0x10: 'STANDARD_INFORMATION',
    0x20: 'ATTRIBUTE_LIST',
    0x30: 'FILE_NAME',
    0x40: 'OBJECT_ID',
    0x50: 'SECURITY_DESCRIPTOR',
    0x60: 'VOLUME_NAME',
    0x70: 'VOLUME_INFORMATION',
    0x80: 'DATA',
    0x90: 'INDEX_ROOT',
    0xA0: 'INDEX_ALLOCATION',
    0xB0: 'BITMAP',
    0xC0: 'REPARSE_POINT',
    0xD0: 'EA_INFORMATION',
    0xE0: 'EA',
    0xF0: 'PROPERTY_SET',
    0x100: 'LOGGED_UTILITY_STREAM'
}

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Data structures
NTFSBootSector = namedtuple('NTFSBootSector', [
    'oem_id', 'bytes_per_sector', 'sectors_per_cluster',
    'mft_cluster', 'mft_mirror_cluster', 'mft_record_size',
    'volume_serial', 'checksum'
])

class NTFSFileEntry:
    def __init__(self):
        self.name = None
        self.size = 0
        self.created = None
        self.modified = None
        self.accessed = None
        self.attributes = []
        self.is_directory = False
        self.parent_ref = None
        self.record_number = -1

    def __repr__(self):
        return (f"NTFSFileEntry(name={self.name}, size={self.size}, "
                f"is_directory={self.is_directory}, record_number={self.record_number})")

class NTFS:
    def __init__(self, disk_path, partition_offset=0):
        self.disk_path = disk_path
        self.partition_offset = partition_offset
        self.disk = None
        self.boot_sector = None
        self.bytes_per_cluster = 0
        self.cluster_size = 0
        self.files = []
        self.volume_serial = None
        
    def __enter__(self):
        self.open()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        
    def open(self):
        """Open the disk for reading"""
        try:
            # Use binary mode with buffering=0 for raw disk access
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
        """Close the disk"""
        if self.disk:
            self.disk.close()
            self.disk = None
            
    def read_boot_sector(self):
        """Read and parse the NTFS boot sector"""
        try:
            self.disk.seek(self.partition_offset * SECTOR_SIZE)
            data = self.disk.read(SECTOR_SIZE)
            
            if len(data) < 512:
                raise ValueError("Couldn't read full boot sector")
            
            # Validate NTFS signature
            if data[3:11] != NTFS_SIGNATURE:
                raise ValueError("Not a valid NTFS filesystem")
                
            # Parse boot sector with better error checking
            bytes_per_sector = struct.unpack('<H', data[11:13])[0]
            if bytes_per_sector != 512 and bytes_per_sector != 4096:
                raise ValueError(f"Unsupported sector size: {bytes_per_sector}")
                
            sectors_per_cluster = struct.unpack('<B', data[13:14])[0]
            mft_record_size_raw = struct.unpack('<b', data[64:65])[0]
            
            # Calculate MFT record size (can be negative indicating power of 2)
            mft_record_size = (2 ** abs(mft_record_size_raw) 
                             if mft_record_size_raw < 0 
                             else mft_record_size_raw * 1024)
            
            self.boot_sector = NTFSBootSector(
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
            logger.debug(f"Boot sector info: {self.boot_sector}")
            return True
            
        except Exception as e:
            logger.error(f"Error reading boot sector: {e}")
            return False
            
    def read_mft_record(self, record_number):
        """Read an MFT record from disk"""
        try:
            # Calculate the byte offset to the MFT
            mft_offset = self.boot_sector.mft_cluster * self.bytes_per_cluster
            
            # Calculate the byte offset to the specific record
            record_offset = record_number * self.boot_sector.mft_record_size
            
            # Combine with partition offset
            absolute_offset = (self.partition_offset * SECTOR_SIZE 
                              + mft_offset 
                              + record_offset)
            
            # Ensure we don't try to seek beyond file limits
            if absolute_offset < 0:
                raise ValueError(f"Invalid negative offset: {absolute_offset}")
            
            absolute_offset = 33941504
            # print (absolute_offset)
            self.disk.seek(absolute_offset)
            # Read the MFT record
            record_data = self.disk.read(self.boot_sector.mft_record_size)
            
            if len(record_data) < 42:  # Minimum valid record size
                logger.debug(f"Record {record_number} too small")
                return None, 0
                
            if record_data[0:4] != b'FILE':
                # logger.debug(f"Record {record_number} missing FILE signature")
                return None, 0
            return record_data, absolute_offset
            
        except Exception as e:
            logger.error(f"Error reading MFT record {record_number}: {e}")
            return None, 0
            
    def parse_file_entry(self, record_data, record_number):
        """Parse an MFT record into a file entry"""
        try:
            entry = NTFSFileEntry()
            entry.record_number = record_number

            # Get the offset to the first attribute
            attr_offset = struct.unpack('<H', record_data[20:22])[0]
            # print (attr_offset, 1)

            # Parse all attributes
            while attr_offset + 24  <= len(record_data):  # Minimum attribute header size
                attr_type = struct.unpack('<I', record_data[attr_offset:attr_offset+4])[0]
                attr_length = struct.unpack('<I', record_data[attr_offset+4:attr_offset+8])[0]

                content_length = struct.unpack('<I', record_data[attr_offset+16:attr_offset+20])[0]
                # content_offset += attr_offset
                content_offset = struct.unpack('<H', record_data[attr_offset+20:attr_offset+22])[0]
                content_offset += attr_offset
                # print (attr_type, attr_length)
                if attr_type == 0xFFFFFFFF or attr_length == 0:
                    # print(1)
                    break
                    
                # Validate attribute length
                if attr_offset + attr_length > len(record_data):
                    logger.warning(f"Attribute at offset {attr_offset} exceeds record boundary")
                    break
                # print(record_data[20:22])
                if (attr_type == 0x30):
                    print ('content_offset',content_offset)
                    print ('content_length',content_length)
                attr_data = record_data[content_offset:content_offset+content_length]
                # print (attr_data)
                self.parse_attribute(entry, attr_type, attr_data)
                
                # Move to next attribute
                attr_offset += attr_length
                
            return entry if entry.name else None
            
        except Exception as e:
            logger.error(f"Error parsing record {record_number}: {e}")
            return None
        
    def parse_attribute(self, entry, attr_type, attr_data):
        # print(attr_type, attr_data[0:8])
        try:
            if attr_type == 0x10:  # Standard Information
                if len(attr_data) >= 48:
                    entry.created = self.parse_ntfs_time(struct.unpack('<Q', attr_data[24:32])[0])
                    entry.modified = self.parse_ntfs_time(struct.unpack('<Q', attr_data[32:40])[0])
                    entry.accessed = self.parse_ntfs_time(struct.unpack('<Q', attr_data[40:48])[0])
                    
            elif attr_type == 0x30:  # File Name
                print(attr_data)
                if len(attr_data) >= 66:
                    parent_ref = struct.unpack('<Q', attr_data[0:8])[0]
                    flags = struct.unpack('<Q', attr_data[56:64])[0]
                    print('attr',attr_data[0])
                    name_length = attr_data[64]
                    # print (name_length)
                    if 66 + name_length * 2 <= len(attr_data):
                        try:
                            name = attr_data[66:66+name_length*2].decode('utf-16le', errors='replace')
                            # print('name' ,name)
                            if not entry.name:  # Only set if not already set
                                entry.name = name
                            entry.parent_ref = parent_ref
                            entry.is_directory = bool(flags & 0x10000000)
                        except UnicodeDecodeError:
                            logger.warning("Failed to decode filename")
                            
            elif attr_type == 0x80:  # Data
                if len(attr_data) >= 24:
                    non_resident = attr_data[8]
                    if non_resident == 0:  # Resident
                        attr_size = struct.unpack('<I', attr_data[16:20])[0]
                        entry.size = attr_size
                    elif len(attr_data) >= 56:  # Non-resident
                        entry.size = struct.unpack('<Q', attr_data[48:56])[0]
                        
            # Record attribute type
            attr_name = ATTRIBUTE_TYPES.get(attr_type, f'UNKNOWN_{hex(attr_type)}')
            if attr_name not in entry.attributes:
                entry.attributes.append(attr_name)
                
        except Exception as e:
            logger.warning(f"Error parsing attribute {hex(attr_type)}: {e}")
        
    def parse_ntfs_time(self, ntfs_time):
        """Convert NTFS 64-bit time to Python datetime"""
        if ntfs_time == 0:
            return None
        try:
            return datetime.datetime(1601, 1, 1) + datetime.timedelta(microseconds=ntfs_time//10)
        except (OverflowError, ValueError):
            return None
        
    def scan_files(self, max_files=100):
        """Scan the MFT for files"""
        if not self.boot_sector:
            if not self.read_boot_sector():
                return False
                
        self.files = []
        valid_records = 0
        
        try:
            for i in range(0, max_files):
                record_data, _ = self.read_mft_record(i)
                if record_data:
                    entry = self.parse_file_entry(record_data, i)
                    if entry:
                        self.files.append(entry)
                        valid_records += 1
                        
            logger.info(f"Scanned {valid_records} valid files out of {max_files} records")
            return True
            
        except Exception as e:
            logger.error(f"Error during scan: {e}")
            return False
        
    def print_files(self):
        """Print discovered files"""
        print(f"\nFound {len(self.files)} files:")
        print("{:<8} {:<50} {:<10} {:<20} {:<10}".format(
            "Record", "Name", "Size", "Created", "Type"))
        print("-" * 100)
        
        for file in sorted(self.files, key=lambda x: x.record_number):
            file_type = "DIR" if file.is_directory else "FILE"
            created_str = file.created.strftime('%Y-%m-%d %H:%M') if file.created else "N/A"
            print("{:<8} {:<50} {:<10} {:<20} {:<10}".format(
                file.record_number,
                file.name[:50] if file.name else "N/A",
                file.size,
                created_str,
                file_type))

    def find_file(self, name):
        """Find a file by name (case insensitive)"""
        return [f for f in self.files if f.name and name.lower() in f.name.lower()]

def check_filesystem(disk_path):
    """Check if the specified path is an NTFS volume"""
    try:
        with NTFS(disk_path) as ntfs:
            if ntfs.open():
                if ntfs.read_boot_sector():
                    return True
        return False
    except:
        return False

if __name__ == "__main__":
    # Determine drive to scan
    if len(sys.argv) > 1:
        disk_path = sys.argv[1]
    else:
        disk_path = r'\\.\E:'
    
    print(f"Attempting to scan {disk_path}...")
    
    # First verify we can access the drive
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
    
    # Check filesystem
    if not check_filesystem(disk_path):
        print("ERROR: Not an NTFS filesystem or cannot read boot sector")
        sys.exit(1)
    
    # Perform the scan
    with NTFS(disk_path) as ntfs:
        if ntfs.read_boot_sector():
            print("\nNTFS Boot Sector Information:")
            print(f"OEM ID: {ntfs.boot_sector.oem_id}")
            print(f"Bytes per sector: {ntfs.boot_sector.bytes_per_sector}")
            print(f"Sectors per cluster: {ntfs.boot_sector.sectors_per_cluster}")
            print(f"MFT starts at cluster: {ntfs.boot_sector.mft_cluster}")
            print(f"MFT record size: {ntfs.boot_sector.mft_record_size}")
            print(f"Volume serial: {hex(ntfs.boot_sector.volume_serial)}")
            
            print("\nScanning files...")
            if ntfs.scan_files(1):
                ntfs.print_files()
            else:
                print("Failed to scan files")