from __future__ import absolute_import, print_function, unicode_literals

import sys

from .consts import *

class P1NanoTGEComponent(object):
    """ Baseclass for every 'sub component' of the Mackie Control. Just offers some """

    def __init__(self, main_script):
        self.__last_send_messages = [[], [], [], []]
        self.__main_script = main_script

    def destroy(self):
        self.__main_script = None

    def main_script(self):
        return self.__main_script

    def shift_is_pressed(self):
        return self.__main_script.shift_is_pressed()

    def option_is_pressed(self):
        return self.__main_script.option_is_pressed()

    def control_is_pressed(self):
        return self.__main_script.control_is_pressed()

    def alt_is_pressed(self):
        return self.__main_script.alt_is_pressed()

    def song(self):
        return self.__main_script.song()

    def script_handle(self):
        return self.__main_script.handle()

    def application(self):
        return self.__main_script.application()

    def send_midi(self, bytes):
        if self.__main_script:
            self.__main_script.send_midi(bytes)
        else:
            sys.stderr.write('Main script not available, cannot send MIDI message')

    def request_rebuild_midi_map(self):
        self.__main_script.request_rebuild_midi_map()

    def visible_detail_view(self):
        if self.application().view.is_view_visible('Detail/DeviceChain'):
            return "Detail/DeviceChain"
        elif self.application().view.is_view_visible('Detail/Clip'):
            return "Detail/Clip"

    def visible_main_view(self):
        if self.application().view.is_view_visible('Session'):
            return "Session"
        elif self.application().view.is_view_visible('Arranger'):
            return "Arranger"

    def focus_visible_detail_view(self,show_if_hidden=False):
        if self.application().view.is_view_visible('Detail'):
            self.application().view.focus_view(self.visible_detail_view())
        elif show_if_hidden:
            self.application().view.show_view('Detail')
            self.application().view.focus_view(self.visible_detail_view())

    def total_number_of_sends(self):
        return len(self.song().view.selected_track.mixer_device.sends)

    def tge_sends_slots(self):
        return min(NUM_CHANNEL_STRIPS - 1, self.total_number_of_sends())

    def tge_plugins_slots(self):
        return NUM_CHANNEL_STRIPS - 1 - self.tge_sends_slots()

    def tge_sends_indices(self):
        return range(1, 1 + self.tge_sends_slots())

    def tge_plugins_indices(self):
        return range(1 + self.tge_sends_slots(), NUM_CHANNEL_STRIPS)

    def sends(self):
        return self.song().view.selected_track.mixer_device.sends