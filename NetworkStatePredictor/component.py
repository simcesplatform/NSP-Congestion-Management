# -*- coding: utf-8 -*-
# Copyright 2021 Tampere University and VTT Technical Research Centre of Finland
# This software was developed as a part of the ProCemPlus project: https://www.senecc.fi/projects/procemplus
# This software was developed as a part of EU project INTERRFACE: http://www.interrface.eu/.
#  This source code is licensed under the MIT license. See LICENSE in the repository root directory.
# Author(s): Mehdi Attar <mehdi.attar@tuni.fi>
#            Ville Heikkilä <ville.heikkila@tuni.fi>

import asyncio
from socket import CAN_ISOTP
from typing import Any, cast, Set, Union

from tools.components import AbstractSimulationComponent
from tools.exceptions.messages import MessageError
from tools.messages import BaseMessage, AbstractMessage
from tools.tools import FullLogger, load_environmental_variables
from tools.message.block import TimeSeriesBlock, QuantityBlock, QuantityArrayBlock, ValueArrayBlock
from collections import defaultdict
import cmath
import math
import numpy

# import all the required message classes
from NetworkStatePredictor.current_forecast_state import ForecastStateMessageCurrent
from NetworkStatePredictor.voltage_forecast_state import ForecastStateMessageVoltage
from domain_messages.resource_forecast.resource_forecast_state import ResourceForecastPowerMessage
from domain_messages.NIS.NISBusMessage import NISBusMessage
from domain_messages.NIS.NISComponentMessage import NISComponentMessage
from domain_messages.CIS.CISCustomerMessage import CISCustomerMessage
from domain_messages.resource.resource_state import ResourceStateMessage


# initialize logging object for the module
LOGGER = FullLogger(__name__)

# topics to listen
BUS_DATA_TOPIC = "Init.NIS.NetworkBusInfo"
CUSTOMER_DATA_TOPIC = "Init.CIS.CustomerInfo"
COMPONENT_DATA_TOPIC = "Init.NIS.NetworkComponentInfo"
RESOURCE_STATE_TOPIC = "ResourceState.#" # wild card is used to listen to all sub topics of resource state
RESOURCE_FORECAST_TOPIC = "ResourceForecastState."

# Initialization data for power flow
POWER_FLOW_PERCISION = "POWER_FLOW_PERCISION"
APPARENT_POWER_BASE = "APPARENT_POWER_BASE"
ROOT_BUS_VOLTAGE = "ROOT_BUS_VOLTAGE"

# Forecast
FORECAST_HORIZON = "FORECAST_HORIZON"
# Resources
NUM_OF_RESOURCES = "NUM_OF_RESOURCES" 
RESOURCE_CATEGORIES = "RESOURCE_CATEGORIES"
# Grid id
GRID_ID = "GRID_ID" # name of the grid 
# time interval in seconds on how often to check whether the component is still running
TIMEOUT = 2.0
# ready made lists for further use in the code
voltage_new_node = ["voltage_new_node_1","voltage_new_node_2","voltage_new_node_3","voltage_new_node_neutral"]
voltage_old_node = ["voltage_old_node_1","voltage_old_node_2","voltage_old_node_3","voltage_old_node_neutral"]
current_node = ["current_node_1","current_node_2","current_node_3","current_node_neutral"]
power_node = ["power_node_1","power_node_2","power_node_3"]
admittance_node = ["admittance_node_1","admittance_node_2","admittance_node_3","admittance_node_neutral"]
delta_v_phase = ["delta_v_phase_1","delta_v_phase_2","delta_v_phase_3","delta_v_phase_neutral"]
current_phase = ["current_phase_1","current_phase_2","current_phase_3","current_phase_neutral"]




