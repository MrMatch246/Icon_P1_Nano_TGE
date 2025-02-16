import sys
from itertools import chain


from _Generic.Devices import *
from .P1NanoTGEComponent import *
from ableton.v3.live import track_index

flatten_target = lambda routing_target: routing_target.display_name


def flatten_target_list(target_list):
    """
        Takes a list of RoutingType- or RoutingChannel objects
        and returns a list of their `display_names`
    """
    target_names = []
    for target in target_list:
        name = flatten_target(target)
        if name not in target_names:
            target_names.append(name)
    return target_names


def target_by_name(target_list, name):
    """
        Return the first object in `target_list` whose `display_name` is equal to `name`
    """
    matches = [t for t in target_list if t.display_name == name]
    return matches[0] if matches else None


class ChannelStripController(P1NanoTGEComponent):
    """
       Controls all channel-strips of the Mackie Control and controller extensions
       (Mackie Control XTs) if available: Maps and controls the faders, VPots and the
       displays depending on the assignemnt modes (Vol_Pan, PlugIn, IO, Send) and
       edit and flip mode.

       stack_offset vs. strip_index vs. bank_channel_offset:

       When using multiple sets of channel strips (stacking them), we will still only
       have one ChannelStripController which rules them all.
       To identify and seperate them, the implementation uses 3 different kind of
       indices or offsets:

       - strip_index: is the index of a channel_strip within its controller box,
         so strip no 1 on an extension (XT) and strip number one on the 'main' Mackie
         will both have a strip_index of 1.
         We need to preserve this index, because every device (extension or main controller
         will use a unique MIDI port to send out its MIDI messages which uses the
         strip_index, encoded into the MIDI messages channel, to tell the hardware which
         channel on the controller is meant.

       - stack_offset: descibes how many channels are left to the device that a
         channel_strip belongs to. For example: You have 3 Mackies: First, a XT, then
         the main Mackie, then another XT.
         The first XT will have the stack_index 0, the main Mackie, the stack_index 8,
         because 8 faders are on present before it. The second XT has a stack_index of 16

       - bank_cha_offset: this shifts all available channel strips within all the tracks
         that should be controlled. For example: If you have a song with 32 tracks, and
         a main Mackie Control + a XT on the right, then you want to shift the first fader
         of the main Mackie to Track 16, to be able to control Track 16 to 32.

       The master channel strip is hardcoded and not in the list of "normal" channel_strips,
       because its always mapped to the master_volume.
    """

    def __init__(self, main_script, channel_strips, master_strip, main_display_controller):
        P1NanoTGEComponent.__init__(self, main_script)
        self.__left_extensions = []
        self.__right_extensions = []
        self.__own_channel_strips = channel_strips
        self.__master_strip = master_strip
        self.__channel_strips = channel_strips
        self.__main_display_controller = main_display_controller
        self.__meters_enabled = False
        self.__assignment_mode = CSM_MULTI_TGE
        self.__sub_mode_in_io_mode = CSM_IO_FIRST_MODE
        self.__plugin_mode = PCM_DEVICES
        self.__plugin_mode_offsets = [0 for x in range(PCM_NUMMODES)]
        self.__chosen_plugin = None
        self.__ordered_plugin_parameters = []
        self.__displayed_plugins = []
        self.__last_attached_selected_track = None
        self.__send_mode_offset = 0
        self.__flip = False
        self.__view_returns = False
        self.__bank_cha_offset = 0
        self.__bank_cha_offset_returns = 0
        self.__within_track_added_or_deleted = False
        self.song().add_visible_tracks_listener(
            self.__on_tracks_added_or_deleted)
        self.song().view.add_selected_track_listener(
            self.__on_selected_track_changed)
        for t in chain(self.song().visible_tracks, self.song().return_tracks):
            if not t.solo_has_listener(self.__update_rude_solo_led):
                t.add_solo_listener(self.__update_rude_solo_led)
            if not t.has_audio_output_has_listener(
                self.__on_any_tracks_output_type_changed):
                t.add_has_audio_output_listener(
                    self.__on_any_tracks_output_type_changed)
        self.__on_selected_track_changed()
        for s in self.__own_channel_strips:
            s.set_channel_strip_controller(self)
        self.__reassign_channel_strip_offsets()
        self.__reassign_channel_strip_parameters(for_display_only=False)
        self._last_assignment_mode = self.__assignment_mode

    def destroy(self):
        self.song().remove_visible_tracks_listener(
            self.__on_tracks_added_or_deleted)
        self.song().view.remove_selected_track_listener(
            self.__on_selected_track_changed)
        for t in chain(self.song().visible_tracks, self.song().return_tracks):
            if t.solo_has_listener(self.__update_rude_solo_led):
                t.remove_solo_listener(self.__update_rude_solo_led)
            if t.has_audio_output_has_listener(
                self.__on_any_tracks_output_type_changed):
                t.remove_has_audio_output_listener(
                    self.__on_any_tracks_output_type_changed)
        st = self.__last_attached_selected_track
        if st and st.devices_has_listener(
            self.__on_selected_device_chain_changed):
            st.remove_devices_listener(self.__on_selected_device_chain_changed)
        for note in channel_strip_assignment_switch_ids:
            self.send_midi((NOTE_ON_STATUS, note, BUTTON_STATE_OFF))
        for note in channel_strip_control_switch_ids:
            self.send_midi((NOTE_ON_STATUS, note, BUTTON_STATE_OFF))
        self.send_midi((NOTE_ON_STATUS, SELECT_RUDE_SOLO, BUTTON_STATE_OFF))
        self.send_midi((CC_STATUS, 75, g7_seg_led_conv_table[' ']))
        self.send_midi((CC_STATUS, 74, g7_seg_led_conv_table[' ']))
        P1NanoTGEComponent.destroy(self)

    def set_controller_extensions(self, left_extensions, right_extensions):
        u"""
            Called from the main script (after all scripts where initialized), to let us
            know where and how many MackieControlXT are installed.
            There exists only one ChannelStripController, so we will take care about the
            extensions channel strips
        """
        self.__left_extensions = left_extensions
        self.__right_extensions = right_extensions
        self.__channel_strips = []
        stack_offset = 0
        for le in left_extensions:
            for s in le.channel_strips():
                self.__channel_strips.append(s)
                s.set_stack_offset(stack_offset)
            stack_offset += NUM_CHANNEL_STRIPS
        for s in self.__own_channel_strips:
            self.__channel_strips.append(s)
            s.set_stack_offset(stack_offset)
        stack_offset += NUM_CHANNEL_STRIPS
        for re in right_extensions:
            for s in re.channel_strips():
                self.__channel_strips.append(s)
                s.set_stack_offset(stack_offset)
            stack_offset += NUM_CHANNEL_STRIPS
        for s in self.__channel_strips:
            s.set_channel_strip_controller(self)
        self.refresh_state()

    def refresh_state(self):
        self.__update_assignment_mode_leds()
        self.__update_assignment_display()
        self.__update_rude_solo_led()
        self.__reassign_channel_strip_offsets()
        self.__on_flip_changed()
        self.__update_view_returns_mode()

    def request_rebuild_midi_map(self):
        u""" Overridden to call also the extensions request_rebuild_midi_map """
        P1NanoTGEComponent.request_rebuild_midi_map(self)
        for ex in self.__left_extensions + self.__right_extensions:
            ex.request_rebuild_midi_map()

    def on_update_display_timer(self):
        
        self.__update_channel_strip_strings()

    def toggle_meter_mode(self):
        u""" Called from the main script when the display toggle button was pressed """
        self.__meters_enabled = not self.__meters_enabled
        self.__apply_meter_mode(meter_state_changed=True)

    def handle_assignment_switch_ids(self, switch_id, value):
        if switch_id == SID_ASSIGNMENT_IO:
            if value == BUTTON_PRESSED:
                self.__set_assignment_mode(CSM_IO)
                #self.__set_assignment_mode(CSM_MULTI_TGE)



        elif switch_id == SID_ASSIGNMENT_SENDS:
            if value == BUTTON_PRESSED:
                self.__set_assignment_mode(CSM_SENDS)
        elif switch_id == SID_ASSIGNMENT_PAN:
            if value == BUTTON_PRESSED:
                self.__set_assignment_mode(CSM_VOLPAN)
        elif switch_id == SID_ASSIGNMENT_PLUG_INS:
            if value == BUTTON_PRESSED:
                self.__set_assignment_mode(CSM_PLUGINS)
        elif switch_id == SID_ASSIGNMENT_EQ:
            if value == BUTTON_PRESSED:
                self.__switch_to_prev_page()
        elif switch_id == SID_ASSIGNMENT_DYNAMIC:
            if value == BUTTON_PRESSED:
                self.__switch_to_next_page()

    def handle_control_switch_ids(self, switch_id, value):
        """ Missing def added """
        if switch_id == SID_FADERBANK_PREV_BANK:
            if value == BUTTON_PRESSED:
                if self.shift_is_pressed():
                    self.__set_channel_offset(0)
                else:
                    self.__set_channel_offset(
                        self.__strip_offset() - len(self.__channel_strips))
        elif switch_id == SID_FADERBANK_NEXT_BANK:
            if value == BUTTON_PRESSED:
                if self.shift_is_pressed():
                    last_possible_offset = (
                                               (self.__controlled_num_of_tracks() - self.__strip_offset()) // len(self.__channel_strips)
                                           ) * len(self.__channel_strips) + self.__strip_offset()
                    if last_possible_offset == self.__controlled_num_of_tracks():
                        last_possible_offset -= len(self.__channel_strips)
                    self.__set_channel_offset(last_possible_offset)
                elif self.__strip_offset() < self.__controlled_num_of_tracks() - len(
                    self.__channel_strips):
                    self.__set_channel_offset(
                        self.__strip_offset() + len(self.__channel_strips))
        elif switch_id == SID_FADERBANK_PREV_CH:
            if value == BUTTON_PRESSED:
                if self.shift_is_pressed():
                    self.__set_channel_offset(0)
                else:
                    self.__set_channel_offset(self.__strip_offset() - 1)
        elif switch_id == SID_FADERBANK_NEXT_CH:
            if value == BUTTON_PRESSED:
                if self.shift_is_pressed():
                    self.__set_channel_offset(
                        self.__controlled_num_of_tracks() - len(
                            self.__channel_strips))
                elif self.__strip_offset() < self.__controlled_num_of_tracks() - len(
                    self.__channel_strips):
                    self.__set_channel_offset(self.__strip_offset() + 1)
        elif switch_id == SID_FADERBANK_FLIP:
            if value == BUTTON_PRESSED:
                self.__toggle_flip()
        elif switch_id == SID_FADERBANK_EDIT:
            if value == BUTTON_PRESSED:
                self.__toggle_view_returns()

    def handle_vpot_rotation(self, strip_index, stack_offset, cc_value):
        """ Forwarded to us by the channel_strips """
        if self.__assignment_mode == CSM_IO:
            if cc_value >= 64:
                direction = -1
            else:
                direction = 1
            channel_strip = self.__channel_strips[stack_offset + strip_index]
            current_routing = self.__routing_target(channel_strip)
            available_routings = self.__available_routing_targets(channel_strip)
            if current_routing and available_routings:
                if current_routing in available_routings:
                    i = list(available_routings).index(current_routing)
                    if direction == 1:
                        new_i = min(len(available_routings) - 1, i + direction)
                    else:
                        new_i = max(0, i + direction)
                    new_routing = available_routings[new_i]
                elif len(available_routings):
                    new_routing = available_routings[0]
                self.__set_routing_target(channel_strip, new_routing)
        elif self.__assignment_mode == CSM_PLUGINS:
            return
        elif self.__assignment_mode == CSM_MULTI_TGE:
            #TODO Check if we are actually supposed to just return here.
            #It appears that the vpot is already connected to the parameters in the plugins case
            # which means that we would then be connected too.
            # Only IO mode is to be done manually.
            # I want to implement a new rotation target that switches things
            # in the script, this would probably the place for this
            return

        channel_strip = self.__channel_strips[stack_offset + strip_index]

    def handle_fader_touch(self, strip_offset, stack_offset, touched):
        """ Forwarded to us by the channel_strips """
        self.__reassign_channel_strip_parameters(for_display_only=True)

    def handle_pressed_v_pot(self, strip_index, stack_offset):
        u""" Forwarded to us by the channel_strips """
        if self.__assignment_mode == CSM_VOLPAN or self.__assignment_mode == CSM_SENDS or self.__assignment_mode == CSM_PLUGINS and self.__plugin_mode == PCM_PARAMETERS:
            self.handle_pressed_v_pot_reset_value(stack_offset, strip_index)
        elif self.__assignment_mode == CSM_PLUGINS and self.__plugin_mode == PCM_DEVICES:
            self.handle_pressed_v_pot_plugin_device(stack_offset, strip_index)
        elif self.__assignment_mode == CSM_MULTI_TGE:
            if strip_index in range(0, self.total_number_of_sends() + 1):
                self.handle_pressed_v_pot_reset_value(stack_offset, strip_index)
            elif strip_index in range(self.total_number_of_sends() + 1, NUM_CHANNEL_STRIPS + 1):
                if self.__plugin_mode == PCM_DEVICES:
                    self.handle_pressed_v_pot_plugin_device(stack_offset, strip_index - self.total_number_of_sends() - 1)
                elif self.__plugin_mode == PCM_PARAMETERS:
                    self.handle_pressed_v_pot_reset_value(stack_offset, strip_index)

    def handle_pressed_v_pot_reset_value(self, stack_offset, strip_index):
        if stack_offset + strip_index in range(0, len(self.__channel_strips)):
            param = self.__channel_strips[
                stack_offset + strip_index].v_pot_parameter()
        if param and param.is_enabled:
            if param.is_quantized:
                if param.value + 1 > param.max:
                    param.value = param.min
                else:
                    param.value = param.value + 1
            else:
                param.value = param.default_value

    def handle_pressed_v_pot_plugin_device(self, stack_offset, strip_index):
        #sys.stderr.write(f"handle_pressed_v_pot_plugin_device: {stack_offset}, {strip_index}\n")
        device_index = strip_index + stack_offset + self.__plugin_mode_offsets[
            PCM_DEVICES]
        if device_index >= 0 and device_index < len(
            self.song().view.selected_track.devices):
            if self.__chosen_plugin != None:
                self.__chosen_plugin.remove_parameters_listener(
                    self.__on_parameter_list_of_chosen_plugin_changed)
            self.__chosen_plugin = self.song().view.selected_track.devices[
                device_index]
            if self.__chosen_plugin != None:
                self.__chosen_plugin.add_parameters_listener(
                    self.__on_parameter_list_of_chosen_plugin_changed)
            self.__reorder_parameters()
            self.__plugin_mode_offsets[PCM_PARAMETERS] = 0
            self.__set_plugin_mode(PCM_PARAMETERS)

    def assignment_mode(self):
        return self.__assignment_mode

    def __strip_offset(self):
        """ Return the bank_channel offset depending if we are in return mode or not """
        if self.__view_returns:
            return self.__bank_cha_offset_returns
        return self.__bank_cha_offset

    def __controlled_num_of_tracks(self):
        """
            Return the number of tracks, depending on if we are in send_track
            mode or normal track mode
        """
        if self.__view_returns:
            return len(self.song().return_tracks)
        return len(self.song().visible_tracks)

    def __send_parameter(self, strip_index, stack_index):
        """ Return the send parameter that is assigned to the given channel strip """

        send_index = strip_index + stack_index + self.__send_mode_offset
        if send_index < len(self.song().view.selected_track.mixer_device.sends):
            p = self.song().view.selected_track.mixer_device.sends[send_index]
            return (p, p.name)
        return (None, None)

    def __plugin_parameter(self, strip_index, stack_index):
        """ Return the parameter that is assigned to the given channel strip """

        if self.__plugin_mode == PCM_DEVICES:
            return (None, None)
        if self.__plugin_mode == PCM_PARAMETERS:
            parameters = self.__ordered_plugin_parameters
            parameter_index = strip_index + stack_index + \
                              self.__plugin_mode_offsets[PCM_PARAMETERS]
            if parameter_index >= 0 and parameter_index < len(parameters):
                return parameters[parameter_index]
            return (None, None)

    def __any_fader_is_touched(self):
        for s in self.__channel_strips:
            if s.is_touched():
                return True
        else:
            return False

    def __can_flip(self):
        if self.__assignment_mode == CSM_PLUGINS and self.__plugin_mode == PCM_DEVICES:
            return False
        if self.__assignment_mode == CSM_IO:
            return False
        return True

    def __can_switch_to_prev_page(self):
        """ Return true if pressing the "prev" button will have any effect """
        if self.__assignment_mode == CSM_PLUGINS:
            return self.__plugin_mode_offsets[self.__plugin_mode] > 0
        elif self.__assignment_mode == CSM_SENDS:
            return self.__send_mode_offset > 0
        elif self.__assignment_mode == CSM_MULTI_TGE:
            #TODO TEST THIS
            if self.tge_plugins_slots() > 0:
                return self.__plugin_mode_offsets[self.__plugin_mode] > 0
            elif self.tge_sends_slots() > 0:
                return self.__send_mode_offset > 0
        else:
            return False

    def __can_switch_to_next_page(self):
        """ Return true if pressing the "next" button will have any effect """
        #TODO TEST THIS
        do_plugins = False
        do_sends = False
        plugin_page_size = len(self.__channel_strips)
        send_page_size = len(self.__channel_strips)
        if self.__assignment_mode == CSM_MULTI_TGE:
            do_plugins = self.tge_plugins_slots() > 0
            do_sends = self.tge_sends_slots() > 0
            plugin_page_size = self.tge_plugins_slots()
            send_page_size = self.tge_sends_slots()


        if self.__assignment_mode == CSM_PLUGINS or do_plugins:
            sel_track = self.song().view.selected_track
            if self.__plugin_mode == PCM_DEVICES:
                return self.__plugin_mode_offsets[PCM_DEVICES] + plugin_page_size < len(sel_track.devices)
            if self.__plugin_mode == PCM_PARAMETERS:
                parameters = self.__ordered_plugin_parameters
                return self.__plugin_mode_offsets[PCM_PARAMETERS] + plugin_page_size < len(parameters)
        elif self.__assignment_mode == CSM_SENDS or do_sends:
            return self.__send_mode_offset + send_page_size < len(self.song().return_tracks)
        return False

    def __available_routing_targets(self, channel_strip):
        t = channel_strip.assigned_track()
        if t:
            if self.__sub_mode_in_io_mode == CSM_IO_MODE_INPUT_MAIN:
                return flatten_target_list(t.available_input_routing_types)
            if self.__sub_mode_in_io_mode == CSM_IO_MODE_INPUT_SUB:
                return flatten_target_list(t.available_input_routing_channels)
            if self.__sub_mode_in_io_mode == CSM_IO_MODE_OUTPUT_MAIN:
                return flatten_target_list(t.available_output_routing_types)
            if self.__sub_mode_in_io_mode == CSM_IO_MODE_OUTPUT_SUB:
                return flatten_target_list(t.available_output_routing_channels)
        else:
            return None

    def __routing_target(self, channel_strip):
        t = channel_strip.assigned_track()
        if t:
            if self.__sub_mode_in_io_mode == CSM_IO_MODE_INPUT_MAIN:
                return flatten_target(t.input_routing_type)
            if self.__sub_mode_in_io_mode == CSM_IO_MODE_INPUT_SUB:
                return flatten_target(t.input_routing_channel)
            if self.__sub_mode_in_io_mode == CSM_IO_MODE_OUTPUT_MAIN:
                return flatten_target(t.output_routing_type)
            if self.__sub_mode_in_io_mode == CSM_IO_MODE_OUTPUT_SUB:
                return flatten_target(t.output_routing_channel)
        else:
            return None

    def __set_routing_target(self, channel_strip, target_string):
        t = channel_strip.assigned_track()
        if t:
            if self.__sub_mode_in_io_mode == CSM_IO_MODE_INPUT_MAIN:
                t.input_routing_type = target_by_name(
                    t.available_input_routing_types, target_string)
            elif self.__sub_mode_in_io_mode == CSM_IO_MODE_INPUT_SUB:
                t.input_routing_channel = target_by_name(
                    t.available_input_routing_channels, target_string)
            elif self.__sub_mode_in_io_mode == CSM_IO_MODE_OUTPUT_MAIN:
                t.output_routing_type = target_by_name(
                    t.available_output_routing_types, target_string)
            elif self.__sub_mode_in_io_mode == CSM_IO_MODE_OUTPUT_SUB:
                t.output_routing_channel = target_by_name(
                    t.available_output_routing_channels, target_string)

    def __set_channel_offset(self, new_offset):
        """
            Set and validate a new channel_strip offset, which shifts all available channel
            strips within all the available tracks or reutrn tracks
        """
        if new_offset < 0:
            new_offset = 0
        elif new_offset >= self.__controlled_num_of_tracks():
            new_offset = self.__controlled_num_of_tracks() - 1
        if self.__view_returns:
            self.__bank_cha_offset_returns = new_offset
        else:
            self.__bank_cha_offset = new_offset
        self.__main_display_controller.set_channel_offset(new_offset)
        self.__reassign_channel_strip_offsets()
        self.__reassign_channel_strip_parameters(for_display_only=False)
        self.__update_channel_strip_strings()
        self.request_rebuild_midi_map()

    def set_assignment_mode(self, mode):
        self.__set_assignment_mode(mode)

    def __set_assignment_mode(self, mode):
        for plugin in self.__displayed_plugins:
            if plugin != None:
                plugin.remove_name_listener(self.__update_plugin_names)
        self.__displayed_plugins = []
        self.__main_display_controller.set_show_current_track_colors(False)
        if mode == CSM_PLUGINS:
            self.__assignment_mode = mode
            self.__main_display_controller.set_show_parameter_names(True)
            self.__main_display_controller.set_show_current_track_colors(True)
            self.__set_plugin_mode(PCM_DEVICES)
        elif mode == CSM_SENDS:
            self.__main_display_controller.set_show_parameter_names(True)
            self.__main_display_controller.set_show_current_track_colors(True)
            self.__assignment_mode = mode
        elif mode == CSM_MULTI_TGE:
            #TODO TEST THIS
            self.__main_display_controller.set_show_parameter_names(True)
            self.__main_display_controller.set_show_current_track_colors(True)
            self.__assignment_mode = mode
            self.__set_plugin_mode(PCM_DEVICES)
        else:
            if mode == CSM_IO:
                for s in self.__channel_strips:
                    s.unlight_vpot_leds()

            self.__main_display_controller.set_show_parameter_names(False)
            if self.__assignment_mode != mode:
                self.__assignment_mode = mode
            elif self.__assignment_mode == CSM_IO:
                self.__switch_to_next_io_mode()

        self.__update_assignment_mode_leds()
        self.__update_assignment_display()
        self.__apply_meter_mode()
        self.__reassign_channel_strip_parameters(for_display_only=False)
        self.__update_channel_strip_strings()
        self.__update_page_switch_leds()

        #TODO TEST THIS
        if mode == CSM_PLUGINS or mode == CSM_MULTI_TGE:
            self.__update_vpot_leds_in_plugins_device_choose_mode()
        self.__update_flip_led()
        self.request_rebuild_midi_map()


    def __set_plugin_mode(self, new_mode):
        """
            Set a new plugin sub-mode, which can be:
            1. Choosing the device to control (PCM_DEVICES)
            2. Controlling the chosen devices parameters (PCM_PARAMETERS)
        """

        if self.__plugin_mode != new_mode:
            self.__plugin_mode = new_mode
            self.__reassign_channel_strip_parameters(for_display_only=False)
            self.request_rebuild_midi_map()
            if self.__plugin_mode == PCM_DEVICES:
                self.__update_vpot_leds_in_plugins_device_choose_mode()
            else:
                for plugin in self.__displayed_plugins:
                    if plugin != None:
                        plugin.remove_name_listener(self.__update_plugin_names)

                self.__displayed_plugins = []
            self.__update_page_switch_leds()
            self.__update_flip_led()
            self.__update_page_switch_leds()


    def __switch_to_prev_page(self):
        """
            Switch to the previous page in the non track strip modes (choosing plugs, or
            controlling devices)
        """
        if self.__can_switch_to_prev_page():
            do_plugins = False
            do_sends = False
            plugin_page_size = len(self.__channel_strips)
            send_page_size = len(self.__channel_strips)
            if self.__assignment_mode == CSM_MULTI_TGE:
                do_plugins = len(self.plugin_strips_tge()) > 0
                do_sends = len(self.send_strips_tge()) > 0
                plugin_page_size = self.tge_plugins_slots()
                send_page_size = self.tge_sends_slots()

            if self.__assignment_mode == CSM_PLUGINS or do_plugins:
                self.__plugin_mode_offsets[self.__plugin_mode] -= plugin_page_size
                if self.__plugin_mode == PCM_DEVICES:
                    self.__update_vpot_leds_in_plugins_device_choose_mode()
            elif self.__assignment_mode == CSM_SENDS or do_sends:
                self.__send_mode_offset -= send_page_size
            self.__reassign_channel_strip_parameters(for_display_only=False)
            self.__update_channel_strip_strings()
            self.__update_page_switch_leds()
            self.request_rebuild_midi_map()

    def __switch_to_next_page(self):
        """
            Switch to the next page in the non track strip modes (choosing plugs, or
            controlling devices)
        """
        if self.__can_switch_to_next_page():
            do_plugins = False
            do_sends = False
            plugin_page_size = len(self.__channel_strips)
            send_page_size = len(self.__channel_strips)
            if self.__assignment_mode == CSM_MULTI_TGE:
                do_plugins = self.tge_plugins_slots() > 0
                do_sends = self.tge_sends_slots() > 0
                plugin_page_size = self.tge_plugins_slots()
                send_page_size = self.tge_sends_slots()


            if self.__assignment_mode == CSM_PLUGINS or do_plugins:
                self.__plugin_mode_offsets[self.__plugin_mode] += plugin_page_size
                if self.__plugin_mode == PCM_DEVICES:
                    self.__update_vpot_leds_in_plugins_device_choose_mode()
            elif self.__assignment_mode == CSM_SENDS or do_sends:
                self.__send_mode_offset += send_page_size
            self.__reassign_channel_strip_parameters(for_display_only=False)
            self.__update_channel_strip_strings()
            self.__update_page_switch_leds()
            self.request_rebuild_midi_map()

    def __switch_to_next_io_mode(self):
        """ Step through the available IO modes (In/OutPut//Main/Sub) """
        self.__sub_mode_in_io_mode += 1
        if self.__sub_mode_in_io_mode > CSM_IO_LAST_MODE:
            self.__sub_mode_in_io_mode = CSM_IO_FIRST_MODE

    def __reassign_channel_strip_offsets(self):
        """ Update the channel strips bank_channel offset
        """
        for s in self.__channel_strips:
            s.set_bank_and_channel_offset(self.__strip_offset(),
                                          self.__view_returns,
                                          self.__within_track_added_or_deleted)
    def pan_strip_tge(self):
        return self.__channel_strips[0]

    def send_strips_tge(self):
        #TODO CHECK OFFSETS HERE, MAYBE NEED TO ADD or SUBSTRACT 1
        return self.__channel_strips[1:min(NUM_CHANNEL_STRIPS, self.total_number_of_sends() + 1)]

    def plugin_strips_tge(self):
        #TODO CHECK OFFSETS HERE, MAYBE NEED TO ADD or SUBSTRACT 1
        if self.total_number_of_sends() + 1 < NUM_CHANNEL_STRIPS:
            return self.__channel_strips[self.total_number_of_sends() + 1:NUM_CHANNEL_STRIPS]
        else:
            return []

    def __reassign_channel_strip_parameters(self, for_display_only):
        """ Reevaluate all v-pot/fader -> parameter assignments """
        display_parameters = []
        current_strip = self.__channel_strips[0]
        current_track = current_strip.assigned_track()
        for index, s in enumerate(self.__channel_strips):
            vpot_param = (None, None)
            slider_param = (None, None)
            vpot_display_mode = VPOT_DISPLAY_SINGLE_DOT
            slider_display_mode = VPOT_DISPLAY_SINGLE_DOT

            if self.__assignment_mode == CSM_MULTI_TGE:

                do_volpan = index == 0
                do_sends = index in self.tge_sends_indices()
                do_plugins =  index in self.tge_plugins_indices()
                #sys.stderr.write("do_volpan: " + str(do_volpan) + " do_sends: " + str(do_sends) + " do_plugins: " + str(do_plugins) )
                if do_volpan:
                    if current_track and current_track.has_audio_output:
                        vpot_param = (current_track.mixer_device.panning, current_track.name)
                        vpot_display_mode = VPOT_DISPLAY_BOOST_CUT
                        slider_param = (current_track.mixer_device.volume, u'Volume')
                        slider_display_mode = VPOT_DISPLAY_WRAP
                    elif current_track:
                        vpot_param = (None, current_track.name)

                elif do_plugins:
                    vpot_param = self.__plugin_parameter(index - self.total_number_of_sends() - 1, current_strip.stack_offset())
                    vpot_display_mode = VPOT_DISPLAY_WRAP
                    if current_track and current_track.has_audio_output:
                        slider_param = (current_track.mixer_device.volume, u'Volume')
                        slider_display_mode = VPOT_DISPLAY_WRAP

                elif do_sends:
                    vpot_param = self.__send_parameter(index-1, current_strip.stack_offset())
                    vpot_display_mode = VPOT_DISPLAY_WRAP
                    if current_track and current_track.has_audio_output:
                        slider_param = (current_track.mixer_device.volume, u'Volume')
                        slider_display_mode = VPOT_DISPLAY_WRAP
            else:
                if self.__assignment_mode == CSM_VOLPAN:
                    if s.assigned_track() and s.assigned_track().has_audio_output:
                        vpot_param = (s.assigned_track().mixer_device.panning, u'Pan')
                        vpot_display_mode = VPOT_DISPLAY_BOOST_CUT
                        slider_param = (s.assigned_track().mixer_device.volume, u'Volume')
                        slider_display_mode = VPOT_DISPLAY_WRAP

                elif self.__assignment_mode == CSM_PLUGINS:
                    vpot_param = self.__plugin_parameter(s.strip_index(), s.stack_offset())
                    vpot_display_mode = VPOT_DISPLAY_WRAP
                    if s.assigned_track() and s.assigned_track().has_audio_output:
                        slider_param = (s.assigned_track().mixer_device.volume, u'Volume')
                        slider_display_mode = VPOT_DISPLAY_WRAP

                elif self.__assignment_mode == CSM_SENDS:
                    vpot_param = self.__send_parameter(s.strip_index(), s.stack_offset())
                    vpot_display_mode = VPOT_DISPLAY_WRAP
                    if s.assigned_track() and s.assigned_track().has_audio_output:
                        slider_param = (s.assigned_track().mixer_device.volume, u'Volume')
                        slider_display_mode = VPOT_DISPLAY_WRAP

                elif self.__assignment_mode == CSM_IO:
                    if s.assigned_track() and s.assigned_track().has_audio_output:
                        slider_param = (s.assigned_track().mixer_device.volume, u'Volume')
            if self.__flip and self.__can_flip():
                if self.__any_fader_is_touched():
                    display_parameters.append(vpot_param)
                else:
                    display_parameters.append(slider_param)
                if not for_display_only:
                    s.set_v_pot_parameter(slider_param[0], slider_display_mode)
                    s.set_fader_parameter(vpot_param[0])
            else:
                if self.__any_fader_is_touched():
                    display_parameters.append(slider_param)
                else:
                    display_parameters.append(vpot_param)
                if not for_display_only:
                    s.set_v_pot_parameter(vpot_param[0], vpot_display_mode)
                    s.set_fader_parameter(slider_param[0])
        self.__main_display_controller.set_channel_offset(self.__strip_offset())
        if len(display_parameters):
            self.__main_display_controller.set_parameters(display_parameters)
        if (self.__assignment_mode == CSM_PLUGINS or self.__assignment_mode == CSM_MULTI_TGE) and self.__plugin_mode == PCM_DEVICES:
            self.__update_vpot_leds_in_plugins_device_choose_mode()

    def _need_to_update_meter(self, meter_state_changed):
        #TODO TEST THIS
        return meter_state_changed and (self.__assignment_mode == CSM_VOLPAN or self.__assignment_mode == CSM_MULTI_TGE)

    def __apply_meter_mode(self, meter_state_changed = False):
        """ Update the meter mode in the displays and channel strips """
        if self.__assignment_mode == CSM_MULTI_TGE:
            #TODO TEST THIS !!!!
            for index, s in enumerate(self.__channel_strips):
                if index == 0:
                    s.enable_meter_mode(True, needs_to_send_meter_mode=self._need_to_update_meter(meter_state_changed))
                else:
                    s.enable_meter_mode(False, needs_to_send_meter_mode=self._need_to_update_meter(meter_state_changed))


        enabled = self.__meters_enabled and self.__assignment_mode is CSM_VOLPAN
        send_meter_mode = self._last_assignment_mode != self.__assignment_mode or self._need_to_update_meter(
            meter_state_changed)
        for s in self.__channel_strips:
            s.enable_meter_mode(enabled,
                                needs_to_send_meter_mode=send_meter_mode)
        self.__main_display_controller.enable_meters(enabled)
        self._last_assignment_mode = self.__assignment_mode

    def __toggle_flip(self):
        """ En/Disable V-Pot / Fader flipping """
        if self.__can_flip():
            self.__flip = not self.__flip
            self.__on_flip_changed()

    def __toggle_view_returns(self):
        """ Toggle if we want to control the return tracks or normal tracks """
        self.__view_returns = not self.__view_returns
        self.__update_view_returns_mode()

    def __update_assignment_mode_leds(self):
        """ Show which assignment mode is currently active """
        #TGE Patch we remove IO and Add Multi Mode
        if self.__assignment_mode == CSM_IO:
            sid_on_switch = SID_ASSIGNMENT_IO
        elif self.__assignment_mode == CSM_MULTI_TGE:
            sid_on_switch = SID_SOFTWARE_F1
            #sid_on_switch = SID_ASSIGNMENT_IO
        elif self.__assignment_mode == CSM_SENDS:
            sid_on_switch = SID_ASSIGNMENT_SENDS
        elif self.__assignment_mode == CSM_VOLPAN:
            sid_on_switch = SID_ASSIGNMENT_PAN
        elif self.__assignment_mode == CSM_PLUGINS:
            sid_on_switch = SID_ASSIGNMENT_PLUG_INS
        else:
            sid_on_switch = None
        assignment_switch_ids = [SID_ASSIGNMENT_IO, SID_ASSIGNMENT_SENDS, SID_ASSIGNMENT_PAN, SID_ASSIGNMENT_PLUG_INS,SID_SOFTWARE_F1]
        assignment_switch_ids.remove(sid_on_switch)
        for s in assignment_switch_ids:
            self.send_midi((NOTE_ON_STATUS, s, BUTTON_STATE_OFF))
            self.send_midi((NOTE_ON_STATUS, s, BUTTON_STATE_OFF))
        self.send_midi((NOTE_ON_STATUS, sid_on_switch, BUTTON_STATE_ON))
        self.send_midi((NOTE_ON_STATUS, sid_on_switch, BUTTON_STATE_ON))


    def __update_assignment_display(self):
        """
            Update the main display to show the current assignment mode
            It works like this:
            - In VolPan mode, show the track name of the first track
            - In Send mode, show the send name of the first send
            - In Plugin mode, show the device name of the first device
            - In IO mode, show the routing target of the first track

        """
        ass_string = [' ', ' ']
        if self.__assignment_mode == CSM_VOLPAN:
            ass_string = ['P', 'N']
        elif self.__assignment_mode == CSM_PLUGINS or self.__assignment_mode == CSM_SENDS:
            if self.__last_attached_selected_track == self.song().master_track:
                ass_string = ['M', 'A']
            for t in self.song().return_tracks:
                if t == self.__last_attached_selected_track:
                    ass_string = ['R', chr(ord('A') + list(
                        self.song().return_tracks).index(t))]
                    break
            for t in self.song().visible_tracks:
                if t == self.__last_attached_selected_track:
                    ass_string = list('%.2d' % min(99, list(
                        self.song().visible_tracks).index(t) + 1))
                    break
        elif self.__assignment_mode == CSM_IO:
            if self.__sub_mode_in_io_mode == CSM_IO_MODE_INPUT_MAIN:
                ass_string = ['I', "'"]
            elif self.__sub_mode_in_io_mode == CSM_IO_MODE_INPUT_SUB:
                ass_string = ['I', ',']
            elif self.__sub_mode_in_io_mode == CSM_IO_MODE_OUTPUT_MAIN:
                ass_string = ['0', "'"]
            elif self.__sub_mode_in_io_mode == CSM_IO_MODE_OUTPUT_SUB:
                ass_string = ['0', ',']
            else:
                pass
        elif self.__assignment_mode == CSM_MULTI_TGE:
            #TODO TGE: Implement this correctly once external display arrives
            ass_string = ['T','G']
        self.send_midi((CC_STATUS, 75, g7_seg_led_conv_table[ass_string[0]]))
        self.send_midi((CC_STATUS, 74, g7_seg_led_conv_table[ass_string[1]]))

    def __update_rude_solo_led(self):
        any_track_soloed = False
        for t in chain(self.song().tracks, self.song().return_tracks):
            if t.solo:
                any_track_soloed = True
                break
        if any_track_soloed:
            self.send_midi((NOTE_ON_STATUS, SELECT_RUDE_SOLO, BUTTON_STATE_ON))
        else:
            self.send_midi((NOTE_ON_STATUS, SELECT_RUDE_SOLO, BUTTON_STATE_OFF))

    def __update_page_switch_leds(self):
        """ Visualize if the "prev" an "next" buttons can be pressed """
        if self.__can_switch_to_prev_page():
            self.send_midi((NOTE_ON_STATUS, SID_ASSIGNMENT_EQ, BUTTON_STATE_ON))
        else:
            self.send_midi(
                (NOTE_ON_STATUS, SID_ASSIGNMENT_EQ, BUTTON_STATE_OFF))
        if self.__can_switch_to_next_page():
            self.send_midi(
                (NOTE_ON_STATUS, SID_ASSIGNMENT_DYNAMIC, BUTTON_STATE_ON))
        else:
            self.send_midi(
                (NOTE_ON_STATUS, SID_ASSIGNMENT_DYNAMIC, BUTTON_STATE_OFF))

    def __update_flip_led(self):
        if self.__flip and self.__can_flip():
            self.send_midi(
                (NOTE_ON_STATUS, SID_FADERBANK_FLIP, BUTTON_STATE_ON))
        else:
            self.send_midi(
                (NOTE_ON_STATUS, SID_FADERBANK_FLIP, BUTTON_STATE_OFF))

    def __update_vpot_leds_in_plugins_device_choose_mode(self):
        """
            To be called in assignment mode CSM_PLUGINS, submode PCM_DEVICES only:
            This will enlighten all poties which can be pressed to choose a device
            for editing, and unlight all poties where pressing will have no effect
        """
        sel_track = self.song().view.selected_track
        count = 0
        for s in self.__channel_strips:
            offset = self.__plugin_mode_offsets[self.__plugin_mode]
            if sel_track and offset + count >= 0 and (
                offset + count < len(sel_track.devices)):
                s.show_full_enlighted_poti()
            else:
                s.unlight_vpot_leds()
            count += 1

    def __update_channel_strip_strings(self):
        """ In IO mode, collect all strings that will be visible in the main display manually """
        if not self.__any_fader_is_touched():

            if self.__assignment_mode == CSM_MULTI_TGE and self.__plugin_mode == PCM_DEVICES:
                for plugin in self.__displayed_plugins:
                    if plugin != None:
                        plugin.remove_name_listener(self.__update_plugin_names)
                self.__displayed_plugins = []
                sel_track = self.song().view.selected_track
                plugin_start = self.total_number_of_sends() + 1 #+ self.__plugin_mode_offsets[PCM_DEVICES]G
                for i in range(len(self.__channel_strips)):
                    device_index = i - plugin_start + self.__plugin_mode_offsets[PCM_DEVICES]
                    if i >= plugin_start and i < len(sel_track.devices) + plugin_start:

                        if device_index < len(sel_track.devices):
                            sel_track.devices[device_index].add_name_listener(
                                self.__update_plugin_names)
                            self.__displayed_plugins.append(
                                sel_track.devices[device_index])
                        else:
                            self.__displayed_plugins.append(None)
                    else:
                        self.__displayed_plugins.append(None)
                device_strings = {}
                for index,plugin in enumerate(self.__displayed_plugins):
                    if plugin != None:
                        device_strings[index] = plugin.name

                #sys.stderr.write(f"Updating plugin names: {device_strings}\n")
                self.__main_display_controller.update_channel_strip_strings(device_strings)
            elif self.__assignment_mode == CSM_IO:
                targets = []
                for s in self.__channel_strips:
                    if self.__routing_target(s):
                        targets.append(self.__routing_target(s))
                    else:
                        targets.append('')
                self.__main_display_controller.set_channel_strip_strings(
                    targets)
            elif self.__assignment_mode == CSM_PLUGINS and self.__plugin_mode == PCM_DEVICES:
                for plugin in self.__displayed_plugins:
                    if plugin != None:
                        plugin.remove_name_listener(self.__update_plugin_names)
                self.__displayed_plugins = []
                sel_track = self.song().view.selected_track
                for i in range(len(self.__channel_strips)):
                    device_index = i + self.__plugin_mode_offsets[PCM_DEVICES]
                    if device_index >= 0 and device_index < len(
                        sel_track.devices):
                        sel_track.devices[device_index].add_name_listener(
                            self.__update_plugin_names)
                        self.__displayed_plugins.append(
                            sel_track.devices[device_index])
                    else:
                        self.__displayed_plugins.append(None)
                self.__update_plugin_names()

    def __update_plugin_names(self):
        device_strings = []
        for plugin in self.__displayed_plugins:
            if plugin != None:
                device_strings.append(plugin.name)
            else:
                device_strings.append('')
        self.__main_display_controller.set_channel_strip_strings(device_strings)

    def __update_view_returns_mode(self):
        """ Update the control return tracks LED """
        if self.__view_returns:
            self.send_midi(
                (NOTE_ON_STATUS, SID_FADERBANK_EDIT, BUTTON_STATE_ON))
        else:
            self.send_midi(
                (NOTE_ON_STATUS, SID_FADERBANK_EDIT, BUTTON_STATE_OFF))
        self.__main_display_controller.set_show_return_track_names(
            self.__view_returns)
        self.__reassign_channel_strip_offsets()
        self.__reassign_channel_strip_parameters(for_display_only=False)
        self.request_rebuild_midi_map()

    def __on_selected_track_changed(self):
        """ Notifier, called as soon as the selected track has changed """
        st = self.__last_attached_selected_track
        if st and st.devices_has_listener(
            self.__on_selected_device_chain_changed):
            st.remove_devices_listener(self.__on_selected_device_chain_changed)
        self.__last_attached_selected_track = self.song().view.selected_track
        st = self.__last_attached_selected_track
        if st:
            st.add_devices_listener(self.__on_selected_device_chain_changed)

        if not self.__view_returns:
            for i, track in enumerate(self.song().visible_tracks):
                if track == self.song().view.selected_track:
                    self.__set_channel_offset(i)
                    #sys.stderr.write(f"Setting channel offset to {i} for track {track.name}\n")
                    break


        #TODO TEST THIS
        if self.__assignment_mode == CSM_MULTI_TGE:
            do_plugin = self.tge_plugins_slots() > 0
            do_sends = self.tge_sends_slots() > 0
        else:
            do_plugin = self.__assignment_mode == CSM_PLUGINS
            do_sends = self.__assignment_mode == CSM_SENDS

        if do_plugin:
            self.__plugin_mode_offsets = [0 for x in range(PCM_NUMMODES)]
            if self.__chosen_plugin != None:
                self.__chosen_plugin.remove_parameters_listener(
                    self.__on_parameter_list_of_chosen_plugin_changed)
            self.__chosen_plugin = None
            self.__ordered_plugin_parameters = []
            self.__update_assignment_display()
            if self.__plugin_mode == PCM_DEVICES:
                self.__update_vpot_leds_in_plugins_device_choose_mode()
            else:
                self.__set_plugin_mode(PCM_DEVICES)
        if do_sends:
            self.__reassign_channel_strip_parameters(for_display_only=False)
            self.__update_assignment_display()
            self.request_rebuild_midi_map()

    def __on_flip_changed(self):
        """ Update the flip button LED when the flip mode changed """
        self.__update_flip_led()
        if self.__can_flip():
            self.__update_assignment_display()
            self.__reassign_channel_strip_parameters(for_display_only=False)
            self.request_rebuild_midi_map()

    def __on_selected_device_chain_changed(self):
        """ Notifier, called as soon as the selected device chain has changed """
        #TODO TEST THIS
        if self.__assignment_mode == CSM_PLUGINS or self.__assignment_mode == CSM_MULTI_TGE:
            if self.__plugin_mode == PCM_DEVICES:
                self.__update_vpot_leds_in_plugins_device_choose_mode()
                self.__update_page_switch_leds()
            elif self.__plugin_mode == PCM_PARAMETERS:
                if not self.__chosen_plugin:
                    self.__set_plugin_mode(PCM_DEVICES)
                elif self.__chosen_plugin not in self.__last_attached_selected_track.devices:
                    if self.__chosen_plugin != None:
                        self.__chosen_plugin.remove_parameters_listener(
                            self.__on_parameter_list_of_chosen_plugin_changed)
                    self.__chosen_plugin = None
                    self.__set_plugin_mode(PCM_DEVICES)

    def __on_tracks_added_or_deleted(self):
        """ Notifier, called as soon as tracks where added, removed or moved """
        self.__within_track_added_or_deleted = True
        for t in chain(self.song().visible_tracks, self.song().return_tracks):
            if not t.solo_has_listener(self.__update_rude_solo_led):
                t.add_solo_listener(self.__update_rude_solo_led)
            if not t.has_audio_output_has_listener(
                self.__on_any_tracks_output_type_changed):
                t.add_has_audio_output_listener(
                    self.__on_any_tracks_output_type_changed)
        if self.__send_mode_offset >= len(self.song().return_tracks):
            self.__send_mode_offset = 0
            self.__reassign_channel_strip_parameters(for_display_only=False)
            self.__update_channel_strip_strings()
        if self.__strip_offset() + len(
            self.__channel_strips) >= self.__controlled_num_of_tracks():
            self.__set_channel_offset(max(0,
                                          self.__controlled_num_of_tracks() - len(
                                              self.__channel_strips)))
        self.__reassign_channel_strip_parameters(for_display_only=False)
        self.__update_channel_strip_strings()

        #TODO ADD PAGING FOR MULTI TGE HERE??
        if self.__assignment_mode == CSM_SENDS:
            self.__update_page_switch_leds()

        self.refresh_state()
        self.__main_display_controller.refresh_state()
        self.__within_track_added_or_deleted = False
        self.request_rebuild_midi_map()

    def __on_any_tracks_output_type_changed(self):
        """
            Called as soon as any device chain has changed (devices where
            added/removed/swapped...)
        """
        self.__reassign_channel_strip_parameters(for_display_only=False)
        self.request_rebuild_midi_map()

    def __on_parameter_list_of_chosen_plugin_changed(self):
        self.__reorder_parameters()
        self.__reassign_channel_strip_parameters(for_display_only=False)
        self.request_rebuild_midi_map()

    def __reorder_parameters(self):
        result = []
        if self.__chosen_plugin:
            if self.__chosen_plugin.class_name in list(DEVICE_DICT.keys()):
                device_banks = DEVICE_DICT[self.__chosen_plugin.class_name]
                for bank in device_banks:
                    for param_name in bank:
                        parameter_name = ''
                        parameter = get_parameter_by_name(self.__chosen_plugin,
                                                          param_name)
                        if parameter:
                            parameter_name = parameter.name
                        result.append((parameter, parameter_name))
            else:
                result = [(p, p.name) for p in
                          self.__chosen_plugin.parameters[1:]]
        else:
            pass
        self.__ordered_plugin_parameters = result



