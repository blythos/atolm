import struct

def read_u32_be(data, offset=0):
    return struct.unpack('>I', data[offset:offset+4])[0]

def read_u16_be(data, offset=0):
    return struct.unpack('>H', data[offset:offset+2])[0]

def decode_rgb555(val):
    """
    Saturn RGB555 format: R = bits 0-4, G = bits 5-9, B = bits 10-14, MSB = bit 15
    Returns (R, G, B) in 0-255 range.
    """
    r = (val & 0x001F) << 3
    g = ((val & 0x03E0) >> 5) << 3
    b = ((val & 0x7C00) >> 10) << 3
    return (r, g, b)

def fixed_to_float(val, fractional_bits=16):
    """Convert Saturn fixed-point (usually 16.16) to float."""
    return val / (1 << fractional_bits)
