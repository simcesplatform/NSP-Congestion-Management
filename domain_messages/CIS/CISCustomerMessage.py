# -*- coding: utf-8 -*-
# Copyright 2021 Tampere University and VTT Technical Research Centre of Finland
# This software was developed as a part of the ProCemPlus project: https://www.senecc.fi/projects/procemplus
# This software was developed as a part of the EU project INTERRFACE: http://interrface.eu/
# This source code is licensed under the MIT license. See LICENSE in the repository root directory.
# Author(s): Ville Heikkilä <ville.heikkila@tuni.fi>
#          : Mehdi Attar <mehdi.attar@tuni.fi>

"""
Module containing the message class for CIS Customer Information.
"""

from __future__ import annotations
from typing import Any, Dict, List, Union

from tools.exceptions.messages import MessageValueError
from tools.messages import AbstractResultMessage
from tools.tools import FullLogger

LOGGER = FullLogger(__name__)

class CISCustomerMessage(AbstractResultMessage):
    """the message class contain the structure for what is published
    to the Init.CIS.CustomerInfo by CIS component"""

    CLASS_MESSAGE_TYPE = "Init.CIS.CustomerInfo"
    MESSAGE_TYPE_CHECK = True

    ResourceId = "ResourceId"
    CustomerId = "CustomerId"
    BusName = "BusName"

    # all attributes specific that are added to the AbstractResult should be introduced here
    MESSAGE_ATTRIBUTES = {
        ResourceId: "resource_id",
        CustomerId : "customer_id",
        BusName : "bus_name"
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
    def resource_id(self) -> List[str]:
        return self.__resource_id

    @resource_id.setter
    def resource_id(self, resource_id: List[str]):
        if self._check_resource_id(resource_id):
            self.__resource_id=resource_id
            return
        raise MessageValueError("'{:s}' is an invalid value for ResourceId".format(resource_id))

    @classmethod
    def _check_resource_id(cls, resource_id: List[str]) -> bool:
        if isinstance(resource_id, list):
            return True
        else:
            return False

    ######################
    @property
    def customer_id(self) -> List[str]:
        return self.__customer_id

    @customer_id.setter
    def customer_id(self, customer_id: List[str]):
        if self._check_customer_id(customer_id):
            self.__customer_id=customer_id
        else:
            raise MessageValueError("Invalid value, {}, for attribute: CustomerId".format(customer_id))

    @classmethod
    def _check_customer_id(cls, customer_id: List[str]) -> bool:
        if isinstance(customer_id, list):
            return True
        else:
            return False
    ######################
    @property
    def bus_name(self) -> List[str]:
        return self.__bus_name

    @bus_name.setter
    def bus_name(self, bus_name: List[str]):
        if self._check_bus_name(bus_name):
            self.__bus_name=bus_name
        else:
            raise MessageValueError("Invalid value, {}, for attribute: BusName".format(bus_name))

    @classmethod
    def _check_bus_name(cls, bus_name: List[str]) -> bool:
        if isinstance(bus_name, list):
            return True
        else:
            return False


CISCustomerMessage.register_to_factory()
