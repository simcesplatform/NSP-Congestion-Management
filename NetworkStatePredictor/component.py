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
from tools.messages import BaseMessage
from tools.tools import FullLogger, load_environmental_variables
from collections import defaultdict
import cmath
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
POWER_FLOW_PERCISION = 0.001 # default power flow percision is 0.001 p.u.
APPARENT_POWER_BASE = 10000 # default apparent power is 10000 kW
ROOT_BUS_VOLTAGE = 1.02 # default root bus voltage (primary substation voltage) is 1.02 p.u.

# Forecast
FORECAST_HORIZON = 36 # default forecast horizon
# Resources
NUM_OF_RESOURCES = 0 
RESOURCE_CATEGORIES = "RESOURCE_CATEGORIES"
# Grid id
GRID_ID = "GRID_ID" # name of the grid 
# time interval in seconds on how often to check whether the component is still running
TIMEOUT = 2.0
# ready made lists for further use in the code
voltage_new_node = ["voltage_new_node_1","voltage_new_node_2","voltage_new_node_3"]
voltage_old_node = ["voltage_old_node_1","voltage_old_node_2","voltage_old_node_3"]
current_node = ["current_node_1","current_node_2","current_node_3"]
power_node = ["power_node_1","power_node_2","power_node_3"]
delta_v_phase = ["delta_v_phase_1","delta_v_phase_2","delta_v_phase_3"]
current_phase = ["current_phase_1","current_phase_2","current_phase_3"]




