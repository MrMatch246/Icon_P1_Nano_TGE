from __future__ import absolute_import, print_function, unicode_literals
from .consts import *

class P1NanoTGEComponent(object):
    """ Baseclass for every 'sub component' of the Mackie Control. Just offers some """

    def __init__(self, main_script):
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
        self.__main_script.send_midi(bytes)

    def request_rebuild_midi_map(self):
        self.__main_script.request_rebuild_midi_map()

    def visible_detail_viw(self):
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
            self.application().view.focus_view(self.visible_detail_viw())
        elif show_if_hidden:
            self.application().view.show_view('Detail')
            self.application().view.focus_view(self.visible_detail_viw())