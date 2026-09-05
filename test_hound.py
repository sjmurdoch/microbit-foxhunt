from hound_logic import calculate_num_bars, calculate_highest_zone, get_beep_interval

def test_calculate_num_bars_min():
    assert calculate_num_bars(-105, 0) == 0
    assert calculate_num_bars(-110, 0) == 0

def test_calculate_num_bars_max():
    assert calculate_num_bars(-40, 0) == 5
    assert calculate_num_bars(-30, 0) == 5

def test_calculate_num_bars_mid():
    # Range is 65. Midpoint is ~ -72.5
    assert calculate_num_bars(-72, 0) == 2

def test_calculate_num_bars_with_offset():
    # If signal is -40 (strong), it normally gives 5 bars
    assert calculate_num_bars(-40, 0) == 5
    # If we add 30 attenuation (shift signal to -70), it should be around 2 bars
    assert calculate_num_bars(-40, 30) == 2

def test_calculate_highest_zone():
    assert calculate_highest_zone("Z1", 0) == 1
    assert calculate_highest_zone("Z2", 1) == 2
    assert calculate_highest_zone("Z3", 2) == 3
    # Should not downgrade zone within the cycle
    assert calculate_highest_zone("Z1", 3) == 3
    assert calculate_highest_zone("Z2", 3) == 3
    
def test_get_beep_interval():
    assert get_beep_interval(0) == 0
    assert get_beep_interval(1) == 1000
    assert get_beep_interval(2) == 500
    assert get_beep_interval(3) == 200