class NetworkStatePredictor(AbstractSimulationComponent,QuantityBlock,QuantityArrayBlock,TimeSeriesBlock,ValueArrayBlock,AbstractMessage): # the NetworkStatePredictor class inherits from AbstractSimulationComponent class
    """
    The NetworkStatePredictor (NSP) component is initialized in the beginning of the simulation by the platform manager.
    NSP listens to NIS, CIS, ResourceForecaster and Resource. After that, the NSP runs a predictive power flow.
    the JSON structure for bus data is available:
    https://simcesplatform.github.io/energy_msg-init-nis-networkbusinfo/
    The JSON structure for component data is available :
    https://simcesplatform.github.io/energy_msg-init-nis-networkcomponentinfo/
    the JSON structure for resource forecasted data:
    https://simcesplatform.github.io/energy_msg-resourceforecaststate-power/
    the JSON structure for resource state data:
    https://simcesplatform.github.io/energy_msg-resourcestate/
    The JSON structure for publishing the forecasted current values:
    https://simcesplatform.github.io/energy_msg-networkforecaststate-current/
    The JSON structure for publishing the forecastred voltage values:
    https://simcesplatform.github.io/energy_msg-networkforecaststate-voltage/
    """
    LOGGER.info("5")
    # Constructor
    def __init__(self):
        """
        The NSP component is initiated in the beginning of the simulation by the simulation manager
        and in every epoch, it calculates and publishes the network state forecast.
        """
        super().__init__()
        LOGGER.info("6")
        # Load environmental variables for those parameters that were not given to the constructor.

        try:
            environment = load_environmental_variables(
                (POWER_FLOW_PERCISION,float, 0.001),
                (APPARENT_POWER_BASE,int,10000),
                (ROOT_BUS_VOLTAGE,float,1.02),
                (FORECAST_HORIZON,int,36),
                (NUM_OF_RESOURCES,int),
                (GRID_ID,str),
                (RESOURCE_CATEGORIES,str))
        except (ValueError, TypeError, MessageError) as message_error:
                LOGGER.error(f"{type(message_error).__name__}: {message_error}")
        LOGGER.info("7")
        # publishing to topics

        self._power_flow_percision = environment[POWER_FLOW_PERCISION]
        self._apparent_power_base = environment[APPARENT_POWER_BASE]
        self._root_bus_voltage = environment[ROOT_BUS_VOLTAGE]
        self._forecast_horizon = environment[FORECAST_HORIZON]
        self._num_resources = environment[NUM_OF_RESOURCES] # resources including loads, generations and storages
        self._grid_id = environment[GRID_ID]
        self._resource_categories = environment[RESOURCE_CATEGORIES].split(",")

        self._voltage_forecast_topic="NetworkForecastState."+self._grid_id+".Voltage."  # according to documentation: https://simcesplatform.github.io/energy_topics/
        self._current_forecast_topic="NetworkForecastState."+self._grid_id+".Current."
        LOGGER.info("8")
        # Listening to the required topics
        self._other_topics = [
			BUS_DATA_TOPIC, 
			CUSTOMER_DATA_TOPIC,
			COMPONENT_DATA_TOPIC,
            RESOURCE_STATE_TOPIC
		]
        for i in range (0,len(self._resource_categories)): # https://simcesplatform.github.io/energy_topic-resourceforecaststate/
            locals()["FORECAST_TOPIC_"+str(i)] = RESOURCE_FORECAST_TOPIC+self._resource_categories[i]+".#" # wild card is used to listen to all resource Ids
            self._other_topics.append(locals()["FORECAST_TOPIC_"+str(i)])

        LOGGER.info("9")
        # for incoming messages
        self._nis_bus_data = {}       # Dict for NIS data
        self._nis_component_data = {}  # Dict for NIS data
        self._cis_customer_data = {}   # Dict for CIS data
        self._resources_forecasts=[]  # List for incoming forecast data
        self._resources = {} # dict for components' resources
        self._resources["CustomerId"] = [0 for i in range(self._num_resources + 1)]
        self._resources["Node"] = [0 for i in range(self._num_resources + 1)]
        self._resources["ResourceId"] = [0 for i in range(self._num_resources + 1)]
        self._resource_id_logger = [0 for i in range(self._num_resources + 1)]

        LOGGER.info("10")
        # for outgoing messages
        self._voltage_forecast_template = {}  # template for voltage forecast messages
        self._current_forecast_template = {} # template for current forecast messages
        self._voltage_forecast = []  # List for voltage forecasts
        self._current_forecast = []  # List for current forecasts

        # mapping and internal variables
        self._per_unit = {}  # Dict for per unit values
        self._bus = {}  # Dict for nodal values
        self._branch = {}  # Dict for branches
        self._power = {}  # Dict for power
        self._impedance = {} # Dict for components' impedances 

        LOGGER.info("11")
        self._resource_forecast_msg_counter = 0
        self._resource_state_msg_counter = 0
        self._nis_bus_data_received = False
        self._nis_component_data_received = False
        self._cis_data_received = False
        self._input_data_ready = False
        LOGGER.info("12")

    def clear_epoch_variables(self) -> None:
        """Clears all the variables that are used to store information about the received input within the
           current epoch. This method is called automatically after receiving an epoch message for a new epoch.
        """
        self._resource_forecast_msg_counter = 0 # clearing the counter of resource forecast messages in the beginning of the current epoch
        self._resource_state_msg_counter = 0 # clearing the counter of resource state messages in the beginning of the current epoch
        self._input_data_ready = False
        self._resources_forecasts = [] # clearing the resource forecasts data in the beginning of the current epoch
        self._resource_id_logger = [0 for i in range(self._num_resources + 1)] # clearing the resource id logger in the beginning of the current epoch
        self._forecast_time_index = [] 
        self._voltage_forecast = []  
        self._current_forecast = []

        self._resources["CustomerId"] = [0 for i in range(self._num_resources + 1)] # clearing the resource messages
        self._resources["Node"] = [0 for i in range(self._num_resources + 1)]
        self._resources["ResourceId"] = [0 for i in range(self._num_resources + 1)]

        LOGGER.info("Input parameters cleared for epoch {:d}".format(self._latest_epoch_message.epoch_number))
        


    async def process_epoch(self) -> bool:
        """
        Process the epoch and do all the required calculations.
        Returns False, if processing the current epoch was not yet possible.
        Otherwise, returns True, which indicates that the epoch processing was fully completed.
        This also indicated that the component is ready to send a Status Ready message to the Simulation Manager.
        """
        #input_data_ready = False
        #if self._resource_forecast_msg_counter == self._num_resources and self._nis_bus_data_received==True and \
        #    self._nis_component_data_received==True and self._cis_data_received==True and \
        #    self._resource_state_msg_counter == self._num_resources:
        LOGGER.info("14")
        if self._input_data_ready == True:
            if self._latest_epoch == 1: # the calculation of this section is only needed once in Epoch 1
                
                # setting up per unit dictionary

                self._per_unit["voltage_base"] = self._nis_bus_data.bus_voltage_base.values
                self._per_unit["s_base"] = [self._apparent_power_base for i in range(self._num_buses)]
                self._per_unit["i_base"] = abs(numpy.divide(self._per_unit["s_base"],(numpy.array(self._per_unit["voltage_base"]))*cmath.sqrt(3))) # since we have line to line voltages sqrt(3) is needed
                self._per_unit["z_base"] = [i / j for i, j in zip(self._per_unit["voltage_base"],self._per_unit["i_base"])]

                LOGGER.info("self._per_unit[voltage_base] is {}".format(self._per_unit["voltage_base"]))
                LOGGER.info("self._per_unit[s_base] is {}".format(self._per_unit["s_base"]))
                LOGGER.info("self._per_unit[i_base] is {}".format(self._per_unit["i_base"]))
                LOGGER.info("self._per_unit[z_base] is {}".format(self._per_unit["z_base"]))
                LOGGER.info("15")
                # creating a graph according to the network topology of NIS data

                edges=[]
                for i in range (self._num_branches):
                    list_1 = [self._nis_component_data.sending_end_bus[i],self._nis_component_data.receiving_end_bus[i]]
                    edges.append(list_1)
                graph = defaultdict(list)
                for edge in edges:
                    a, b = edge[0], edge[1]
                    graph[a].append(b)
                    graph[b].append(a)
                self._graph = graph

                LOGGER.info("self._graph is {}".format(self._graph))
                LOGGER.info("16")
                # impedances
                    # The network assumed to be symmetric. The neutral wire assumes to have a same characteristics than phase wires.

                self._branch["impedance"]=[0 for i in range(self._num_branches)]
                self._branch["impedance_angle_polar"]=[0 for i in range(self._num_branches)] 
                for i in range (self._num_branches):   
                    self._branch["impedance"][i]=complex(self._nis_component_data.resistance.values[i],self._nis_component_data.reactance.values[i])
                    #    [Abs,Angle]=cmath.polar(w)
                    #    self._branch["impedance_angle_polar"][i]=Angle

                LOGGER.info("branch impedance is {}".format(self._branch["impedance"]))

                # Nodal admittances
                for i in range(4):
                    self._bus[admittance_node[i]] = [0 for i in range(self._num_buses)]

                merged_list=list(zip(self._nis_component_data.sending_end_bus,self._nis_component_data.receiving_end_bus))
                for bus in range (self._num_buses):
                    bus_name=self._nis_bus_data.bus_name[bus]
                    nearby_buses=self._graph[bus_name]
                    length=len(nearby_buses)
                    for n in range(length):
                        to_bus=nearby_buses[n]
                        c=[bus_name,to_bus]
                        c1=[to_bus,bus_name]
                        for k in range(self._num_branches):
                            if c==list(merged_list[k]) or c1==list(merged_list[k]):
                                self._bus["admittance_node_1"][bus] = self._nis_component_data.shunt_admittance.values[k]/2 + self._bus["admittance_node_1"][bus]
                                self._bus["admittance_node_2"][bus] = self._nis_component_data.shunt_admittance.values[k]/2 + self._bus["admittance_node_1"][bus]
                                self._bus["admittance_node_3"][bus] = self._nis_component_data.shunt_admittance.values[k]/2 + self._bus["admittance_node_1"][bus]
                                self._bus["admittance_node_neutral"][bus] = self._nis_component_data.shunt_admittance.values[k]/2 + self._bus["admittance_node_1"][bus]

                LOGGER.info("17")
                # preparing voltage and current forecast messages templates

                self._voltage_forecast_template={'Forecast': {'TimeIndex': ["0"],\
                'Series': {'Magnitude': {'UnitOfMeasure': 'kV', 'Values': [0]},\
                'Angle': {'UnitOfMeasure': 'deg', 'Values': [0]}},\
                'Bus': 'load', 'Node': 1}}
                self._voltage_forecast_template["Forecast"]["TimeIndex"]=self._forecast_time_index
                self._voltage_forecast_template["Forecast"]["Series"]["Magnitude"]["Values"]=[0 for i in range(self._forecast_horizon)]
                self._voltage_forecast_template["Forecast"]["Series"]["Angle"]["Values"]=[0 for i in range(self._forecast_horizon)]

                LOGGER.info("self._voltage_forecast_template is {}".format(self._voltage_forecast_template))

                self._current_forecast_template={"Forecast" : {"TimeIndex" :["0"],\
                "Series" :{"MagnitudeSendingEnd" :{"UnitOfMeasure" : "A","Values" :[0]},\
                "MagnitudeReceivingEnd" :{"UnitOfMeasure" : "A","Values" :[0]},\
                "AngleSendingEnd" :{"UnitOfMeasure" : "deg","Values" :[0]},\
                "AngleReceivingEnd" :{"UnitOfMeasure" : "deg","Values" :[0]}}},\
                "DeviceId" : "XYZ","Phase" : 1}
                self._current_forecast_template["Forecast"]["TimeIndex"]=self._forecast_time_index
                self._current_forecast_template["Forecast"]["Series"]["MagnitudeSendingEnd"]["Values"]=[0 for i in range(self._forecast_horizon)]
                self._current_forecast_template["Forecast"]["Series"]["MagnitudeReceivingEnd"]["Values"]=[0 for i in range(self._forecast_horizon)]
                self._current_forecast_template["Forecast"]["Series"]["AngleSendingEnd"]["Values"]=[0 for i in range(self._forecast_horizon)]
                self._current_forecast_template["Forecast"]["Series"]["AngleReceivingEnd"]["Values"]=[0 for i in range(self._forecast_horizon)] 

                LOGGER.info("self._current_forecast_template is {}".format(self._current_forecast_template))   

            # setting up branch dictionary
            LOGGER.info("17")
            self._branch["current_phase_1"] = [0 for i in range(self._num_branches)]
            self._branch["delta_v_phase_1"] = [0 for i in range(self._num_branches)]

            self._branch["current_phase_2"] = [0 for i in range(self._num_branches)]
            self._branch["delta_v_phase_2"] = [0 for i in range(self._num_branches)]
            
            self._branch["current_phase_3"] = [0 for i in range(self._num_branches)]
            self._branch["delta_v_phase_3"] = [0 for i in range(self._num_branches)]

            self._branch["current_phase_neutral"] = [0 for i in range(self._num_branches)]
            self._branch["delta_v_phase_neutral"] = [0 for i in range(self._num_branches)]

            # Duplicaiton of the template of voltage and current forecasts, ready to be filled when power flow is done

            LOGGER.info("18")

            for duplication in range (self._num_buses):
                for nodes_num in range(3):  # Each bus has three nodes
                    self._voltage_forecast.append(self._voltage_forecast_template)
            for duplication in range (self._num_branches):
                for phases_num in range (3): # each branch has three phases
                    self._current_forecast.append(self._current_forecast_template)

            # setting up node dictionary for all four nodes
            LOGGER.info("19")

            for node in range (3):
                self._bus[power_node[node]] = [0 for i in range(self._num_buses)]
            for node in range (4):
                self._bus[voltage_old_node[node]]=[0 for i in range(self._num_buses)]
            for bus in range (self._num_buses):
                LOGGER.info("voltage old node 1 is {}".format(self._bus["voltage_old_node_1"]))
                LOGGER.info("voltage old node 1 is {}".format(self._bus["voltage_old_node_1"][bus])) 
                self._bus["voltage_old_node_1"][bus] = self._root_bus_voltage
                self._bus["voltage_old_node_2"][bus] = cmath.rect(self._root_bus_voltage,4*math.pi/3)
                self._bus["voltage_old_node_3"][bus] = cmath.rect(self._root_bus_voltage,2*math.pi/3)
                self._bus["voltage_old_node_neutral"][bus] = 0
            for node in range(4):
                self._bus[current_node[node]] = [0 for i in range(self._num_buses)]
                self._bus[voltage_new_node[node]] = [0 for i in range(self._num_buses)]
                self._bus[current_node[node]] = [0 for i in range(self._num_buses)]
                self._bus[voltage_new_node[node]][self._root_bus_index] = self._root_bus_voltage
                self._branch[current_phase[node]] = [0 for i in range(self._num_branches)]
                self._branch[delta_v_phase[node]] = [0 for i in range(self._num_branches)]
            
            # calculate backward-forward sweep powerflow for each timestep of the forecast horizon based on https://ieeexplore.ieee.org/abstract/document/1245548
            LOGGER.info("20")

            for horizon in range (self._forecast_horizon): 

                power_flow_error_node=10 # 10 is a value that is way larger than the aaceptable limit to make sure that the first iteration will begin
                LOGGER.info("22")

                while power_flow_error_node > self._power_flow_percision: # stop power flow when enough accuracy of voltages reached

                    for p in range (3):    
                        self._bus[power_node[p]]=[0 for i in range(self._num_buses)]

                    LOGGER.info("23")

                    for i in range (self._resource_forecast_msg_counter): # calculating nodal powers based on the power forecasts
                        LOGGER.info("23.1")
                        # finding its power
                        try:
                            temp_power = self._resources_forecasts[i].forecast.series["RealPower"].values[horizon]
                            LOGGER.info("temp_power is {}".format(temp_power))
                            power_per_unit = (temp_power/self._apparent_power_base) # Per unit power
                            LOGGER.info("power per unit is {}".format(power_per_unit))
                        except BaseException as err:
                            LOGGER.info(f"Unexpected {err=}, {type(err)=}")
                        # Finding the resourceId
                        temp_resource_id = self._resources_forecasts[i].resource_id
                        LOGGER.info("temp_resource_id {:s}".format(temp_resource_id))
                        # finding the node that it is connected to
                        try:
                            index = self._resources["ResourceId"].index(temp_resource_id)
                            LOGGER.info("index is {}".format(index))    
                        except:
                            LOGGER.warning("Resource forecast has a resource id that doesnot exist in the resources messages")
                        Connected_node = self._resources["Node"][index]
                        LOGGER.info("connected node is {}".format(Connected_node))
                        # finding the bus where the power should be added to
                        try:
                            temp_index = self._cis_customer_data.resource_id.index(temp_resource_id)
                        except:
                            LOGGER.warning("Resource forecast message has a resource id that doesnot exist in the CIS data")

                        temp_bus_name = self._cis_customer_data.bus_name[temp_index]
                        temp_row = self._nis_bus_data.bus_name.index(temp_bus_name)

                        LOGGER.info("bus name is {}".format(temp_bus_name))

                        if Connected_node == 1:
                            self._bus["power_node_1"][temp_row] = power_per_unit + self._bus["power_node_1"][temp_row]
                        elif Connected_node == 2:
                            self._bus["power_node_2"][temp_row] = power_per_unit + self._bus["power_node_2"][temp_row]
                        elif Connected_node == 3:
                            self._bus["power_node_3"][temp_row] = power_per_unit + self._bus["power_node_3"][temp_row]
                        elif Connected_node == "three_phase":
                            power_per_unit_per_phase = power_per_unit/cmath.sqrt(3)  # calculate power per phase
                            self._bus["power_node_1"][temp_row] = power_per_unit_per_phase + self._bus["power_node_1"][temp_row]
                            self._bus["power_node_2"][temp_row] = power_per_unit_per_phase + self._bus["power_node_2"][temp_row]
                            self._bus["power_node_3"][temp_row] = power_per_unit_per_phase + self._bus["power_node_3"][temp_row]

                        LOGGER.info("Power at node 1 is {}".format(self._bus["power_node_1"])) 
                        LOGGER.info("Power at node 2 is {}".format(self._bus["power_node_2"])) 
                        LOGGER.info("Power at node 3 is {}".format(self._bus["power_node_3"])) 

                    # calculating nodal currents

                    LOGGER.info("24")
                    for bus in range (self._num_buses): 
                        LOGGER.info("bus is {}".format(bus))
                        for node in range (0,3):   # for each phase
                            LOGGER.info("node is {}".format(node))
                            LOGGER.info("voltage old is {}".format(self._bus[voltage_old_node[node]][bus]))
                            LOGGER.info("voltage at neutral point is {}".format(self._bus["voltage_old_node_neutral"][bus]))
                            voltage_difference = self._bus[voltage_old_node[node]][bus] - self._bus["voltage_old_node_neutral"][bus]
                            self._bus[current_node[node]][bus] = self._bus[power_node[node]][bus]/voltage_difference
                            LOGGER.info("current is {}".format(self._bus[current_node[node]][bus]))
                            LOGGER.info("voltage difference is {}".format(voltage_difference))
                        self._bus["current_node_neutral"][bus]=-(self._bus["current_node_1"][bus]+self._bus["current_node_2"][bus]+self._bus["current_node_3"][bus])

                    for bus in range(self._num_buses): # taking into account line admittances
                        for node in range (0,4):
                            self._bus[current_node[node]][bus] = self._bus[current_node[node]][bus]-(self._bus[admittance_node[node]][bus]*self._bus[voltage_old_node[node]][bus])


                    LOGGER.info("Current at phase 1 is {}".format(self._bus[current_node[0]]))
                    LOGGER.info("Current at phase 2 is {}".format(self._bus[current_node[1]]))
                    LOGGER.info("Current at phase 3 is {}".format(self._bus[current_node[2]]))
                    LOGGER.info("Current at phase neutral is {}".format(self._bus[current_node[3]])) 

                    # calculating branch currents
                    LOGGER.info("25")
                    for i in range (self._num_branches):  
                        from_bus = self._nis_component_data.sending_end_bus[i]
                        to_bus = self._nis_component_data.receiving_end_bus[i]
                        buses_list = []
                        buses_list.append(from_bus)
                        buses_list.append(to_bus)
                        buses_list = set(buses_list)
                        LOGGER.info("25.1")
                        for j in range (self._num_buses):
                            LOGGER.info("The nis bus name is {:s}".format(self._nis_bus_data.bus_name[j]))
                            if self._root_bus_name != self._nis_bus_data.bus_name[j]:
                                try:
                                    shortest_path = self._shortest_path(self._root_bus_name,self._nis_bus_data.bus_name[j])
                                    LOGGER.info("the shortest path is {}".format(shortest_path))
                                except BaseException as err:
                                    LOGGER.info(f"Unexpected {err=}, {type(err)=}")
                                if len(buses_list.intersection(shortest_path)) == 2: # current passes through the branch
                                    LOGGER.info("The nodal current passes through the branch")
                                    for phases in range (0,4):
                                        self._branch[current_phase[phases]][i] = self._bus[current_node[phases]][j] + self._branch[current_phase[phases]][i]
                                        LOGGER.info("the branch current is {}".format(self._branch[current_phase[phases]][i]))
                    
                    LOGGER.info("25.2")
                    LOGGER.info("the branch current at phase 1 is {}".format(self._branch[current_phase[0]]))
                    LOGGER.info("the branch current at phase 2 is {}".format(self._branch[current_phase[1]]))
                    LOGGER.info("the branch current at phase 3 is {}".format(self._branch[current_phase[2]]))
                    LOGGER.info("the branch current at phase neutral is {}".format(self._branch[current_phase[3]]))

                    # calculating the voltage drop over each branch
                    LOGGER.info("26")
                    for row in range (self._num_branches): 
                        for kk in range (0,4):
                            self._branch[delta_v_phase[kk]][row] = self._branch[current_phase[kk]][row] * self._branch["impedance"][row]

                    #voltage_node_1 = []
                    #voltage_node_2 = []
                    #voltage_node_3 = []
                    #voltage_node_1.append(self._bus["voltage_new_node_1"])
                    #voltage_node_2.append(self._bus["voltage_new_node_2"])
                    #voltage_node_3.append(self._bus["voltage_new_node_3"])
                    #zero_avail_node_1 = voltage_node_1.count(0)
                    #zero_avail_node_2 = voltage_node_2.count(0)
                    #zero_avail_node_3 = voltage_node_3.count(0)
                    #zero_avail_node_3 = voltage_node_3.count(0)
                    zero_avail = {}
                    zero_avail = self._bus["voltage_new_node_1"] + self._bus["voltage_new_node_2"] + self._bus["voltage_new_node_3"]  
                    zero_avail_num = zero_avail.count(0)
                    LOGGER.info("the number of 0 voltages are {}".format(zero_avail_num))
                    
                    # calculating the new voltages
                    LOGGER.info("27")

                    while zero_avail_num != 0:
                        for bus in range (self._num_buses):
                            for node in range (0,4):
                                LOGGER.info("the node is {}".format(node))
                                if self._bus[voltage_new_node[node]][bus] == 0:
                                    bus_name = self._nis_bus_data.bus_name[bus]
                                    LOGGER.info("the bus name is {}".format(bus_name))
                                    nearby_buses=self._graph[bus_name]
                                    LOGGER.info("the nearby buses are {}".format(nearby_buses))
                                    #self._tree_creator(bus_name,1) # It finds the neighbouring buses
                                    #num_nearby_buses = len(self._nearby_buses)
                                    length = len(nearby_buses)
                                    if length > 0:
                                        for a in range (length):
                                            index = self._nis_bus_data.bus_name.index(nearby_buses[a])
                                            if self._bus[voltage_new_node[node]][index] > 0:
                                                to_bus = nearby_buses[a]
                                                from_bus = bus_name
                                                branch = [from_bus,to_bus]
                                                branch1 = [to_bus,from_bus]
                                                shortest_path1 = self._shortest_path(self._root_bus_name,from_bus)
                                                shortest_path2 = self._shortest_path(self._root_bus_name,to_bus)
                                                for b in range (self._num_branches):
                                                    aa = [self._nis_component_data.sending_end_bus[b],self._nis_component_data.receiving_end_bus[b]]
                                                    if aa == branch or aa == branch1:
                                                        row = b
                                                        if len(shortest_path1) > len(shortest_path2):
                                                            self._bus[voltage_new_node[node]][bus] = self._bus[voltage_old_node[node]][self._nearby_buses[a]] + self._branch[delta_v_phase[node]][row]
                                                        else:
                                                            self._bus[voltage_new_node[node]][bus] = self._bus[voltage_old_node[node]][self._nearby_buses[a]] - self._branch[delta_v_phase[node]][row]
                                                        break
                                                break
                        zero_avail = {}
                        zero_avail = self._bus["voltage_new_node_1"] + self._bus["voltage_new_node_2"] + self._bus["voltage_new_node_3"]
                        zero_avail_num = zero_avail.count(0)
                        LOGGER.info("the number of 0 voltages are {}".format(zero_avail_num))
                         
                    for w in range (self._num_buses): # calculate the error only for node 1
                        power_flow_error_node[w] = abs(self._bus["voltage_old_node_1"][w]-self._bus["voltage_new_node_1"][w])
                        power_flow_error_node=max(power_flow_error_node[w])
                    for p in range (4): # clear values for a fresh start
                        self._bus[voltage_old_node[p]]=self._bus[voltage_new_node[p]]
                        self._bus[voltage_new_node[p]]=[0 for i in range(self._num_buses)]
                        self._bus[current_node[p]] = [0 for i in range(self._num_buses)]
                        self._bus[voltage_new_node[p]][self._root_bus_index] = self._root_bus_voltage
                        self._branch[current_phase[p]] = [0 for i in range(self._num_branches)]
                        self._branch[delta_v_phase[p]] = [0 for i in range(self._num_branches)]

                else:
                    
                    LOGGER.info("27")
                    # storing voltage values as a result of power flow
                    for bus in range (self._num_buses):
                        bus_name=self._nis_bus_data.bus_name[bus]
                        for node in range (0,3):
                            row = bus*3 + node
                            [absolute,angle] = cmath.polar(self._bus[voltage_new_node[node-1]][bus])
                            self._voltage_forecast[row]["Forecast"]["Series"]["Magnitude"]["Values"][horizon] = absolute
                            self._voltage_forecast[row]["Forecast"]["Series"]["Angle"]["Values"][horizon] = angle*(360/(2*3.1415))    # radian to degree
                            self._voltage_forecast[row]["Forecast"]["Bus"] = bus_name
                            self._voltage_forecast[row]["Forecast"]["Node"] = node
                    
                    LOGGER.info("28")
                    for branch in range (self._num_branches):
                        device_id = self._nis_component_data.device_id[branch]
                        for phase in range (0,3):
                            row = branch*3 + phase
                            self._current_forecast[row]["Forecast"]["DeviceId"] = device_id
                            self._current_forecast[row]["Forecast"]["Phase"] = phase
                            self._current_forecast[row]["Forecast"]["Series"]["MagnitudeSendingEnd"]["Values"][horizon] = self._branch[current_phase[phase-1]][branch]
                            self._current_forecast[row]["Forecast"]["Series"]["MagnitudeReceivingEnd"]["Values"][horizon] = self._branch[current_phase[phase-1]][branch]
                            self._current_forecast[row]["Forecast"]["Series"]["AngleSendingEnd"]["Values"][horizon] = 0 # needs to be specified later
                            self._current_forecast[row]["Forecast"]["Series"]["AngleReceivingEnd"]["Values"][horizon] = 0 # needs to be specified later
                    
                    # Getting ready for power flow of a new timestep
                    LOGGER.info("29")
                    for k in range (0,3):
                        self._bus[voltage_old_node[k]] = [1 for i in range(self._num_buses)]
                        self._bus[voltage_old_node[k]][self._root_bus_index] = self._root_bus_voltage # fixing the root bus voltage
                        self._bus[voltage_new_node[k]] = [0 for i in range(self._num_buses)]
                        self._bus[voltage_new_node[k]][self._root_bus_index] = self._root_bus_voltage # fixing the root bus voltage

            # when power flow is done for all time steps

            for p in range (len(self._voltage_forecast)):
                
                voltage_message = self._message_generator.get_message(
                ForecastStateMessageVoltage,
                EpochNumber = self._latest_epoch,
                TriggeringMessageIds = self._triggering_message_ids,
                Forecast = self._voltage_forecast[p]["Forecast"],
                Bus = self._voltage_forecast[p]["Bus"],
                Node = self._voltage_forecast[p]["Node"])

                voltage_topic = self._voltage_forecast_topic + self._voltage_forecast[p]["Bus"]
                
                LOGGER.info("30")
                await self._send_message(voltage_message, voltage_topic)
            for n in range (len(self._current_forecast)):
                
                current_message = self._message_generator.get_message(
                ForecastStateMessageCurrent,
                EpochNumber = self._latest_epoch,
                TriggeringMessageIds = self._triggering_message_ids,
                Forecast = self._current_forecast[n]["Forecast"],
                DeviceId = self._current_forecast[n]["DeviceId"],
                Phase = self._current_forecast[n]["Phase"])

                current_topic = self._current_forecast_topic + self._current_forecast[n]["DeviceId"]

                LOGGER.info("31")
                await self._send_message(current_message, current_topic)
            # return True to indicate that the component is finished with the current epoch
            return True
        else:
            return False

    async def general_message_handler(self, message_object: Union[BaseMessage,QuantityBlock, Any],
                                      message_routing_key: str) -> None:
        """
        TODO: NIS,CIS, ResourceStateForecast and ResourceState messages are handled here.
        """
        # ignore simple messages from components that have not been registered as input components
        # Forecast
        if isinstance(message_object,ResourceForecastPowerMessage):
            # added extra cast to allow Pylance to recognize that message_object is an instance of SimpleMessage
            message_object = cast(ResourceForecastPowerMessage, message_object)
            LOGGER.info("Received {:s} message from topic {:s}".format(
                message_object.message_type, message_routing_key))
            self._resource_forecast_message_handler(message_object)

        # Resource state
        elif isinstance(message_object,ResourceStateMessage):
            message_object = cast(ResourceStateMessage,message_object)
            self._resource_state_msg_counter = self._resource_state_msg_counter+1
            LOGGER.info("Received {}".format(self._resource_state_msg_counter))
            LOGGER.info("Received {:s} message from topic {:s}".format(
                message_object.message_type, message_routing_key))
            self._resources["CustomerId"][self._resource_state_msg_counter] = message_object.customerid
            self._resources["ResourceId"][self._resource_state_msg_counter]=message_object.source_process_id

            if  message_object.node in range (1,4):
                self._resources["Node"][self._resource_state_msg_counter]=message_object.node
                LOGGER.info("there is node 1 or 2 or 3")
            else:
                self._resources["Node"][self._resource_state_msg_counter]="three_phase"
                LOGGER.info("it is three phase")

        # NIS bus
        elif isinstance(message_object,NISBusMessage) and self._latest_epoch == 1: # NIS data is only published in the first epoch
            message_object = cast(NISBusMessage,message_object)
            LOGGER.info("Received {:s} message from topic {:s}".format(
                message_object.message_type, message_routing_key))
            self._nis_bus_data = message_object
            self._num_buses = len(self._nis_bus_data.bus_name)
            self._root_bus_index = self._nis_bus_data.bus_type.index("root")
            self._root_bus_name = self._nis_bus_data.bus_name[self._root_bus_index] # name of the root bus

            LOGGER.info("NISBusMessage was received")
            self._nis_bus_data_received = True

        # NIS component
        elif isinstance(message_object,NISComponentMessage) and self._latest_epoch == 1: # NIS data is only published in the first epoch
            message_object = cast(NISComponentMessage,message_object)
            LOGGER.info("Received {:s} message from topic {:s}".format(
                message_object.message_type, message_routing_key))
            self._nis_component_data = message_object
            self._num_branches = len(self._nis_component_data.device_id)

            if self._nis_component_data.power_base.value != self._apparent_power_base:
                LOGGER.warning("Power base in NIS and manifest arenot equal")
                LOGGER.warning("Power base in NIS file:{} is used".format(self._nis_component_data.power_base.value))
                self._apparent_power_base = self._nis_component_data.power_base.value

            LOGGER.info("NISComponentMessage was received")
            self._nis_component_data_received = True

        # CIS
        elif isinstance(message_object,CISCustomerMessage) and self._latest_epoch == 1: # CIS data is only published in the first epoch
            message_object = cast(CISCustomerMessage,message_object)
            LOGGER.info("Received {:s} message from topic {:s}".format(
                message_object.message_type, message_routing_key))
            self._cis_customer_data = message_object
            if self._num_resources != len(self._cis_customer_data.resource_id):
                LOGGER.warning("The number of resources {:s} in CIS donot match with its number {} in manifest file".format(
                len(self._cis_customer_data.resource_id),self._num_resources))

            LOGGER.info("CISCustomerMessage was received")
            self._cis_data_received = True

        else:
            LOGGER.warning("Received unknown message from {}: {}".format(message_routing_key, message_object))

        if self._resource_forecast_msg_counter == self._num_resources and self._nis_bus_data_received==True and \
            self._nis_component_data_received==True and self._cis_data_received==True and \
            self._resource_state_msg_counter == self._num_resources:
                self._input_data_ready = True
                LOGGER.info("all required data were received, now ready for the actual functionality")
                await self.process_epoch()
    
    def _resource_forecast_message_handler(self,forecasted_data:Union [ResourceForecastPowerMessage,TimeSeriesBlock]) -> None:
        if self._resource_forecast_msg_counter == [] or self._resource_forecast_msg_counter == 0 :
            self._resource_forecast_msg_counter = 0
            self._resources_forecasts.append(forecasted_data)
            self._resource_id_logger[self._resource_forecast_msg_counter] = forecasted_data.resource_id
            self._resource_forecast_msg_counter = self._resource_forecast_msg_counter + 1
            LOGGER.info("forecast message counter {}".format(self._resource_forecast_msg_counter)) 
        else:
            try: 
                self._resource_id_logger.index(forecasted_data.resource_id) # if ResourceId doesnot exist, it goes to the exception
                LOGGER.warning("The forecast of the resource id {} has already been received".format(forecasted_data.resource_id))
            except: # this message has a new ResourceId
                self._resources_forecasts.append(forecasted_data)
                self._resource_id_logger[self._resource_forecast_msg_counter] = forecasted_data.resource_id
                self._resource_forecast_msg_counter = self._resource_forecast_msg_counter + 1
                LOGGER.info("forecast message counter {}".format(self._resource_forecast_msg_counter))
                if self._forecast_time_index: # if self._forecast_time_index is empty  
                    self._forecast_time_index = forecasted_data.forecast.time_index
                if self._forecast_horizon != len(forecasted_data.forecast.time_index):
                    self._forecast_horizon = len(forecasted_data.forecast.time_index)
                    LOGGER.warning("The forecast horizon in the manifest file is not equal to the message {} forecasts' horizon".format(forecasted_data.message_id))
                
                async def _send_message(self, MessageContent, Topic):
                    await self._rabbitmq_client.send_message(
                    topic_name=Topic,
                    message_bytes=MessageContent.bytes())

    def _shortest_path(self,start, goal): # https://www.geeksforgeeks.org/building-an-undirected-graph-and-finding-shortest-path-using-dictionaries-in-python/
        explored = []
        # Queue for traversing the graph in the _shortest_path 
        queue = [[start]]
        
        # If the desired node is reached
        if start == goal:
            print("Same Node")
            return
        
        # Loop to traverse the graph with the help of the queue
        while queue:
            path = queue.pop(0)
            node = path[-1]
            
            # Condition to check if the current node is not visited
            if node not in explored:
                neighbours = self._graph[node]
                
                # Loop to iterate over the neighbours of the node
                for neighbour in neighbours:
                    new_path = list(path)
                    new_path.append(neighbour)
                    queue.append(new_path)
                    
                    # Condition to check if the neighbour node is the goal
                    if neighbour == goal:
                        #print("Shortest path = ", *new_path)
                        return new_path
                explored.append(node)

    def _tree_creator(self, node, distance): # https://www.geeksforgeeks.org/print-all-neigbour-nodes-within-distance-k/
        tree = [[] for i in range(self._num_branches)]
        self._nearby_buses = []
        for i in range(self._num_branches):
            fro = self._graph[i][0]
            to = self._graph[i][1]
    
            tree[fro].append(to)
            tree[to].append(fro)
    
        self._dfs(distance, node, -1,tree)
    def _dfs(self,distance,node,parent,tree):
        if distance<0:
            return
        self._nearby_buses.append(node)
        for i in tree[node]:
            if i!=parent:
                self._dfs(distance-1,i,node)        

def create_component() -> NetworkStatePredictor:         # Factory function. making instance of the class
    """
    Creates and returns a NSP Component based on the environment variables.
    """
    LOGGER.info("4")
    return NetworkStatePredictor()    # the birth of the NIS object


async def start_component():
    """
    Creates and starts a SimpleComponent component.
    """
    LOGGER.info("1")
    simple_component = create_component()
    LOGGER.info("2")
    # The component will only start listening to the message bus once the start() method has been called.
    await simple_component.start()
    LOGGER.info("3")
    # Wait in the loop until the component has stopped itself.
    while not simple_component.is_stopped:
        await asyncio.sleep(TIMEOUT)


if __name__ == "__main__":
    asyncio.run(start_component())

