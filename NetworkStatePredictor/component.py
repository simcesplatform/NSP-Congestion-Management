# -*- coding: utf-8 -*-
# Copyright 2023 Tampere University.
# This software was developed as a part of doctroal studies of Mehdi Attar, funded by Fortum and Neste Foundation.
#  This source code is licensed under the MIT license. See LICENSE in the repository root directory.
# Author(s): Mehdi Attar <mehdi.attar@tuni.fi>
#            software template : Ville Heikkilä <ville.heikkila@tuni.fi>

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
RESOURCE_STATE_TOPIC1 = "ResourceState.Load.#" # wild card could be used to listen to all sub topics of resource state. i.e.:ResourceState.#
RESOURCE_STATE_TOPIC2 = "ResourceState.Generator.#" 
RESOURCE_FORECAST_TOPIC = "ResourceForecastState."

# Initialization data for power flow
POWER_FLOW_PERCISION = "POWER_FLOW_PERCISION"
MAX_ITERATION = "MAX_ITERATION"
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
TIMEOUT = 1.0

# ready made lists for further use in the code
voltage_new_node = ["voltage_new_node_1","voltage_new_node_2","voltage_new_node_3","voltage_new_node_neutral"]
voltage_old_node = ["voltage_old_node_1","voltage_old_node_2","voltage_old_node_3","voltage_old_node_neutral"]
current_node = ["current_node_1","current_node_2","current_node_3","current_node_neutral"]
power_node = ["power_node_1","power_node_2","power_node_3"]
admittance_node = ["admittance_node_1","admittance_node_2","admittance_node_3","admittance_node_neutral"]
delta_v_phase = ["delta_v_phase_1","delta_v_phase_2","delta_v_phase_3","delta_v_phase_neutral"]
current_phase = ["current_phase_1","current_phase_2","current_phase_3","current_phase_neutral"]


