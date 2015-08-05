from xml.dom import minidom
import socket
import httplib
import logging
import time

import yamaha_av

class YamahaAV(object):
    def __init__(self, ip, port=80, default_timeout=3.0):
        self.ip_address = ip
        self.port = port
        self.model_name = None
        self.default_timeout = default_timeout
        self.logger = logging.getLogger('yamaha-av')
        self.active_zone = 0

        self.zones = []
        self.sources = []
        self.info_sources = []
        self.feature_sources = []
        self.input_sources = []
        self.sources_rename = []

    def setup(self):
        self._setup_availability()

        # TODO: What does this do?
        #self._get_available_zones()

    def _setup_availability(self):
        """
        Query the receiver to see which zones and inputs it supports.
        Should be called after a successful ip check.
        """
        xmldoc = self.get_system_config()

        zones = []
        inputs = []

        for node in xmldoc.getElementsByTagName("Feature_Existence"): #just in case there are multiple "Feature" sections
            x = 0
            stop = False
            while not stop:
                try:
                    if node.childNodes[x].firstChild.data != "0":
                        if node.childNodes[x].tagName != "Main_Zone" and node.childNodes[x].tagName[:4] != "Zone":
                            inputs.append(str(node.childNodes[x].tagName))
                        else:
                            zones.append(str(node.childNodes[x].tagName))
                except:
                    stop=True
                x += 1

        self.feature_sources = list(inputs)
        self.info_sources = list(inputs)

        #models from RX-V use this
        x = 0
        for node in xmldoc.getElementsByTagName("Input"):
            stop = False
            while not stop:
                try:
                    self.sources_rename.append([str(node.childNodes[x].tagName), str(node.childNodes[x].firstChild.data)])
                    self.input_sources.append(str(node.childNodes[x].firstChild.data).strip())
                    inputs.append(str(node.childNodes[x].firstChild.data))
                except:
                    stop=True
                x += 1

        #models from N-Line use this
        if x == 0: #this means the other lookup resulted in nothing
            MainInputxmldoc = self.get_main_zone_inputs()
            x = 0
            for node in MainInputxmldoc.getElementsByTagName("Input_Sel_Item"):
                stop = False
                while not stop:
                    try:
                        self.sources_rename.append([str(node.childNodes[x].tagName), str(node.childNodes[x].firstChild.data)])
                        self.input_sources.append(str(node.childNodes[x].firstChild.firstChild.data).strip())
                        inputs.append(str(node.childNodes[x].firstChild.firstChild.data))
                    except:
                        stop=True
                    x += 1

        self.zones = [ zone.replace('_', ' ').strip() for zone in zones ]
        self.sources = [ input.replace('_', ' ').strip() for input in inputs ]
        #self.sources = list(set(self.sources))
        tempList =[]
        for source in self.sources_rename:
            tempList.append([source[0].replace('_','').strip(), source[1].replace('_','').strip()])
        self.sources_rename = list(tempList)

    def _get_available_zones(self, include_active, fallback_zones, limit=None):
        """
        Returns the zones that are marked as available based on availability, and
        optionally includes an active zone. If zone availability info is not present,
        this will return fallback_zones. Optionally a limit can be imposed to only show
        a certain amount of zones if the code does not support the extra zones yet.
        """
        if len(self.zones) > 0:
            if limit is not None and limit < len(self.zones):
                # For example, limit to only 2 zones
                zones = [ self.zones[i] for i in range(limit) ]
            else:
                # Must use list() to create a copy
                zones = list(self.zones)
            if include_active:
                return ['Active Zone'] + zones
            else:
                return zones
        else:
            return fallback_zones

    def convert_zone_to_int(self, zone, convert_active=False):
        """
        Convert a zone name into the integer value that it represents:
        Examples:
        Active Zone: -1
        Main Zone: 0
        Zone 2: 2
        Zone A: -65 (this is the negative version of the integer that represents this letter: 'A' -> 65, thus -65)
        """
        if zone in ['Main Zone', 'Main_Zone', 'MZ']:
            return 0
        elif 'active' in zone.lower():
            # -1 means active zone
            if convert_active:
                return self.active_zone
            else:
                return -1
        else:
            z = zone.replace('Zone_', '').replace('Zone', '').replace('Z', '').strip()
            if z in [ 'A', 'B', 'C', 'D' ]:
                return -1 * ord(z)
            return int(z)

    def _do_xml(self, xml, **kwargs):
        """
        Base function to send/receive xml using either GET or POST

        Optional Parameters:
        timeout, ip, port, return_result, print_error, close_xml, print_xml
        """
        timeout = float(kwargs.get('timeout', self.default_timeout))
        ip = kwargs.get('ip', self.ip_address)
        port = kwargs.get('port', self.port)
        return_result = kwargs.get('return_result', False)
        print_error = kwargs.get('print_error', True)
        close_xml = kwargs.get('close_xml', False)
        print_xml = kwargs.get('print_xml', False)

        if close_xml:
            xml = yamaha_av._close_xml_tags(xml)
        if print_xml:
            print xml

        conn = httplib.HTTPConnection('{0}:{1}'.format(ip, port), timeout=float(timeout))
        headers = { "Content-type": "text/xml" }
        try:
            conn.request("POST", "/YamahaRemoteControl/ctrl", "", headers)
            conn.send(xml)
            if return_result:
                response = conn.getresponse()
                rval = response.read()
                conn.close()
                return rval
            else:
                response = conn.getresponse()
                rval = response.read()
                conn.close()
                if rval != "":
                    if str(rval[25]) == "0":
                        return True
                    else:
                        self.logger.error("Command did not go to Yamaha Receiver, error code " + str(rval[25]))
                else:
                    self.logger.error("Command did not go to Yamaha Receiver, error NOT possible to set on this model.")
        except socket.error:
            if print_error:
                self.logger.error("Unable to communicate with Yamaha Receiver. The connection timed out.")
                return None
            else:
                raise

    def _send_xml(self, xml, **kwargs):
        """
        Communicate with the receiver, but do not wait or return the results
        """
        if not 'return_result' in kwargs:
            kwargs['return_result'] = False
        self._do_xml(xml, **kwargs)

    def _put_xml(self, xml, **kwargs):
        self._send_xml('<YAMAHA_AV cmd="PUT">{0}</YAMAHA_AV>'.format(xml), **kwargs)

    def _zone_put_xml(self, zone, xml, **kwargs):
        if zone == -1:
            zone = self.active_zone
        if zone < 2:
            self._put_xml('<Main_Zone>{0}</Main_Zone>'.format(xml), **kwargs)
        elif zone < -1:
            self._put_xml('<Zone_{1}>{0}</Zone_{1}>'.format(xml, chr(-1 * zone)), **kwargs)
        else:
            self._put_xml('<Zone_{1}>{0}</Zone_{1}>'.format(xml, zone), **kwargs)

    def _receive_xml(self, xml, **kwargs):
        kwargs['return_result'] = True
        return self._do_xml(xml, **kwargs)

    def _get_xml(self, xml, **kwargs):
        return self._receive_xml('<YAMAHA_AV cmd="GET">{0}</YAMAHA_AV>'.format(xml), **kwargs)

    def _zone_get_xml(self, zone, xml, **kwargs):
        if zone == -1:
            zone = self.active_zone
        if zone < 2:
            return self._get_xml('<Main_Zone>{0}</Main_Zone>'.format(xml), **kwargs)
        elif zone < -1:
            return self._get_xml('<Zone_{1}>{0}</Zone_{1}>'.format(xml, chr(-1 * zone)), **kwargs)
        else:
            return self._get_xml('<Zone_{1}>{0}</Zone_{1}>'.format(xml, zone), **kwargs)

    def get_sound_video(self, zone=-1, **kwargs):
        return self._zone_get_xml(zone, '<Sound_Video>GetParam</Sound_Video>', **kwargs)

    def get_basic_status(self, zone=-1, **kwargs):
        return self._zone_get_xml(zone, '<Basic_Status>GetParam</Basic_Status>', **kwargs)

    def get_tuner_status(self, **kwargs):
        return self._get_xml('<Tuner><Play_Info>GetParam</Play_Info></Tuner>', **kwargs)

    def get_device_status(self, input, section, **kwargs):
        return self._get_xml('<{0}><{1}>GetParam</{1}></{0}>'.format(input, section), **kwargs)

    def get_tuner_presets(self, **kwargs):
        return self._get_xml('<Tuner><Play_Control><Preset><Data>GetParam</Data></Preset></Play_Control></Tuner>', **kwargs)

    def get_config(self, **kwargs):
        return self._get_xml('<System><Config>GetParam</Config></System>', **kwargs)

    def get_sound_video_string(self, param, zone=-1, elem=None, **kwargs):
        if elem in ["Treble", "Bass"]:
            xml = self._zone_get_xml(zone, '<Sound_Video><Tone><{0}>GetParam</{0}></Tone></Sound_Video>'.fromat(elem), **kwargs)
        else:
            xml = self.get_sound_video(zone, **kwargs)
        xmldoc = minidom.parseString(xml)
        value = xmldoc.getElementsByTagName(param)[0].firstChild.data
        return value

    def get_volume_string(self, param, zone=-1, elem=None, **kwargs):
        xml = self._zone_get_xml(zone, '<Volume><{0}>GetParam</{0}></Volume>'.format(elem), **kwargs)
        xmldoc = minidom.parseString(xml)
        value = xmldoc.getElementsByTagName(param)[0].firstChild.data
        return value

    def get_status_string(self, param, zone=-1, **kwargs):
        xml = self.get_basic_status(zone, **kwargs)
        if kwargs.get('print_xml', False):
            print xml
        xmldoc = minidom.parseString(xml)
        value = xmldoc.getElementsByTagName(param)[0].firstChild.data
        return value

    def get_status_strings(self, params, zone=-1, **kwargs):
        """
        Return multiple values as to to not query the receiver over the network more than once
        """
        xml = self.get_basic_status(zone, **kwargs)
        if kwargs.get('print_xml', False):
            print xml
        xmldoc = minidom.parseString(xml)
        values = []
        for param in params:
            values.append(xmldoc.getElementsByTagName(param)[0].firstChild.data)
        return tuple(values)

    def get_status_param_is_on(self, param, zone=-1, **kwargs):
        return self.get_status_string(param, zone, **kwargs) == "On"

    def get_status_int(self, param, zone=-1, **kwargs):
        return int(self.get_status_string(param, zone, **kwargs))

    def get_config_string(self, param, **kwargs):
        xml = self.get_config(**kwargs)
        if kwargs.get('print_xml', False):
            print xml
        xmldoc = minidom.parseString(xml)
        value = xmldoc.getElementsByTagName(param)[0].firstChild.data
        return value

    def get_config_param_is_on(self, param, **kwargs):
        return self.get_config_string(param, **kwargs) == "On"

    def get_config_int(self, param, **kwargs):
        return int(self.get_config_string(param, **kwargs))

    def get_tuner_string(self, param, **kwargs):
        xml = self.get_tuner_status(**kwargs)
        if kwargs.get('print_xml', False):
            print xml
        xmldoc = minidom.parseString(xml)
        value = xmldoc.getElementsByTagName(param)[0].firstChild.data
        return value

    def get_tuner_param_is_on(self, param, **kwargs):
        return self.get_tuner_string(param, **kwargs) == "On"

    def get_tuner_int(self, param, **kwargs):
        return int(self.get_tuner_string(param, **kwargs))

    def get_device_string(self, param, input, section, **kwargs):
        xml = self.get_device_status(input, section, **kwargs)
        if kwargs.get('print_xml', False):
            print xml
        xmldoc = minidom.parseString(xml)
        if param[:4] == "Line":
            value = xmldoc.getElementsByTagName('Txt')[int(param[5])-1].firstChild.data
        else:
            value = xmldoc.getElementsByTagName(param)[0].firstChild.data
        return value

    def get_device_strings(self, params, input, section, **kwargs):
        """
        Return multiple values as to to not query the receiver over the network more than once
        """
        xml = self.get_device_status(input, section, **kwargs)
        if kwargs.get('print_xml', False):
            print xml
        xmldoc = minidom.parseString(xml)
        values = []
        for param in params:
            if param.startswith("Line"):
                values.append(xmldoc.getElementsByTagName('Txt')[int(param[5])-1].firstChild.data)
            else:
                values.append(xmldoc.getElementsByTagName(param)[0].firstChild.data)
        return tuple(values)

    def get_system_pattern_1(self, param=None, **kwargs):
        types = ['Front', 'Center', 'Sur', 'Sur_Back', 'Subwoofer']
        speakers = []
        levels = []
        for type in types:
            xml = self.get_xml('<System><Speaker_Preout><Pattern_1><Config><{0}>GetParam</{0}></Config></Pattern_1></Speaker_Preout></System>'.format(type), **kwargs)
            xmldoc = minidom.parseString(xml)
            value = xmldoc.getElementsByTagName("Type")[0].firstChild.data
            if value != "None":
                if value == "Use":
                    speakers.append("Subwoofer_1")
                    try:
                        if xmldoc.getElementsByTagName("Type")[1].firstChild.data == "Use":
                            speakers.append("Subwoofer_2")
                    except:
                        pass
                elif value[-2:] == "x2":
                    speakers.append("Sur_Back_R")
                    speakers.append("Sur_Back_L")
                if type == "Sur":
                    speakers.append("Sur_R")
                    speakers.append("Sur_L")
                if type == "Front":
                    speakers.append("Front_R")
                    speakers.append("Front_L")
                if type == "Center":
                    speakers.append("Center")
        if param == "Active Speakers":
            return speakers
        #This is then also done only if levels are requested
        else:
            for speaker in speakers:
                xml = self.get_xml('<System><Speaker_Preout><Pattern_1><Lvl>GetParam</Lvl></Pattern_1></Speaker_Preout></System>', **kwargs)
                xmldoc = minidom.parseString(xml)
                levels.append([speaker, float(xmldoc.getElementsByTagName(speaker)[0].firstChild.firstChild.data) /10])
            return levels

    def send_any(self, value, action):
        if action == "Put":
            self._put_xml(self, value)
        else:
            #now find param
            #to do this, parse value (originally passed)
            param = value.split("GetParam")
            param = param[0].split("<")
            param = param[-1]
            param = param[0:-1]
            values = value.split("<" + param + ">")
            values2 = values[1].split("</" + param + ">")
            value = values[0] + "GetParam" + values2[1]
            xml = self._get_xml(self, value)
            xmldoc = minidom.parseString(xml)

            return xmldoc.getElementsByTagName(param)[0].firstChild.data

    def increase_volume(self, zone=-1, inc=0.5):
        self.change_volume(zone, inc)

    def decrease_volume(self, zone=-1, dec=0.5):
        self.change_volume(zone, -1 * dec)

    def change_volume(self, zone=-1, diff=0.0):
        if abs(diff) == 0.5 or int(abs(diff)) in [1, 2, 5]:
            # Faster volume method which uses the built in methods
            param1 = 'Up' if diff > 0 else 'Down'
            param2 = ' {0} dB'.format(int(abs(diff))) if abs(diff) != 0.5 else ''
            self._zone_put_xml(zone, '<Volume><Lvl><Val>{0}{1}</Val><Exp></Exp><Unit></Unit></Lvl></Volume>'.format(param1, param2))
            # Sleep for a little amount of time to ensure we do not get "stuck" sending too many calls in short succession
            time.sleep(0.03)
        else:
            # Slower method that relies on get_volume() first
            self.set_volume(zone, (self.get_volume() / 10.0) + diff)

    def get_volume(self):
        return self.get_status_int('Val')

    def set_volume(self, zone=-1, value=-25.0):
        self._zone_put_xml(zone, '<Volume><Lvl><Val>{0}</Val><Exp>1</Exp><Unit>dB</Unit></Lvl></Volume>'.format(int(value * 10.0)))

    def set_max_volume(self, zone=-1, value=16.5):
        self._zone_put_xml(zone, '<Volume><Max_Lvl><Val>{0}</Val><Exp>1</Exp><Unit>dB</Unit></Max_Lvl></Volume>'.format(int(value * 10.0)))

    def set_init_volume(self, zone=-1, value=-50.0, mode="Off"):
        self._zone_put_xml(zone, '<Volume><Init_Lvl><Mode>{1}</Mode><Lvl><Val>{0}</Val><Exp>1</Exp><Unit>dB</Unit></Lvl></Init_Lvl></Volume>'.format(int(value * 10.0), mode))

    def set_pattern1(self, levels):
        for speaker in levels:
            self._put_xml('<System><Speaker_Preout><Pattern_1><Lvl><{0}><Val>{1}</Val><Exp>1</Exp><Unit>dB</Unit></{0}></Lvl></Pattern_1></Speaker_Preout></System>'.format(speaker[0], int(speaker[1]*10)))

    def set_bass(self, zone=-1, value=-0.0):
        self._zone_put_xml(zone, '<Sound_Video><Tone><Bass><Val>{0}</Val><Exp>1</Exp><Unit>dB</Unit></Bass></Tone></Sound_Video>'.format(int(value * 10.0)))

    def set_treble(self, zone=-1, value=-0.0):
        self._zone_put_xml(zone, '<Sound_Video><Tone><Treble><Val>{0}</Val><Exp>1</Exp><Unit>dB</Unit></Treble></Tone></Sound_Video>'.format(int(value * 10.0)))

    def mute_on(self, zone=-1):
        self._zone_put_xml(zone, '<Volume><Mute>On</Mute></Volume>')

    def mute_off(self, zone=-1):
        self._zone_put_xml(zone, '<Volume><Mute>Off</Mute></Volume>')

    def get_mute(self, zone=-1):
        return self._get_status_param_is_on('Mute', zone)

    def power_on(self, zone=-1):
        self._zone_put_xml(zone, '<Power_Control><Power>On</Power></Power_Control>')

    def power_off(self, zone=-1):
        self._zone_put_xml(zone, '<Power_Control><Power>Off</Power></Power_Control>')

    def power_standby(self, zone=-1):
        self._zone_put_xml(zone, '<Power_Control><Power>Standby</Power></Power_Control>')

    def toggle_on_standby(self, zone=-1):
        self._zone_put_xml(zone, '<Power_Control><Power>On/Standby</Power></Power_Control>')

    def toggle_mute(self, zone=-1):
        if self.get_mute(zone):
            self.mute_off(zone)
        else:
            self.mute_on(zone)

    def change_source(self, source, zone=-1):
        #first look to see if the source has been renamed
        for s in self.sources_rename:
            if source == s[1]:
                source = s[0]
        self._zone_put_xml(zone, '<Input><Input_Sel>{0}</Input_Sel></Input>'.format(source))

    def feature_video_out(self, feature, source):
        #first look to see if the source has been renamed
        for s in self.sources_rename:
            if source == s[1]:
                source = s[0]
            #first look to see if the source has been renamed
        for s in self.sources_rename:
            if feature == s[1]:
                feature = s[0]
        self._put_xml('<System><Input_Output><Assign><Video_Out><{0}>{1}</{0}></Video_Out></Assign></Input_Output></System>'.format(feature, source))

    def source_audio_in(self, audio, video):
        #first look to see if the source has been renamed
        for s in self.sources_rename:
            if audio == s[1]:
                audio = s[0]
            #first look to see if the source has been renamed
        for s in self.sources_rename:
            if video == s[1]:
                video = s[0]
        self._put_xml('<System><Input_Output><Assign><Audio_In><{0}>{1}</{0}></Audio_In></Assign></Input_Output></System>'.format(video, audio))

    def wallpaper(self, pic):
        self._put_xml('<System><Misc><Display><Wall_Paper>{0}</Wall_Paper></Display></Misc></System>'.format(pic))

    def DisplayDimmer(self, level):
        self._put_xml('<System><Misc><Display><FL><Dimmer>{0}</Dimmer></FL></Display></Misc></System>'.format(level))

    def straight(self, zone=-1):
        self.zone_put_xml(zone, '<Surround><Program_Sel><Current><Straight>On</Straight><Sound_Program>Straight</Sound_Program></Current></Program_Sel></Surround>')

    def surround_decode(self, zone=-1):
        self._zone_put_xml(zone, '<Surround><Program_Sel><Current><Straight>Off</Straight><Sound_Program>Surround Decoder</Sound_Program></Current></Program_Sel></Surround>')

    def toggle_straight_decode(self, zone=-1):
        if self.get_straight(zone):
            self.surround_decode(zone)
        else:
            self.straight(zone)

    def get_straight(self, zone=-1):
        return self.get_status_param_is_on('Straight', zone)

    def channel7_on(self, zone=-1): # McB 1/11/2014 - Turn 7-channel mode on and off
        self._zone_put_xml(zone, '<Surround><Program_Sel><Current><Sound_Program>7ch Stereo</Sound_Program></Current></Program_Sel></Surround>')

    def channel7_off(self, zone=-1):
        self._zone_put_xml(zone, '<Surround><Program_Sel><Current><Sound_Program>Standard</Sound_Program></Current></Program_Sel></Surround>')

    def set_enhancer(self, arg, zone=-1):
        self._zone_put_xml(zone, '<Surround><Program_Sel><Current><Enhancer>{0}</Enhancer></Current></Program_Sel></Surround>'.format(arg))

    def get_enhancer(self, zone=-1):
        return self.get_status_param_is_on('Enhancer', zone)

    def toggle_enhancer(self):
        if self.get_enhancer():
            self.set_enhancer("Off")
        else:
            self.set_enhancer("On")

    def set_sleep(self, arg, zone=-1):
        self._zone_put_xml(zone, '<Power_Control><Sleep>{0}</Sleep></Power_Control>'.format(arg))

    def set_radio_preset(self, preset):
        self._put_xml('<Tuner><Play_Control><Preset><Preset_Sel>{0}</Preset_Sel></Preset></Play_Control></Tuner>'.format(preset))

    def get_radio_band(self):
        return self.get_tuner_string('Band')

    def toggle_radio_amfm(self):
        if self.get_radio_band() == 'FM':
            self.set_radio_band('AM')
        else:
            self.set_radio_band('FM')

    def set_radio_band(self, band):
        self._put_xml('<Tuner><Play_Control><Tuning><Band>{0}</Band></Tuning></Play_Control></Tuner>'.format(band))

    def next_radio_preset(self):
        self._put_xml('<Tuner><Play_Control><Preset><Preset_Sel>Up', close_xml=True)

    def prev_radio_preset(self):
        self._put_xml('<Tuner><Play_Control><Preset><Preset_Sel>Down', close_xml=True)

    def modify_radio_preset(self, diff, turn_on, wrap):
        """
        Deprecated
        """
        oldpreset = self.get_tuner_int('Preset_Sel')
        preset = oldpreset + diff
        self.set_radio_preset(preset)
        if turn_on:
            is_on = self.is_radio_on()
            if not is_on:
                self.change_source('TUNER')
        if wrap and (not turn_on or is_on):
            count = self.get_radio_preset_count()
            if diff > 0 and preset > count:
                preset = 1
                self.set_radio_preset(preset)
            elif diff < 0 and preset < 1:
                preset = count
                self.set_radio_preset(preset)

    def get_radio_preset_count(self, **kwargs):
        """
        Currently broken
        """
        xml = self.get_tuner_presets(**kwargs)
        if kwargs.get('print_xml', False):
            print xml
        xmldoc = minidom.parseString(xml)
        count = 0
        done = False
        while not done and count <= 40:
            num = "Number_{0}".format(count + 1)
            value = xmldoc.getElementsByTagName(num)[0].getElementsByTagName('Status')[0].firstChild.data
            if value == 'Exist':
                count += 1
            else:
                done = True
        return count

    def is_radio_on(self):
        return self.get_status_string('Input_Sel') == "TUNER"

    def radio_freq(self, updown):
        if self.get_radio_band() == 'FM':
            val = '<FM><Val>{0}</Val></FM>'.format(updown)
        else:
            val = '<AM><Val>{0}</Val></AM>'.format(updown)
        self._put_xml('<Tuner><Play_Control><Tuning><Freq>{0}</Freq></Tuning></Play_Control></Tuner>'.format(val))

    def set_radio_freq(self, freq, band):
        if band == 'FM':
            self._put_xml('<Tuner><Play_Control><Tuning><Freq><FM><Val>{0}</Val></FM></Freq></Tuning></Play_Control></Tuner>'.format(int(freq*100)))
        else:
            self._put_xml('<Tuner><Play_Control><Tuning><Freq><AM><Val>{0}</Val></AM></Freq></Tuning></Play_Control></Tuner>'.format(int(freq)))

    def set_scene(self, scene_num, zone=-1):
        self._zone_put_xml(zone, '<Scene><Scene_Sel>Scene {0}</Scene_Sel></Scene>'.format(scene_num))

    def send_code(self, code):
        self._put_xml('<System><Misc><Remote_Signal><Receive><Code>{0}</Code></Receive></Remote_Signal></Misc></System>'.format(code))

    def set_active_zone(self, zone):
        self.active_zone = zone
        self.logger.info("Active Zone: Zone", zone if zone > -1 else chr(-1 * zone))

    def get_source_name(self, zone=-1):
        return self.get_status_string("Input_Sel", zone)

    def get_system_config(self):
        xml = self.get_config()
        xmldoc = minidom.parseString(xml)
        return xmldoc

    def get_system_io_vol_trim(self):
        sources = []
        xml = self._get_xml('<System><Input_Output><Volume_Trim>GetParam</Volume_Trim></Input_Output></System>')
        xmldoc = minidom.parseString(xml)
        for item in xmldoc.getElementsByTagName('Val'):
            sources.append([item.parentNode.tagName, item.firstChild.data])
        return sources

    def set_system_io_vol_trim(self, sources):
        for source in sources:
            self._put_xml('<System><Input_Output><Volume_Trim><{0}><Val>{1}</Val><Exp>1</Exp><Unit>dB</Unit></{0}></Volume_Trim></Input_Output></System>'.format(source[0], source[1]))

    def get_main_zone_inputs(self):
        xml = self._get_xml('<Main_Zone><Input><Input_Sel_Item>GetParam</Input_Sel_Item></Input></Main_Zone>')
        xmldoc = minidom.parseString(xml)
        return xmldoc

    def get_availability_dict(self, items_to_check):
        xml = self.get_config()
        xmldoc = minidom.parseString(xml)
        res = {}
        for item in items_to_check:
            try:
                value = xmldoc.getElementsByTagName(item)[0].firstChild.data
            except:
                value = None
            res[item] = value
        return res

