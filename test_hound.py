from hound_logic import HoundController

def test_attenuator():
    hound = HoundController()
    hound.process_packet("Z1", -50, 0) # Strong signal
    assert hound.get_display_bars() == 4
    hound.process_inputs(button_a=True, button_b=False) # Attenuate by 5
    assert hound.get_display_bars() == 3
    hound.process_inputs(button_a=False, button_b=True) # Decrease attenuation
    assert hound.get_display_bars() == 4

def test_zone_hierarchy():
    hound = HoundController()
    hound.process_packet("Z1", -90, 0)
    assert hound.highest_zone == 1
    hound.process_packet("Z2", -80, 50)
    assert hound.highest_zone == 2
    hound.process_packet("Z3", -70, 100)
    assert hound.highest_zone == 3
    # Stray Z1 shouldn't downgrade it before it plays
    hound.process_packet("Z1", -70, 150)
    assert hound.highest_zone == 3

def test_audio_timing_zone1():
    hound = HoundController()
    hound.process_packet("Z1", -90, 0)
    # Shouldn't play at t=500
    assert hound.get_beep_to_play(500) == 0
    # Should play at t=1001
    assert hound.get_beep_to_play(1001) == 1
    # Should reset zone
    assert hound.highest_zone == 0
    # Shouldn't play again immediately
    assert hound.get_beep_to_play(1002) == 0

def test_audio_timing_zone3():
    hound = HoundController()
    # If we get Z3, it should play every 200ms
    hound.process_packet("Z3", -50, 0)
    assert hound.get_beep_to_play(201) == 3
    assert hound.highest_zone == 0
    # If we get another Z3
    hound.process_packet("Z3", -50, 250)
    assert hound.get_beep_to_play(402) == 3
    
def test_timeout():
    hound = HoundController()
    hound.process_packet("Z3", -50, 0)
    hound.check_timeout(500)
    assert hound.highest_zone == 3 # Not timed out yet
    hound.check_timeout(1001)
    assert hound.highest_zone == 0 # Timed out
    assert hound.get_display_bars() == 0

def test_radio_headers():
    hound = HoundController()
    hound.process_packet("\x01\x00\x01Z2", -80, 0)
    assert hound.highest_zone == 2
