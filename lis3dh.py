import machine
import ustruct

# Default I2C address for LIS3DH (can be 0x18 if SDO/SA0 is pulled LOW)
LIS3DH_I2C_ADDR = 0x19

# LIS3DH Register Addresses
_LIS3DH_REG_STATUS1      = 0x07  # Status Register
_LIS3DH_REG_OUT_CFG      = 0x08
_LIS3DH_REG_WHO_AM_I     = 0x0F  # Device ID Register (Should return 0x33)
_LIS3DH_REG_TEMP_CFG     = 0x1F  # Temperature Sensor Register
_LIS3DH_REG_CTRL1        = 0x20  # Control Register 1 (ODR, Low-Power, Axes Enable)
_LIS3DH_REG_CTRL2        = 0x21  # Control Register 2 (High-Pass Filter)
_LIS3DH_REG_CTRL3        = 0x22  # Control Register 3 (Interrupt 1 Routing)
_LIS3DH_REG_CTRL4        = 0x23  # Control Register 4 (BDU, Full-Scale, High-Res)
_LIS3DH_REG_CTRL5        = 0x24  # Control Register 5 (FIFO enable, Boot)
_LIS3DH_REG_CTRL6        = 0x26  # Control Register 6
_LIS3DH_REG_STATUS       = 0x27  # Status Data Register
_LIS3DH_REG_OUT_X_L      = 0x28  # X-Axis Data Low (Auto-increment to Y and Z)

# Configuration Register Bit Masks and Values for CTRL_REG1
_ODR_MASK    = 0xF0  # Output Data Rate Bits (Bits 4, 5, 6, 7)
_LP_MASK     = 0x08  # Low-Power Mode Enable Bit (Bit 3)
_ZEN_MASK    = 0x04  # Z-Axis Enable (Bit 2)
_YEN_MASK    = 0x02  # Y-Axis Enable (Bit 1)
_XEN_MASK    = 0x01  # X-Axis Enable (Bit 0)

# Output Data Rate (ODR) settings for CTRL_REG1 (ODR3, ODR2, ODR1, ODR0 bits)
ODR_POWER_DOWN = (0b0000 << 4)
ODR_1HZ        = (0b0001 << 4)
ODR_10HZ       = (0b0010 << 4)
ODR_25HZ       = (0b0011 << 4)
ODR_50HZ       = (0b0100 << 4)
ODR_100HZ      = (0b0101 << 4)
ODR_200HZ      = (0b0110 << 4)
ODR_400HZ      = (0b0111 << 4)

# Full-Scale (FS) settings for CTRL_REG4 (FS1, FS0 bits)
_FS_MASK     = 0x30
FS_2G        = (0b00 << 4)  # +/- 2g
FS_4G        = (0b01 << 4)  # +/- 4g
FS_8G        = (0b10 << 4)  # +/- 8g
FS_16G       = (0b11 << 4)  # +/- 16g

# High-Resolution and BDU bit masks for CTRL_REG4
_HR_MASK     = 0x08  # High-Resolution Enable Bit
_BDU_MASK    = 0x80  # Block Data Update Bit

