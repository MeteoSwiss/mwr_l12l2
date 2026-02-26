import unittest
import numpy as np

from mwr_l12l2.errors import MWRDataError
from mwr_l12l2.utils.atmosphere_utils import (
    AtmosphericConstants,
    calculate_pressure_from_altitude
)


class TestAtmosphericConstants(unittest.TestCase):
    """Test that atmospheric constants have expected values"""
    
    def test_constants_values(self):
        """Verify that atmospheric constants are set to standard values"""
        self.assertEqual(AtmosphericConstants.P0, 1013.25)
        self.assertEqual(AtmosphericConstants.T0, 288.15)
        self.assertEqual(AtmosphericConstants.L, 0.0065)
        self.assertEqual(AtmosphericConstants.R, 8.31447)
        self.assertEqual(AtmosphericConstants.M, 0.0289644)
        self.assertEqual(AtmosphericConstants.g, 9.80665)
        self.assertEqual(AtmosphericConstants.TROPOPAUSE_HEIGHT, 12000)


class TestCalculatePressureFromAltitude(unittest.TestCase):
    """Test the calculate_pressure_from_altitude function"""
    
    def test_sea_level(self):
        """Test pressure calculation at sea level (0 m)"""
        station_pressure, psfc_min, psfc_max = calculate_pressure_from_altitude(0)
        
        # At sea level, pressure should equal P0
        self.assertAlmostEqual(station_pressure, AtmosphericConstants.P0, places=2)
        self.assertAlmostEqual(station_pressure, 1013.25, places=2)
        
        # Check that min/max bounds are reasonable
        self.assertAlmostEqual(psfc_min, 0.85 * 1013.25, places=2)
        self.assertAlmostEqual(psfc_max, 1.1 * 1013.25, places=2)
    
    def test_moderate_altitude(self):
        """Test pressure calculation at moderate altitude (1500 m, typical mountain station)"""
        station_pressure, psfc_min, psfc_max = calculate_pressure_from_altitude(1500)
        
        # At 1500 m, pressure should be approximately 845 hPa (based on barometric formula)
        # Using exact calculation: P = P0 * (1 - L*h/T0)^(g*M/(R*L))
        expected_pressure = 1013.25 * (1 - 0.0065 * 1500 / 288.15) ** (9.80665 * 0.0289644 / (8.31447 * 0.0065))
        self.assertAlmostEqual(station_pressure, expected_pressure, places=2)
        self.assertAlmostEqual(station_pressure, 845.6, places=0)
        
        # Check that min/max bounds are set correctly
        self.assertAlmostEqual(psfc_min, 0.85 * station_pressure, places=2)
        self.assertAlmostEqual(psfc_max, 1.1 * station_pressure, places=2)
        
    def test_high_altitude(self):
        """Test pressure calculation at high altitude (5000 m, high mountain station)"""
        station_pressure, psfc_min, psfc_max = calculate_pressure_from_altitude(5000)
        
        # At 5000 m, pressure should be approximately 540 hPa
        expected_pressure = 1013.25 * (1 - 0.0065 * 5000 / 288.15) ** (9.80665 * 0.0289644 / (8.31447 * 0.0065))
        self.assertAlmostEqual(station_pressure, expected_pressure, places=2)
        self.assertAlmostEqual(station_pressure, 540.2, places=0)
        
        # Check that min/max bounds are set correctly
        self.assertAlmostEqual(psfc_min, 0.85 * station_pressure, places=2)
        self.assertAlmostEqual(psfc_max, 1.1 * station_pressure, places=2)
    
    def test_negative_altitude(self):
        """Test pressure calculation at negative altitude (below sea level, e.g., Dead Sea)"""
        
        # Below sea level we shoudl excpect and error of type MWRDataError
        altitude = -400
        with self.assertRaises(MWRDataError) as context:
            calculate_pressure_from_altitude(altitude)
        
        # Check error message contains relevant information
        self.assertIn("negative", str(context.exception).lower())
        self.assertIn(str(altitude), str(context.exception))
    
    def test_tropopause_boundary(self):
        """Test pressure calculation just below the tropopause"""
        altitude = AtmosphericConstants.TROPOPAUSE_HEIGHT - 100
        station_pressure, psfc_min, psfc_max = calculate_pressure_from_altitude(altitude)
        
        # Should not raise an error
        self.assertIsInstance(station_pressure, (float, np.floating))
        self.assertGreater(station_pressure, 0)
        self.assertLess(station_pressure, AtmosphericConstants.P0)
    
    def test_above_tropopause_raises_error(self):
        """Test that altitude above tropopause raises MWRDataError"""
        altitude = AtmosphericConstants.TROPOPAUSE_HEIGHT + 100
        
        with self.assertRaises(MWRDataError) as context:
            calculate_pressure_from_altitude(altitude)
        
        # Check error message contains relevant information
        self.assertIn("tropopause", str(context.exception).lower())
        self.assertIn(str(altitude), str(context.exception))
    
    def test_at_tropopause_raises_error(self):
        """Test that altitude exactly at tropopause raises MWRDataError"""
        altitude = AtmosphericConstants.TROPOPAUSE_HEIGHT
        
        with self.assertRaises(MWRDataError) as context:
            calculate_pressure_from_altitude(altitude)
    
    def test_return_types(self):
        """Test that function returns correct number and types of values"""
        result = calculate_pressure_from_altitude(1000)
        
        # Should return 3 values
        self.assertEqual(len(result), 3)
        station_pressure, psfc_min, psfc_max = result
        
        # All should be numeric
        self.assertIsInstance(station_pressure, (float, np.floating))
        self.assertIsInstance(psfc_min, (float, np.floating))
        self.assertIsInstance(psfc_max, (float, np.floating))
    
    def test_bounds_relationship(self):
        """Test that min < pressure < max for various altitudes"""
        test_altitudes = [0, 500, 1000, 2000, 5000, 10000]
        
        for altitude in test_altitudes:
            station_pressure, psfc_min, psfc_max = calculate_pressure_from_altitude(altitude)
            
            # Check ordering
            self.assertLess(psfc_min, station_pressure,
                          f"Min pressure should be less than station pressure at {altitude} m")
            self.assertLess(station_pressure, psfc_max,
                          f"Station pressure should be less than max pressure at {altitude} m")
            
            # Check that bounds are exactly 0.85 and 1.1 times the station pressure
            self.assertAlmostEqual(psfc_min / station_pressure, 0.85, places=10)
            self.assertAlmostEqual(psfc_max / station_pressure, 1.1, places=10)
    
    def test_pressure_decreases_with_altitude(self):
        """Test that pressure decreases monotonically with increasing altitude"""
        altitudes = [0, 1000, 2000, 3000, 4000, 5000]
        pressures = []
        
        for altitude in altitudes:
            station_pressure, _, _ = calculate_pressure_from_altitude(altitude)
            pressures.append(station_pressure)
        
        # Check that each pressure is less than the previous one
        for i in range(1, len(pressures)):
            self.assertLess(pressures[i], pressures[i-1],
                          f"Pressure should decrease with altitude: {altitudes[i]} m vs {altitudes[i-1]} m")


if __name__ == '__main__':
    unittest.main()
