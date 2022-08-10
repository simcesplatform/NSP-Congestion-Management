# -*- coding: utf-8 -*-
# Copyright 2021 Tampere University and VTT Technical Research Centre of Finland
# This software was developed as a part of the ProCemPlus project: https://www.senecc.fi/projects/procemplus
# This software was developed as a part of the EU project INTERRFACE: http://interrface.eu/
# This source code is licensed under the MIT license. See LICENSE in the repository root directory.
# Author(s): Ville Heikkilä <ville.heikkila@tuni.fi>
#          : Mehdi Attar <mehdi.attar@tuni.fi>

"""
Module containing the message class for NIS Bus information.
"""

from __future__ import annotations
from typing import Any, Dict, List, Union

from tools.exceptions.messages import MessageValueError
from tools.messages import AbstractResultMessage
from tools.message.block import QuantityArrayBlock, ValueArrayBlock
from tools.tools import FullLogger

LOGGER = FullLogger(__name__)

class NISBusMessage(AbstractResultMessage):
    """the message class contain the structure for what is published
    to the Init.NIS.NetworkBusInfo by NIS component"""

    CLASS_MESSAGE_TYPE = "Init.NIS.NetworkBusInfo"
    MESSAGE_TYPE_CHECK = True

    BusVoltageBase = "BusVoltageBase"
    BusName = "BusName"
    BusType = "BusType"

    # all attributes specific that are added to the AbstractResult should be introduced here
    MESSAGE_ATTRIBUTES = {
        BusVoltageBase: "bus_voltage_base",
        BusName : "bus_name",
        BusType : "bus_type"
    }
    # list all attributes that are optional here (use the JSON attribute names)
    OPTIONAL_ATTRIBUTES = []
    # all attributes that are using the Quantity block format should be listed here
    QUANTITY_BLOCK_ATTRIBUTES = {
    }
    # all attributes that are using the Quantity array block format should be listed here
    QUANTITY_ARRAY_BLOCK_ATTRIBUTES = {
        BusVoltageBase : "kV"
    }
    # all attributes that are using the Time series block format should be listed here
    TIMESERIES_BLOCK_ATTRIBUTES = []
    ##################################
    ##################################
    # always include these definitions to update the full list of attributes to these class variables
    # no need to modify anything here
    MESSAGE_ATTRIBUTES_FULL = {
        **AbstractResultMessage.MESSAGE_ATTRIBUTES_FULL,
        **MESSAGE_ATTRIBUTES
    }
    OPTIONAL_ATTRIBUTES_FULL = AbstractResultMessage.OPTIONAL_ATTRIBUTES_FULL + OPTIONAL_ATTRIBUTES
    QUANTITY_BLOCK_ATTRIBUTES_FULL = {
        **AbstractResultMessage.QUANTITY_BLOCK_ATTRIBUTES_FULL,
        **QUANTITY_BLOCK_ATTRIBUTES
    }
    QUANTITY_ARRAY_BLOCK_ATTRIBUTES_FULL = {
        **AbstractResultMessage.QUANTITY_ARRAY_BLOCK_ATTRIBUTES_FULL,
        **QUANTITY_ARRAY_BLOCK_ATTRIBUTES
    }
    TIMESERIES_BLOCK_ATTRIBUTES_FULL = (
        AbstractResultMessage.TIMESERIES_BLOCK_ATTRIBUTES_FULL +
        TIMESERIES_BLOCK_ATTRIBUTES
    )
    ######################
    @property
    def bus_name(self) -> List[str]:
        return self.__bus_name

    @bus_name.setter
    def bus_name(self, bus_name: List[str]):
        if self._check_bus_name(bus_name):
            self.__bus_name=bus_name
            return
        raise MessageValueError("'{:s}' is an invalid value for BusName".format(bus_name))

    @classmethod
    def _check_bus_name(cls, bus_name: List[str]) -> bool:
        if isinstance(bus_name, list):
            return True
        else:
            return False

    ######################
    @property
    def bus_type(self) -> List[str]:
        return self.__bus_type

    @bus_type.setter
    def bus_type(self, bus_type: List[str]):
        if self._check_bus_type(bus_type):
            self.__bus_type=bus_type
        else:
            raise MessageValueError("Invalid value, {}, for attribute: bus_type".format(bus_type))

    @classmethod
    def _check_bus_type(cls, bus_type: List[str]) -> bool:
        if not isinstance(bus_type, list):
            return False
        dummy_num=bus_type.count("dummy")
        usage_point_num=bus_type.count("usage-point")
        root_num=bus_type.count("root")
        total_numbers=len(bus_type)
        if (dummy_num+usage_point_num+root_num==total_numbers) and (root_num==1):
            return True
        else:
            return False

    ######################
    @property
    def bus_voltage_base(self) -> QuantityArrayBlock:
        return self.__bus_voltage_base

    @bus_voltage_base.setter
    def bus_voltage_base(self, bus_voltage_base: Union[QuantityArrayBlock, Dict[str, Any]]):
        if self._check_bus_voltage_base(bus_voltage_base):
            self._set_quantity_array_block_value(self.BusVoltageBase, bus_voltage_base)
        else:
            raise MessageValueError("Invalid value, {}, for attribute: bus_voltage_base".format(bus_voltage_base))

    @classmethod
    def _check_bus_voltage_base(cls, bus_voltage_base: Union[List[float], QuantityArrayBlock, Dict[str, Any]]) -> bool:
        return cls._check_quantity_array_block(
            value=bus_voltage_base,
            unit=cls.QUANTITY_ARRAY_BLOCK_ATTRIBUTES[cls.BusVoltageBase]
        )



NISBusMessage.register_to_factory()
