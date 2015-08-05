import yamaha_av
import logging
import time
from pprint import pprint

logger = logging.getLogger("yamaha-av-test")

def main():
    avs = yamaha_av.discover_all()
    for av in avs:
        logger.info("Found Yamaha Receiver IP: {0} [{1}]".format(av.ip_address, av.model_name))

    av = yamaha_av.discover("RX-V473")
    if av is not None:
        av.setup()

        logger.info(av.get_basic_status())
        av.power_on()
        time.sleep(0.3)

        logger.info(av.get_basic_status())
        av.increase_volume()
        time.sleep(0.3)

        logger.info(av.get_basic_status())
        av.decrease_volume()
        time.sleep(0.3)

        logger.info(av.get_basic_status())
        av.power_standby()
        time.sleep(0.3)

        logger.info(av.get_basic_status())


if __name__ == "__main__":
    main()

