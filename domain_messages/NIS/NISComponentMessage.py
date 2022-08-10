# -*- coding: utf-8 -*-
# Copyright 2021 Tampere University and VTT Technical Research Centre of Finland
# This software was developed as a part of the ProCemPlus project: https://www.senecc.fi/projects/procemplus
# This software was developed as a part of the EU project INTERRFACE: http://interrface.eu/
# This source code is licensed under the MIT license. See LICENSE in the repository root directory.
# Author(s): Ville Heikkilä <ville.heikkila@tuni.fi>
#            Mehdi Attar <mehdi.attar@tuni.fi>

"""
Module containing the message class for NIS Component information.
"""

from __future__ import annotations
from typing import Any, Dict, List, Union

from tools.exceptions.messages import MessageValueError
from tools.messages import AbstractResultMessage
from tools.message.block import QuantityBlock, QuantityArrayBlock
from tools.tools import FullLogger

LOGGER = FullLogger(__name__)

##################################################################################################################
class NISComponentMessage(AbstractResultMessage):
    """Description for the SimpleMessage class"""
    CLASS_MESSAGE_TYPE = "Init.NIS.NetworkComponentInfo"
    MESSAGE_TYPE_CHECK = True

    Resistance ="Resistance"
    Reactance = "Reactance"
    ShuntAdmittance = "ShuntAdmittance"
    ShuntConductance = "ShuntConductance"
    RatedCurrent = "RatedCurrent"
    SendingEndBus = "SendingEndBus"
    ReceivingEndBus = "ReceivingEndBus"
    DeviceId = "DeviceId"
    PowerBase = "PowerBase"

    # all attributes specific that are added to the AbstractResult should be introduced here
    MESSAGE_ATTRIBUTES = {
        Resistance : "resistance",
        Reactance : "reactance",
        ShuntAdmittance : "shunt_admittance",
        ShuntConductance : "shunt_conductance",
        RatedCurrent : "rated_current",
        SendingEndBus : "sending_end_bus",
        ReceivingEndBus : "receiving_end_bus",
        DeviceId : "device_id",
        PowerBase : "power_base"
    }
    # list all attributes that are optional here (use the JSON attribute names)
    OPTIONAL_ATTRIBUTES = []
    # all attributes that are using the Quantity array block format should be listed here
    QUANTITY_ARRAY_BLOCK_ATTRIBUTES = {
        Resistance : "{pu}",
        Reactance : "{pu}",
        ShuntAdmittance : "{pu}",
        ShuntConductance : "{pu}",
        RatedCurrent : "{pu}",
    }
    # all attributes that are using the Quantity block format should be listed here
    QUANTITY_BLOCK_ATTRIBUTES = {
        PowerBase : "kV.A"
    }
    # all attributes that are using the Time series block format should be listed here
    TIMESERIES_BLOCK_ATTRIBUTES = []
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

    ########

    @property
    def resistance(self) -> QuantityArrayBlock:
        return self.__resistance

    @resistance.setter
    def resistance(self, resistance: Union[QuantityArrayBlock, Dict[str, Any]]):
        if self._check_resistance(resistance):
            self._set_quantity_array_block_value(self.Resistance, resistance)
        else:
            raise MessageValueError("Invalid value, {}, for attribute: Resistance ".format(resistance))

    @classmethod
    def _check_resistance(cls, resistance: Union[List[float], QuantityArrayBlock, Dict[str, Any]]) -> bool:
        return cls._check_quantity_array_block(
            value=resistance,
            unit=cls.QUANTITY_ARRAY_BLOCK_ATTRIBUTES[cls.Resistance])

    #######

    @property
    def reactance(self) -> QuantityArrayBlock:
        return self.__reactance

    @reactance.setter
    def reactance(self, reactance: Union[QuantityArrayBlock, Dict[str, Any]]):
        if self._check_reactance(reactance):
            self._set_quantity_array_block_value(self.Reactance, reactance)
        else:
            raise MessageValueError("Invalid value, {}, for attribute: Reactance ".format(reactance))

    @classmethod
    def _check_reactance(cls, reactance: Union[List[float], QuantityArrayBlock, Dict[str, Any]]) -> bool:
        return cls._check_quantity_array_block(
            value=reactance,
            unit=cls.QUANTITY_ARRAY_BLOCK_ATTRIBUTES[cls.Reactance])

    #######

    @property
    def shunt_admittance(self) -> QuantityArrayBlock:
        """The value of the ShuntAdmittanceArray attribute."""
        return self.__shunt_admittance

    @shunt_admittance.setter
    def shunt_admittance(self, shunt_admittance: Union[QuantityArrayBlock, Dict[str, Any]]):
        if self._check_shunt_admittance(shunt_admittance):
            self._set_quantity_array_block_value(self.ShuntAdmittance, shunt_admittance)
        else:
            raise MessageValueError("Invalid value, {}, for attribute: ShuntAdmittance".format(shunt_admittance))

    @classmethod
    def _check_shunt_admittance(cls, shunt_admittance: Union[List[float], QuantityArrayBlock, Dict[str, Any]]) -> bool:
        return cls._check_quantity_array_block(
            value=shunt_admittance,
            unit=cls.QUANTITY_ARRAY_BLOCK_ATTRIBUTES[cls.ShuntAdmittance])

    #######

    @property
    def shunt_conductance(self) -> QuantityArrayBlock:
        """The value of the ShuntConductance attribute."""
        return self.__shunt_conductance

    @shunt_conductance.setter
    def shunt_conductance(self, shunt_conductance: Union[QuantityArrayBlock, Dict[str, Any]]):
        if self._check_shunt_conductance(shunt_conductance):
            self._set_quantity_array_block_value(self.ShuntConductance, shunt_conductance)
        else:
            raise MessageValueError("Invalid value, {}, for attribute:ShuntConductance ".format(shunt_conductance))

    @classmethod
    def _check_shunt_conductance(cls, shunt_conductance: Union[List[float], QuantityArrayBlock, Dict[str, Any]]) -> bool:
        return cls._check_quantity_array_block(
            value=shunt_conductance,
            unit=cls.QUANTITY_ARRAY_BLOCK_ATTRIBUTES[cls.ShuntConductance])

    ########

    @property
    def rated_current(self) -> QuantityArrayBlock:
        """The value of the RatedCurrent attribute."""
        return self.__rated_current

    @rated_current.setter
    def rated_current(self, rated_current: Union[QuantityArrayBlock, Dict[str, Any]]):
        if self._check_rated_current(rated_current):
            self._set_quantity_array_block_value(self.RatedCurrent, rated_current)
        else:
            raise MessageValueError("Invalid value, {}, for attribute:RatedCurrent ".format(rated_current))

    @classmethod
    def _check_rated_current(cls, rated_current: Union[List[float], QuantityArrayBlock, Dict[str, Any]]) -> bool:
        return cls._check_quantity_array_block(
            value=rated_current,
            unit=cls.QUANTITY_ARRAY_BLOCK_ATTRIBUTES[cls.RatedCurrent])

    ########

    @property
    def device_id(self) -> List[str]:
        """The value of the DeviceIdArray attribute."""
        return self.__device_id

    @device_id.setter
    def device_id(self, device_id: List[str]):
        if self._check_device_id(device_id):
            self.__device_id = device_id
        else:
            raise MessageValueError("Invalid value, {}, for attribute:DeviceId ".format(device_id))

    @classmethod
    def _check_device_id(cls, device_id:List[str]) -> bool:
        return isinstance(device_id, list)

    ########

    @property
    def sending_end_bus(self) -> List[str]:
        """The value of the SendingEndBusArray attribute."""
        return self.__sending_end_bus

    @sending_end_bus.setter
    def sending_end_bus(self, sending_end_bus:List[str]):
        if self._check_sending_end_bus(sending_end_bus):
            self.__sending_end_bus = sending_end_bus
        else:
            raise MessageValueError("Invalid value, {}, for attribute:SendingEndBus ".format(sending_end_bus))

    @classmethod
    def _check_sending_end_bus(cls, sending_end_bus: List[str]) -> bool:
        return isinstance(sending_end_bus, list)

    ########

    @property
    def receiving_end_bus(self)-> List[str]:
        """The value of the ReceivingEndBus attribute."""
        return self.__receiving_end_bus

    @receiving_end_bus.setter
    def receiving_end_bus(self, receiving_end_bus: List[str]):
        if self._check_receiving_end_bus(receiving_end_bus):
            self.__receiving_end_bus = receiving_end_bus
        else:
            raise MessageValueError("Invalid value, {}, for attribute:ReceivingEndBus ".format(receiving_end_bus))

    @classmethod
    def _check_receiving_end_bus(cls, receiving_end_bus:List[str]) -> bool:
        return isinstance(receiving_end_bus, list)

    #########

    @property
    def power_base(self) -> QuantityBlock:
        """The value of the PowerBaseArray attribute."""
        return self.__power_base  # type: ignore  # pylint: disable=no-member

    @power_base.setter
    def power_base(self, power_base: Union[QuantityBlock, Dict[str, Any]]):
        if self._check_power_base(power_base):
            self._set_quantity_block_value(self.PowerBase, power_base)
        else:
            raise MessageValueError("Invalid value, {}, for attribute: POWER_BASE_ATTRIBUTE ".format(power_base))

    @classmethod
    def _check_power_base(cls, power_base: Union[QuantityBlock, Dict[str, Any]]) -> bool:
        return cls._check_quantity_block(
            value=power_base,
            unit=cls.QUANTITY_BLOCK_ATTRIBUTES[cls.PowerBase])

NISComponentMessage.register_to_factory()
