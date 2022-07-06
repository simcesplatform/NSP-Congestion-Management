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
from tools.message.block import TimeSeriesBlock
from tools.tools import FullLogger

LOGGER = FullLogger(__name__)

class ForecastStateMessageVoltage(AbstractResultMessage):
    """the message class contain the structure for what is published
    to the networkforecaststate.voltage by NetworkStatePredictor component"""

    CLASS_MESSAGE_TYPE = "NetworkForecastState.Voltage"
    MESSAGE_TYPE_CHECK = True

    FORECAST_SERIES_ATTRIBUTE = "Forecast"
    FORECAST_SERIES_NAMES = ["Magnitude","Angle"]
    FORECAST_SERIES_UNITS= ["kV","deg"]

    Bus = "Bus"
    Node = "Node"

    # all attributes specific that are added to the AbstractResult should be introduced here
    MESSAGE_ATTRIBUTES = {
        FORECAST_SERIES_ATTRIBUTE : "forecast",
        Bus : "bus",
        Node : "node"
    }
    # list all attributes that are optional here (use the JSON attribute names)
    OPTIONAL_ATTRIBUTES = []
    # all attributes that are using the Quantity block format should be listed here
    QUANTITY_BLOCK_ATTRIBUTES = {
    }
    # all attributes that are using the Quantity array block format should be listed here
    QUANTITY_ARRAY_BLOCK_ATTRIBUTES = {
    }
    # all attributes that are using the Time series block format should be listed here
    TIMESERIES_BLOCK_ATTRIBUTES = [FORECAST_SERIES_ATTRIBUTE]
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
    def forecast(self) -> TimeSeriesBlock:
        return self.__forecast

    @forecast.setter
    def forecast(self, forecast: Union[TimeSeriesBlock, Dict[str, Any]]):
        if self._check_forecast(forecast):
            self.__forecast=forecast
            return
        raise MessageValueError("'{:s}' is an invalid value for BusName".format(forecast))

    @classmethod
    def _check_forecast(cls, forecast: Union[TimeSeriesBlock, Dict[str, Any]]) -> bool:
        return cls._check_timeseries_block(
            value=forecast,
            block_check=cls._check_voltage_forecast_block
        )

    @classmethod
    def _check_voltage_forecast_block(cls, voltage_block: TimeSeriesBlock) -> bool:
        for voltage_series_name in cls.FORECAST_SERIES_NAMES:
            if voltage_series_name not in voltage_block.series:
                return False
            current_series = voltage_block.series[voltage_series_name]
            if current_series.unit_of_measure != cls.FORECAST_SERIES_UNITS:
                return False

    ######################
    @property
    def bus(self) -> List[str]:
        return self.__bus

    @bus.setter
    def bus(self, bus: List[str]):
        if self._check_bus(bus):
            self.__bus=bus
        else:
            raise MessageValueError("Invalid value, {}, for attribute: bus_type".format(bus))

    @classmethod
    def _check_bus(cls, bus: List[str]) -> bool:
        if not isinstance(bus, str):
            return False

    ######################
    @property
    def node(self) -> List[int]:
        return self.__node

    @node.setter
    def node(self, node: List[int]):
        if self._check_node(node):
            self.__node=node
        else:
            raise MessageValueError("Invalid value, {}, for attribute: bus_voltage_base".format(node))

    @classmethod
    def _check_node(cls, node: List[int]) -> bool:
        if not node==1 and not node==2 and not node==3: # three phase system posses three nodes!
            return False

ForecastStateMessageVoltage.register_to_factory()
