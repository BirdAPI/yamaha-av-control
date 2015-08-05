import socket
from collections import deque
from threading import Thread
import logging
import Queue
import sys

from YamahaAV import YamahaAV

logger = logging.getLogger('yamaha-av')
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

# static / constants

# NUMCHAR_CODES[zone][action]
NUMCHAR_CODES = {
    1: { '1': '7F0151AE',
         '2': '7F0152AD',
         '3': '7F0153AC',
         '4': '7F0154AB',
         '5': '7F0155AA',
         '6': '7F0156A9',
         '7': '7F0157A8',
         '8': '7F0158A7',
         '9': '7F0159A6',
         '0': '7F015AA5',
         '+10': '7F015BA4',
         'ENT': '7F015CA3' },
    2: { '1': '7F01718F',
         '2': '7F01728C',
         '3': '7F01738D',
         '4': '7F01748A',
         '5': '7F01758B',
         '6': '7F017688',
         '7': '7F017789',
         '8': '7F017886',
         '9': '7F017986',
         '0': '7F017A84',
         '+10': '7F017B85',
         'ENT': '7F017C82' }
}
NUMCHAR_CODES[0] = NUMCHAR_CODES[1]

# OPERATION_CODES[zone][action]
OPERATION_CODES = {
    1: { 'Play': '7F016897',
         'Stop': '7F016996',
         'Pause': '7F016798',
         'Search-': '7F016A95',
         'Search+': '7F016E94',
         'Skip-': '7F016C93',
         'Skip+': '7F016D92',
         'FM': '7F015827',
         'AM': '7F01552A' },
    2: { 'Play': '7F018876',
         'Stop': '7F018977',
         'Pause': '7F018779',
         'Search-': '7F018A74',
         'Search+': '7F018B75',
         'Skip-': '7F018C72',
         'Skip+': '7F018D73',
         'FM': '7F015927',
         'AM': '7F015628' }
}
OPERATION_CODES[0] = OPERATION_CODES[1]

# CURSOR_CODES[zone][action]
CURSOR_CODES = {
    1: { 'Up': '7A859D62',
         'Down': '7A859C63',
         'Left': '7A859F60',
         'Right': '7A859E61',
         'Enter': '7A85DE21',
         'Return': '7A85AA55',
         'Level': '7A858679',
         'On Screen': '7A85847B',
         'Option': '7A856B14',
         'Top Menu': '7A85A0DF',
         'Pop Up Menu': '7A85A4DB' },
    2: { 'Up': '7A852B55',
         'Down': '7A852C52',
         'Left': '7A852D53',
         'Right': '7A852E50',
         'Enter': '7A852F51',
         'Return': '7A853C42',
         'Option': '7A856C12',
         'Top Menu': '7A85A1DF',
         'Pop Up Menu': '7A85A5DB' },
}
CURSOR_CODES[0] = CURSOR_CODES[1]

# Objects used in the GetInfo action
MENU_OBJECTS = [ 'Menu Layer', 'Menu Name' ]
LINE_OBJECTS = [ 'Line 1', 'Line 2', 'Line 3', 'Line 4', 'Line 5', 'Line 6', 'Line 7', 'Line 8', 'Current Line', 'Max Line' ]
GENERIC_PLAYBACK_OBJECTS = [ 'Playback Info', 'Repeat Mode', 'Shuffle', 'Artist', 'Album', 'Song' ] + MENU_OBJECTS + LINE_OBJECTS
ZONE_OBJECTS = [ 'Power', 'Sleep', 'Volume Level', 'Mute', 'Input Selection', 'Scene', 'Init Volume Mode', 'Init Volume Level', 'Max Volume Level' ]
MAIN_ZONE_OBJECTS = ZONE_OBJECTS + [ 'Straight', 'Enhancer', 'Sound Program', 'Treble', 'Bass' ]
NET_RADIO_OBJECTS = [ 'Playback Info', 'Station' ] + MENU_OBJECTS + LINE_OBJECTS
PANDORA_OBJECTS = [ 'Playback Info', 'Station', 'Album', 'Song' ] + MENU_OBJECTS + LINE_OBJECTS
SIRIUS_IR_OBJECTS = [ 'Playback Info', 'Artist', 'Channel', 'Title' ] + MENU_OBJECTS + LINE_OBJECTS
SIRIUS_OBJECTS = [ 'Antenna Strength', 'Category', 'Channel Number', 'Channel Name', 'Artist', 'Song', 'Composer' ]
SYSTEM_OBJECTS = [ 'Active Speakers', 'PreOut Levels' ]