class LIS3DH:
    """
    MicroPython driver for the LIS3DH / LIS3DHTR 3-Axis Accelerometer.

    This class provides methods to initialize the sensor, configure its
    output data rate, scale range, axis states, and read the 16-bit
    X, Y, and Z acceleration channel data.
    """

    def __init__(self, i2c, address=LIS3DH_I2C_ADDR):
        """
        Initializes the LIS3DH sensor.

        Args:
            i2c (machine.I2C): The initialized I2C bus object.
            address (int): The I2C address of the LIS3DH sensor.
                           Defaults to 0x19 (or 0x18 if SA0 is pulled low).
        """
        self.i2c = i2c
        self.address = address
        self._current_ctrl1 = 0x07  # Default: Normal mode, all 3 axes enabled (X, Y, Z = 1)
        self._current_ctrl4 = 0x00  # Default: +/- 2g, low-res/normal

        # Verify device ID (WHO_AM_I should return 0x33)
        if self._read_byte(_LIS3DH_REG_WHO_AM_I) != 0x33:
            raise RuntimeError("LIS3DH device not found or invalid WHO_AM_I response.")

        # Initialize sensor with default settings:
        # - Enable all axes
        # - Output Data Rate to 50Hz
        # - Enable Block Data Update (BDU) and High-Resolution mode
        self.set_data_rate(ODR_50HZ)
        self.enable_axes(True, True, True)
        self.set_full_scale(FS_2G)
        self.set_high_resolution(True)
        self.set_block_data_update(True)

    def _read_byte(self, register):
        """Reads a single byte from the specified register."""
        data = self.i2c.readfrom_mem(self.address, register, 1)
        return data[0]

    def _write_byte(self, register, value):
        """Writes a single byte to the specified register."""
        self.i2c.writeto_mem(self.address, register, bytes([value]))

    def _read_word_signed(self, register):
        """
        Reads a 16-bit signed word from the specified register.
        The LIS3DH uses little-endian byte ordering (LSB first).
        """
        # Set MSB (bit 7) of the register address to 1 to enable auto-increment
        # across sequential bytes (e.g., reading L and H bytes for an axis).
        data = self.i2c.readfrom_mem(self.address, register | 0x80, 2)
        return ustruct.unpack('<h', data)[0]

    def set_data_rate(self, odr_value):
        """
        Sets the output data rate (ODR) for the accelerometer.

        Args:
            odr_value (int): One of the ODR_ constants (e.g., ODR_50HZ, ODR_100HZ).
        """
        self._current_ctrl1 = (self._current_ctrl1 & ~_ODR_MASK) | (odr_value & _ODR_MASK)
        self._write_byte(_LIS3DH_REG_CTRL1, self._current_ctrl1)

    def enable_axes(self, x=True, y=True, z=True):
        """Enables or disables individual X, Y, and Z measurement axes."""
        if x: self._current_ctrl1 |= _XEN_MASK
        else: self._current_ctrl1 &= ~_XEN_MASK
        
        if y: self._current_ctrl1 |= _YEN_MASK
        else: self._current_ctrl1 &= ~_YEN_MASK
        
        if z: self._current_ctrl1 |= _ZEN_MASK
        else: self._current_ctrl1 &= ~_ZEN_MASK
        
        self._write_byte(_LIS3DH_REG_CTRL1, self._current_ctrl1)

    def set_full_scale(self, fs_value):
        """
        Sets the full-scale measurement range.

        Args:
            fs_value (int): One of the FS_ constants (FS_2G, FS_4G, FS_8G, FS_16G).
        """
        self._current_ctrl4 = (self._current_ctrl4 & ~_FS_MASK) | (fs_value & _FS_MASK)
        self._write_byte(_LIS3DH_REG_CTRL4, self._current_ctrl4)

    def set_high_resolution(self, enable=True):
        """Enables or disables 12-bit High-Resolution mode."""
        if enable:
            self._current_ctrl4 |= _HR_MASK
        else:
            self._current_ctrl4 &= ~_HR_MASK
        self._write_byte(_LIS3DH_REG_CTRL4, self._current_ctrl4)

    def set_block_data_update(self, enable=True):
        """Enables Block Data Update (prevents reading old/new data mix)."""
        if enable:
            self._current_ctrl4 |= _BDU_MASK
        else:
            self._current_ctrl4 &= ~_BDU_MASK
        self._write_byte(_LIS3DH_REG_CTRL4, self._current_ctrl4)

    def read_x(self):
        """
        Reads the 16-bit signed X channel data.

        Returns:
            int: The raw signed X channel value.
        """
        val = self._read_word_signed(_LIS3DH_REG_OUT_X_L)
        # Right shift depending on resolution mode if needed (High-res is left-aligned to 16 bits)
        return val >> 4

    def read_y(self):
        """
        Reads the 16-bit signed Y channel data.

        Returns:
            int: The raw signed Y channel value.
        """
        val = self._read_word_signed(_LIS3DH_REG_OUT_X_L + 2)
        return val >> 4

    def read_z(self):
        """
        Reads the 16-bit signed Z channel data.

        Returns:
            int: The raw signed Z channel value.
        """
        val = self._read_word_signed(_LIS3DH_REG_OUT_X_L + 4)
        return val >> 4

    def read_xyz(self):
        """
        Reads X, Y, and Z acceleration channels in a single burst transaction.

        Returns:
            tuple: (x, y, z) raw signed integer values.
        """
        # Read all 6 bytes starting from OUT_X_L with auto-increment enabled (0x80)
        data = self.i2c.readfrom_mem(self.address, _LIS3DH_REG_OUT_X_L | 0x80, 6)
        x = ustruct.unpack('<h', data[0:2])[0] >> 4
        y = ustruct.unpack('<h', data[2:4])[0] >> 4
        z = ustruct.unpack('<h', data[4:6])[0] >> 4
        return (x, y, z)
