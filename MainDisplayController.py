import sys

from .P1NanoTGEComponent import *
from ableton.v3.live import liveobj_color_to_midi_rgb_values

class MainDisplayController(P1NanoTGEComponent):
    """
        Controlling all available main displays (the display above the channel strips),
        which will be only one when only using the 'main' Mackie Control, and severals
        when using at least one Mackie Control XT, attached to the main Mackie Control

        The Displays can be run in two modes: Channel and Global mode:
        - In channel mode 2*6 characters can be shown for each channel strip
        - In global mode, you can setup the two 54 charchter lines to whatever you want

        See 'class ChannelStripController' for descriptions of the stack_index or details
        about the different assignment modes.
    """

    def __init__(self, main_script, display):
        P1NanoTGEComponent.__init__(self, main_script)
        self.__left_extensions = []
        self.__right_extensions = []
        self.__displays = [display]
        self.__own_display = display
        self.__parameters = [[] for x in range(NUM_CHANNEL_STRIPS)]
        self.__channel_strip_strings = ['' for x in range(NUM_CHANNEL_STRIPS)]
        self.__channel_strip_mode = True
        self.__show_parameter_names = True
        self.__bank_channel_offset = 0
        self.__meters_enabled = False
        self.__show_return_tracks = False
        self.__show_current_track_colors = True #False means we show track colors for all tracks within the visible range True means all displays show the color of the selected track

    def destroy(self):
        self.enable_meters(False)
        P1NanoTGEComponent.destroy(self)

    def set_controller_extensions(self, left_extensions, right_extensions):
        """
            Called from the main script (after all scripts where initialized), to let us
            know where and how many MackieControlXT are installed.
        """
        self.__left_extensions = left_extensions
        self.__right_extensions = right_extensions
        self.__displays = []
        stack_offset = 0
        for le in left_extensions:
            self.__displays.append(le.main_display())
            le.main_display().set_stack_offset(stack_offset)
            stack_offset += NUM_CHANNEL_STRIPS
        self.__displays.append(self.__own_display)
        self.__own_display.set_stack_offset(stack_offset)
        stack_offset += NUM_CHANNEL_STRIPS
        for re in right_extensions:
            self.__displays.append(re.main_display())
            re.main_display().set_stack_offset(stack_offset)
            stack_offset += NUM_CHANNEL_STRIPS
        self.__parameters = [[] for x in
                             range(len(self.__displays) * NUM_CHANNEL_STRIPS)]
        self.__channel_strip_strings = ['' for x in range(
            len(self.__displays) * NUM_CHANNEL_STRIPS)]
        self.refresh_state()

    def enable_meters(self, enabled):
        if self.__meters_enabled != enabled:
            self.__meters_enabled = enabled
            self.refresh_state()

    def set_show_parameter_names(self, enable):
        self.__show_parameter_names = enable

    def set_show_current_track_colors(self, enable):
        self.__show_current_track_colors = enable

    def show_current_track_color(self):
        return self.__show_current_track_colors

    def set_channel_offset(self, channel_offset):
        self.__bank_channel_offset = channel_offset

    def parameters(self):
        return self.__parameters

    def set_parameters(self, parameters):
        if parameters:
            self.set_channel_strip_strings(None)
        for d in self.__displays:
            self.__parameters = parameters

    def channel_strip_strings(self):
        return self.__channel_strip_strings

    def set_channel_strip_strings(self, channel_strip_strings):
        if channel_strip_strings:
            self.set_parameters(None)
        self.__channel_strip_strings = channel_strip_strings

    def update_channel_strip_strings(self, channel_strip_strings_dict):
        #sys.stderr.write(f'uCSS: {channel_strip_strings_dict} for {self.__channel_strip_strings}\n')
        if not self.__channel_strip_strings:
            self.__channel_strip_strings = [None for x in range(NUM_CHANNEL_STRIPS)]
        for i, channel_strip_string in channel_strip_strings_dict.items():
            self.__channel_strip_strings = self.__channel_strip_strings[:i] + [
                channel_strip_string] + self.__channel_strip_strings[i + 1:]

    def set_show_return_track_names(self, show_returns):
        self.__show_return_tracks = show_returns

    def refresh_state(self):
        for d in self.__displays:
            d.refresh_state()

    def on_update_display_timer(self):
        for display in self.__displays:
            if self.__channel_strip_mode:
                upper_string = ''
                lower_string = ''
                track_index_range = list(
                    range(self.__bank_channel_offset + display.stack_offset(),
                          self.__bank_channel_offset + display.stack_offset() + NUM_CHANNEL_STRIPS))
                if not self.__show_return_tracks:
                    for i,track in enumerate(self.song().visible_tracks):
                        if track == self.song().view.selected_track:
                            selected_track_index = i
                            track_index_range = list(
                                range(selected_track_index,
                                      selected_track_index + NUM_CHANNEL_STRIPS))
                            break

                if self.__show_return_tracks:
                    tracks = self.song().return_tracks
                else:
                    tracks = self.song().visible_tracks

                for strip_index, t in enumerate(track_index_range):
                    if self.__parameters and self.__show_parameter_names:
                        if self.__parameters[strip_index]:
                            upper_string += self.__generate_7_char_string(
                                self.__parameters[strip_index][1])
                        else:
                            upper_string += self.__generate_7_char_string('')
                    elif t < len(tracks) and not self.__show_current_track_colors:
                        upper_string += self.__generate_7_char_string(
                            tracks[t].name)
                    else:
                        upper_string += self.__generate_7_char_string('')
                    #upper_string += ' '
                    if self.__channel_strip_strings and \
                        self.__channel_strip_strings[strip_index]:
                        lower_string += self.__generate_7_char_string(
                            self.__channel_strip_strings[strip_index])
                    elif self.__parameters and self.__parameters[strip_index]:

                        if self.__parameters[strip_index][0]:
                            lower_string += self.__generate_7_char_string(
                                str(self.__parameters[strip_index][0]))
                        else:
                            lower_string += self.__generate_7_char_string('')
                    else:
                        lower_string += self.__generate_7_char_string('')
                    #lower_string += ' '
                #sys.stderr.write(f'upper_string: {upper_string}')
                #sys.stderr.write(f'lower_string: {lower_string}\n')

                if self.__show_current_track_colors:
                    track_colors = []
                    for i in range(NUM_CHANNEL_STRIPS):
                        track_colors.append(liveobj_color_to_midi_rgb_values(self.song().view.selected_track))
                    display.send_display_colors(track_colors)
                else:
                    track_colors = []
                    for i, track in enumerate(tracks):
                        if i in track_index_range:
                            track_colors.append(liveobj_color_to_midi_rgb_values(track))
                    display.send_display_colors(track_colors)


                display.send_display_string(lower_string, 0, 0)
                if not self.__meters_enabled:
                    display.send_display_string(upper_string, 1, 0)

                #below_lower_string = ["ABCDEFx", "GHIJKLx", "MNOPQRx", "STUVWXx", "YZ1234", "567890","abcdef", "ghijky"]
                #below_lower_string2 = ["ABCDEFx", "GHIJKLx", "MNOPQRx", "STUVWXx", "YZ1234", "567890","abcdef", "ghijky"]

                #display.send_secondary_display_string(below_lower_string)
                #display.send_secondary_display_string(below_lower_string2, 1)
            else:
                ascii_message = u'< _1234 guck ma #!?:;_ >'
                if not self.__test:
                    self.__test = 0
                self.__test = self.__test + 1
                if self.__test > NUM_CHARS_PER_DISPLAY_LINE - len(
                    ascii_message):
                    self.__test = 0
                self.send_display_string(ascii_message, 0, self.__test)

    def __generate_7_char_string(self, display_string):
        max_length = 7
        if not display_string:
            return ' ' * max_length
        if len(display_string.strip()) > max_length and display_string.endswith(
            'dB') and display_string.find('.') != -1:
            display_string = display_string[:-2]
        if len(display_string) > max_length:
            for um in [' ',
                       'i',
                       'o',
                       'u',
                       'e',
                       'a']:
                while len(display_string) > max_length and display_string.rfind(um,
                                                                       1) != -1:
                    
                    um_pos = display_string.rfind(um, 1)
                    display_string = display_string[:um_pos] + display_string[
                                                               um_pos + 1:]

        else:
            display_string = display_string.center(max_length)
        ret = ''
        for i in range(max_length):
            ret += display_string[i]

        return ret
