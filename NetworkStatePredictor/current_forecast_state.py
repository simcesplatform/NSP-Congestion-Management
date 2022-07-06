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

class ForecastStateMessageCurrent(AbstractResultMessage):
    """the message class contain the structure for what is published
    to the networkforecaststate.current by NetworkStateForecaster component"""

    CLASS_MESSAGE_TYPE = "NetworkForecastState.Current"
    MESSAGE_TYPE_CHECK = True

    FORECAST_SERIES_ATTRIBUTE = "Forecast"
    FORECAST_SERIES_NAMES = ["MagnitudeSendingEnd","MagnitudeReceivingEnd","AngleSendingEnd","AngleReceivingEnd"]
    FORECAST_SERIES_UNITS= ["A","A","deg","deg"]

    Device_Id = "DeviceId"
    Phase = "Phase"

    # all attributes specific that are added to the AbstractResult should be introduced here
    MESSAGE_ATTRIBUTES = {
        FORECAST_SERIES_ATTRIBUTE : "forecast",
        Device_Id : "deviceid",
        Phase : "phase"
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
            block_check=cls._check_current_forecast_block
        )

    @classmethod
    def _check_current_forecast_block(cls, current_block: TimeSeriesBlock) -> bool:
        for current_series_name in cls.FORECAST_SERIES_NAMES:
            if current_series_name not in current_block.series:
                return False
            current_series = current_block.series[current_series_name]
            if current_series.unit_of_measure != cls.FORECAST_SERIES_UNITS:
                return False

    ######################
    @property
    def deviceid(self) -> List[str]:
        return self.__deviceid

    @deviceid.setter
    def deviceid(self, deviceid: List[str]):
        if self._check_deviceid(deviceid):
            self.__deviceid=deviceid
        else:
            raise MessageValueError("Invalid value, {}, for attribute: bus_type".format(deviceid))

    @classmethod
    def _check_deviceid(cls, deviceid: List[str]) -> bool:
        if not isinstance(deviceid, str):
            return False

    ######################
    @property
    def phase(self) -> List[int]:
        return self.__phase

    @phase.setter
    def phase(self, phase: List[int]):
        if self._check_phase(phase):
            self.__phase=phase
        else:
            raise MessageValueError("Invalid value, {}, for attribute: bus_voltage_base".format(phase)))

    @classmethod
    def _check_phase(cls, phase: List[int]) -> bool:
        if not phase==1 and not phase==2 and not phase==3: # three phase system.
            return False

ForecastStateMessageCurrent.register_to_factory()
