import sys,traceback

from .P1NanoTGE import P1NanoTGE


def create_instance(c_instance):
    return P1NanoTGE(c_instance)

        


from _Framework.Capabilities import *


def get_capabilities():
    return {CONTROLLER_ID_KEY: controller_id(vendor_id=2675, product_ids=[6],
                                             model_name='MCU Pro USB v3.1'),
            PORTS_KEY: [inport(props=[SCRIPT, REMOTE]), inport(props=[]),
                        inport(props=[]), inport(props=[]),
                        outport(props=[SCRIPT, REMOTE]), outport(props=[]),
                        outport(props=[]), outport(props=[])]}