# Supported zone definitions
#ALL_ZONES = [ 'Main Zone', 'Zone 2', 'Zone 3', 'Zone 4', 'Zone A', 'Zone B', 'Zone C', 'Zone D' ]
#ALL_ZONES_PLUS_ACTIVE = [ 'Active Zone' ] + ALL_ZONES
#TWO_ZONES = [ 'Main Zone', 'Zone 2' ]
#TWO_ZONES_PLUS_ACTIVE = [ 'Active Zone' ] + TWO_ZONES

def _get_lan_ip():
    """
    Attempts to open a socket connection to Google's DNS
    servers in order to determine the local IP address
    of this computer. Eg, 192.168.1.100
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8",80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "192.168.1.100"

def _get_network_prefix():
    """
    Returns the network prefix, which is the local IP address
    without the last segment, Eg: 192.168.1.100 -> 192.168.1
    """
    lan_ip = _get_lan_ip()
    return lan_ip[:lan_ip.rfind('.')]

def _create_ip_range(range_start, range_end):
    """
    Given a start ip, eg 192.168.1.1, and an end ip, eg 192.168.1.254,
    generate a list of all of the ips within that range, including
    the start and end ips.
    """
    ip_range = []
    start = int(range_start[range_start.rfind('.')+1:])
    end = int(range_end[range_end.rfind('.')+1:])
    for i in range(start, end+1):
        ip = range_start[:range_start.rfind('.')+1] + str(i)
        ip_range.append(ip)
    return ip_range

def _open_to_close_tag(tag):
    """
    Given an opening xml tag, return the matching close tag
    eg. '<YAMAHA_AV cmd="PUT"> becomes </YAMAHA_AV>
    """
    index = tag.find(' ')
    if index == -1:
        index = len(tag) - 1
    return '</' + tag[1:index] + '>'

def _close_xml_tags(xml):
    """
    Automagically takes an input xml string and returns that string
    with all of the xml tags properly closed. It can even handle when
    the open tag is in the middle of the string and not the end.
    """
    output = []
    stack = []
    xml_chars = deque(list(xml))
    c = None

    while len(xml_chars) > 0:
        while len(xml_chars) > 0 and c != '<':
            c = xml_chars.popleft()
            if c != '<':
                output.append(c)
        if c == '<':
            temp = [ '<' ]
            c = xml_chars.popleft()
            end_tag = c == '/'
            while c != '>':
                temp.append(c)
                c = xml_chars.popleft()
            temp.append('>')
            tag = ''.join(temp)
            if end_tag:
                other_tag = stack.pop()
                other_close_tag = _open_to_close_tag(other_tag)
                while other_close_tag != tag:
                    output.append(other_close_tag)
                    other_tag = stack.pop()
                    other_close_tag = _open_to_close_tag(other_tag)
            elif not tag.endswith('/>'):
                # Only add to stack if not self-closing
                stack.append(tag)
            output.append(tag)

    while len(stack) > 0:
        tag = stack.pop()
        output.append(_open_to_close_tag(tag))

    return ''.join(output)

def discover(model_name):
    avs = discover_all()
    for av in avs:
        if model_name.upper() in ["ANY", "", None] or av.model_name.upper() == model_name.upper():
            return av
    return None

def discover_all():
    """
    Blasts the network with requests, attempting to find any and all yamaha receivers
    on the local network. First it detects the user's local ip address, eg 192.168.1.100.
    Then, it converts that to the network prefix, eg 192.168.1, and then sends a request
    to every ip on that subnet, eg 192.168.1.1 -> 192.168.1.254. It does each request on
    a separate thread in order to avoid waiting for the timeout for every 254 requests
    one by one.
    """
    threads = []

    # Get network prefix (eg 192.168.1)
    net_prefix = _get_network_prefix()
    ip_range = _create_ip_range(net_prefix + '.1', net_prefix + '.254')

    result_queue = Queue.Queue()
    for ip in ip_range:
        t = Thread(target=_try_connect, kwargs={'ip': ip, 'result_queue': result_queue})
        t.daemon = True
        threads.append(t)
        t.start()
    for t in threads:
        t.join()

    avs = []
    if result_queue.empty():
        logger.info("Yamaha Receiver Was Not Found!")
    while not result_queue.empty():
        av = result_queue.get()
        avs.append(av)
    return avs

def _try_connect(ip, result_queue, port=80, timeout=1.0):
    """
    Used with the auto-detect-ip functions, determines if a yamaha receiver is
    waiting at the other end of the given ip address.
    """
    try:
        av = YamahaAV(ip, port)
        model = av.get_config_string('Model_Name', timeout=timeout, ip=ip, print_error=False)
        av.model_name = model
        logger.info('{0}: {1}'.format(ip, model))
        result_queue.put(av)
    except:
        pass