class NetworkStatePredictor(AbstractSimulationComponent): # the NetworkStatePredictor class inherits from AbstractSimulationComponent class
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
    # Constructor
    def __init__(self):
        """
        The NSP component is initiated in the beginning of the simulation by the simulation manager
        and in every epoch, it calculates and publishes the network state forecast.
        """
        super().__init__()

        # Load environmental variables for those parameters that were not given to the constructor.

        environment = load_environmental_variables(
            (POWER_FLOW_PERCISION, float, 0.001),
            (APPARENT_POWER_BASE,float,10000),
            (ROOT_BUS_VOLTAGE,float,1.02),
            (FORECAST_HORIZON,int,36),
            (NUM_OF_RESOURCES,int),
            (GRID_ID,str),
            (RESOURCE_CATEGORIES,str))

        # publishing to topics

        self._power_flow_percision = environment[POWER_FLOW_PERCISION]
        self._apparent_power_base = environment[APPARENT_POWER_BASE]
        self._root_bus_voltage = environment[ROOT_BUS_VOLTAGE]
        self._forecast_horizon = environment[FORECAST_HORIZON]
        self._num_resources = environment[NUM_OF_RESOURCES] # resources including loads, generations and storages
        self._grid_id = environment[GRID_ID]
        self._resource_categories = environment[RESOURCE_CATEGORIES]

        self._voltage_forecast_topic="NetworkForecastState."+self._grid_id+".Voltage."  # according to documentation: https://simcesplatform.github.io/energy_topics/
        self._current_forecast_topic="NetworkForecastState."+self._grid_id+".Current."

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

        
        # for incoming messages
        self._nis_bus_data = {}       # Dict for NIS data
        self._nis_component_data = {}  # Dict for NIS data
        self._cis_customer_data = {}   # Dict for CIS data
        self._resources_forecasts=[]  # List for incoming forecast data
        self._resources = {} # List for components' resources
        self._resources["BusName"] = [0 for i in range(self._num_resources)]
        self._resources["Node"] = [0 for i in range(self._num_resources)]
        self._resources["ResourceId"] = [0 for i in range(self._num_resources)]

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

        self._resource_forecast_msg_counter=0
        self._resource_state_msg_counter=0
        self._nis_bus_data_received=False
        self._nis_component_data_received=False
        self._cis_data_received=False


    def clear_epoch_variables(self) -> None:
        """Clears all the variables that are used to store information about the received input within the
           current epoch. This method is called automatically after receiving an epoch message for a new epoch.
        """
        self._resource_forecast_msg_counter = 0 # clearing the counter of resource forecast messages in the beginning of the current epoch
        self._resource_state_msg_counter = 0 # clearing the counter of resource state messages in the beginning of the current epoch
        self._resources_forecasts = [] # clearing the resource forecasts data in the beginning of the current epoch
        self._resource_id_logger = [] # clearing the resource id logger in the beginning of the current epoch
        self._forecast_time_index = [] 
        self._voltage_forecast = []  
        self._current_forecast = []

        self._resources["BusName"] = [0 for i in range(self._num_resources)] # clearing the resource messages
        self._resources["Node"] = [0 for i in range(self._num_resources)]
        self._resources["ResourceId"] = [0 for i in range(self._num_resources)]

        LOGGER.info("Input parameters cleared for epoch {:d}".format(self._latest_epoch_message.epoch_number))
        


    async def process_epoch(self) -> bool:
        """
        Process the epoch and do all the required calculations.
        Returns False, if processing the current epoch was not yet possible.
        Otherwise, returns True, which indicates that the epoch processing was fully completed.
        This also indicated that the component is ready to send a Status Ready message to the Simulation Manager.
        """
        input_data_ready = False
        if self._resource_forecast_msg_counter == self._num_resources and self._nis_bus_data_received==True and \
            self._nis_component_data_received==True and self._cis_data_received==True and \
            self._resource_state_msg_counter == self._num_resources:
            input_data_ready = True
        if input_data_ready == True:
            if self.process_epoch == 1: # the calculation of this section is only needed once in Epoch 1
                
                # setting up per unit dictionary

                self._per_unit["voltage_base"] = self._nis_bus_data["BusVoltageBase"]["Values"]
                self._per_unit["s_base"] = [self._apparent_power_base for i in range(self._num_buses)]
                self._per_unit["i_base"] = abs(self._per_unit["s_base"]/(numpy.array(self._per_unit["voltage_base"]))*cmath.sqrt(3)) # since we have line to line voltages sqrt(3) is needed
                self._per_unit["z_base"] = [i / j for i, j in zip(self._per_unit["voltage_base"],self._per_unit["i_base"])]
            
                # creating a graph according to the network topology of NIS data

                edges=[]
                for i in range (self._num_branches):
                    list_1 = [self._nis_component_data["SendingEndBus"][i],self._nis_component_data["ReceivingEndBus"][i]]
                    edges.append(list_1)
                graph = defaultdict(list)
                for edge in edges:
                    a, b = edge[0], edge[1]
                    graph[a].append(b)
                    graph[b].append(a)
                self._graph = graph

                # impedances
                # The network assumed to be symmetric.

                self._branch["impedance_length_polar"]=[0 for i in range(self._num_branches)]
                self._branch["impedance_angle_polar"]=[0 for i in range(self._num_branches)]
                for i in range (self._num_branches):
                    w=complex(self._nis_component_data["Resistance"][i],self._nis_component_data["Reactance"][i])
                    [Abs,Angle]=cmath.polar(w)
                    self._branch["impedance_length_polar"][i]=Abs
                    self._branch["impedance_angle_polar"][i]=Angle

                # preparing the blank voltage and current forecast messages

                self._voltage_forecast_template={'Forecast': {'TimeIndex': ["0"],\
                'Series': {'Magnitude': {'UnitOfMeasure': 'kV', 'Values': [0]},\
                'Angle': {'UnitOfMeasure': 'deg', 'Values': [0]}},\
                'Bus': 'load', 'Node': 1}}
                self._voltage_forecast_template["Forecast"]["TimeIndex"]=self._forecast_time_index
                self._voltage_forecast_template["Forecast"]["Series"]["Magnitude"]["Values"]=[0 for i in range(self._forecast_horizon)]
                self._voltage_forecast_template["Forecast"]["Angle"]["Values"]=[0 for i in range(self._forecast_horizon)]

                self._current_forecast_template={"Forecast" : {"TimeIndex" :["0"],\
                "Series" :{"MagnitudeSendingEnd" :{"UnitOfMeasure" : "A","Values" :[0]},\
                "MagnitudeReceivingEnd" :{"UnitOfMeasure" : "A","Values" :[0]},\
                "AngleSendingEnd" :{"UnitOfMeasure" : "deg","Values" :[0]},\
                "AngleReceivingEnd" :{"UnitOfMeasure" : "deg","Values" :[0]}}},\
                "DeviceId" : "XYZ","Phase" : 1}
                self._current_forecast_template["Forecast"]["TimeIndex"]=self._forecast_time_index
                self._current_forecast_template["Forecast"]["Series"]["MagnitudeSendingEnd"]["Values"]=[0 for i in range(self._forecast_horizon)]
                self._current_forecast_template["Forecast"]["Series"]["MagnitudeReceivingingEnd"]["Values"]=[0 for i in range(self._forecast_horizon)]
                self._current_forecast_template["Forecast"]["Series"]["AngleSendingEnd"]["Values"]=[0 for i in range(self._forecast_horizon)]
                self._current_forecast_template["Forecast"]["Series"]["AngleReceivingEnd"]["Values"]=[0 for i in range(self._forecast_horizon)]
            else:    

                # setting up branch dictionary

                self._branch["current_phase_1"] = [0 for i in range(self._num_branches)]
                self._branch["delta_v_phase_1"] = [0 for i in range(self._num_branches)]

                self._branch["current_phase_2"] = [0 for i in range(self._num_branches)]
                self._branch["delta_v_phase_2"] = [0 for i in range(self._num_branches)]
                
                self._branch["current_phase_3"] = [0 for i in range(self._num_branches)]
                self._branch["delta_v_phase_3"] = [0 for i in range(self._num_branches)]

                # setting up node dictionary for all three nodes

                for node in range (2):
                    self._bus[current_node[node]] = [0 for i in range(self._num_buses)]
                    self._bus[power_node[node]] = [0 for i in range(self._num_buses)]
                    self._bus[voltage_old_node[node]] = [1 for i in range(self._num_buses)]
                    self._bus[voltage_old_node[node]][self._root_bus_index] = self._root_bus_voltage # fixing the root bus voltage
                    self._bus[voltage_new_node[node]] = [0 for i in range(self._num_buses)]
                    self._bus[voltage_new_node[node]][self._root_bus_index] = self._root_bus_voltage # fixing the root bus voltage

                # Duplicaiton of the template of voltage and current forecasts, ready to be filled when power flow is done

                for duplication in range (self._num_buses):
                    for nodes_num in range(3):  # Each bus has three nodes
                        self._voltage_forecast.append(self._voltage_forecast_template)
                for duplication in range (self._num_branches):
                    for phases_num in range (3): # each branch has three phases
                        self._current_forecast.append(self._current_forecast_template)
                
                # calculate backward-forward sweep powerflow for each timestep of the forecast horizon

                for horizon in range (self._forecast_horizon): 
                    power_flow_error_node_1=[]
                    for w in range (self._num_buses): # calculate the error only for node 1
                        power_flow_error_node_1[w]=abs(self._bus["voltage_old_node_1"][w]-self._bus["voltage_new_node_1"][w])
                    
                    for s in range (2):  # set the voltage new as 1 for all buses
                        self._bus[voltage_new_node[s]] = [1 for i in range(self._num_buses)]
                        self._bus[voltage_new_node[s]][self._root_bus_index] = self._root_bus_voltage # fixing the root bus voltage

                    while max(power_flow_error_node_1) > self._power_flow_percision: # stop power flow when enough accuracy of voltages reached
                        for p in range (3): # clear values for a fresh start
                            self._bus[voltage_old_node[p]]=self._bus[voltage_new_node[p]]
                            self._bus[voltage_new_node[p]]=[0 for i in range(self._num_buses)]
                            self._bus[voltage_new_node[p]][self._root_bus_index] = self._root_bus_voltage
                            self._bus[current_node[p]] = [0 for i in range(self._num_buses)]
                            self._bus[power_node[p]]=[0 for i in range(self._num_buses)]
                            self._branch[current_phase[p]] = [0 for i in range(self._num_branches)]
                            self._branch[delta_v_phase[p]] = [0 for i in range(self._num_branches)]

                        for i in range (self._resource_forecast_msg_counter): # calculating nodal powers
                            temp_forecast = self._resources_forecasts[i]

                            # finding its power

                            temp_power = temp_forecast["Forecast"]["Series"]["RealPower"]["Values"][horizon] # temp_power in kW
                            
                            # finding the node that it is connected to
                            
                            temp_resource_id = temp_forecast["ResourceId"]
                            try:
                                index = self._resources["ResourceId"].index(temp_resource_id)
                            except:
                                LOGGER.warning("Resource forecast has a resource id that doesnot exist in the resources messages {}".format(temp_forecast.MessageId))
                            node_value = self._resources["Node"][index]

                            # finding the bus (its location what means its row) where the power should be added to
                            
                            try:
                                temp_index = self._cis_customer_data["ResourceId"].index(temp_resource_id)
                            except:
                                LOGGER.warning("Resource forecast message {} has a resource id that doesnot exist in the CIS data".format(temp_forecast.MessageId))

                            temp_bus_name = self._cis_customer_data["BusName"][temp_index]
                            temp_row = self._nis_bus_data["BusName"].index(temp_bus_name)
                            
                            power_per_unit = (temp_power/self._apparent_power_base) # power in per unit
                            if node_value == 1:
                                self._bus["power_node_1"][temp_row] = power_per_unit + self._bus["power_node_1"][temp_row]
                            elif node_value == 2:
                                self._bus["power_node_2"][temp_row] = power_per_unit + self._bus["power_node_2"][temp_row]
                            elif node_value == 3:
                                self._bus["power_node_3"][temp_row] = power_per_unit + self._bus["power_node_3"][temp_row]
                            elif node_value == "three_phase":
                                power_per_unit_per_phase = power_per_unit/cmath.sqrt(3)  # calculate power per phase
                                self._bus["power_node_1"][temp_row] = power_per_unit_per_phase + self._bus["power_node_1"][temp_row]
                                self._bus["power_node_2"][temp_row] = power_per_unit_per_phase + self._bus["power_node_2"][temp_row]
                                self._bus["power_node_3"][temp_row] = power_per_unit_per_phase + self._bus["power_node_3"][temp_row]

                        for i in range (self._num_buses): # calculating nodal currents
                            for f in range (0,3):
                                self._bus[current_node[f]] = [i / j for i, j in zip(self._bus[power_node[f]],self._bus[voltage_old_node[f]])]

                        for i in range (self._num_branches):  # calculating branch currents
                            from_bus = self._nis_component_data["SendingEndBus"][i]
                            to_bus = self._nis_component_data["ReceivingEndBus"][i]
                            buses_list = []
                            buses_list.append(from_bus)
                            buses_list.append(to_bus)
                            buses_list = set(buses_list)
                            for j in range (self._num_buses):
                                shortest_path = self._shortest_path(self._root_bus_name,self._nis_bus_data["BusName"][j])
                                if len(buses_list.intersection(shortest_path)) == 2: # current passes through the branch
                                    for phases in range (0,3):
                                        self._branch[current_phase[phases]][i] = self._bus[current_node[phases]][j] + self._branch[current_phase[phases]][i]
                        
                        for row in range (self._num_branches): # calculating the voltage drop over each branch
                            for kk in range (0,3):
                                self._branch[delta_v_phase[kk]][row] = self._branch[current_phase[kk]][row] * self._branch["impedance_length_polar"][row]

                        voltage_node_1 = []
                        voltage_node_2 = []
                        voltage_node_3 = []
                        voltage_node_1.append(self._bus["voltage_new_node_1"])
                        voltage_node_2.append(self._bus["voltage_new_node_2"])
                        voltage_node_3.append(self._bus["voltage_new_node_2"])
                        zero_avail_node_1 = voltage_node_1.count(0)
                        zero_avail_node_2 = voltage_node_2.count(0)
                        zero_avail_node_3 = voltage_node_3.count(0)
                        zero_availibility = [zero_avail_node_1,zero_avail_node_2,zero_avail_node_3]
                        
                        for ii in range (0,3):
                            zero_avail = zero_availibility[ii]
                            while zero_avail != 0: # calculating the new voltages
                                for node in range (self._num_buses):

                                    if self._bus[voltage_new_node[ii]][node] == 0:
                                        bus_name = self._nis_bus_data["BusName"][node]
                                        self._tree_creator(bus_name,1) # It finds the neighbouring buses
                                        num_nearby_buses = len(self._nearby_buses)
                                        if num_nearby_buses > 0:
                                            for a in range (num_nearby_buses):
                                                if self._bus[voltage_new_node[ii]][self._nearby_buses[a]] > 0:
                                                    from_bus = self._nearby_buses[a]
                                                    to_bus = bus_name
                                                    branch = [from_bus,to_bus]
                                                    branch1 = [to_bus,from_bus]
                                                    for b in range (self._num_branches):
                                                        if self._graph[b] == branch or self._graph[b] == branch1:
                                                            row = b
                                                            break
                                                    self._bus[voltage_new_node[ii]][node] = self._bus[voltage_new_node[ii]][self._nearby_buses[a]] - (self._branch[current_phase[ii]][row]*self._branch["impedance_length_polar"][row])
                                                    break                                
                                zero_avail = self._bus[voltage_new_node[ii]].count(0)
                        for w in range (self._num_buses): # calculate the error only for node 1
                            power_flow_error_node_1[w] = abs(self._bus["voltage_old_node_1"][w]-self._bus["voltage_new_node_1"][w])
                    else:
                        
                        # storing voltage values as a result of power flow
                        for bus in range (self._num_buses):
                            bus_name=self._nis_bus_data["BusName"][bus]
                            for node in range (1,4):
                                row = bus*3 + node
                                self._voltage_forecast[row]["Forecast"]["Series"]["Magnitude"]["Values"][horizon] = self._bus[voltage_new_node[node-1]][bus]
                                self._voltage_forecast[row]["Forecast"]["Series"]["Angle"]["Values"][horizon] = 0    # Later add angle here
                                self._voltage_forecast[row]["Forecast"]["Bus"] = bus_name
                                self._voltage_forecast[row]["Forecast"]["Node"] = node
                        
                        for branch in range (self._num_branches):
                            device_id = self._nis_component_data["DeviceId"][branch]
                            for phase in range (1,4):
                                row = branch*3 + phase
                                self._current_forecast[row]["Forecast"]["DeviceId"] = device_id
                                self._current_forecast[row]["Forecast"]["Phase"] = phase
                                self._current_forecast[row]["Forecast"]["Series"]["MagnitudeSendingEnd"]["Values"][horizon] = self._branch[current_phase[phase-1]][branch]
                                self._current_forecast[row]["Forecast"]["Series"]["MagnitudeReceivingEnd"]["Values"][horizon] = self._branch[current_phase[phase-1]][branch]
                                self._current_forecast[row]["Forecast"]["Series"]["AngleSendingEnd"]["Values"][horizon] = 0 # needs to be specified later
                                self._current_forecast[row]["Forecast"]["Series"]["AngleReceivingEnd"]["Values"][horizon] = 0 # needs to be specified later
                        
                        # Getting ready for power flow of a new timestep

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

                    await self._send_message(current_message, current_topic)
            # return True to indicate that the component is finished with the current epoch
            return True

    async def general_message_handler(self, message_object: Union[BaseMessage, Any],
                                      message_routing_key: str) -> None:
        """
        TODO: NIS,CIS, ResourceStateForecast and ResourceState messages are handled here.
        """
        # ignore simple messages from components that have not been registered as input components

        if isinstance(message_object,ResourceForecastPowerMessage):
            # added extra cast to allow Pylance to recognize that message_object is an instance of SimpleMessage
            message_object = cast(ResourceForecastPowerMessage, message_object)
            LOGGER.debug("Received {:s} message from topic {:s}".format(
                message_object.message_type, message_object.message_routing_key))
            await self._resource_forecast_message_handler(message_object)

        elif isinstance(message_object,NISBusMessage) and self.process_epoch == 1: # NIS data is only published in the first epoch
            message_object=cast(NISBusMessage,message_object)
            LOGGER.debug("Received {:s} message from topic {:s}".format(
                message_object.message_type, message_object.message_routing_key))
            self._nis_bus_data=message_object
            self._num_buses=len(self._nis_bus_data["BusName"])
            self._root_bus_index=self._nis_bus_data["BusType"].index("root")
            self._root_bus_name=self._nis_bus_data["BusType"][self._root_bus_index] # name of the root bus

            self._nis_bus_data_received=True

        elif isinstance(message_object,NISComponentMessage) and self.process_epoch == 1: # NIS data is only published in the first epoch
            message_object=cast(NISComponentMessage,message_object)
            LOGGER.debug("Received {:s} message from topic {:s}".format(
                message_object.message_type, message_object.message_routing_key))
            self._nis_component_data=message_object
            self._num_branches=len(self._nis_component_data["DeviceId"])

            if self._nis_component_data["PowerBase"]["Value"] != self._apparent_power_base:
                LOGGER.debug("Power base in NIS and manifest arenot equal")
                self._apparent_power_base=self._nis_component_data["PowerBase"]["Value"]

            self._nis_component_data_received=True

        elif isinstance(message_object,CISCustomerMessage) and self.process_epoch == 1: # CIS data is only published in the first epoch
            message_object=cast(CISCustomerMessage,message_object)
            LOGGER.debug("Received {:s} message from topic {:s}".format(
                message_object.message_type, message_object.message_routing_key))
            self._cis_customer_data=message_object
            if self._num_resources != len(self._cis_customer_data["ResourceId"]):
                LOGGER.debug("The number of resources {:s} in CIS donot match with its number {:s} in manifest file".format(
                len(self._cis_customer_data["ResourceId"]),self._cis_customer_data))

            self._cis_data_received=True
        elif isinstance(message_object,ResourceStateMessage):
            message_object=cast(ResourceStateMessage,message_object)
            self._resource_state_msg_counter=self._resource_state_msg_counter+1
            LOGGER.debug("Received {:s} message from topic {:s}".format(
                message_object.message_type, message_object.message_routing_key))
            self._resources["BusName"][self._resource_state_msg_counter]=message_object.Bus
            self._resources["ResourceId"][self._resource_state_msg_counter]=message_object.SourceProcessId
            if message_object.has_key["Node"] and message_object.Node in range (1,4):
                self._resources["Node"][self._resource_state_msg_counter]=message_object.Node
            else:
                self._resources["Node"][self._resource_state_msg_counter]="three_phase"


        else:
            LOGGER.debug("Received unknown message from {}: {}".format(message_routing_key, message_object))
            

    async def _send_message(self, MessageContent, Topic):
        await self._rabbitmq_client.send_message(
            topic_name=Topic,
            message_bytes=MessageContent.bytes())
    
    async def _resource_forecast_message_handler(self,forecasted_data:ResourceForecastPowerMessage) -> None:
        if self._resource_forecast_msg_counter==[] or self._resource_forecast_msg_counter==0 :
            self._resource_forecast_msg_counter=0
            self._resource_id_logger=self._cis_customer_data["ResourceId"]

        if self._resource_id_logger.count(forecasted_data["Forecast"]["ResourceId"])==1:
            self._resource_id_logger.remove[forecasted_data["Forecast"]["ResourceId"]]
            self._resource_forecast_msg_counter=self._resource_forecast_msg_counter+1
            self._resources_forecasts.append(forecasted_data)
            if self._forecast_time_index: # if self._forecast_time_index is empty  
                self._forecast_time_index=forecasted_data["Forecast"]["TimeIndex"]
            if self._forecast_horizon!=len(forecasted_data["Forecast"]["TimeIndex"]):
                self._forecast_horizon=len(forecasted_data["Forecast"]["TimeIndex"])
                LOGGER.warning("The forecast horizon in the manifest file is not equal to the message {} forecasts' horizon".format(forecasted_data["MessageId"]))
        else:
            LOGGER.warning("The forecast of the resource id {} has already been received".format(forecasted_data["Forecast"]["ResourceId"]))
        
    
    def _shortest_path(self,start, goal): # https://www.geeksforgeeks.org/building-an-undirected-graph-and-finding-shortest-path-using-dictionaries-in-python/
        explored = []
        # Queue for traversing the graph in the BFS
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
        return
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
    return NetworkStatePredictor()    # the birth of the NIS object


async def start_component():
    """
    Creates and starts a SimpleComponent component.
    """
    simple_component = create_component()

    # The component will only start listening to the message bus once the start() method has been called.
    await simple_component.start()

    # Wait in the loop until the component has stopped itself.
    while not simple_component.is_stopped:
        await asyncio.sleep(TIMEOUT)


if __name__ == "__main__":
    asyncio.run(start_component())