class NetworkStatePredictor(AbstractSimulationComponent): # the NetworkStatePredictor class inherits from AbstractSimulationComponent class
    """
    The NetworkStatePredictor (NSP) component is initialized in the beginning of the simulation by the simulation manager.
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
        and in every epoch, it calculates and publishes the network state forecasts.
        """
        super().__init__()
        LOGGER.info("6")

        # Load environmental variables for those parameters that were not given to the constructor.
        try:
            environment = load_environmental_variables(
                (POWER_FLOW_PERCISION,float, 0.001),
                (MAX_ITERATION,int,3),
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
        self._max_iteration = environment[MAX_ITERATION]
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
            RESOURCE_STATE_TOPIC1,
            RESOURCE_STATE_TOPIC2
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
        self._voltage_forecast_template = []  # template for voltage forecast messages
        self._current_forecast_template = [] # template for current forecast messages
        self._voltage_forecast = []  # list for voltage forecasts
        self._current_forecast = []  # list for current forecasts

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
        self._calculation_completed = False
        self._epoch_internal = []
        self._sending_to_receiving = {}       # to store a concatenation of sending end bus and receving end bus into one dict
        self._paths = {}   # to store the shortest path between the source bus and the bus nth. this is used to reduce the number of calling the shortest_path function.
        LOGGER.info("12")

    def clear_epoch_variables(self) -> None:
        """Clears all the variables that are used to store information about the received input within the
           current epoch. This method is called automatically after receiving an epoch message for a new epoch.
        """
        if self._epoch_internal == [] or self._epoch_internal < self._latest_epoch_message.epoch_number: # the if statement is there to only reset the values when a new epoch arrives
            self._resource_forecast_msg_counter = 0 # clearing the counter of resource forecast messages in the beginning of the current epoch
            self._resource_state_msg_counter = 0 # clearing the counter of resource state messages in the beginning of the current epoch
            self._input_data_ready = False
            self._calculation_completed = False
            self._resources_forecasts = [] # clearing the resource forecasts data in the beginning of the current epoch
            self._resource_id_logger = [0 for i in range(self._num_resources + 1)] # clearing the resource id logger in the beginning of the current epoch
            self._forecast_time_index = [] 
            self._voltage_forecast = []  
            self._current_forecast = []
            self._epoch_internal = self._latest_epoch_message.epoch_number

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
        if self._calculation_completed == True:
            LOGGER.info("calculations have already been completed!")
            return True

        if self._input_data_ready == True:
            if self._latest_epoch == 1: # the calculation of this section is only needed once in Epoch 1
                LOGGER.info("14.to reduce the computational time, Network related calculations is only done in Epoch 1")

                # setting up per unit dictionary
                self._per_unit["voltage_base"] = self._nis_bus_data.bus_voltage_base.values
                self._per_unit["s_base"] = [self._apparent_power_base for i in range(self._num_buses)]
                self._per_unit["i_base"] = abs(numpy.divide(self._per_unit["s_base"],(numpy.array(self._per_unit["voltage_base"]))*cmath.sqrt(3))) # since we have line to line voltages sqrt(3) is needed
                self._per_unit["z_base"] = [i / j for i, j in zip((1000*self._per_unit["voltage_base"]),self._per_unit["i_base"])]
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
                #LOGGER.info("self._graph is {}".format(self._graph))
                LOGGER.info("16")

                # impedances
                    # The network assumed to be symmetric. The neutral wire assumes to have a same characteristics than phase wires.
                self._branch["impedance"]=[0 for i in range(self._num_branches)]
                self._branch["impedance_angle_polar"]=[0 for i in range(self._num_branches)] 
                for i in range (self._num_branches):   
                    self._branch["impedance"][i]=complex(self._nis_component_data.resistance.values[i],self._nis_component_data.reactance.values[i])

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
                
                # sending end and receiving end bus concatenation
                for i in range (self._num_branches):
                    self._sending_to_receiving[i] = [self._nis_component_data.sending_end_bus[i],self._nis_component_data.receiving_end_bus[i]]
                #LOGGER.info("sending to receiving bus concatenation is {}".format(self._sending_to_receiving))

                # creation of a dictionary for the shortest paths
                for i in range (self._num_buses):
                    if self._nis_bus_data.bus_name[i] != self._root_bus_name:
                        self._paths[i]=self._shortest_path(self._root_bus_name,self._nis_bus_data.bus_name[i])  # in self._paths[key], the key is the index of the buses in self._nis_bus_data.bus_name 
            
            # preparing voltage and current forecast messages templates   
            LOGGER.info("17.preparing voltage and current forecast messages templates")
            for bus in range (self._num_buses): # making a list of dictionaries
                for node in range(4):  # Each bus has three nodes + neutral node
                    a = {}
                    a = {'Forecast': {'TimeIndex': ["0"],\
                    'Series': {'Magnitude': {'UnitOfMeasure': 'kV', 'Values': [0]},\
                    'Angle': {'UnitOfMeasure': 'deg', 'Values': [0]}}},\
                    'Bus': 'load', 'Node': 1}
                    a["Forecast"]["TimeIndex"] = self._forecast_time_index
                    a["Forecast"]["Series"]["Magnitude"]["Values"] = [0 for i in range(self._forecast_horizon)]
                    a["Forecast"]["Series"]["Angle"]["Values"] = [0 for i in range(self._forecast_horizon)]
                    self._voltage_forecast_template.append(a) 
        
            for branch in range (self._num_branches): # making a list of dictionaries
                for phase in range (4): # each branch has three phases + neutral phase
                    a = {}
                    a = {"Forecast" : {"TimeIndex" :["0"],\
                    "Series" :{"MagnitudeSendingEnd" :{"UnitOfMeasure" : "A","Values" :[0]},\
                    "MagnitudeReceivingEnd" :{"UnitOfMeasure" : "A","Values" :[0]},\
                    "AngleSendingEnd" :{"UnitOfMeasure" : "deg","Values" :[0]},\
                    "AngleReceivingEnd" :{"UnitOfMeasure" : "deg","Values" :[0]}}},\
                    "DeviceId" : "XYZ","Phase" : 1}
                    a["Forecast"]["TimeIndex"] = self._forecast_time_index
                    a["Forecast"]["Series"]["MagnitudeSendingEnd"]["Values"] = [0 for i in range(self._forecast_horizon)]
                    a["Forecast"]["Series"]["MagnitudeReceivingEnd"]["Values"] = [0 for i in range(self._forecast_horizon)]
                    a["Forecast"]["Series"]["AngleSendingEnd"]["Values"] = [0 for i in range(self._forecast_horizon)]
                    a["Forecast"]["Series"]["AngleReceivingEnd"]["Values"] = [0 for i in range(self._forecast_horizon)]
                    self._current_forecast_template.append(a)

            self._voltage_forecast = self._voltage_forecast_template
            self._current_forecast = self._current_forecast_template

            # setting up node dictionary for all four nodes and branches
            LOGGER.info("18.setting up node dictionary for all four nodes and branches ")
            self._resetting_lists()

            # calculate backward-forward sweep powerflow for each timestep of the forecast horizon based on https://ieeexplore.ieee.org/abstract/document/1245548
            LOGGER.info("19. starting backward forward power flow")

            for horizon in range (self._forecast_horizon): 

                power_flow_error_node=10 # 10 is a value that is way larger than the aaceptable limit to make sure that the first iteration will begin
                LOGGER.info("20. horizon is {}".format(horizon))
                LOGGER.info("mapping loads to the network nodal powers")
                # calculating nodal powers based on the power forecasts
                #LOGGER.info("resource_ids are {}".format(self._resources["ResourceId"]))
                for i in range (self._resource_forecast_msg_counter):
                    #LOGGER.info("21")
                    # finding its power
                    try:
                        temp_power = self._resources_forecasts[i].forecast.series["RealPower"].values[horizon]
                    #    LOGGER.info("temp_power is {}".format(temp_power))
                        power_per_unit = (temp_power/self._apparent_power_base) # Per unit power
                    #    LOGGER.info("power per unit is {}".format(power_per_unit))
                    except BaseException as err:
                        LOGGER.info(f"Unexpected {err=}, {type(err)=}")
                    # Finding the resourceId
                    temp_resource_id = self._resources_forecasts[i].resource_id
                    #LOGGER.info("temp_resource_id is {:s}".format(temp_resource_id))
                    
                    # finding the node that it is connected to
                    try:
                        index = self._resources["ResourceId"].index(temp_resource_id)
                    #    LOGGER.info("index is {}".format(index))    
                    except:
                        LOGGER.warning("Resource forecast has a resource id that doesnot exist in the resources messages")
                    Connected_node = self._resources["Node"][index]
                    #LOGGER.info("connected node is {}".format(Connected_node))
                    # finding the bus where the power should be added to
                    try:
                        temp_index = self._cis_customer_data.resource_id.index(temp_resource_id)
                    except:
                        LOGGER.warning("Resource forecast message has a resource id that doesnot exist in the CIS data")

                    temp_bus_name = self._cis_customer_data.bus_name[temp_index]
                    temp_row = self._nis_bus_data.bus_name.index(temp_bus_name)

                    #LOGGER.info("bus name is {}".format(temp_bus_name))

                    if Connected_node == 1:
                        self._bus["power_node_1"][temp_row] = power_per_unit + self._bus["power_node_1"][temp_row]
                    elif Connected_node == 2:
                        self._bus["power_node_2"][temp_row] = power_per_unit + self._bus["power_node_2"][temp_row]
                    elif Connected_node == 3:
                        self._bus["power_node_3"][temp_row] = power_per_unit + self._bus["power_node_3"][temp_row]
                    elif Connected_node == "three_phase":
                        power_per_unit_per_phase = power_per_unit/cmath.sqrt(3)  # calculate power per phase
                        #power_per_unit_per_phase = power_per_unit/3  # calculate power per phase
                        self._bus["power_node_1"][temp_row] = power_per_unit_per_phase + self._bus["power_node_1"][temp_row]
                        self._bus["power_node_2"][temp_row] = power_per_unit_per_phase + self._bus["power_node_2"][temp_row]
                        self._bus["power_node_3"][temp_row] = power_per_unit_per_phase + self._bus["power_node_3"][temp_row]

                    #LOGGER.info("Power at node 1 is {}".format(self._bus["power_node_1"])) 
                    #LOGGER.info("Power at node 2 is {}".format(self._bus["power_node_2"])) 
                    #LOGGER.info("Power at node 3 is {}".format(self._bus["power_node_3"]))
                #    LOGGER.info("22") 
            #    LOGGER.info("Power at node 1 is {}".format(self._bus["power_node_1"])) 

                iteration = 0    # Number of sweeps in the power flow
                while power_flow_error_node > self._power_flow_percision and iteration < self._max_iteration: # stop power flow when enough accuracy of voltages reached                    
                    
                    # calculating nodal currents
                    iteration = iteration+1
                    LOGGER.info("23. iteration is {}".format(iteration))
                    LOGGER.info("23.1 calculation of nodal currents")
                    for bus in range (self._num_buses): 
                    #    LOGGER.info("bus is {}".format(bus))
                        for node in range (0,3):   # for each phase
                            voltage_difference = self._bus[voltage_old_node[node]][bus] - self._bus["voltage_old_node_neutral"][bus]
                            self._bus[current_node[node]][bus] = numpy.conj(self._bus[power_node[node]][bus]/voltage_difference) # I*=P/V
                        self._bus["current_node_neutral"][bus]=-(self._bus["current_node_1"][bus]+self._bus["current_node_2"][bus]+self._bus["current_node_3"][bus])

                    for bus in range(self._num_buses): # taking into account line admittances
                        for node in range (0,4):
                            self._bus[current_node[node]][bus] = self._bus[current_node[node]][bus]-(self._bus[admittance_node[node]][bus]*self._bus[voltage_old_node[node]][bus])


                #    LOGGER.info("Current at node 1 is {}".format(self._bus[current_node[0]]))
                    #LOGGER.info("Current at node 2 is {}".format(self._bus[current_node[1]]))
                    #LOGGER.info("Current at node 3 is {}".format(self._bus[current_node[2]]))
                    #LOGGER.info("Current at node neutral is {}".format(self._bus[current_node[3]])) 

                    # calculating branch currents
                    LOGGER.info("24 calculation of branch currents. backward sweep")

                    for i in range (self._num_buses):
                        if abs(self._bus[current_node[0]][i])>0.0001 or abs(self._bus[current_node[1]][i])>0.0001 or abs(self._bus[current_node[2]][i])>0.0001:  # calculation is only done for buses with a non negligable load
                        #    LOGGER.info("i is {}".format(i))
                        #    LOGGER.info("bus name is {}".format(self._nis_bus_data.bus_name[i]))
                            shortest_path = self._paths[i]
                            #LOGGER.info("shortest path is {}".format(shortest_path))

                            for j in range (self._num_branches):
                                from_bus = self._nis_component_data.sending_end_bus[j]
                                to_bus = self._nis_component_data.receiving_end_bus[j]
                                try:
                                    shortest_path.index(from_bus)    # we want to know where the bus value exist in the shortest path or not
                                    shortest_path.index(to_bus)
                                #    LOGGER.info("from bus is {}".format(from_bus))
                                #    LOGGER.info("to bus is {}".format(to_bus))
                                #    LOGGER.info("the row was found number{}".format(j))
                                #    LOGGER.info("the nodal current is {}".format(self._bus[current_node[0]][i]))
                                    for phases in range (0,4):
                                        self._branch[current_phase[phases]][j] = self._bus[current_node[phases]][i] + self._branch[current_phase[phases]][j]
                                #    LOGGER.info("branch current is {}".format(self._branch[current_phase[0]]))
                                except:
                                    pass    
                    
                #    LOGGER.info("the branch current at phase 1 for the new method is {}".format(self._branch[current_phase[0]]))        
                    
                #    LOGGER.info("25")
                #    LOGGER.info("the branch current at phase 1 is {}".format(self._branch[current_phase[0]]))
                #    LOGGER.info("the branch current at phase 2 is {}".format(self._branch[current_phase[1]]))
                #    LOGGER.info("the branch current at phase 3 is {}".format(self._branch[current_phase[2]]))
                #    LOGGER.info("the branch current at phase neutral is {}".format(self._branch[current_phase[3]]))

                    # calculating the voltage drop over each branch
                    LOGGER.info("25 calculation of voltage drop over each branch")
                    for row in range (self._num_branches):
                        for kk in range (0,4):
                            self._branch[delta_v_phase[kk]][row] = -(self._branch[current_phase[kk]][row] * self._branch["impedance"][row]) # we add negative here becasue P consumption is assumed to be negative and p production is positive. Also only we assume that branch impedances are symmetric.
                    #        LOGGER.info("delta v is {}".format(self._branch[delta_v_phase[kk]][row]))

                #    LOGGER.info("the voltage drop at phase 1 is {}".format(self._branch[delta_v_phase[0]]))
                #    LOGGER.info("the voltage drop at phase 2 is {}".format(self._branch[delta_v_phase[1]]))
                #    LOGGER.info("the voltage drop at phase 3 is {}".format(self._branch[delta_v_phase[2]]))
                #    LOGGER.info("the voltage drop at phase neutral is {}".format(self._branch[delta_v_phase[3]]))
                    zero_avail = {}
                    zero_avail = self._bus["voltage_new_node_1"] + self._bus["voltage_new_node_2"] + self._bus["voltage_new_node_3"]  
                    zero_avail_num = zero_avail.count(0)
                    #LOGGER.info("the number of 0 voltages are {}".format(zero_avail_num))
                    
                    # calculating the new voltages
                    LOGGER.info("26. calculating the new voltages. forward sweep")

                    while zero_avail_num != 0:
                    #    LOGGER.info("the new voltage for the node neutral is {}".format(self._bus["voltage_new_node_neutral"]))
                        for bus in range (self._num_buses):
                            node = 0
                            if self._bus[voltage_new_node[node]][bus] == 0:
                                bus_name = self._nis_bus_data.bus_name[bus]
                                nearby_buses=self._graph[bus_name]
                                length = len(nearby_buses)
                    #            LOGGER.info("Bus Name is {}".format(bus_name))
                    #            LOGGER.info("Nearby buses are {}".format(nearby_buses))
                    #            LOGGER.info("length of nearby buses is {}".format(length))
                                if length > 0:
                                    for a in range (length):
                                        index = self._nis_bus_data.bus_name.index(nearby_buses[a])
                    #                    LOGGER.info("Bus Name index is {}".format(index))
                                        if abs(self._bus[voltage_new_node[node]][index]) > 0.1:
                    #                        LOGGER.info("the existing voltage is {}".format(self._bus[voltage_new_node[node]][index]))
                                            to_bus = nearby_buses[a]
                                            from_bus = bus_name
                    #                        LOGGER.info("to bus is {}".format(to_bus))
                    #                        LOGGER.info("from bus is {}".format(from_bus))
                                            branch = [from_bus,to_bus]
                                            branch1 = [to_bus,from_bus]

                                            shortest_path1 = self._paths[self._nis_bus_data.bus_name.index(from_bus)]

                                            try:
                                                shortest_path2 = self._paths[index]
                                            except:
                                                shortest_path2 = None   

                                            if shortest_path2 == None: # if it is source bus
                                                shortest_path2_length = 0
                                            else:
                                                shortest_path2_length = len(shortest_path2)
                                            
                                            try:
                                                row=list(self._sending_to_receiving.keys())[list(self._sending_to_receiving.values()).index(branch)]
                                            except:
                                                row=list(self._sending_to_receiving.keys())[list(self._sending_to_receiving.values()).index(branch1)]
                #                            LOGGER.info("the row is {}".format(row))
                                            if len(shortest_path1) > shortest_path2_length:
                                                for node in range (0,4):
            #                                        LOGGER.info("voltage is reduced as much as {}".format(self._branch[delta_v_phase[node]][row]))
            #                                        LOGGER.info("voltage before change is {}".format(self._bus[voltage_new_node[node]][bus]))
                                                    self._bus[voltage_new_node[node]][bus] = self._bus[voltage_new_node[node]][index] - self._branch[delta_v_phase[node]][row]
            #                                        LOGGER.info("voltage after change is {}".format(self._bus[voltage_new_node[node]][bus]))

                                            else:
                                                for node in range (0,4):
            #                                        LOGGER.info("voltage is increased as much as {}".format(self._branch[delta_v_phase[node]][row]))
            #                                        LOGGER.info("voltage before change is {}".format(self._bus[voltage_new_node[node]][bus]))
                                                    self._bus[voltage_new_node[node]][bus] = self._bus[voltage_new_node[node]][index] + self._branch[delta_v_phase[node]][row]
            #                                        LOGGER.info("voltage after change is {}".format(self._bus[voltage_new_node[node]][bus]))
                                            break

                        zero_avail = {}
                        zero_avail = self._bus["voltage_new_node_1"] # + self._bus["voltage_new_node_2"] + self._bus["voltage_new_node_3"]
                        zero_avail_num = zero_avail.count(0)
                        LOGGER.info("zero available is {}".format(zero_avail_num))

                    LOGGER.info("the voltage at phase 1 is {}".format(self._bus["voltage_new_node_1"]))

                    error = [0 for i in range(self._num_buses)]
                    for w in range (self._num_buses): # calculate the error only for node 1    
                        error[w] = abs(self._bus["voltage_old_node_1"][w]-self._bus["voltage_new_node_1"][w])
                    
                    LOGGER.info("error was calculated")
                    power_flow_error_node=max(error)
                    LOGGER.info("the maximum error is {}".format(abs(power_flow_error_node)))

                    if power_flow_error_node > self._power_flow_percision and iteration < self._max_iteration:
                        for p in range (4): # clear values for a fresh start
                            self._bus[voltage_old_node[p]]=self._bus[voltage_new_node[p]]
                            self._bus[voltage_new_node[p]]=[0 for i in range(self._num_buses)]
                            self._bus[current_node[p]] = [0 for i in range(self._num_buses)]
                            self._branch[current_phase[p]] = [0 for i in range(self._num_branches)]
                            self._branch[delta_v_phase[p]] = [0 for i in range(self._num_branches)]
                        self._bus["voltage_new_node_1"][self._root_bus_index] = self._root_bus_voltage
                        self._bus["voltage_new_node_2"][self._root_bus_index] = cmath.rect(self._root_bus_voltage,4*math.pi/3)
                        self._bus["voltage_new_node_3"][self._root_bus_index] = cmath.rect(self._root_bus_voltage,2*math.pi/3)

                else:
                    
                    LOGGER.info("27.1 power flow is accurate enough or the max iteration number is reached")
                #    LOGGER.info("voltage new for node 1 is : {}".format(self._bus["voltage_new_node_1"]))
                #    LOGGER.info("voltage new for node 2 is : {}".format(self._bus["voltage_new_node_2"]))
                #    LOGGER.info("voltage new for node 3 is : {}".format(self._bus["voltage_new_node_3"]))
                #    LOGGER.info("voltage new for node neutral is : {}".format(self._bus["voltage_new_node_neutral"]))

                    # storing voltage values as a result of power flow
                    LOGGER.info("28 storing the voltage values")
                    for bus in range (self._num_buses):
                        bus_name=self._nis_bus_data.bus_name[bus]
                #        LOGGER.info("bus name is : {}".format(bus_name))
                        voltage_base = self._nis_bus_data.bus_voltage_base.values[bus]
                #        LOGGER.info("voltage base is : {}".format(voltage_base))
                        for node in range (0,4):
                            row = bus*4 + node
                            voltage = self._bus[voltage_new_node[node]][bus]
                            [absolute,angle] = cmath.polar(voltage*voltage_base)
                            self._voltage_forecast[row]["Forecast"]["Series"]["Magnitude"]["Values"][horizon] = absolute
                            self._voltage_forecast[row]["Forecast"]["Series"]["Angle"]["Values"][horizon] = angle*57.29    # radian to degree (360/(2*3.1415))=57.29
                            self._voltage_forecast[row]["Bus"] = bus_name
                            if node < 3:
                                self._voltage_forecast[row]["Node"] = node+1
                            else:
                                self._voltage_forecast[row]["Node"] = "neutral"
                    
                    LOGGER.info("28.1 storing the current values")
                    for branch in range (self._num_branches):
                        device_id = self._nis_component_data.device_id[branch]
                        sending_end_bus = self._nis_component_data.sending_end_bus[branch]
                        index = self._nis_bus_data.bus_name.index(sending_end_bus)
                        voltage_base = self._nis_bus_data.bus_voltage_base.values[index]
                        s_base = []
                        s_base = self._per_unit["s_base"]
                    #    LOGGER.info("s base is : {}".format(s_base))
                        current_base = [x / ((voltage_base)*cmath.sqrt(3)) for x in s_base]
                #        LOGGER.info("device id is : {}".format(device_id))
                #        LOGGER.info("voltage base is : {}".format(voltage_base))
                #        LOGGER.info("current base is : {}".format(current_base))
                        for phase in range (0,4):
                            row = branch*4 + phase
                            current = self._branch[current_phase[phase]][branch]
                            [absolute,angle] = cmath.polar(current*current_base[0])
                            self._current_forecast[row]["Forecast"]["Series"]["MagnitudeSendingEnd"]["Values"][horizon] = absolute
                            self._current_forecast[row]["Forecast"]["Series"]["MagnitudeReceivingEnd"]["Values"][horizon] = absolute
                            self._current_forecast[row]["Forecast"]["Series"]["AngleSendingEnd"]["Values"][horizon] = angle
                            self._current_forecast[row]["Forecast"]["Series"]["AngleReceivingEnd"]["Values"][horizon] = angle
                            self._current_forecast[row]["DeviceId"] = device_id 
                            if phase < 3:
                                self._current_forecast[row]["Phase"] = phase+1
                            else:
                                self._current_forecast[row]["Phase"] = "neutral"
                    # Getting ready for power flow of a new timestep

                    self._resetting_lists()

            #LOGGER.info("the final voltage forecast is {}".format(self._voltage_forecast))
            # when power flow is done for all time steps
            LOGGER.info("29. All Power flows are done")

            q = 0
            for p in range (0,len(self._voltage_forecast)):
                if type(self._voltage_forecast[p]["Node"]) == int: # we donot need to send the voltage values for the neutral nodes
                    voltage_message = self._message_generator.get_message(
                    ForecastStateMessageVoltage,
                    EpochNumber = self._latest_epoch,
                    TriggeringMessageIds = self._triggering_message_ids,
                    Forecast = self._voltage_forecast[p]["Forecast"],
                    Bus = self._voltage_forecast[p]["Bus"],
                    Node = self._voltage_forecast[p]["Node"])

                    voltage_topic = self._voltage_forecast_topic + self._voltage_forecast[p]["Bus"]
                    
                    q = q+1
                    LOGGER.info("voltage sent is {}".format(q))
                    await self._send_message(voltage_message, voltage_topic)
            
            q = 0
            for n in range (0,len(self._current_forecast)):
                if type(self._current_forecast[n]["Phase"]) == int:  # we donot need to send the current values for the neutral wire
                    current_message = self._message_generator.get_message(
                    ForecastStateMessageCurrent,
                    EpochNumber = self._latest_epoch,
                    TriggeringMessageIds = self._triggering_message_ids,
                    Forecast = self._current_forecast[n]["Forecast"],
                    DeviceId = self._current_forecast[n]["DeviceId"],
                    Phase = self._current_forecast[n]["Phase"])

                    current_topic = self._current_forecast_topic + self._current_forecast[n]["DeviceId"]

                    q = q+1
                    LOGGER.info("current sent is {}".format(q))
                    await self._send_message(current_message, current_topic)
            LOGGER.info("all forecasts were successfully sent")
            self._calculation_completed = True
            return True  # return True to indicate that the component is finished with the current epoch
        else:
            LOGGER.info("input data arenot complete")
            return False # return False to indicate that the component is not finished with the current epoch

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
            #LOGGER.info("Received {:s} message from topic {:s}".format(
            #    message_object.message_type, message_routing_key))
            self._resource_forecast_message_handler(message_object)

        # Resource state
        elif isinstance(message_object,ResourceStateMessage):
            message_object = cast(ResourceStateMessage,message_object)
            self._resource_state_msg_counter = self._resource_state_msg_counter+1

            LOGGER.info("Received {}".format(self._resource_state_msg_counter))

        #    LOGGER.info("Received {:s} message from topic {:s}".format(
        #        message_object.message_type, message_routing_key))
            
            self._resources["CustomerId"][self._resource_state_msg_counter] = message_object.customerid

            index = message_routing_key.index(".",14)                    # 'ResourceState.Load.load41' resource state has 13 characters. so if we find the index of the second ".", then we can find the resource id
        #    LOGGER.info("the resource id is {}".format(message_routing_key[index+1:len(message_routing_key)]))
            self._resources["ResourceId"][self._resource_state_msg_counter] = message_routing_key[index+1:len(message_routing_key)]
        #    LOGGER.info("Resourceid is {:s}".format(self._resources["ResourceId"][self._resource_state_msg_counter]))

            if  message_object.node in range (1,4):
                self._resources["Node"][self._resource_state_msg_counter]=message_object.node
            #    LOGGER.info("there is node 1 or 2 or 3")
            else:
                self._resources["Node"][self._resource_state_msg_counter]="three_phase"
            #    LOGGER.info("it is three phase")

        # NIS bus
        elif isinstance(message_object,NISBusMessage) and self._latest_epoch == 1: # NIS data is only published in the first epoch
            message_object = cast(NISBusMessage,message_object)
            #LOGGER.info("Received {:s} message from topic {:s}".format(
            #    message_object.message_type, message_routing_key))
            self._nis_bus_data = message_object
            self._num_buses = len(self._nis_bus_data.bus_name)
            self._root_bus_index = self._nis_bus_data.bus_type.index("root")
            self._root_bus_name = self._nis_bus_data.bus_name[self._root_bus_index] # name of the root bus

            LOGGER.info("NISBusMessage was received")
            self._nis_bus_data_received = True

        # NIS component
        elif isinstance(message_object,NISComponentMessage) and self._latest_epoch == 1: # NIS data is only published in the first epoch
            message_object = cast(NISComponentMessage,message_object)
            #LOGGER.info("Received {:s} message from topic {:s}".format(
            #    message_object.message_type, message_routing_key))
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
            #LOGGER.info("Received {:s} message from topic {:s}".format(
            #    message_object.message_type, message_routing_key))
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
                await self.start_epoch()
    
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
        #    print("Same Node")
            pass
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

    def _resetting_lists(self):
        for node in range (3):
                self._bus[power_node[node]] = [0 for i in range(self._num_buses)]
        
        for node in range (4):
            self._bus[voltage_old_node[node]] = [0 for i in range(self._num_buses)]
            self._bus[voltage_new_node[node]] = [0 for i in range(self._num_buses)]
        self._bus["voltage_new_node_1"][self._root_bus_index] = self._root_bus_voltage
        self._bus["voltage_new_node_2"][self._root_bus_index] = cmath.rect(self._root_bus_voltage,4*math.pi/3)
        self._bus["voltage_new_node_3"][self._root_bus_index] = cmath.rect(self._root_bus_voltage,2*math.pi/3)

        for bus in range (self._num_buses):
            self._bus["voltage_old_node_1"][bus] = self._root_bus_voltage
            self._bus["voltage_old_node_2"][bus] = cmath.rect(self._root_bus_voltage,4*math.pi/3)
            self._bus["voltage_old_node_3"][bus] = cmath.rect(self._root_bus_voltage,2*math.pi/3)
            self._bus["voltage_old_node_neutral"][bus] = 0

        for node in range(4):
            self._bus[current_node[node]] = [0 for i in range(self._num_buses)]
            self._branch[current_phase[node]] = [0 for i in range(self._num_branches)]
            self._branch[delta_v_phase[node]] = [0 for i in range(self._num_branches)]
        #LOGGER.info("the old bus voltage is {}".format(self._bus["voltage_old_node_1"]))
        #LOGGER.info("the new bus voltage is {}".format(self._bus["voltage_new_node_1"]))
        return True
        


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

