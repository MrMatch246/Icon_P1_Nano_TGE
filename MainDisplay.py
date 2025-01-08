import sys

from .P1NanoTGEComponent import *

class MainDisplay(P1NanoTGEComponent):
    """ Representing one main 2 row display of a Mackie Control or Extension """

    def __init__(self, main_script):
        P1NanoTGEComponent.__init__(self, main_script)
        self.__stack_offset = 0
        self.__last_send_messages = [[], [], [], []]

    def destroy(self):
        NUM_CHARS_PER_DISPLAY_LINE = 54
        upper_message = 'Ableton Live'.center(NUM_CHARS_PER_DISPLAY_LINE)
        self.send_display_string(upper_message, 0, 0)
        lower_message = 'Device is offline'.center(NUM_CHARS_PER_DISPLAY_LINE)
        self.send_display_string(lower_message, 1, 0)
        P1NanoTGEComponent.destroy(self)

    def stack_offset(self):
        return self.__stack_offset

    def set_stack_offset(self, offset):
        """
            This is the offset that one gets by 'stacking' several MackieControl XTs:
            the first is at index 0, the second at 8, etc ...
        """
        self.__stack_offset = offset

    def send_display_string(self, display_string, display_row, cursor_offset):
        if display_row in range(2):
            offset = display_row * 56 + cursor_offset
        else:
            self.send_secondary_display_string(display_string, display_row, cursor_offset)
        message_string = [ord(c) for c in display_string]
        for i in range(len(message_string)):
            if message_string[i] >= 128:
                message_string[i] = 0

        if self.__last_send_messages[display_row] != message_string:
            self.__last_send_messages[display_row] = message_string
            if self.main_script().is_extension():
                device_type = SYSEX_DEVICE_TYPE_XT
            else:
                device_type = SYSEX_DEVICE_TYPE
            display_sysex = (0xf0, 0x0, 0x0, 102, device_type, 18, offset) + tuple(message_string) + (247,)
            self.send_midi(display_sysex)

    def send_secondary_display_string(self, display_string, display_row, cursor_offset):
        if display_row in range(2,4):
            offset = display_row * 56 + cursor_offset
        else:
            return
        message_string = [ord(c) for c in display_string]
        for i in range(len(message_string)):
            if message_string[i] >= 128:
                message_string[i] = 0
        if self.__last_send_messages[display_row] != message_string:
            self.__last_send_messages[display_row] = message_string
            secondary_display_sysex = (0xf0, 0x0, 0x0 , 0x02, 0x4e, 0x15, 0x15, offset) + tuple(message_string) + (0xf7,)
            self.send_midi(secondary_display_sysex)



    def send_display_colors(self, track_colors):
        sysex_header = ["F0", "00", "02", "4E", "16", "14"]
        sysex_footer = ["F7"]

        # Flatten the color data into the SysEx message
        color_data = [str(hex(item)) for color in track_colors for item in color]  # Flatten the color list
        sysex_message = sysex_header + color_data + sysex_footer

        # Convert to MIDI bytes as integers
        midi_bytes = tuple(int(byte, 16) for byte in sysex_message)

        # Send the SysEx message
        self.send_midi(midi_bytes)

    def refresh_state(self):
        self.__last_send_messages = [[], [] ,[], []]

    def on_update_display_timer(self):
        return